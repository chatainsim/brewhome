import json
import os
import sqlite3
import time
import urllib.request
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, current_app

from db import get_db, get_readings_db, _log, DB_PATH, READINGS_DB_PATH
from constants import BrewStatus
from helpers import api_error

bp = Blueprint('admin', __name__)

APP_VERSION = "0.0.7"


# ---------------------------------------------------------------------------
# BJCP
# ---------------------------------------------------------------------------

@bp.route('/api/bjcp')
def get_bjcp():
    q = request.args.get('q', '').strip().lower()
    with get_db() as conn:
        if q:
            rows = conn.execute(
                '''SELECT * FROM bjcp_styles
                   WHERE LOWER(name) LIKE ? OR LOWER(category) LIKE ?
                   ORDER BY id''',
                (f'%{q}%', f'%{q}%')
            ).fetchall()
        else:
            rows = conn.execute('SELECT * FROM bjcp_styles ORDER BY id').fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------

@bp.route('/api/trash')
def get_trash():
    with get_db() as conn:
        recipes  = conn.execute("SELECT id, name, style, deleted_at FROM recipes WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
        inv      = conn.execute("SELECT id, name, category, quantity, unit, deleted_at FROM inventory_items WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
        brews    = conn.execute("SELECT id, name, brew_date, status, deleted_at FROM brews WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
        beers    = conn.execute("SELECT id, name, type, abv, deleted_at FROM beers WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
    return jsonify({
        'recipes':   [dict(r) for r in recipes],
        'inventory': [dict(r) for r in inv],
        'brews':     [dict(r) for r in brews],
        'beers':     [dict(r) for r in beers],
    })


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@bp.route('/api/stats')
def get_stats():
    with get_db() as conn:
        def scalar(sql, params=()):
            return conn.execute(sql, params).fetchone()[0]
        _active_ph = ','.join('?' * len(BrewStatus.ACTIVE))
        return jsonify({
            'inventory_count': scalar('SELECT COUNT(*) FROM inventory_items WHERE archived=0'),
            'recipes_count':   scalar('SELECT COUNT(*) FROM recipes   WHERE archived=0'),
            'brews_count':     scalar('SELECT COUNT(*) FROM brews      WHERE archived=0'),
            'brews_active':    scalar(f'SELECT COUNT(*) FROM brews WHERE archived=0 AND status IN ({_active_ph})', BrewStatus.ACTIVE),
            'beers_count':     scalar('SELECT COUNT(*) FROM beers      WHERE archived=0'),
            'kegs_count':      scalar('SELECT COUNT(*) FROM soda_kegs  WHERE archived=0'),
            'total_33cl':      scalar('SELECT COALESCE(SUM(stock_33cl),0) FROM beers WHERE archived=0'),
            'total_75cl':      scalar('SELECT COALESCE(SUM(stock_75cl),0) FROM beers WHERE archived=0'),
            'total_liters':    scalar(
                'SELECT COALESCE(SUM(stock_33cl*0.33 + stock_75cl*0.75),0) FROM beers WHERE archived=0'
            ),
        })


# ---------------------------------------------------------------------------
# Version check
# ---------------------------------------------------------------------------

_version_cache = {'result': None, 'ts': 0}


def _parse_semver(v):
    v = v.strip().lstrip('v')
    try:
        return tuple(int(x) for x in v.split('.'))
    except (ValueError, AttributeError):
        return (0,)


@bp.route('/api/version/check')
def check_app_version():
    now = time.time()
    if _version_cache['result'] and now - _version_cache['ts'] < 6 * 3600:
        return jsonify(_version_cache['result'])
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/chatainsim/brewhome/releases/latest',
            headers={'User-Agent': f'BrewHome/{APP_VERSION}', 'Accept': 'application/vnd.github+json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        latest = data.get('tag_name', '').lstrip('v')
        result = {
            'current': APP_VERSION,
            'latest': latest,
            'update_available': _parse_semver(latest) > _parse_semver(APP_VERSION),
            'release_url': data.get('html_url', 'https://github.com/chatainsim/brewhome/releases'),
        }
    except Exception as e:
        current_app.logger.debug(f"check_app_version: {e}")
        result = {'current': APP_VERSION, 'latest': None, 'update_available': False, 'error': str(e)}
    _version_cache['result'] = result
    _version_cache['ts'] = now
    return jsonify(result)


# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------

_SECRET_KEYS = frozenset()


@bp.route('/api/app-settings', methods=['GET'])
def get_app_settings():
    with get_db() as conn:
        rows = conn.execute('SELECT key, value FROM app_settings').fetchall()
    result = {}
    for r in rows:
        if r['key'] in _SECRET_KEYS:
            result[r['key']] = '***' if r['value'] else ''
        else:
            result[r['key']] = r['value']
    return jsonify(result)


@bp.route('/api/app-settings', methods=['PUT'])
def save_app_settings():
    data = request.json or {}
    with get_db() as conn:
        for key, value in data.items():
            if key in _SECRET_KEYS and value == '***':
                continue
            if value is None or value == '':
                conn.execute('DELETE FROM app_settings WHERE key=?', (key,))
            else:
                conn.execute(
                    'INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)',
                    (key, str(value))
                )
    if any(k in data for k in ('telegram_token', 'telegram_chat_id', 'telegram_notifs', 'telegram_tz',
                               'tg_brewing_events')):
        try:
            from blueprints.integrations import reschedule_telegram
            reschedule_telegram()
        except Exception as e:
            current_app.logger.warning(f"Telegram reschedule error: {e}")
    if any(k.startswith('gh_data_backup_') for k in data):
        try:
            from blueprints.integrations import reschedule_github_backup
            reschedule_github_backup()
        except Exception as e:
            current_app.logger.warning(f"GitHub backup reschedule error: {e}")
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

@bp.route('/api/activity', methods=['GET', 'POST', 'DELETE'])
def activity_log_api():
    if request.method == 'POST':
        d = request.json or {}
        _log(d.get('category', 'system'), d.get('action', 'event'),
             d.get('label', ''), d.get('entity_id'))
        return jsonify({'success': True})
    if request.method == 'DELETE':
        category = request.args.get('category')
        exclude  = request.args.get('exclude')
        with get_db() as conn:
            if category:
                conn.execute('DELETE FROM activity_log WHERE category=?', (category,))
            elif exclude:
                conn.execute('DELETE FROM activity_log WHERE category!=?', (exclude,))
            else:
                conn.execute('DELETE FROM activity_log')
        return jsonify({'success': True})
    # GET
    try:
        limit  = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))
    except ValueError:
        return api_error('validation', 400, detail='limit and offset must be integers')
    category = request.args.get('category')
    exclude  = request.args.get('exclude')
    with get_db() as conn:
        if category:
            rows  = conn.execute(
                'SELECT * FROM activity_log WHERE category=? ORDER BY ts DESC LIMIT ? OFFSET ?',
                (category, limit, offset)).fetchall()
            total = conn.execute('SELECT COUNT(*) FROM activity_log WHERE category=?', (category,)).fetchone()[0]
        elif exclude:
            rows  = conn.execute(
                'SELECT * FROM activity_log WHERE category!=? ORDER BY ts DESC LIMIT ? OFFSET ?',
                (exclude, limit, offset)).fetchall()
            total = conn.execute('SELECT COUNT(*) FROM activity_log WHERE category!=?', (exclude,)).fetchone()[0]
        else:
            rows  = conn.execute(
                'SELECT * FROM activity_log ORDER BY ts DESC LIMIT ? OFFSET ?',
                (limit, offset)).fetchall()
            total = conn.execute('SELECT COUNT(*) FROM activity_log').fetchone()[0]
    return jsonify({'items': [dict(r) for r in rows], 'total': total})


# ---------------------------------------------------------------------------
# Checklist templates
# ---------------------------------------------------------------------------

@bp.route('/api/checklist-templates', methods=['GET'])
def get_checklist_templates():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM checklist_templates ORDER BY created_at').fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/checklist-templates', methods=['POST'])
def create_checklist_template():
    d = request.json or {}
    name = (d.get('name') or '').strip()
    if not name:
        return api_error('missing_field', 400, detail='name required')
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO checklist_templates (name, description, items) VALUES (?,?,?)',
            (name, d.get('description') or None, json.dumps(d.get('items') or []))
        )
        row = conn.execute('SELECT * FROM checklist_templates WHERE id=?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@bp.route('/api/checklist-templates/<int:tid>', methods=['PUT'])
def update_checklist_template(tid):
    d = request.json or {}
    with get_db() as conn:
        conn.execute(
            'UPDATE checklist_templates SET name=?, description=?, items=? WHERE id=?',
            (d.get('name'), d.get('description') or None, json.dumps(d.get('items') or []), tid)
        )
        row = conn.execute('SELECT * FROM checklist_templates WHERE id=?', (tid,)).fetchone()
        if not row:
            return api_error('not_found', 404)
        return jsonify(dict(row))


@bp.route('/api/checklist-templates/<int:tid>', methods=['DELETE'])
def delete_checklist_template(tid):
    with get_db() as conn:
        conn.execute('DELETE FROM checklist_templates WHERE id=?', (tid,))
    return jsonify({'ok': True})


@bp.route('/api/brews/<int:brew_id>/checklist', methods=['GET'])
def get_brew_checklist(brew_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM brew_checklists WHERE brew_id=?', (brew_id,)).fetchone()
        if not row:
            return jsonify({'brew_id': brew_id, 'template_id': None, 'checked_items': []})
        return jsonify({**dict(row), 'checked_items': json.loads(row['checked_items'] or '[]')})


@bp.route('/api/brews/<int:brew_id>/checklist', methods=['POST'])
def save_brew_checklist(brew_id):
    d = request.json or {}
    template_id = d.get('template_id')
    checked     = json.dumps(d.get('checked_items') or [])
    with get_db() as conn:
        conn.execute(
            '''INSERT INTO brew_checklists (brew_id, template_id, checked_items, updated_at)
               VALUES (?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(brew_id) DO UPDATE SET
                 template_id=excluded.template_id,
                 checked_items=excluded.checked_items,
                 updated_at=CURRENT_TIMESTAMP''',
            (brew_id, template_id, checked)
        )
        row = conn.execute('SELECT * FROM brew_checklists WHERE brew_id=?', (brew_id,)).fetchone()
        return jsonify({**dict(row), 'checked_items': json.loads(row['checked_items'] or '[]')})


# ---------------------------------------------------------------------------
# DB admin
# ---------------------------------------------------------------------------

@bp.route('/api/admin/db-stats')
def admin_db_stats():
    main_size     = os.path.getsize(DB_PATH)          if os.path.exists(DB_PATH)          else 0
    readings_size = os.path.getsize(READINGS_DB_PATH) if os.path.exists(READINGS_DB_PATH) else 0
    main_tables = {}
    with get_db() as conn:
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            name = row['name']
            main_tables[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    readings_tables = {}
    with get_readings_db() as conn:
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            name = row['name']
            readings_tables[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    return jsonify({
        'main':     {'size': main_size,     'tables': main_tables},
        'readings': {'size': readings_size, 'tables': readings_tables},
    })


@bp.route('/api/admin/vacuum', methods=['POST'])
def admin_vacuum():
    try:
        for path in (DB_PATH, READINGS_DB_PATH):
            conn = sqlite3.connect(path)
            conn.execute('VACUUM')
            conn.close()
        return jsonify({
            'ok': True,
            'main_size':     os.path.getsize(DB_PATH)          if os.path.exists(DB_PATH)          else 0,
            'readings_size': os.path.getsize(READINGS_DB_PATH) if os.path.exists(READINGS_DB_PATH) else 0,
        })
    except Exception as e:
        current_app.logger.exception("vacuum failed")
        return api_error('internal_error', 500)


@bp.route('/api/admin/export-sql')
def admin_export_sql():
    lines = []
    conn = sqlite3.connect(DB_PATH)
    try:
        for line in conn.iterdump():
            lines.append(line)
    finally:
        conn.close()
    sql_str = '\n'.join(lines)
    filename = f'brewhome_{datetime.now().strftime("%Y-%m-%d")}.sql'
    return Response(sql_str, mimetype='text/plain',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


# ---------------------------------------------------------------------------
# Scale guide (connected balance)
# ---------------------------------------------------------------------------

def _sg_get():
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key='scale_guide_session'").fetchone()
    if row and row['value']:
        try:
            return json.loads(row['value'])
        except (json.JSONDecodeError, ValueError) as e:
            current_app.logger.warning(f"scale_guide_session: invalid JSON in DB, resetting — {e}")
    return None


def _sg_set(data):
    with get_db() as conn:
        if data is None:
            conn.execute("DELETE FROM app_settings WHERE key='scale_guide_session'")
        else:
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES ('scale_guide_session', ?)",
                (json.dumps(data, ensure_ascii=False),)
            )


@bp.route('/api/scale-guide', methods=['GET'])
def scale_guide_get():
    session = _sg_get()
    if not session:
        return jsonify({'active': False})
    step  = session.get('step', 0)
    malts = session.get('malts', [])
    if step >= len(malts):
        _sg_set(None)
        return jsonify({'active': False, 'finished': True})
    m       = malts[step]
    qty     = float(m.get('quantity') or 0)
    unit    = (m.get('unit') or 'g').lower()
    target_kg = qty / 1000 if unit == 'g' else qty
    return jsonify({
        'active':     True,
        'brew_name':  session.get('brew_name', ''),
        'step':       step + 1,
        'total':      len(malts),
        'malt_name':  m.get('name', '?'),
        'target_kg':  round(target_kg, 3),
    })


@bp.route('/api/scale-guide/start', methods=['POST'])
def scale_guide_start():
    d         = request.json or {}
    malts_raw = d.get('malts', [])
    if not malts_raw:
        return api_error('no_malts', 400)
    malts = [{'name': m.get('name', '?'), 'quantity': m.get('quantity', 0),
              'unit': m.get('unit', 'g')} for m in malts_raw]
    session = {
        'recipe_id': d.get('recipe_id'),
        'brew_name': d.get('brew_name', ''),
        'malts':     malts,
        'step':      0,
    }
    _sg_set(session)
    return jsonify({'ok': True, 'total': len(malts), 'first_malt': malts[0]['name']})


@bp.route('/api/scale-guide/next', methods=['POST'])
def scale_guide_next():
    session = _sg_get()
    if not session:
        return api_error('no_session', 404)
    session['step'] = session.get('step', 0) + 1
    malts = session.get('malts', [])
    if session['step'] >= len(malts):
        _sg_set(None)
        return jsonify({'finished': True, 'active': False})
    _sg_set(session)
    m = malts[session['step']]
    qty = float(m.get('quantity') or 0)
    unit = (m.get('unit') or 'g').lower()
    target_kg = qty / 1000 if unit == 'g' else qty
    return jsonify({
        'ok': True, 'active': True,
        'step':      session['step'] + 1,
        'total':     len(malts),
        'malt_name': m.get('name', '?'),
        'target_kg': round(target_kg, 3),
    })


@bp.route('/api/scale-guide/stop', methods=['POST'])
def scale_guide_stop():
    _sg_set(None)
    return jsonify({'ok': True})
