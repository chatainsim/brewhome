import json
from datetime import date
from flask import Blueprint, jsonify, request, current_app
from db import get_db, _log
from helpers import validate, api_error

bp = Blueprint('beers', __name__)

_BEER_SCHEMA = {
    'name':        {'type': str,          'max_len': 200},
    'type':        {'type': str,          'max_len': 100},
    'description': {'type': str,          'max_len': 5000},
    'origin':      {'type': str,          'max_len': 200},
    'abv':         {'type': (int, float), 'min_val': 0,  'max_val': 30},
    'stock_33cl':  {'type': int,          'min_val': 0,  'max_val': 10000},
    'stock_75cl':  {'type': int,          'min_val': 0,  'max_val': 10000},
    'keg_liters':           {'type': (int, float), 'min_val': 0,   'max_val': 10000},
    'refermentation_days':  {'type': int,          'min_val': 1,   'max_val': 365},
}


@bp.route('/api/beers', methods=['GET'])
def get_beers():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT b.*, br.brew_date, br.photos_url as brew_photos_url, r.name as recipe_name
               FROM beers b
               LEFT JOIN brews br ON b.brew_id=br.id
               LEFT JOIN recipes r ON b.recipe_id=r.id
               WHERE b.deleted_at IS NULL
               ORDER BY COALESCE(b.sort_order, 9999) ASC, b.created_at DESC'''
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/beers/reorder', methods=['PUT'])
def reorder_beers():
    items = request.json or []
    if any(not isinstance(it.get('sort_order'), int) or isinstance(it.get('sort_order'), bool) or it.get('sort_order') < 0
           for it in items if it.get('id') is not None):
        return api_error('validation', 400, detail='sort_order must be a non-negative integer')
    valid = [(it['sort_order'], it['id']) for it in items
             if it.get('id') is not None and it.get('sort_order') is not None]
    with get_db() as conn:
        conn.executemany('UPDATE beers SET sort_order=? WHERE id=?', valid)
    return jsonify({'success': True})


@bp.route('/api/beers', methods=['POST'])
def create_beer():
    d = request.json or {}
    if not d.get('name'):
        return api_error('missing_field', 400, detail='name is required')
    errors = validate(d, _BEER_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        s33 = d.get('stock_33cl', 0)
        s75 = d.get('stock_75cl', 0)
        keg = d.get('keg_liters')
        cur = conn.execute(
            '''INSERT INTO beers (name,type,abv,stock_33cl,stock_75cl,initial_33cl,initial_75cl,keg_liters,keg_initial_liters,origin,description,photo,brew_id,recipe_id,brew_date,bottling_date,refermentation,refermentation_days)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('name'), d.get('type'), d.get('abv'), s33, s75,
             d.get('initial_33cl', s33), d.get('initial_75cl', s75),
             keg, d.get('keg_initial_liters', keg),
             d.get('origin'), d.get('description'),
             d.get('photo'), d.get('brew_id'), d.get('recipe_id'),
             d.get('brew_date'), d.get('bottling_date'),
             1 if d.get('refermentation') else 0,
             int(d['refermentation_days']) if d.get('refermentation_days') else None)
        )
        beer_id = cur.lastrowid
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        _log('beer', 'created', json.dumps({'_i18n':'act.beer_created','name':d.get('name','')}), beer_id, conn)
    # Telegram bottling notification (outside DB context to avoid locking)
    if d.get('brew_id') and (s33 or s75 or keg):
        try:
            from blueprints.integrations import _tg_fire_bottling
            _tg_fire_bottling(d.get('name'), s33, s75, keg, d.get('bottling_date'))
        except Exception as e:
            current_app.logger.warning('tg bottling notification failed: %s', e)
    return jsonify(dict(row)), 201


@bp.route('/api/beers/<int:beer_id>', methods=['PUT'])
def update_beer(beer_id):
    d = request.json or {}
    errors = validate(d, _BEER_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        existing = conn.execute('SELECT initial_33cl, initial_75cl, keg_initial_liters FROM beers WHERE id=?', (beer_id,)).fetchone()
        if not existing:
            return api_error('not_found', 404)
        init33 = d['initial_33cl'] if 'initial_33cl' in d else existing['initial_33cl']
        init75 = d['initial_75cl'] if 'initial_75cl' in d else existing['initial_75cl']
        keg_init = d['keg_initial_liters'] if 'keg_initial_liters' in d else existing['keg_initial_liters']
        conn.execute(
            '''UPDATE beers SET name=?,type=?,abv=?,stock_33cl=?,stock_75cl=?,
               initial_33cl=?,initial_75cl=?,keg_liters=?,keg_initial_liters=?,origin=?,description=?,photo=?,
               brew_date=?,bottling_date=?,refermentation=?,refermentation_days=? WHERE id=?''',
            (d.get('name'), d.get('type'), d.get('abv'), d.get('stock_33cl', 0),
             d.get('stock_75cl', 0), init33, init75,
             d.get('keg_liters'), keg_init,
             d.get('origin'), d.get('description'),
             d.get('photo'), d.get('brew_date'), d.get('bottling_date'),
             1 if d.get('refermentation') else 0,
             int(d['refermentation_days']) if d.get('refermentation_days') else None,
             beer_id)
        )
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        return jsonify(dict(row))


@bp.route('/api/beers/<int:beer_id>/tasting', methods=['PUT'])
def update_beer_tasting(beer_id):
    d = request.json
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE beers SET
               taste_appearance=?, taste_aroma=?, taste_flavor=?,
               taste_bitterness=?, taste_mouthfeel=?, taste_overall=?,
               taste_finish=?, taste_rating=?, taste_date=?,
               taste_score_appearance=?, taste_score_aroma=?, taste_score_flavor=?,
               taste_score_bitterness=?, taste_score_mouthfeel=?, taste_score_finish=?
               WHERE id=?''',
            (d.get('taste_appearance'), d.get('taste_aroma'), d.get('taste_flavor'),
             d.get('taste_bitterness'), d.get('taste_mouthfeel'), d.get('taste_overall'),
             d.get('taste_finish'), d.get('taste_rating'), d.get('taste_date'),
             d.get('taste_score_appearance'), d.get('taste_score_aroma'), d.get('taste_score_flavor'),
             d.get('taste_score_bitterness'), d.get('taste_score_mouthfeel'), d.get('taste_score_finish'),
             beer_id)
        )
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        return jsonify(dict(row))


@bp.route('/api/beers/<int:beer_id>', methods=['DELETE'])
def delete_beer(beer_id):
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE beers SET archived=1, deleted_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL',
            (beer_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/beers/<int:beer_id>/restore', methods=['POST'])
def restore_beer(beer_id):
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE beers SET archived=0, deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL',
            (beer_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/beers/<int:beer_id>/purge', methods=['DELETE'])
def purge_beer(beer_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM beers WHERE id=? AND deleted_at IS NOT NULL', (beer_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/beers/<int:beer_id>/stock', methods=['PATCH'])
def patch_beer_stock(beer_id):
    d = request.json or {}
    for field in ('stock_33cl', 'stock_75cl', 'keg_liters'):
        if field in d:
            if not isinstance(d[field], (int, float)) or d[field] < 0:
                return api_error('validation', 400, fields={field: 'must be a non-negative number'})
    with get_db() as conn:
        cur = conn.execute('SELECT stock_33cl, stock_75cl, keg_liters, name FROM beers WHERE id=?', (beer_id,)).fetchone()
        if not cur:
            return api_error('not_found', 404)
        old_33  = cur['stock_33cl']  or 0
        old_75  = cur['stock_75cl']  or 0
        old_keg = cur['keg_liters']  or 0.0
        new_33  = d.get('stock_33cl',  old_33)
        new_75  = d.get('stock_75cl',  old_75)
        new_keg = d.get('keg_liters',  old_keg)
        conn.execute(
            'UPDATE beers SET stock_33cl=?, stock_75cl=?, keg_liters=? WHERE id=?',
            (new_33, new_75, new_keg, beer_id)
        )
        d33  = max(0, old_33  - new_33)
        d75  = max(0, old_75  - new_75)
        dkeg = max(0.0, round(old_keg - new_keg, 3))
        if d33 > 0 or d75 > 0 or dkeg > 0:
            today_local = date.today().isoformat()
            conn.execute(
                'INSERT INTO consumption_log (beer_id, beer_name, qty_33cl, qty_75cl, keg_liters, ts) VALUES (?,?,?,?,?,?)',
                (beer_id, cur['name'], d33, d75, dkeg, today_local)
            )
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        return jsonify(dict(row))


@bp.route('/api/consumption/depletion')
def get_consumption_depletion():
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    with get_db() as conn:
        rows = conn.execute('''
            SELECT
                c.beer_id,
                b.name  AS beer_name,
                ROUND(SUM(c.qty_33cl)*0.33 + SUM(c.qty_75cl)*0.75 + SUM(c.keg_liters), 3) AS consumed_liters,
                MIN(c.ts) AS first_log,
                CAST(julianday(MAX(c.ts)) - julianday(MIN(c.ts)) + 1 AS INTEGER) AS span_days,
                b.stock_33cl, b.stock_75cl, b.keg_liters AS keg_stock
            FROM consumption_log c
            JOIN beers b ON c.beer_id = b.id
            WHERE c.beer_id IS NOT NULL AND b.archived = 0
            GROUP BY c.beer_id
            HAVING consumed_liters > 0
        ''').fetchall()
    results = []
    for row in rows:
        current = (row['stock_33cl'] or 0)*0.33 + (row['stock_75cl'] or 0)*0.75 + (row['keg_stock'] or 0)
        if current <= 0:
            continue
        span = max(row['span_days'] or 1, 1)
        daily = row['consumed_liters'] / span
        if daily <= 0:
            continue
        days_rem = current / daily
        results.append({
            'beer_id':        row['beer_id'],
            'beer_name':      row['beer_name'],
            'current_liters': round(current, 2),
            'daily_rate':     round(daily, 3),
            'days_remaining': int(round(days_rem)),
            'depletion_date': (today + _td(days=int(days_rem))).isoformat(),
            'span_days':      span,
        })
    results.sort(key=lambda x: x['days_remaining'])
    return jsonify(results)


@bp.route('/api/consumption')
def get_consumption():
    with get_db() as conn:
        by_month = conn.execute('''
            SELECT strftime('%Y-%m', ts) as period,
                   SUM(qty_33cl)              as total_33cl,
                   SUM(qty_75cl)              as total_75cl,
                   ROUND(SUM(keg_liters), 2)  as total_keg
            FROM consumption_log
            GROUP BY period ORDER BY period
        ''').fetchall()
        by_beer = conn.execute('''
            SELECT beer_id, beer_name,
                   SUM(qty_33cl)                                                   as total_33cl,
                   SUM(qty_75cl)                                                   as total_75cl,
                   ROUND(SUM(keg_liters), 2)                                       as total_keg,
                   ROUND(SUM(qty_33cl)*0.33 + SUM(qty_75cl)*0.75 + SUM(keg_liters), 2) as total_liters
            FROM consumption_log
            GROUP BY beer_id
            ORDER BY total_liters DESC
            LIMIT 10
        ''').fetchall()
    return jsonify({'by_month': [dict(r) for r in by_month],
                    'by_beer':  [dict(r) for r in by_beer]})


@bp.route('/api/beers/<int:beer_id>', methods=['PATCH'])
def patch_beer(beer_id):
    d = request.json
    with get_db() as conn:
        cur = conn.execute('UPDATE beers SET archived=? WHERE id=?',
                           (1 if d.get('archived') else 0, beer_id))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        return jsonify(dict(row))
