from flask import Blueprint, jsonify, request
from db import get_db, _log_inv
from helpers import api_error, validate, VALID_UNITS

bp = Blueprint('shopping', __name__)

_VALID_CATS = frozenset({'malt', 'houblon', 'levure', 'autre'})


# ── Conversion d'unités ───────────────────────────────────────────────────────
def _to_base(qty, unit):
    """Convertit une quantité vers l'unité de base (g ou mL).
    Retourne (valeur_base, dimension) où dimension ∈ {'weight','volume','count'}."""
    if unit == 'kg':           return qty * 1000, 'weight'
    if unit == 'g':            return qty,         'weight'
    if unit == 'L':            return qty * 1000,  'volume'
    if unit in ('mL', 'ml'):   return qty,          'volume'
    return qty, 'count'                             # sachet, pièce, unité…

def _from_base(base_val, unit):
    """Reconvertit depuis la valeur de base vers l'unité cible."""
    if unit == 'kg':           return base_val / 1000
    if unit == 'g':            return base_val
    if unit == 'L':            return base_val / 1000
    if unit in ('mL', 'ml'):   return base_val
    return base_val

def _add_qty(inv_qty, inv_unit, add_qty, add_unit):
    """Additionne deux quantités en convertissant les unités si nécessaire.
    Retourne la nouvelle quantité exprimée dans inv_unit."""
    inv_base, inv_dim = _to_base(inv_qty, inv_unit)
    add_base, add_dim = _to_base(add_qty, add_unit)
    if inv_dim == add_dim:
        return _from_base(inv_base + add_base, inv_unit)
    # Dimensions incompatibles (ex. g + sachet) → addition brute sans conversion
    return inv_qty + add_qty

_SHOPPING_SCHEMA = {
    'name':     {'type': str,          'max_len': 200},
    'category': {'type': str,          'max_len': 20,  'allowed_values': _VALID_CATS},
    'unit':     {'type': str,          'max_len': 20,  'allowed_values': VALID_UNITS},
    'quantity': {'type': (int, float), 'min_val': 0},
    'notes':    {'type': str,          'max_len': 500},
}


@bp.route('/api/shopping-list', methods=['GET'])
def get_shopping_list():
    """Retourne uniquement les articles actifs (non encore achetés)."""
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT * FROM shopping_list WHERE bought_at IS NULL
               ORDER BY checked ASC, COALESCE(sort_order,9999) ASC, created_at ASC'''
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/shopping-list/history', methods=['GET'])
def get_shopping_history():
    """Retourne l'historique des articles achetés (soft-deleted), 100 derniers."""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM shopping_list WHERE bought_at IS NOT NULL ORDER BY bought_at DESC LIMIT 100'
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/shopping-list', methods=['POST'])
def create_shopping_item():
    d = request.json or {}
    if not d.get('name') or not d.get('category'):
        return api_error('missing_field', 400, detail='name and category are required')
    errors = validate(d, _SHOPPING_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        max_order = conn.execute(
            'SELECT COALESCE(MAX(sort_order),0) FROM shopping_list WHERE bought_at IS NULL'
        ).fetchone()[0]
        cur = conn.execute(
            '''INSERT INTO shopping_list (name, category, quantity, unit, notes, inventory_item_id, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (d['name'], d['category'],
             d.get('quantity', 1), d.get('unit', 'g'),
             d.get('notes') or None,
             d.get('inventory_item_id') or None,
             max_order + 1)
        )
        row = conn.execute('SELECT * FROM shopping_list WHERE id=?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@bp.route('/api/shopping-list/bulk-check', methods=['PUT'])
def bulk_check_shopping_items():
    """Coche ou décoche plusieurs articles en une seule requête."""
    d       = request.json or {}
    ids     = [int(x) for x in d.get('ids', []) if isinstance(x, (int, float))]
    checked = 1 if d.get('checked') else 0
    if not ids:
        return api_error('bad_request', 400, detail='ids required')
    with get_db() as conn:
        placeholders = ','.join('?' * len(ids))
        conn.execute(
            f'UPDATE shopping_list SET checked=?, updated_at=CURRENT_TIMESTAMP'
            f' WHERE id IN ({placeholders}) AND bought_at IS NULL',
            [checked, *ids]
        )
    return jsonify({'ok': True, 'updated': len(ids)})


@bp.route('/api/shopping-list/reorder', methods=['PUT'])
def reorder_shopping_list():
    items = request.json or []
    if not isinstance(items, list):
        return api_error('bad_request', 400)
    with get_db() as conn:
        for it in items:
            if not isinstance(it.get('id'), int) or not isinstance(it.get('sort_order'), int):
                continue
            conn.execute('UPDATE shopping_list SET sort_order=? WHERE id=?', (it['sort_order'], it['id']))
    return jsonify({'ok': True})


@bp.route('/api/shopping-list/buy', methods=['POST'])
def buy_shopping_items():
    """Marque les articles cochés comme achetés (soft-delete via bought_at) et met à jour l'inventaire.

    Retourne un token d'annulation contenant les IDs et les changements d'inventaire
    pour permettre un undo côté client dans les 8 secondes.
    """
    with get_db() as conn:
        checked = conn.execute(
            'SELECT * FROM shopping_list WHERE checked=1 AND bought_at IS NULL'
        ).fetchall()
        bought_ids  = []
        inv_changes = []

        for item in checked:
            inv_id = item['inventory_item_id']
            inv    = None
            if inv_id:
                inv = conn.execute(
                    'SELECT * FROM inventory_items WHERE id=? AND deleted_at IS NULL', (inv_id,)
                ).fetchone()

            if inv:
                old_qty = inv['quantity']
                new_qty = _add_qty(old_qty, inv['unit'], item['quantity'], item['unit'])
                # delta exprimé dans l'unité de l'inventaire pour que undo-buy
                # puisse soustraire sans avoir à re-convertir
                delta_inv = new_qty - old_qty
                conn.execute(
                    'UPDATE inventory_items SET quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                    (new_qty, inv['id'])
                )
                _log_inv(inv['id'], delta_inv, old_qty, new_qty, 'shopping', conn=conn)
                inv_changes.append({'id': inv['id'], 'delta': delta_inv, 'was_created': False})
            else:
                cur2 = conn.execute(
                    '''INSERT INTO inventory_items (name, category, quantity, unit, notes)
                       VALUES (?, ?, ?, ?, ?)''',
                    (item['name'], item['category'], item['quantity'], item['unit'], item['notes'])
                )
                new_inv_id = cur2.lastrowid
                if item['quantity'] > 0:
                    _log_inv(new_inv_id, item['quantity'], 0.0, item['quantity'], 'shopping', conn=conn)
                inv_changes.append({'id': new_inv_id, 'delta': item['quantity'], 'was_created': True})

            # Soft-delete : marquer comme acheté plutôt que supprimer
            conn.execute(
                'UPDATE shopping_list SET bought_at=CURRENT_TIMESTAMP, checked=0 WHERE id=?',
                (item['id'],)
            )
            bought_ids.append(item['id'])

        return jsonify({
            'ok':         True,
            'count':      len(bought_ids),
            'bought_ids': bought_ids,
            'inv_changes': inv_changes,
        })


@bp.route('/api/shopping-list/undo-buy', methods=['POST'])
def undo_buy():
    """Annule un achat récent : restaure les articles dans la liste active et inverse les changements d'inventaire."""
    d          = request.json or {}
    bought_ids = [int(x) for x in d.get('bought_ids', []) if isinstance(x, (int, float))]
    inv_changes = d.get('inv_changes', [])

    if not bought_ids:
        return api_error('bad_request', 400, detail='bought_ids required')

    with get_db() as conn:
        placeholders = ','.join('?' * len(bought_ids))
        conn.execute(
            f'UPDATE shopping_list SET bought_at=NULL, checked=0 WHERE id IN ({placeholders})',
            bought_ids
        )

        for change in inv_changes:
            inv_id      = change.get('id')
            delta       = change.get('delta', 0)
            was_created = change.get('was_created', False)
            if not isinstance(inv_id, int) or inv_id <= 0:
                continue
            if was_created:
                conn.execute(
                    'UPDATE inventory_items SET deleted_at=CURRENT_TIMESTAMP WHERE id=?', (inv_id,)
                )
            else:
                inv = conn.execute(
                    'SELECT * FROM inventory_items WHERE id=? AND deleted_at IS NULL', (inv_id,)
                ).fetchone()
                if inv:
                    old_qty = inv['quantity']
                    new_qty = max(0.0, old_qty - delta)
                    conn.execute(
                        'UPDATE inventory_items SET quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                        (new_qty, inv_id)
                    )
                    _log_inv(inv_id, -delta, old_qty, new_qty, 'undo_shopping', conn=conn)

        return jsonify({'ok': True, 'restored': len(bought_ids)})


@bp.route('/api/shopping-list/<int:item_id>', methods=['PUT'])
def update_shopping_item(item_id):
    d = request.json or {}
    partial = {k: v for k, v in d.items() if k in _SHOPPING_SCHEMA}
    errors  = validate(partial, _SHOPPING_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        item = conn.execute('SELECT * FROM shopping_list WHERE id=?', (item_id,)).fetchone()
        if not item:
            return api_error('not_found', 404)
        conn.execute(
            '''UPDATE shopping_list
               SET name=?, category=?, quantity=?, unit=?, notes=?,
                   inventory_item_id=?, checked=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (d.get('name',             item['name']),
             d.get('category',         item['category']),
             d.get('quantity',         item['quantity']),
             d.get('unit',             item['unit']),
             d.get('notes',            item['notes']),
             d.get('inventory_item_id',item['inventory_item_id']),
             int(d['checked']) if 'checked' in d else item['checked'],
             item_id)
        )
        row = conn.execute('SELECT * FROM shopping_list WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row))


@bp.route('/api/shopping-list/<int:item_id>', methods=['DELETE'])
def delete_shopping_item(item_id):
    with get_db() as conn:
        conn.execute('DELETE FROM shopping_list WHERE id=?', (item_id,))
        return jsonify({'ok': True})
