from flask import Blueprint, jsonify, request, current_app
from db import get_db, _log_inv
from helpers import validate, api_error

bp = Blueprint('inventory', __name__)

_INVENTORY_SCHEMA = {
    'name':             {'type': str,          'max_len': 200},
    'category':         {'type': str,          'max_len': 50},
    'unit':             {'type': str,          'max_len': 20},
    'origin':           {'type': str,          'max_len': 200},
    'notes':            {'type': str,          'max_len': 2000},
    'quantity':         {'type': (int, float), 'min_val': 0},
    'ebc':              {'type': (int, float), 'min_val': 0,  'max_val': 100000},
    'alpha':            {'type': (int, float), 'min_val': 0,  'max_val': 100},
    'price_per_unit':   {'type': (int, float), 'min_val': 0},
    'min_stock':        {'type': (int, float), 'min_val': 0},
    'yeast_generation': {'type': int,          'min_val': 1,  'max_val': 10},
}


@bp.route('/api/inventory', methods=['GET'])
def get_inventory():
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM inventory_items WHERE deleted_at IS NULL ORDER BY COALESCE(sort_order, 9999) ASC, category, name'
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/inventory', methods=['POST'])
def create_inventory_item():
    d = request.json or {}
    if not d.get('name') or not d.get('category'):
        return api_error('missing_field', 400, detail='name and category are required')
    errors = validate(d, _INVENTORY_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        if request.args.get('force') != '1':
            dup = conn.execute(
                'SELECT id, name FROM inventory_items WHERE name=? AND category=? AND deleted_at IS NULL',
                (d['name'], d['category'])
            ).fetchone()
            if dup:
                return api_error('duplicate', 409, name=dup['name'], id=dup['id'])
        initial_qty = d.get('quantity', 0) or 0
        cur = conn.execute(
            'INSERT INTO inventory_items (name,category,quantity,unit,origin,ebc,alpha,notes,price_per_unit,yeast_type,yeast_mfg_date,yeast_open_date,yeast_generation) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (d.get('name'), d.get('category'), initial_qty, d.get('unit', 'kg'),
             d.get('origin'), d.get('ebc'), d.get('alpha'), d.get('notes'),
             d.get('price_per_unit'),
             d.get('yeast_type'), d.get('yeast_mfg_date') or None, d.get('yeast_open_date') or None,
             d.get('yeast_generation') or 1)
        )
        item_id = cur.lastrowid
        if initial_qty > 0:
            _log_inv(item_id, initial_qty, 0.0, initial_qty, 'created', conn=conn)
        row = conn.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row)), 201


@bp.route('/api/inventory/<int:item_id>', methods=['PUT'])
def update_inventory_item(item_id):
    d = request.json or {}
    errors = validate(d, _INVENTORY_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        old_row = conn.execute('SELECT quantity FROM inventory_items WHERE id=?', (item_id,)).fetchone()
        if not old_row:
            return api_error('not_found', 404)
        old_qty = old_row['quantity']
        new_qty = d.get('quantity')
        cur = conn.execute(
            '''UPDATE inventory_items
               SET name=?,category=?,quantity=?,unit=?,origin=?,ebc=?,alpha=?,notes=?,
                   price_per_unit=?,min_stock=?,expiry_date=?,
                   yeast_type=?,yeast_mfg_date=?,yeast_open_date=?,yeast_generation=?,
                   updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (d.get('name'), d.get('category'), new_qty, d.get('unit', 'kg'),
             d.get('origin'), d.get('ebc'), d.get('alpha'), d.get('notes'),
             d.get('price_per_unit'), d.get('min_stock'), d.get('expiry_date') or None,
             d.get('yeast_type'), d.get('yeast_mfg_date') or None, d.get('yeast_open_date') or None,
             d.get('yeast_generation') or 1, item_id)
        )
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        if new_qty is not None and old_qty != new_qty:
            _log_inv(item_id, new_qty - old_qty, old_qty, new_qty, 'full_edit', conn=conn)
        row = conn.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row))


@bp.route('/api/inventory/reorder', methods=['PUT'])
def reorder_inventory():
    items = request.json or []
    if any(not isinstance(it.get('sort_order'), int) or isinstance(it.get('sort_order'), bool) or it.get('sort_order') < 0
           for it in items if it.get('id') is not None):
        return api_error('validation', 400, detail='sort_order must be a non-negative integer')
    valid = [(it['sort_order'], it['id']) for it in items
             if it.get('id') is not None and it.get('sort_order') is not None]
    with get_db() as conn:
        conn.executemany('UPDATE inventory_items SET sort_order=? WHERE id=?', valid)
    return jsonify({'success': True})


@bp.route('/api/inventory/<int:item_id>', methods=['DELETE'])
def delete_inventory_item(item_id):
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE inventory_items SET archived=1, deleted_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL',
            (item_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/inventory/<int:item_id>/restore', methods=['POST'])
def restore_inventory_item(item_id):
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE inventory_items SET archived=0, deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL',
            (item_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/inventory/<int:item_id>/purge', methods=['DELETE'])
def purge_inventory_item(item_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM inventory_items WHERE id=? AND deleted_at IS NOT NULL', (item_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/inventory/<int:item_id>/qty', methods=['PATCH'])
def patch_inventory_qty(item_id):
    d = request.json or {}
    new_qty = d.get('quantity')
    if new_qty is None:
        return api_error('missing_field', 400, detail='quantity is required')
    if not isinstance(new_qty, (int, float)) or isinstance(new_qty, bool) or new_qty < 0:
        return api_error('validation', 400, fields={'quantity': 'must be a non-negative number'})
    with get_db() as conn:
        old_row = conn.execute(
            'SELECT quantity, min_stock, name, unit FROM inventory_items WHERE id=?', (item_id,)
        ).fetchone()
        if not old_row:
            return api_error('not_found', 404)
        old_qty = old_row['quantity']
        min_stock = old_row['min_stock']
        conn.execute(
            'UPDATE inventory_items SET quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (new_qty, item_id)
        )
        _log_inv(item_id, new_qty - old_qty, old_qty, new_qty, 'manual_update', conn=conn)
        row = conn.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
        item = dict(row)
    # Fire low-stock alert if threshold just crossed (old >= threshold > new)
    if min_stock is not None and new_qty is not None:
        if old_qty >= min_stock > new_qty:
            try:
                from blueprints.integrations import _tg_fire_low_stock
                _tg_fire_low_stock(item['name'], new_qty, item['unit'], min_stock)
            except Exception as e:
                current_app.logger.warning('tg low_stock notification failed: %s', e)
    return jsonify(item)


@bp.route('/api/inventory/<int:item_id>', methods=['PATCH'])
def patch_inventory_item(item_id):
    d = request.json
    with get_db() as conn:
        cur = conn.execute('UPDATE inventory_items SET archived=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                           (1 if d.get('archived') else 0, item_id))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        row = conn.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row))


@bp.route('/api/inventory/<int:item_id>/history', methods=['GET'])
def get_inventory_history(item_id):
    limit = min(max(1, int(request.args.get('limit', 100))), 500)
    with get_db() as conn:
        item = conn.execute(
            'SELECT name, unit FROM inventory_items WHERE id=?', (item_id,)
        ).fetchone()
        if not item:
            return api_error('not_found', 404)
        rows = conn.execute(
            '''SELECT il.*, b.name AS brew_name
               FROM inventory_log il
               LEFT JOIN brews b ON il.entity_type='brew' AND il.entity_id=b.id
               WHERE il.inventory_item_id=?
               ORDER BY il.ts DESC LIMIT ?''',
            (item_id, limit)
        ).fetchall()
    return jsonify({
        'item_name': item['name'],
        'item_unit': item['unit'],
        'entries':   [dict(r) for r in rows],
    })
