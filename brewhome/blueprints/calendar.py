import json
import os
import secrets
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, jsonify, request, current_app

from db import get_db, get_readings_db, PHOTOS_DIR

def _safe_int(val):
    """Convertit val en int, retourne None si absent ou non-entier."""
    if val is None or val == '':
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
from helpers import _image_too_large, _shrink_image_b64, api_error
from constants import BrewStatus

bp = Blueprint('calendar', __name__)


def _cal_purge_brew_photos(conn):
    rows = conn.execute('SELECT photo_file, thumb_file FROM brew_photos').fetchall()
    for r in rows:
        for fname in (r['photo_file'], r['thumb_file']):
            if fname:
                try:
                    os.remove(os.path.join(PHOTOS_DIR, fname))
                except OSError:
                    pass
    conn.execute('DELETE FROM brew_photos')


# ---------------------------------------------------------------------------
# Custom calendar events
# ---------------------------------------------------------------------------

@bp.route('/api/custom_events', methods=['GET'])
def get_custom_events():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM custom_calendar_events ORDER BY event_date').fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/custom_events', methods=['POST'])
def create_custom_event():
    data = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO custom_calendar_events
               (title, emoji, event_date, color, notes, brew_reminder, telegram_notify,
                style, recipe_id, draft_id, recurrence, brew_reminder_days)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                data.get('title', 'Événement'),
                data.get('emoji', '📅'),
                data.get('event_date'),
                data.get('color', '#f59e0b'),
                data.get('notes'),
                1 if data.get('brew_reminder') else 0,
                1 if data.get('telegram_notify') else 0,
                data.get('style') or None,
                data.get('recipe_id') or None,
                data.get('draft_id') or None,
                data.get('recurrence') or None,
                _safe_int(data.get('brew_reminder_days')),
            )
        )
        row = conn.execute('SELECT * FROM custom_calendar_events WHERE id=?', (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.route('/api/custom_events/<int:event_id>', methods=['PUT'])
def update_custom_event(event_id):
    data = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE custom_calendar_events
               SET title=?, emoji=?, event_date=?, color=?, notes=?, brew_reminder=?, telegram_notify=?,
                   style=?, recipe_id=?, draft_id=?, recurrence=?, brew_reminder_days=?
               WHERE id=?''',
            (
                data.get('title', 'Événement'),
                data.get('emoji', '📅'),
                data.get('event_date'),
                data.get('color', '#f59e0b'),
                data.get('notes'),
                1 if data.get('brew_reminder') else 0,
                1 if data.get('telegram_notify') else 0,
                data.get('style') or None,
                data.get('recipe_id') or None,
                data.get('draft_id') or None,
                data.get('recurrence') or None,
                _safe_int(data.get('brew_reminder_days')),
                event_id,
            )
        )
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        row = conn.execute('SELECT * FROM custom_calendar_events WHERE id=?', (event_id,)).fetchone()
    return jsonify(dict(row))


@bp.route('/api/custom_events/<int:event_id>', methods=['DELETE'])
def delete_custom_event(event_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM custom_calendar_events WHERE id=?', (event_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

@bp.route('/api/drafts', methods=['GET'])
def get_drafts():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT id, title, style, volume, ingredients, notes, color,
                      target_date, event_label, sort_order, created_at, updated_at
               FROM draft_recipes ORDER BY sort_order ASC, updated_at DESC'''
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/drafts/<int:draft_id>', methods=['GET'])
def get_draft(draft_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM draft_recipes WHERE id=?', (draft_id,)).fetchone()
        if not row:
            return api_error('not_found', 404)
        return jsonify(dict(row))


@bp.route('/api/drafts/reorder', methods=['PUT'])
def reorder_drafts():
    items = request.json or []
    if any(not isinstance(it.get('sort_order'), int) or isinstance(it.get('sort_order'), bool) or it.get('sort_order') < 0
           for it in items if it.get('id') is not None):
        return api_error('validation', 400, detail='sort_order must be a non-negative integer')
    valid = [(it['sort_order'], it['id']) for it in items
             if it.get('id') is not None and it.get('sort_order') is not None]
    with get_db() as conn:
        conn.executemany('UPDATE draft_recipes SET sort_order=? WHERE id=?', valid)
    return jsonify({'success': True})


@bp.route('/api/drafts', methods=['POST'])
def create_draft():
    data = request.json or {}
    if _image_too_large(data.get('image')):
        shrunk = _shrink_image_b64(data['image'])
        data['image'] = shrunk if not _image_too_large(shrunk) else None
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO draft_recipes (title, style, volume, ingredients, notes, color, target_date, event_label, image)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                data.get('title', 'Nouveau brouillon'),
                data.get('style'),
                data.get('volume'),
                data.get('ingredients'),
                data.get('notes'),
                data.get('color'),
                data.get('target_date'),
                data.get('event_label'),
                data.get('image'),
            )
        )
        row = conn.execute('SELECT * FROM draft_recipes WHERE id=?', (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.route('/api/drafts/<int:draft_id>', methods=['PUT'])
def update_draft(draft_id):
    data = request.json or {}
    if _image_too_large(data.get('image')):
        shrunk = _shrink_image_b64(data['image'])
        data['image'] = shrunk if not _image_too_large(shrunk) else None
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE draft_recipes
               SET title=?, style=?, volume=?, ingredients=?, notes=?, color=?,
                   target_date=?, event_label=?, image=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (
                data.get('title', 'Nouveau brouillon'),
                data.get('style'),
                data.get('volume'),
                data.get('ingredients'),
                data.get('notes'),
                data.get('color'),
                data.get('target_date'),
                data.get('event_label'),
                data.get('image'),
                draft_id,
            )
        )
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        row = conn.execute('SELECT * FROM draft_recipes WHERE id=?', (draft_id,)).fetchone()
    return jsonify(dict(row))


@bp.route('/api/drafts/<int:draft_id>', methods=['DELETE'])
def delete_draft(draft_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM draft_recipes WHERE id=?', (draft_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# AI draft suggest
# ---------------------------------------------------------------------------

@bp.route('/api/ai/draft-suggest', methods=['POST'])
def ai_draft_suggest():
    data = request.json or {}
    style       = (data.get('style')       or '').strip()
    event_label = (data.get('event_label') or '').strip()
    event_desc  = (data.get('event_desc')  or '').strip()
    notes       = (data.get('notes')       or '').strip()
    volume      = data.get('volume') or 10

    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key IN ('ai_api_key', 'ai_model')"
        ).fetchall()
    s = {r['key']: r['value'] for r in rows}
    api_key = (s.get('ai_api_key') or '').strip() or None
    if not api_key:
        return api_error('not_configured', 400, detail='Clé API Gemini non configurée (Paramètres → IA)')
    model = (s.get('ai_model') or '').strip() or 'gemini-2.0-flash'

    context_parts = []
    if style:       context_parts.append(f"Style BJCP : {style}")
    if event_label: context_parts.append(f"Objectif de brassage : {event_label}")
    if event_desc:  context_parts.append(f"Description de l'événement : {event_desc}")
    if notes:       context_parts.append(f"Notes du brasseur : {notes}")
    context_str = '\n'.join(context_parts) if context_parts else "Bière de dégustation générique"

    prompt = f"""Tu es un expert en brassage amateur (homebrewing). Génère une recette de bière pour un brassin de {volume} litres.

{context_str}

Retourne UNIQUEMENT un objet JSON valide (sans markdown, sans backticks, sans commentaires) avec cette structure exacte :
{{
  "title": "Nom suggéré pour la bière",
  "ingredients": [
    {{"type": "malt", "name": "Pale Ale Malt", "qty": 2.5, "unit": "kg"}},
    {{"type": "houblon", "name": "Cascade", "qty": 25, "unit": "g"}},
    {{"type": "levure", "name": "Safale US-05", "qty": 1, "unit": "sachet"}}
  ],
  "notes": "OG cible, FG cible, température de fermentation, durée, conseils de brassage..."
}}

Règles :
- Types autorisés pour "type" : "malt", "houblon", "levure", "autre"
- Unités pour malts : "kg" ou "g"
- Unités pour houblons : "g"
- Unités pour levures : "sachet", "g" ou "mL"
- Adapte les quantités pour exactement {volume} litres
- Inclus tous les malts, houblons (palier amertume + arôme), et la levure"""

    import urllib.request as _ur
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }).encode('utf-8')
    req = _ur.Request(url, data=payload,
                      headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                      method="POST")
    try:
        with _ur.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        if 'candidates' not in result:
            feedback = result.get('promptFeedback', {})
            reason   = feedback.get('blockReason', 'Réponse vide de Gemini')
            current_app.logger.warning(f"Gemini no candidates: {result}")
            return api_error('upstream_error', 502, detail=f"Gemini : {reason}")
        text   = result['candidates'][0]['content']['parts'][0]['text']
        recipe = json.loads(text)
        return jsonify(recipe)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        current_app.logger.warning(f"Gemini HTTPError {e.code}: {body[:400]}")
        try:
            err_msg = json.loads(body).get('error', {}).get('message', body)
        except Exception:
            err_msg = body[:300]
        return api_error('upstream_error', 502, detail=f"Gemini {e.code} : {err_msg}")
    except urllib.error.URLError as e:
        current_app.logger.warning(f"Gemini URLError: {e.reason}")
        return api_error('upstream_error', 502, detail=f"Réseau : {e.reason}")
    except Exception as e:
        current_app.logger.exception("Gemini draft-suggest error")
        return api_error('internal_error', 500)


# ---------------------------------------------------------------------------
# Drafts export / import
# ---------------------------------------------------------------------------

@bp.route('/api/export/drafts')
def export_drafts():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM draft_recipes ORDER BY sort_order ASC, updated_at DESC').fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/import/drafts', methods=['POST'])
def import_drafts():
    body = request.json or {}
    if isinstance(body, list):
        data, mode = body, 'merge'
    else:
        data, mode = body.get('items', []), body.get('mode', 'merge')
    if isinstance(data, dict):
        data = [data]
    imported = 0
    with get_db() as conn:
        if mode == 'replace':
            conn.execute('DELETE FROM draft_recipes')
        for d in data:
            if not d.get('title'):
                continue
            try:
                existing = conn.execute('SELECT id FROM draft_recipes WHERE title=?', (d['title'],)).fetchone()
                img = _shrink_image_b64(d['image']) if _image_too_large(d.get('image')) else d.get('image')
                if existing:
                    conn.execute(
                        '''UPDATE draft_recipes SET style=?,volume=?,ingredients=?,notes=?,color=?,
                           target_date=?,event_label=?,image=? WHERE id=?''',
                        (d.get('style'), d.get('volume'), d.get('ingredients'), d.get('notes'),
                         d.get('color', '#ff9500'), d.get('target_date'), d.get('event_label'),
                         img, existing['id'])
                    )
                else:
                    conn.execute(
                        '''INSERT INTO draft_recipes
                           (title, style, volume, ingredients, notes, color,
                            target_date, event_label, sort_order, image)
                           VALUES (?,?,?,?,?,?,?,?,?,?)''',
                        (d.get('title', 'Brouillon'), d.get('style'), d.get('volume'),
                         d.get('ingredients'), d.get('notes'), d.get('color', '#ff9500'),
                         d.get('target_date'), d.get('event_label'),
                         d.get('sort_order', 0), img)
                    )
                imported += 1
            except Exception as e:
                current_app.logger.warning(f"import_drafts: skipped draft {d.get('title')!r}: {e}")
    return jsonify({'imported': imported})


# ---------------------------------------------------------------------------
# Calendar ICS
# ---------------------------------------------------------------------------

def _ics_escape(text):
    if not text:
        return ''
    return str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n').replace('\r', '')


def _ics_fold(line):
    """Fold iCal property line to max 75 octets per segment (RFC 5545)."""
    encoded = line.encode('utf-8')
    if len(encoded) <= 75:
        return line + '\r\n'
    parts = []
    while encoded:
        budget = 75 if not parts else 74
        chunk = encoded[:budget]
        while chunk and (chunk[-1] & 0xC0) == 0x80:
            chunk = chunk[:-1]
        if not chunk:
            break
        parts.append(chunk.decode('utf-8'))
        encoded = encoded[len(chunk):]
    return ('\r\n ').join(parts) + '\r\n'


def _make_ical():
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%dT%H%M%SZ')

    def _vevent(uid, dtstart, dtend, summary, description=None, rrule=None, alarm_days=None):
        ev = [
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTAMP:{now_utc}',
            f'DTSTART;VALUE=DATE:{dtstart}',
            f'DTEND;VALUE=DATE:{dtend}',
            f'SUMMARY:{_ics_escape(summary)}',
        ]
        if description:
            ev.append(f'DESCRIPTION:{_ics_escape(description)}')
        if rrule:
            ev.append(f'RRULE:{rrule}')
        if alarm_days:
            ev += [
                'BEGIN:VALARM',
                'ACTION:DISPLAY',
                f'DESCRIPTION:{_ics_escape(summary)}',
                f'TRIGGER:-P{alarm_days}D',
                'END:VALARM',
            ]
        ev.append('END:VEVENT')
        return ev

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//BrewHome//BrewHome Calendar//FR',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:BrewHome',
        'X-WR-CALDESC:Calendrier de brassage BrewHome',
    ]

    _ical_dow = {0: 'SU', 1: 'MO', 2: 'TU', 3: 'WE', 4: 'TH', 5: 'FR', 6: 'SA'}

    def _rrule_from_rec(rec_str, event_date):
        if not rec_str:
            return None
        try:
            r = json.loads(rec_str) if isinstance(rec_str, str) else rec_str
            t = r.get('type', '')
            if t == 'yearly':
                return 'FREQ=YEARLY'
            if t == 'yearly_nth_dow':
                dow = _ical_dow.get(r.get('dow', 1), 'MO')
                nth = r.get('nth', 1)
                month = int(event_date[5:7])
                return f'FREQ=YEARLY;BYMONTH={month};BYDAY={nth}{dow}'
            if t == 'monthly':
                return 'FREQ=MONTHLY'
            if t == 'monthly_nth_dow':
                dow = _ical_dow.get(r.get('dow', 1), 'MO')
                nth = r.get('nth', 1)
                return f'FREQ=MONTHLY;BYDAY={nth}{dow}'
            if t == 'weekly':
                interval = int(r.get('interval') or 1)
                return f'FREQ=WEEKLY;INTERVAL={interval}' if interval > 1 else 'FREQ=WEEKLY'
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
        return None

    with get_db() as conn:
        remind_row = conn.execute(
            "SELECT value FROM app_settings WHERE key='default_brew_reminder_days'"
        ).fetchone()
        default_remind = int(remind_row['value']) if remind_row and remind_row['value'] else 45

        for ev in conn.execute(
            'SELECT * FROM custom_calendar_events ORDER BY event_date'
        ).fetchall():
            try:
                dt = datetime.strptime(ev['event_date'][:10], '%Y-%m-%d')
                dtstart = dt.strftime('%Y%m%d')
                dtend = (dt + timedelta(days=1)).strftime('%Y%m%d')
                title = ((ev['emoji'] or '') + ' ' + (ev['title'] or '')).strip()
                rrule = _rrule_from_rec(ev.get('recurrence'), ev['event_date'])
                alarm_days = None
                if ev['brew_reminder']:
                    try:
                        alarm_days = int(ev['brew_reminder_days']) if ev['brew_reminder_days'] else default_remind
                    except (ValueError, TypeError):
                        alarm_days = default_remind
                lines.extend(_vevent(
                    uid=f'brewhome-event-{ev["id"]}@brewhome',
                    dtstart=dtstart, dtend=dtend, summary=title,
                    description=ev.get('notes'), rrule=rrule, alarm_days=alarm_days,
                ))
            except Exception:
                continue

        for brew in conn.execute(
            '''SELECT b.*, r.ferm_time AS r_ferm_time
               FROM brews b LEFT JOIN recipes r ON b.recipe_id=r.id
               WHERE b.brew_date IS NOT NULL ORDER BY b.brew_date'''
        ).fetchall():
            try:
                brew_dt = datetime.strptime(brew['brew_date'][:10], '%Y-%m-%d')
                dtstart = brew_dt.strftime('%Y%m%d')
                dtend = (brew_dt + timedelta(days=1)).strftime('%Y%m%d')
                parts = []
                if brew.get('volume_brewed'):
                    parts.append(f'Volume : {brew["volume_brewed"]} L')
                if brew.get('og'):
                    parts.append(f'OG : {brew["og"]}')
                if brew.get('abv'):
                    parts.append(f'ABV : {brew["abv"]} %')
                status_lbl = {BrewStatus.IN_PROGRESS: 'En cours', BrewStatus.COMPLETED: 'Terminé', 'archived': 'Archivé'}
                if brew.get('status'):
                    parts.append(f'Statut : {status_lbl.get(brew["status"], brew["status"])}')
                if brew.get('notes'):
                    parts.append(brew['notes'])
                lines.extend(_vevent(
                    uid=f'brewhome-brew-{brew["id"]}@brewhome',
                    dtstart=dtstart, dtend=dtend,
                    summary=f'\U0001f37a {brew["name"]}',
                    description='\n'.join(parts) if parts else None,
                ))
                ferm_days = brew.get('ferm_time') or brew.get('r_ferm_time')
                if ferm_days:
                    end_dt = brew_dt + timedelta(days=int(ferm_days))
                    lines.extend(_vevent(
                        uid=f'brewhome-brew-{brew["id"]}-bottling@brewhome',
                        dtstart=end_dt.strftime('%Y%m%d'),
                        dtend=(end_dt + timedelta(days=1)).strftime('%Y%m%d'),
                        summary=f'\U0001f37e Mise en bouteille \u2014 {brew["name"]}',
                    ))
            except Exception:
                continue

    lines.append('END:VCALENDAR')
    return ''.join(_ics_fold(line) for line in lines)


@bp.route('/api/calendar/ics')
def calendar_ics():
    return Response(
        _make_ical(),
        mimetype='text/calendar; charset=utf-8',
        headers={
            'Content-Disposition': 'inline; filename="brewhome.ics"',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        },
    )


# ---------------------------------------------------------------------------
# Calendar export / import
# ---------------------------------------------------------------------------

@bp.route('/api/export/calendar')
def export_calendar():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM custom_calendar_events ORDER BY event_date').fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/import/calendar', methods=['POST'])
def import_calendar():
    body = request.json or {}
    if isinstance(body, list):
        data, mode = body, 'merge'
    else:
        data, mode = body.get('items', []), body.get('mode', 'merge')
    if isinstance(data, dict):
        data = [data]
    imported = 0
    with get_db() as conn:
        if mode == 'replace':
            conn.execute('DELETE FROM custom_calendar_events')
        for ev in data:
            if not ev.get('title') or not ev.get('event_date'):
                continue
            try:
                existing = conn.execute(
                    'SELECT id FROM custom_calendar_events WHERE title=? AND event_date=?',
                    (ev['title'], ev['event_date'])
                ).fetchone()
                if existing:
                    conn.execute(
                        '''UPDATE custom_calendar_events SET emoji=?,color=?,notes=?,
                           brew_reminder=?,telegram_notify=?,style=?,recipe_id=?,draft_id=?
                           WHERE id=?''',
                        (ev.get('emoji', '📅'), ev.get('color', '#f59e0b'), ev.get('notes'),
                         ev.get('brew_reminder', 0), ev.get('telegram_notify', 0),
                         ev.get('style'), ev.get('recipe_id'), ev.get('draft_id'), existing['id'])
                    )
                else:
                    conn.execute(
                        '''INSERT INTO custom_calendar_events
                           (title, emoji, event_date, color, notes,
                            brew_reminder, telegram_notify, style, recipe_id, draft_id)
                           VALUES (?,?,?,?,?,?,?,?,?,?)''',
                        (ev.get('title'), ev.get('emoji', '📅'), ev['event_date'],
                         ev.get('color', '#f59e0b'), ev.get('notes'),
                         ev.get('brew_reminder', 0), ev.get('telegram_notify', 0),
                         ev.get('style'), ev.get('recipe_id'), ev.get('draft_id'))
                    )
                imported += 1
            except Exception as e:
                current_app.logger.warning(f"import_calendar: skipped event {ev.get('title')!r}: {e}")
    return jsonify({'imported': imported})


# ---------------------------------------------------------------------------
# Restore from Git
# ---------------------------------------------------------------------------

@bp.route('/api/restore/git', methods=['POST'])
def restore_from_git():
    """Restaure des données depuis la sauvegarde Git automatique."""
    req_data = request.json or {}
    sections = req_data.get('sections', [])
    mode     = req_data.get('mode', 'merge')

    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key IN "
            "('gh_data_targets','gh_data_repo','gh_data_branch','gh_data_pat','gh_data_api_url')"
        ).fetchall()
    cfg = {r['key']: r['value'] for r in rows}
    targets = []
    if cfg.get('gh_data_targets'):
        try:
            targets = [t for t in json.loads(cfg['gh_data_targets']) if t.get('repo') and t.get('pat')]
        except (json.JSONDecodeError, ValueError):
            pass
    if not targets and cfg.get('gh_data_repo') and cfg.get('gh_data_pat'):
        targets = [{'repo': cfg['gh_data_repo'], 'pat': cfg['gh_data_pat'],
                    'branch': cfg.get('gh_data_branch', 'main') or 'main',
                    'apiUrl': cfg.get('gh_data_api_url', 'https://api.github.com')}]
    if not targets:
        return api_error('no_target', 400)

    target   = targets[0]
    t_repo   = target.get('repo', '').strip()
    t_pat    = target.get('pat', '').strip()
    t_branch = target.get('branch', 'main').strip() or 'main'
    t_api    = (target.get('apiUrl') or 'https://api.github.com').rstrip('/')

    file_map = {
        'inventaire':  'backup_auto/inventaire.json',
        'recettes':    'backup_auto/recettes.json',
        'brassins':    'backup_auto/brassins.json',
        'cave':        'backup_auto/cave.json',
        'catalogue':   'backup_auto/catalogue.json',
        'densimetres': 'backup_auto/densimetres.json',
        'brouillons':  'backup_auto/brouillons.json',
        'calendrier':  'backup_auto/calendrier.json',
    }

    from blueprints.integrations import _gh_get_file

    results = {}
    for section in sections:
        file_path = file_map.get(section)
        if not file_path:
            results[section] = {'error': 'unknown_section'}
            continue
        try:
            content = _gh_get_file(t_repo, t_pat, t_branch, file_path, api_base=t_api)
            items   = json.loads(content)
            if not isinstance(items, list):
                items = [items]
            n = _import_section_direct(section, items, mode)
            results[section] = {'count': n}
        except urllib.error.HTTPError as e:
            results[section] = {'error': 'not_found' if e.code == 404 else f'HTTP {e.code}'}
        except Exception as e:
            current_app.logger.warning(f'restore_from_git: section {section!r} error: {e}')
            results[section] = {'error': str(e)}

    return jsonify({'results': results})


def _import_section_direct(section, items, mode='merge'):
    """Import items for a given section using direct DB calls. Returns count imported."""
    if section == 'inventaire':
        imported = 0
        with get_db() as conn:
            if mode == 'replace':
                conn.execute('DELETE FROM inventory_items')
            for item in items:
                if not item.get('name') or not item.get('category'):
                    continue
                try:
                    existing = conn.execute(
                        'SELECT id FROM inventory_items WHERE name=? AND category=?',
                        (item['name'], item['category'])
                    ).fetchone()
                    if existing:
                        conn.execute(
                            'UPDATE inventory_items SET quantity=?,unit=?,origin=?,ebc=?,alpha=?,notes=? WHERE id=?',
                            (item.get('quantity', 0), item.get('unit', 'g'), item.get('origin'),
                             item.get('ebc'), item.get('alpha'), item.get('notes'), existing['id'])
                        )
                    else:
                        conn.execute(
                            'INSERT INTO inventory_items (name,category,quantity,unit,origin,ebc,alpha,notes) VALUES (?,?,?,?,?,?,?,?)',
                            (item['name'], item['category'], item.get('quantity', 0), item.get('unit', 'g'),
                             item.get('origin'), item.get('ebc'), item.get('alpha'), item.get('notes'))
                        )
                    imported += 1
                except Exception as e:
                    current_app.logger.warning(f"restore inventaire: skipped {item.get('name')!r}: {e}")
        return imported

    elif section == 'catalogue':
        imported = 0
        with get_db() as conn:
            if mode == 'replace':
                conn.execute('DELETE FROM ingredient_catalog')
            for d in items:
                if not d.get('name') or not d.get('category'):
                    continue
                existing = conn.execute(
                    'SELECT id FROM ingredient_catalog WHERE name=? AND category=?',
                    (d['name'], d['category'])
                ).fetchone()
                if existing:
                    conn.execute(
                        '''UPDATE ingredient_catalog SET subcategory=?,ebc=?,gu=?,alpha=?,yeast_type=?,
                           default_unit=?,temp_min=?,temp_max=?,dosage_per_liter=?,
                           attenuation_min=?,attenuation_max=?,alcohol_tolerance=?,max_usage_pct=? WHERE id=?''',
                        (d.get('subcategory'), d.get('ebc'), d.get('gu'), d.get('alpha'),
                         d.get('yeast_type'), d.get('default_unit', 'g'),
                         d.get('temp_min'), d.get('temp_max'), d.get('dosage_per_liter'),
                         d.get('attenuation_min'), d.get('attenuation_max'), d.get('alcohol_tolerance'),
                         d.get('max_usage_pct'), existing['id'])
                    )
                else:
                    conn.execute(
                        '''INSERT INTO ingredient_catalog
                           (name,category,subcategory,ebc,gu,alpha,yeast_type,default_unit,
                            temp_min,temp_max,dosage_per_liter,attenuation_min,attenuation_max,alcohol_tolerance,max_usage_pct)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (d['name'], d['category'], d.get('subcategory'), d.get('ebc'), d.get('gu'),
                         d.get('alpha'), d.get('yeast_type'), d.get('default_unit', 'g'),
                         d.get('temp_min'), d.get('temp_max'), d.get('dosage_per_liter'),
                         d.get('attenuation_min'), d.get('attenuation_max'), d.get('alcohol_tolerance'),
                         d.get('max_usage_pct'))
                    )
                imported += 1
        return imported

    elif section == 'recettes':
        imported = 0
        with get_db() as conn:
            if mode == 'replace':
                conn.execute('DELETE FROM recipe_ingredients')
                conn.execute('DELETE FROM recipes')
            for recipe in items:
                if not recipe.get('name'):
                    continue
                try:
                    existing = conn.execute('SELECT id FROM recipes WHERE name=?', (recipe['name'],)).fetchone()
                    if existing:
                        rid = existing['id']
                        conn.execute(
                            '''UPDATE recipes SET style=?,volume=?,brew_date=?,mash_temp=?,mash_time=?,boil_time=?,
                               mash_ratio=?,evap_rate=?,grain_absorption=?,brewhouse_efficiency=?,
                               ferm_temp=?,ferm_time=?,notes=? WHERE id=?''',
                            (recipe.get('style'), recipe.get('volume', 20),
                             recipe.get('brew_date'), recipe.get('mash_temp', 66), recipe.get('mash_time', 60),
                             recipe.get('boil_time', 60), recipe.get('mash_ratio', 3.0),
                             recipe.get('evap_rate', 3.0), recipe.get('grain_absorption', 0.8),
                             recipe.get('brewhouse_efficiency', 72), recipe.get('ferm_temp'),
                             recipe.get('ferm_time'), recipe.get('notes'), rid)
                        )
                        conn.execute('DELETE FROM recipe_ingredients WHERE recipe_id=?', (rid,))
                    else:
                        cur = conn.execute(
                            '''INSERT INTO recipes
                               (name,style,volume,brew_date,mash_temp,mash_time,boil_time,
                                mash_ratio,evap_rate,grain_absorption,brewhouse_efficiency,
                                ferm_temp,ferm_time,notes)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (recipe['name'], recipe.get('style'), recipe.get('volume', 20),
                             recipe.get('brew_date'), recipe.get('mash_temp', 66), recipe.get('mash_time', 60),
                             recipe.get('boil_time', 60), recipe.get('mash_ratio', 3.0),
                             recipe.get('evap_rate', 3.0), recipe.get('grain_absorption', 0.8),
                             recipe.get('brewhouse_efficiency', 72), recipe.get('ferm_temp'),
                             recipe.get('ferm_time'), recipe.get('notes'))
                        )
                        rid = cur.lastrowid
                    for ing in recipe.get('ingredients', []):
                        conn.execute(
                            '''INSERT INTO recipe_ingredients
                               (recipe_id,name,category,quantity,unit,hop_time,hop_type,
                                hop_days,other_type,other_time,ebc,alpha,notes)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (rid, ing.get('name','?'), ing.get('category','autre'),
                             ing.get('quantity', 0), ing.get('unit', 'g'),
                             ing.get('hop_time'), ing.get('hop_type'), ing.get('hop_days'),
                             ing.get('other_type'), ing.get('other_time'),
                             ing.get('ebc'), ing.get('alpha'), ing.get('notes'))
                        )
                    imported += 1
                except Exception as e:
                    current_app.logger.warning(f"restore recettes: skipped {recipe.get('name')!r}: {e}")
        return imported

    elif section == 'cave':
        imported = 0
        with get_db() as conn:
            if mode == 'replace':
                conn.execute('DELETE FROM beers')
            for beer in items:
                if not beer.get('name'):
                    continue
                try:
                    existing = conn.execute('SELECT id FROM beers WHERE name=?', (beer['name'],)).fetchone()
                    if existing:
                        conn.execute(
                            '''UPDATE beers SET type=?,abv=?,stock_33cl=?,stock_75cl=?,origin=?,description=?,
                               archived=?,initial_33cl=?,initial_75cl=?,brew_date=?,bottling_date=? WHERE id=?''',
                            (beer.get('type'), beer.get('abv'),
                             beer.get('stock_33cl', 0), beer.get('stock_75cl', 0),
                             beer.get('origin'), beer.get('description'), beer.get('archived', 0),
                             beer.get('initial_33cl') or beer.get('stock_33cl', 0),
                             beer.get('initial_75cl') or beer.get('stock_75cl', 0),
                             beer.get('brew_date'), beer.get('bottling_date'), existing['id'])
                        )
                    else:
                        conn.execute(
                            '''INSERT INTO beers
                               (name,type,abv,stock_33cl,stock_75cl,origin,description,photo,
                                archived,initial_33cl,initial_75cl,brew_date,bottling_date)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (beer['name'], beer.get('type'), beer.get('abv'),
                             beer.get('stock_33cl', 0), beer.get('stock_75cl', 0),
                             beer.get('origin'), beer.get('description'), beer.get('photo'),
                             beer.get('archived', 0),
                             beer.get('initial_33cl') or beer.get('stock_33cl', 0),
                             beer.get('initial_75cl') or beer.get('stock_75cl', 0),
                             beer.get('brew_date'), beer.get('bottling_date'))
                        )
                    imported += 1
                except Exception as e:
                    current_app.logger.warning(f"restore cave: skipped {beer.get('name')!r}: {e}")
        return imported

    elif section == 'brassins':
        imported = 0
        with get_db() as conn:
            if mode == 'replace':
                conn.execute('DELETE FROM brew_fermentation_readings')
                _cal_purge_brew_photos(conn)
                conn.execute('DELETE FROM brews')
            for brew in items:
                if not brew.get('name'):
                    continue
                try:
                    recipe_id = None
                    if brew.get('recipe_name'):
                        row = conn.execute('SELECT id FROM recipes WHERE name=?', (brew['recipe_name'],)).fetchone()
                        if row: recipe_id = row['id']
                    if not recipe_id and brew.get('recipe_id'):
                        row = conn.execute('SELECT id FROM recipes WHERE id=?', (brew['recipe_id'],)).fetchone()
                        if row: recipe_id = row['id']
                    existing = conn.execute('SELECT id FROM brews WHERE name=?', (brew['name'],)).fetchone()
                    if existing:
                        conn.execute(
                            '''UPDATE brews SET brew_date=?,volume_brewed=?,og=?,fg=?,abv=?,
                               notes=?,status=?,archived=? WHERE id=?''',
                            (brew.get('brew_date'), brew.get('volume_brewed'),
                             brew.get('og'), brew.get('fg'), brew.get('abv'),
                             brew.get('notes'), brew.get('status', BrewStatus.COMPLETED),
                             brew.get('archived', 0), existing['id'])
                        )
                    else:
                        if not recipe_id:
                            cur = conn.execute(
                                'INSERT INTO recipes (name, volume, brewhouse_efficiency) VALUES (?,?,?)',
                                (brew.get('recipe_name') or brew['name'], brew.get('volume_brewed') or 20, 72)
                            )
                            recipe_id = cur.lastrowid
                        cur = conn.execute(
                            '''INSERT INTO brews
                               (recipe_id, name, brew_date, volume_brewed, og, fg, abv, notes, status, archived)
                               VALUES (?,?,?,?,?,?,?,?,?,?)''',
                            (recipe_id, brew['name'], brew.get('brew_date'),
                             brew.get('volume_brewed'), brew.get('og'), brew.get('fg'), brew.get('abv'),
                             brew.get('notes'), brew.get('status', BrewStatus.COMPLETED), brew.get('archived', 0))
                        )
                        brew_id = cur.lastrowid
                        for reading in brew.get('fermentation', []):
                            conn.execute(
                                '''INSERT INTO brew_fermentation_readings
                                   (brew_id, recorded_at, gravity, temperature, battery, angle)
                                   VALUES (?,?,?,?,?,?)''',
                                (brew_id, reading.get('recorded_at'), reading.get('gravity'),
                                 reading.get('temperature'), reading.get('battery'), reading.get('angle'))
                            )
                    imported += 1
                except Exception as e:
                    current_app.logger.warning(f"restore brassins: skipped {brew.get('name')!r}: {e}")
        return imported

    elif section == 'densimetres':
        imported = 0
        with get_db() as conn:
            if mode == 'replace':
                sids = [r['id'] for r in conn.execute('SELECT id FROM spindles').fetchall()]
                with get_readings_db() as rconn:
                    for sid in sids:
                        rconn.execute('DELETE FROM spindle_readings WHERE spindle_id=?', (sid,))
                conn.execute('DELETE FROM spindles')
            for spindle in items:
                if not spindle.get('name'):
                    continue
                try:
                    existing = conn.execute('SELECT id FROM spindles WHERE name=?', (spindle['name'],)).fetchone()
                    if existing:
                        conn.execute('UPDATE spindles SET notes=? WHERE id=?', (spindle.get('notes'), existing['id']))
                    else:
                        token = secrets.token_urlsafe(16)
                        cur = conn.execute(
                            'INSERT INTO spindles (name, token, notes) VALUES (?,?,?)',
                            (spindle['name'], token, spindle.get('notes'))
                        )
                        with get_readings_db() as rconn:
                            for reading in spindle.get('readings', []):
                                rconn.execute(
                                    '''INSERT INTO spindle_readings
                                       (spindle_id, gravity, temperature, battery, angle, rssi, recorded_at)
                                       VALUES (?,?,?,?,?,?,?)''',
                                    (cur.lastrowid, reading.get('gravity'), reading.get('temperature'),
                                     reading.get('battery'), reading.get('angle'), reading.get('rssi'),
                                     reading.get('recorded_at'))
                                )
                    imported += 1
                except Exception as e:
                    current_app.logger.warning(f"restore densimetres: skipped {spindle.get('name')!r}: {e}")
        return imported

    elif section == 'brouillons':
        imported = 0
        with get_db() as conn:
            if mode == 'replace':
                conn.execute('DELETE FROM draft_recipes')
            for d in items:
                if not d.get('title'):
                    continue
                try:
                    img = _shrink_image_b64(d['image']) if _image_too_large(d.get('image')) else d.get('image')
                    existing = conn.execute('SELECT id FROM draft_recipes WHERE title=?', (d['title'],)).fetchone()
                    if existing:
                        conn.execute(
                            '''UPDATE draft_recipes SET style=?,volume=?,ingredients=?,notes=?,color=?,
                               target_date=?,event_label=?,image=? WHERE id=?''',
                            (d.get('style'), d.get('volume'), d.get('ingredients'), d.get('notes'),
                             d.get('color', '#ff9500'), d.get('target_date'), d.get('event_label'),
                             img, existing['id'])
                        )
                    else:
                        conn.execute(
                            '''INSERT INTO draft_recipes
                               (title, style, volume, ingredients, notes, color,
                                target_date, event_label, sort_order, image)
                               VALUES (?,?,?,?,?,?,?,?,?,?)''',
                            (d.get('title', 'Brouillon'), d.get('style'), d.get('volume'),
                             d.get('ingredients'), d.get('notes'), d.get('color', '#ff9500'),
                             d.get('target_date'), d.get('event_label'), d.get('sort_order', 0), img)
                        )
                    imported += 1
                except Exception as e:
                    current_app.logger.warning(f"restore brouillons: skipped {d.get('title')!r}: {e}")
        return imported

    elif section == 'calendrier':
        imported = 0
        with get_db() as conn:
            if mode == 'replace':
                conn.execute('DELETE FROM custom_calendar_events')
            for ev in items:
                if not ev.get('title') or not ev.get('event_date'):
                    continue
                try:
                    existing = conn.execute(
                        'SELECT id FROM custom_calendar_events WHERE title=? AND event_date=?',
                        (ev['title'], ev['event_date'])
                    ).fetchone()
                    if existing:
                        conn.execute(
                            '''UPDATE custom_calendar_events SET emoji=?,color=?,notes=?,
                               brew_reminder=?,telegram_notify=?,style=?,recipe_id=?,draft_id=? WHERE id=?''',
                            (ev.get('emoji', '📅'), ev.get('color', '#f59e0b'), ev.get('notes'),
                             ev.get('brew_reminder', 0), ev.get('telegram_notify', 0),
                             ev.get('style'), ev.get('recipe_id'), ev.get('draft_id'), existing['id'])
                        )
                    else:
                        conn.execute(
                            '''INSERT INTO custom_calendar_events
                               (title, emoji, event_date, color, notes,
                                brew_reminder, telegram_notify, style, recipe_id, draft_id)
                               VALUES (?,?,?,?,?,?,?,?,?,?)''',
                            (ev.get('title'), ev.get('emoji', '📅'), ev['event_date'],
                             ev.get('color', '#f59e0b'), ev.get('notes'),
                             ev.get('brew_reminder', 0), ev.get('telegram_notify', 0),
                             ev.get('style'), ev.get('recipe_id'), ev.get('draft_id'))
                        )
                    imported += 1
                except Exception as e:
                    current_app.logger.warning(f"restore calendrier: skipped {ev.get('title')!r}: {e}")
        return imported

    return 0
