import os
import gzip
import logging
import logging.handlers
import shutil
import time
from flask import Flask, make_response, render_template, g, request

from db import init_db, init_readings_db, migrate_db, PHOTOS_DIR
from scheduler import _scheduler

app = Flask(__name__)


# ── File logging ──────────────────────────────────────────────────────────────

def _setup_logging(flask_app):
    """Configure file logging with daily rotation and gzip compression.

    Env vars:
      BREWHOME_LOG_FILE  — chemin complet vers le fichier de log
                           (prioritaire sur BREWHOME_LOG_DIR)
      BREWHOME_LOG_DIR   — répertoire ; le fichier sera brewhome.log à l'intérieur
                           Détection automatique si absent :
                             1) /opt/brewhome/logs
                             2) /var/log/brewhome
                             3) <répertoire du script>/logs
      BREWHOME_LOG_LEVEL — DEBUG / INFO / WARNING / ERROR  (défaut : INFO)
      BREWHOME_LOG_KEEP  — nombre de fichiers rotatifs à conserver (défaut : 14)
    """
    level_name = os.environ.get('BREWHOME_LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, level_name, logging.INFO)
    keep = max(1, int(os.environ.get('BREWHOME_LOG_KEEP', '14')))

    # ── Résolution du chemin de log ───────────────────────────────────────────
    log_file = os.environ.get('BREWHOME_LOG_FILE', '').strip() or None
    if not log_file:
        log_dir = os.environ.get('BREWHOME_LOG_DIR', '').strip() or None
        if not log_dir:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            for candidate in (
                '/opt/brewhome/logs',
                '/var/log/brewhome',
                os.path.join(app_dir, 'logs'),
            ):
                try:
                    os.makedirs(candidate, exist_ok=True)
                    probe = os.path.join(candidate, '.write_probe')
                    with open(probe, 'w') as _f:
                        _f.write('')
                    os.unlink(probe)
                    log_dir = candidate
                    break
                except OSError:
                    continue
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'brewhome.log')

    if not log_file:
        flask_app.logger.warning(
            '[BrewHome] Aucun répertoire de log accessible — journalisation fichier désactivée.'
        )
        return

    # ── Handler avec rotation quotidienne + compression gzip ─────────────────
    try:
        handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when='midnight',
            backupCount=keep,
            encoding='utf-8',
            utc=False,
        )

        def _rotator(source, dest):
            with open(source, 'rb') as f_in, gzip.open(dest, 'wb', compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.unlink(source)

        def _namer(default_name):
            # default_name = brewhome.log.YYYY-MM-DD → brewhome.log.YYYY-MM-DD.gz
            return default_name + '.gz'

        handler.rotator = _rotator
        handler.namer   = _namer
        handler.setFormatter(logging.Formatter(
            fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        handler.setLevel(level)

        # Attacher au logger racine pour capturer TOUS les modules
        root = logging.getLogger()
        root.addHandler(handler)
        if root.level == logging.NOTSET or root.level > level:
            root.setLevel(level)

        flask_app.logger.info(
            f'[BrewHome] Logs → {log_file}  niveau={level_name}  rotation=quotidienne  conservation={keep}j'
        )
    except Exception as exc:
        flask_app.logger.warning(f'[BrewHome] Impossible d\'activer les logs fichier : {exc}')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB max request body

_STATIC_V = '0.0.8'  # fallback si _compute_static_v échoue

def _compute_static_v():
    """Version basée sur le mtime max des JS compilés — se met à jour automatiquement."""
    STATIC_JS = os.path.join(os.path.dirname(__file__), 'static', 'js')
    try:
        mtimes = [
            os.path.getmtime(os.path.join(STATIC_JS, f))
            for f in os.listdir(STATIC_JS)
            if f.startswith('bh-') and f.endswith('.js')
        ]
        return format(int(max(mtimes)), 'x') if mtimes else _STATIC_V
    except Exception:
        return _STATIC_V

# ── Register blueprints ───────────────────────────────────────────────────────

from blueprints.catalog      import bp as catalog_bp
from blueprints.inventory    import bp as inventory_bp
from blueprints.recipes      import bp as recipes_bp
from blueprints.brews        import bp as brews_bp
from blueprints.beers        import bp as beers_bp
from blueprints.spindles     import bp as spindles_bp
from blueprints.imports      import bp as imports_bp
from blueprints.integrations import bp as integrations_bp
from blueprints.admin        import bp as admin_bp
from blueprints.calendar     import bp as calendar_bp

app.register_blueprint(catalog_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(recipes_bp)
app.register_blueprint(brews_bp)
app.register_blueprint(beers_bp)
app.register_blueprint(spindles_bp)
app.register_blueprint(imports_bp)
app.register_blueprint(integrations_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(calendar_bp)


# ── DB teardown ───────────────────────────────────────────────────────────────

@app.teardown_appcontext
def _close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
    rdb = g.pop('readings_db', None)
    if rdb is not None:
        rdb.close()


# ── Request logging ──────────────────────────────────────────────────────────

_LOG_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

@app.before_request
def _req_start():
    g._t0 = time.monotonic()

@app.after_request
def _req_log(response):
    if request.method in _LOG_METHODS or response.status_code >= 400:
        ms  = int((time.monotonic() - g.get('_t0', time.monotonic())) * 1000)
        app.logger.info('%-6s %-40s %d  %dms',
                        request.method, request.path, response.status_code, ms)
    return response


# ── Static / PWA routes ───────────────────────────────────────────────────────

@app.route('/')
def index():
    _migrate_scripts_to_js()
    resp = make_response(render_template('index.html', static_v=_compute_static_v()))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/manifest.json')
def pwa_manifest():
    resp = make_response(app.send_static_file('manifest.json'))
    resp.headers['Content-Type'] = 'application/manifest+json'
    return resp


@app.route('/sw.js')
def pwa_sw():
    resp = make_response(app.send_static_file('sw.js'))
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


# ── Global error handler ──────────────────────────────────────────────────────

@app.errorhandler(413)
def handle_too_large(e):
    from flask import jsonify
    return jsonify({'error': 'payload_too_large', 'detail': 'Request body exceeds 10 MB limit'}), 413


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e  # laisser passer les erreurs HTTP normales (404, 405, …)
    app.logger.exception(f"Unhandled exception: {e}")
    from flask import jsonify
    return jsonify({'error': 'Internal server error'}), 500


# ── Main ──────────────────────────────────────────────────────────────────────

def _migrate_scripts_to_js():
    """Compile script_*.html → static/js/bh-*.js si la source est plus récente que la sortie.

    Incrémental : recompile automatiquement après un git pull sans redéploiement manuel.
    Les fichiers .html sources sont conservés (plus de renommage en .bak).
    Les anciens .bak issus de l'ancienne migration one-shot sont aussi pris en compte.
    """
    import re
    SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), 'templates', 'parts', 'scripts')
    STATIC_JS   = os.path.join(os.path.dirname(__file__), 'static', 'js')
    MAPPING = [
        ('script_state.html',      'bh-state.js'),
        ('script_locales.html',    'bh-locales.js'),
        ('script_core.html',       'bh-core.js'),
        ('script_inventaire.html', 'bh-inventaire.js'),
        ('script_recettes.html',   'bh-recettes.js'),
        ('script_brassins.html',   'bh-brassins.js'),
        ('script_cave.html',       'bh-cave.js'),
        ('script_spindles.html',   'bh-spindles.js'),
        ('script_settings.html',   'bh-settings.js'),
        ('script_ui.html',         'bh-ui.js'),
        ('script_calendrier.html', 'bh-calendrier.js'),
        ('script_brouillons.html', 'bh-brouillons.js'),
    ]
    os.makedirs(STATIC_JS, exist_ok=True)
    compiled = 0
    for src_name, dst_name in MAPPING:
        src = os.path.join(SCRIPTS_DIR, src_name)
        bak = src + '.bak'
        dst = os.path.join(STATIC_JS, dst_name)

        # Préférer le .html (source live) au .bak (ancienne migration one-shot)
        if os.path.exists(src):
            active_src = src
        elif os.path.exists(bak):
            active_src = bak
        else:
            continue  # aucune source disponible

        # Recompiler si la destination est absente ou plus ancienne que la source
        if os.path.exists(dst) and os.path.getmtime(active_src) <= os.path.getmtime(dst):
            continue

        with open(active_src, 'r', encoding='utf-8') as f:
            content = f.read()
        content = re.sub(r'^\s*<script[^>]*>\n?', '', content)
        content = re.sub(r'\n?</script>[\s\S]*$', '', content)
        if src_name == 'script_settings.html':
            content = content.replace("{{ '{{' }}", '{{').replace("{{ '}}' }}", '}}')
        with open(dst, 'w', encoding='utf-8') as f:
            f.write(content)
        app.logger.info(f'compile_scripts: {src_name} → {dst_name}')
        compiled += 1
    if compiled:
        app.logger.info(f'compile_scripts: {compiled} fichier(s) recompilé(s).')


if __name__ == '__main__':
    _setup_logging(app)
    from blueprints.integrations import reschedule_telegram, reschedule_github_backup
    with app.app_context():
        _migrate_scripts_to_js()
        os.makedirs(PHOTOS_DIR, exist_ok=True)
        init_db()
        init_readings_db()
        migrate_db()
        _scheduler.flask_app = app
        _scheduler.start()
        try:
            reschedule_telegram()
        except Exception as e:
            app.logger.warning(f"Telegram scheduler init error: {e}")
        try:
            reschedule_github_backup()
        except Exception as e:
            app.logger.warning(f"GitHub backup scheduler init error: {e}")
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000, threads=8)
