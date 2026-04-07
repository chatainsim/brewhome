import json
import os
import sqlite3
import uuid
from datetime import datetime
from flask import Blueprint, jsonify, request, send_from_directory
from db import get_db, _log, _log_inv, PHOTOS_DIR
from helpers import _to_base, _from_base, _make_thumb, _image_too_large, _shrink_image_b64, _b64_to_jpeg_file, _make_thumb_file, validate, api_error
from constants import BrewStatus

bp = Blueprint('brews', __name__)


def _compute_efficiency(conn, recipe_id, og, volume_brewed):
    """Calcule le rendement brasserie réel (%) depuis OG mesurée et volume obtenu.
    Retourne None si les données sont insuffisantes (pas de grain avec GU dans le catalogue).
    """
    if not recipe_id or not og or not volume_brewed or volume_brewed <= 0:
        return None
    rows = conn.execute(
        '''SELECT ri.quantity, ri.unit, ic.gu
           FROM recipe_ingredients ri
           JOIN ingredient_catalog ic
               ON ic.name = ri.name AND ic.category = 'malt'
           WHERE ri.recipe_id = ? AND ri.category = 'malt'
             AND ic.gu IS NOT NULL''',
        (recipe_id,)
    ).fetchall()
    max_pts = sum(
        (r['quantity'] if r['unit'] == 'kg' else r['quantity'] / 1000) * r['gu']
        for r in rows
    )
    if max_pts <= 0:
        return None
    eff = round((og - 1) * 1000 * volume_brewed / max_pts * 100, 1)
    return max(0.0, min(110.0, eff))

_BREW_SCHEMA = {
    'name':                   {'type': str,          'max_len': 200},
    'notes':                  {'type': str,          'max_len': 10000},
    'volume_brewed':          {'type': (int, float), 'min_val': 0,    'max_val': 10000},
    'og':                     {'type': (int, float), 'min_val': 0.9,  'max_val': 1.3},
    'fg':                     {'type': (int, float), 'min_val': 0.9,  'max_val': 1.3},
    'abv':                    {'type': (int, float), 'min_val': 0,    'max_val': 25},
    'ferm_time':              {'type': (int, float), 'min_val': 0,    'max_val': 365},
    'cost_snapshot':          {'type': (int, float), 'min_val': 0,    'max_val': 100000},
    'cost_per_liter_snapshot':{'type': (int, float), 'min_val': 0,    'max_val': 10000},
}


@bp.route('/api/brews', methods=['GET'])
def get_brews():
    with get_db() as conn:
        rows = conn.execute(
            '''WITH
                 ferm_cnt AS (
                   SELECT brew_id, COUNT(*) AS fermentation_count
                   FROM brew_fermentation_readings GROUP BY brew_id
                 ),
                 photo_cnt AS (
                   SELECT brew_id, COUNT(*) AS photo_count
                   FROM brew_photos GROUP BY brew_id
                 ),
                 log_cnt AS (
                   SELECT brew_id, COUNT(*) AS log_count
                   FROM brew_log GROUP BY brew_id
                 ),
                 beer_agg AS (
                   SELECT brew_id,
                          MIN(CASE WHEN bottling_date IS NOT NULL THEN bottling_date END) AS bottling_date,
                          SUM(CASE WHEN archived=0
                                   THEN stock_33cl*0.33 + stock_75cl*0.75 + COALESCE(keg_liters,0)
                                   ELSE 0 END) AS cave_liters
                   FROM beers WHERE brew_id IS NOT NULL GROUP BY brew_id
                 ),
                 cons_agg AS (
                   SELECT bx.brew_id,
                          MIN(c.ts) AS first_consumption,
                          MAX(c.ts) AS last_consumption
                   FROM consumption_log c
                   JOIN beers bx ON c.beer_id=bx.id
                   WHERE bx.brew_id IS NOT NULL GROUP BY bx.brew_id
                 )
               SELECT b.*, r.name AS recipe_name, r.style AS recipe_style,
                      COALESCE(b.ferm_time, r.ferm_time) AS ferm_time,
                      b.ferm_time AS brew_ferm_time,
                      r.ferm_time AS recipe_ferm_time,
                      COALESCE(fc.fermentation_count, 0) AS fermentation_count,
                      COALESCE(pc.photo_count, 0)        AS photo_count,
                      COALESCE(lc.log_count, 0)          AS log_count,
                      ba.bottling_date,
                      ca.first_consumption,
                      ca.last_consumption,
                      ba.cave_liters
               FROM brews b
               LEFT JOIN recipes r      ON r.id=b.recipe_id
               LEFT JOIN ferm_cnt  fc   ON fc.brew_id=b.id
               LEFT JOIN photo_cnt pc   ON pc.brew_id=b.id
               LEFT JOIN log_cnt   lc   ON lc.brew_id=b.id
               LEFT JOIN beer_agg  ba   ON ba.brew_id=b.id
               LEFT JOIN cons_agg  ca   ON ca.brew_id=b.id
               WHERE b.deleted_at IS NULL
               ORDER BY COALESCE(b.sort_order, 9999) ASC, b.created_at DESC'''
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/brews/reorder', methods=['PUT'])
def reorder_brews():
    items = request.json or []
    if any(not isinstance(it.get('sort_order'), int) or isinstance(it.get('sort_order'), bool) or it.get('sort_order') < 0
           for it in items if it.get('id') is not None):
        return api_error('validation', 400, detail='sort_order must be a non-negative integer')
    valid = [(it['sort_order'], it['id']) for it in items
             if it.get('id') is not None and it.get('sort_order') is not None]
    with get_db() as conn:
        conn.executemany('UPDATE brews SET sort_order=? WHERE id=?', valid)
    return jsonify({'success': True})


@bp.route('/api/brews', methods=['POST'])
def create_brew():
    return _do_create_brew()


def _do_create_brew():
    d = request.json or {}
    recipe_id = d.get('recipe_id')
    if not recipe_id:
        return api_error('missing_field', 400, detail='recipe_id required')
    errors = validate(d, _BREW_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    deduct = d.get('deduct_stock', True)

    conn = get_db()

    # ── Pre-flight stock check (read-only, no lock needed) ────────────────────
    ings = []
    if deduct:
        ings = conn.execute(
            '''SELECT ri.*, ii.quantity as stock_qty, ii.unit as inv_unit
               FROM recipe_ingredients ri
               LEFT JOIN inventory_items ii ON ri.inventory_item_id=ii.id
               WHERE ri.recipe_id=?''',
            (recipe_id,)
        ).fetchall()

        insufficient = []
        for i in ings:
            if not i['inventory_item_id']:
                continue
            inv_unit    = i['inv_unit'] or i['unit']
            needed_base = _to_base(i['quantity'], i['unit'])
            stock_base  = _to_base(i['stock_qty'] or 0, inv_unit)
            if stock_base < needed_base:
                available_disp = round(_from_base(stock_base, i['unit']), 6)
                insufficient.append({
                    'name': i['name'],
                    'needed': i['quantity'],
                    'available': available_disp,
                    'unit': i['unit'],
                    'category': i['category'],
                })

        if insufficient and not d.get('force', False):
            return api_error('stock_insuffisant', 409, items=insufficient)

    # ── Batch number uniqueness check (non-archived, non-deleted brews only) ──
    batch_num = d.get('batch_number') if d.get('batch_number') else None
    if batch_num is not None:
        dup = conn.execute(
            'SELECT id FROM brews WHERE batch_number=? AND deleted_at IS NULL AND archived=0',
            (batch_num,)
        ).fetchone()
        if dup:
            return api_error('duplicate_batch_number', 409, detail=str(batch_num))

    # ── Atomic write: stock deduction + brew creation in one transaction ──────
    # BEGIN IMMEDIATE takes the write lock upfront — no TOCTOU between the
    # stock check above and the UPDATE below, and no partial state on error.
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Re-read all stocks under the write lock before any deduction (TOCTOU fix)
        locked_insufficient = []
        locked_stocks = {}  # inventory_item_id -> (stock_base, inv_unit)
        for ing in ings:
            if not ing['inventory_item_id']:
                continue
            inv_unit    = ing['inv_unit'] or ing['unit']
            needed_base = _to_base(ing['quantity'], ing['unit'])
            fresh = conn.execute(
                'SELECT quantity FROM inventory_items WHERE id=?',
                (ing['inventory_item_id'],)
            ).fetchone()
            stock_base = _to_base(fresh['quantity'] if fresh else 0, inv_unit)
            locked_stocks[ing['inventory_item_id']] = (stock_base, inv_unit)
            if stock_base < needed_base:
                locked_insufficient.append({
                    'name':      ing['name'],
                    'needed':    ing['quantity'],
                    'available': round(_from_base(stock_base, ing['unit']), 6),
                    'unit':      ing['unit'],
                    'category':  ing['category'],
                })

        if locked_insufficient and not d.get('force', False):
            conn.execute("ROLLBACK")
            return api_error('stock_insuffisant', 409, items=locked_insufficient)

        _inv_log_pending = []
        for ing in ings:
            if not ing['inventory_item_id']:
                continue
            inv_unit    = ing['inv_unit'] or ing['unit']
            needed_base = _to_base(ing['quantity'], ing['unit'])
            stock_base, _ = locked_stocks[ing['inventory_item_id']]
            new_base = max(0.0, stock_base - needed_base)
            new_qty  = round(_from_base(new_base, inv_unit), 6)
            old_qty  = round(_from_base(stock_base, inv_unit), 6)
            conn.execute(
                'UPDATE inventory_items SET quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                (new_qty, ing['inventory_item_id'])
            )
            _inv_log_pending.append((ing['inventory_item_id'], new_qty - old_qty, old_qty, new_qty))

        actual_eff = _compute_efficiency(conn, recipe_id, d.get('og'), d.get('volume_brewed'))
        cur = conn.execute(
            '''INSERT INTO brews (recipe_id,name,batch_number,brew_date,volume_brewed,og,fg,abv,notes,status,actual_efficiency,cost_snapshot,cost_per_liter_snapshot)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (recipe_id, d.get('name'),
             d.get('batch_number') if d.get('batch_number') else None,
             d.get('brew_date'), d.get('volume_brewed'),
             d.get('og'), d.get('fg'), d.get('abv'), d.get('notes'),
             d.get('status', BrewStatus.COMPLETED), actual_eff,
             d.get('cost_snapshot'), d.get('cost_per_liter_snapshot'))
        )
        brew_id = cur.lastrowid
        brew_name = d.get('name', '')
        for (item_id, delta, old_q, new_q) in _inv_log_pending:
            _log_inv(item_id, delta, old_q, new_q, 'brew_deduction',
                     'brew', brew_id, brew_name, conn)
        row = conn.execute(
            '''SELECT b.*, r.name as recipe_name FROM brews b
               LEFT JOIN recipes r ON b.recipe_id=r.id WHERE b.id=?''',
            (brew_id,)
        ).fetchone()
        _log('brew', 'created', json.dumps({'_i18n':'act.brew_created','name':d.get('name','')}), brew_id, conn)
        conn.execute("COMMIT")
        return jsonify(dict(row)), 201
    except sqlite3.Error:
        conn.execute("ROLLBACK")
        raise


@bp.route('/api/brews/<int:brew_id>', methods=['PUT'])
def update_brew(brew_id):
    d = request.json
    errors = validate(d, _BREW_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        brew_row = conn.execute('SELECT status, recipe_id, fermenting_since FROM brews WHERE id=?', (brew_id,)).fetchone()
        old_status = brew_row['status'] if brew_row else None
        new_status = d.get('status', BrewStatus.COMPLETED)
        batch_num = d.get('batch_number') if d.get('batch_number') else None
        if batch_num is not None:
            dup = conn.execute(
                'SELECT id FROM brews WHERE batch_number=? AND id!=? AND deleted_at IS NULL AND archived=0',
                (batch_num, brew_id)
            ).fetchone()
            if dup:
                return api_error('duplicate_batch_number', 409, detail=str(batch_num))
        actual_eff = _compute_efficiency(
            conn,
            brew_row['recipe_id'] if brew_row else None,
            d.get('og'), d.get('volume_brewed')
        )
        if new_status == 'fermenting' and old_status != 'fermenting':
            fermenting_since = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif new_status != 'fermenting':
            fermenting_since = None
        else:
            fermenting_since = brew_row['fermenting_since'] if brew_row else None
        cur = conn.execute(
            'UPDATE brews SET name=?,brew_date=?,volume_brewed=?,og=?,fg=?,abv=?,notes=?,status=?,ferm_time=?,photos_url=?,actual_efficiency=?,cost_snapshot=?,cost_per_liter_snapshot=?,fermenting_since=? WHERE id=?',
            (d.get('name'), d.get('brew_date'), d.get('volume_brewed'),
             d.get('og'), d.get('fg'), d.get('abv'), d.get('notes'),
             new_status,
             int(d['ferm_time']) if d.get('ferm_time') is not None else None,
             d.get('photos_url') or None,
             actual_eff,
             d.get('cost_snapshot'), d.get('cost_per_liter_snapshot'),
             fermenting_since,
             brew_id)
        )
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        if d.get('status') == BrewStatus.COMPLETED:
            _log('brew', 'completed', json.dumps({'_i18n':'act.brew_completed','name':d.get('name','–')}), brew_id, conn)
            sp = conn.execute('SELECT id FROM spindles WHERE brew_id=?', (brew_id,)).fetchone()
            if sp:
                readings = conn.execute(
                    '''SELECT recorded_at, gravity, temperature, battery, angle
                       FROM rdb.spindle_readings WHERE spindle_id=? ORDER BY recorded_at''',
                    (sp['id'],)
                ).fetchall()
                if readings:
                    conn.executemany(
                        '''INSERT INTO brew_fermentation_readings
                           (brew_id, recorded_at, gravity, temperature, battery, angle)
                           VALUES (?,?,?,?,?,?)''',
                        [(brew_id, r['recorded_at'], r['gravity'], r['temperature'],
                          r['battery'], r['angle']) for r in readings]
                    )
                conn.execute('UPDATE spindles SET brew_id=NULL WHERE brew_id=?', (brew_id,))
                conn.execute('DELETE FROM rdb.spindle_readings WHERE spindle_id=?', (sp['id'],))
            # Migrate temperature sensor readings — batch to avoid N+1
            ts_rows = conn.execute(
                'SELECT id FROM temperature_sensors WHERE brew_id=?', (brew_id,)
            ).fetchall()
            if ts_rows:
                ts_ids = [r['id'] for r in ts_rows]
                ph = ','.join('?' * len(ts_ids))
                all_tr = conn.execute(
                    f'''SELECT recorded_at, temperature
                        FROM rdb.temperature_readings
                        WHERE sensor_id IN ({ph})
                        ORDER BY recorded_at''',
                    ts_ids
                ).fetchall()
                if all_tr:
                    conn.executemany(
                        '''INSERT INTO brew_fermentation_readings
                           (brew_id, recorded_at, temperature, source)
                           VALUES (?,?,?,'temp_sensor')''',
                        [(brew_id, r['recorded_at'], r['temperature']) for r in all_tr]
                    )
                conn.execute(f'UPDATE temperature_sensors SET brew_id=NULL WHERE id IN ({ph})', ts_ids)
                conn.execute(f'DELETE FROM rdb.temperature_readings WHERE sensor_id IN ({ph})', ts_ids)
        row = conn.execute(
            '''SELECT b.*, r.name as recipe_name, r.style as recipe_style,
                      COALESCE(b.ferm_time, r.ferm_time) as ferm_time,
                      b.ferm_time as brew_ferm_time,
                      r.ferm_time as recipe_ferm_time,
                      (SELECT MIN(bottling_date) FROM beers WHERE brew_id=b.id AND bottling_date IS NOT NULL) as bottling_date
               FROM brews b LEFT JOIN recipes r ON b.recipe_id=r.id WHERE b.id=?''',
            (brew_id,)
        ).fetchone()
        return jsonify(dict(row))


@bp.route('/api/brews/<int:brew_id>', methods=['DELETE'])
def delete_brew(brew_id):
    with get_db() as conn:
        row = conn.execute('SELECT name FROM brews WHERE id=?', (brew_id,)).fetchone()
        cur = conn.execute(
            'UPDATE brews SET archived=1, deleted_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL',
            (brew_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        if row:
            _log('brew', 'deleted', json.dumps({'_i18n':'act.brew_deleted','name':row['name']}), brew_id, conn)
        return jsonify({'success': True})


@bp.route('/api/brews/<int:brew_id>/restore', methods=['POST'])
def restore_brew(brew_id):
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE brews SET archived=0, deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL',
            (brew_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/brews/<int:brew_id>/purge', methods=['DELETE'])
def purge_brew(brew_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM brews WHERE id=? AND deleted_at IS NOT NULL', (brew_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/brews/<int:brew_id>/dryhop_done', methods=['POST'])
def mark_dryhop_done(brew_id):
    d = request.json or {}
    date_str = d.get('date', '')
    try:
        from datetime import date as _date
        _date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return api_error('validation', 400, detail='date must be a valid ISO date (YYYY-MM-DD)')
    with get_db() as conn:
        row = conn.execute('SELECT dryhop_done_dates FROM brews WHERE id=? AND deleted_at IS NULL', (brew_id,)).fetchone()
        if not row:
            return api_error('not_found', 404)
        try:
            done = json.loads(row['dryhop_done_dates'] or '[]')
        except (json.JSONDecodeError, TypeError):
            done = []
        if date_str not in done:
            done.append(date_str)
        conn.execute('UPDATE brews SET dryhop_done_dates=? WHERE id=?', (json.dumps(done), brew_id))
        return jsonify({'success': True, 'done_dates': done})


@bp.route('/api/brews/<int:brew_id>', methods=['PATCH'])
def patch_brew(brew_id):
    d = request.json
    with get_db() as conn:
        if 'notes' in d:
            cur = conn.execute('UPDATE brews SET notes=? WHERE id=?',
                               (d.get('notes') or None, brew_id))
        else:
            cur = conn.execute('UPDATE brews SET archived=? WHERE id=?',
                               (1 if d.get('archived') else 0, brew_id))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        row = conn.execute(
            'SELECT b.*, r.name as recipe_name FROM brews b LEFT JOIN recipes r ON b.recipe_id=r.id WHERE b.id=?',
            (brew_id,)).fetchone()
        return jsonify(dict(row))


@bp.route('/api/brews/<int:brew_id>/fermentation', methods=['GET'])
def get_brew_fermentation(brew_id):
    source = request.args.get('source')
    with get_db() as conn:
        if source:
            rows = conn.execute(
                'SELECT * FROM brew_fermentation_readings WHERE brew_id=? AND source=? ORDER BY recorded_at',
                (brew_id, source)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM brew_fermentation_readings WHERE brew_id=? ORDER BY recorded_at',
                (brew_id,)
            ).fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/brews/<int:brew_id>/fermentation', methods=['POST'])
def add_brew_fermentation(brew_id):
    data = request.get_json(force=True)
    recorded_at = data.get('recorded_at', '').strip()
    gravity = data.get('gravity')
    temperature = data.get('temperature')
    notes = data.get('notes', '')
    if not recorded_at or gravity is None:
        return api_error('missing_field', 400, detail='recorded_at and gravity are required')
    try:
        gravity = float(gravity)
        temperature = float(temperature) if temperature not in (None, '') else None
    except (ValueError, TypeError):
        return api_error('invalid_input', 400, detail='invalid numeric values')
    with get_db() as conn:
        brew = conn.execute('SELECT id FROM brews WHERE id=?', (brew_id,)).fetchone()
        if not brew:
            return api_error('not_found', 404)
        cur = conn.execute(
            '''INSERT INTO brew_fermentation_readings
               (brew_id, recorded_at, gravity, temperature, battery, angle, source, notes)
               VALUES (?, ?, ?, ?, NULL, NULL, 'manual', ?)''',
            (brew_id, recorded_at, gravity, temperature, notes)
        )
        return jsonify({'id': cur.lastrowid}), 201


@bp.route('/api/brews/<int:brew_id>/fermentation/<int:reading_id>', methods=['DELETE'])
def delete_brew_fermentation(brew_id, reading_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, source FROM brew_fermentation_readings WHERE id=? AND brew_id=?",
            (reading_id, brew_id)
        ).fetchone()
        if not row:
            return api_error('not_found', 404)
        if row['source'] != 'manual':
            return api_error('forbidden', 403, detail='only manual readings can be deleted')
        conn.execute('DELETE FROM brew_fermentation_readings WHERE id=?', (reading_id,))
        return jsonify({'ok': True})


@bp.route('/api/brews/<int:brew_id>/log', methods=['GET'])
def get_brew_log(brew_id):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM brew_log WHERE brew_id=? ORDER BY ts ASC', (brew_id,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])

@bp.route('/api/brews/<int:brew_id>/log', methods=['POST'])
def add_brew_log(brew_id):
    d = request.json or {}
    ts   = d.get('ts', '').strip()
    step = d.get('step', '').strip() or None
    note = d.get('note', '').strip()
    if not ts or not note:
        return api_error('missing_field', 400, detail='ts and note required')
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO brew_log (brew_id, ts, step, note) VALUES (?,?,?,?)',
            (brew_id, ts, step, note)
        )
        return jsonify({'id': cur.lastrowid, 'ok': True})

@bp.route('/api/brews/<int:brew_id>/log/<int:entry_id>', methods=['DELETE'])
def delete_brew_log(brew_id, entry_id):
    with get_db() as conn:
        row = conn.execute(
            'SELECT id FROM brew_log WHERE id=? AND brew_id=?', (entry_id, brew_id)
        ).fetchone()
        if not row:
            return api_error('not_found', 404)
        conn.execute('DELETE FROM brew_log WHERE id=?', (entry_id,))
        return jsonify({'ok': True})


def _photo_url(filename):
    return f'/api/brew-photos/{filename}'


def _row_to_list_dict(row):
    """Retourne un dict pour la liste (sans la photo plein format)."""
    d = dict(row)
    d['thumb'] = _photo_url(d['thumb_file']) if d.get('thumb_file') else d.get('thumb')
    d.pop('photo', None)
    d.pop('photo_file', None)
    d.pop('thumb_file', None)
    return d


def _row_to_full_dict(row):
    """Retourne un dict avec la photo plein format."""
    d = dict(row)
    d['photo'] = _photo_url(d['photo_file']) if d.get('photo_file') else d.get('photo')
    d['thumb'] = _photo_url(d['thumb_file']) if d.get('thumb_file') else d.get('thumb')
    d.pop('photo_file', None)
    d.pop('thumb_file', None)
    return d


def _delete_photo_files(row):
    """Supprime les fichiers disque associés à une ligne brew_photos."""
    for col in ('photo_file', 'thumb_file'):
        fname = row[col] if col in row.keys() else None
        if fname:
            try:
                os.remove(os.path.join(PHOTOS_DIR, fname))
            except OSError:
                pass


@bp.route('/api/brew-photos/<path:filename>')
def serve_brew_photo(filename):
    safe = os.path.basename(filename)
    return send_from_directory(PHOTOS_DIR, safe)


@bp.route('/api/brews/<int:brew_id>/photos', methods=['GET', 'POST'])
def brew_photos(brew_id):
    if request.method == 'POST':
        d = request.json or {}
        raw = d.get('photo', '')
        if not raw:
            return api_error('missing_field', 400, detail='photo required')
        os.makedirs(PHOTOS_DIR, exist_ok=True)
        uid = uuid.uuid4().hex
        photo_fname = f'{uid}.jpg'
        thumb_fname = f'{uid}_t.jpg'
        photo_path  = os.path.join(PHOTOS_DIR, photo_fname)
        thumb_path  = os.path.join(PHOTOS_DIR, thumb_fname)
        if _image_too_large(raw):
            raw = _shrink_image_b64(raw)
        try:
            _b64_to_jpeg_file(raw, photo_path)
        except Exception as e:
            current_app.logger.warning('brew_photos: failed to save photo %s: %s', photo_fname, e)
            return api_error('image_error', 500)
        try:
            _make_thumb_file(raw, thumb_path)
        except Exception as e:
            current_app.logger.warning('brew_photos: failed to create thumbnail %s: %s', thumb_fname, e)
            try:
                os.remove(photo_path)
            except OSError:
                pass
            return api_error('image_error', 500)
        with get_db() as conn:
            cur = conn.execute(
                'INSERT INTO brew_photos (brew_id, step, caption, photo_file, thumb_file) VALUES (?,?,?,?,?)',
                (brew_id, d.get('step'), d.get('caption'), photo_fname, thumb_fname)
            )
            row = conn.execute(
                'SELECT * FROM brew_photos WHERE id=?', (cur.lastrowid,)
            ).fetchone()
        return jsonify(_row_to_list_dict(row)), 201
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM brew_photos WHERE brew_id=? ORDER BY created_at',
            (brew_id,)
        ).fetchall()
    return jsonify([_row_to_list_dict(r) for r in rows])


@bp.route('/api/brews/<int:brew_id>/photos/<int:photo_id>', methods=['GET', 'DELETE', 'PATCH'])
def brew_photo_item(brew_id, photo_id):
    if request.method == 'DELETE':
        with get_db() as conn:
            row = conn.execute(
                'SELECT * FROM brew_photos WHERE id=? AND brew_id=?', (photo_id, brew_id)
            ).fetchone()
            if row:
                _delete_photo_files(row)
                conn.execute('DELETE FROM brew_photos WHERE id=? AND brew_id=?', (photo_id, brew_id))
        return jsonify({'success': True})
    if request.method == 'PATCH':
        d = request.json or {}
        with get_db() as conn:
            conn.execute(
                'UPDATE brew_photos SET step=?, caption=? WHERE id=? AND brew_id=?',
                (d.get('step') or None, d.get('caption') or None, photo_id, brew_id)
            )
            row = conn.execute('SELECT * FROM brew_photos WHERE id=? AND brew_id=?', (photo_id, brew_id)).fetchone()
        if not row:
            return api_error('not_found', 404)
        return jsonify(_row_to_full_dict(row))
    with get_db() as conn:
        row = conn.execute('SELECT * FROM brew_photos WHERE id=? AND brew_id=?', (photo_id, brew_id)).fetchone()
    if not row:
        return api_error('not_found', 404)
    return jsonify(_row_to_full_dict(row))
