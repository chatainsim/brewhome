import json
from collections import defaultdict
from flask import Blueprint, jsonify, request
from db import get_db, _log
from helpers import validate, api_error

bp = Blueprint('recipes', __name__)

_RECIPE_SCHEMA = {
    'name':                 {'type': str,          'max_len': 200},
    'style':                {'type': str,          'max_len': 100},
    'notes':                {'type': str,          'max_len': 10000},
    'volume':               {'type': (int, float), 'min_val': 0.1,  'max_val': 10000},
    'mash_temp':            {'type': (int, float), 'min_val': 30,   'max_val': 85},
    'mash_time':            {'type': (int, float), 'min_val': 0,    'max_val': 500},
    'boil_time':            {'type': (int, float), 'min_val': 0,    'max_val': 500},
    'mash_ratio':           {'type': (int, float), 'min_val': 0.5,  'max_val': 10},
    'evap_rate':            {'type': (int, float), 'min_val': 0,    'max_val': 50},
    'grain_absorption':     {'type': (int, float), 'min_val': 0,    'max_val': 5},
    'brewhouse_efficiency': {'type': (int, float), 'min_val': 5,    'max_val': 100},
    'ferm_temp':            {'type': (int, float), 'min_val': 0,    'max_val': 50},
    'ferm_time':            {'type': (int, float), 'min_val': 0,    'max_val': 730},
    'rating':               {'type': int,          'min_val': 1,    'max_val': 5},
}


def _save_recipe_snapshot(conn, recipe_id, keep=20):
    """Sauvegarde un snapshot JSON de la recette courante dans recipe_history."""
    old = _recipe_with_ingredients(conn, recipe_id)
    if not old:
        return
    conn.execute(
        'INSERT INTO recipe_history (recipe_id, snapshot) VALUES (?, ?)',
        (recipe_id, json.dumps(old))
    )
    conn.execute(
        '''DELETE FROM recipe_history WHERE recipe_id=? AND id NOT IN (
               SELECT id FROM recipe_history WHERE recipe_id=? ORDER BY id DESC LIMIT ?
           )''',
        (recipe_id, recipe_id, keep)
    )


def _apply_recipe_data(conn, recipe_id, d):
    """Applique un dict recette (PUT ou restore) sur recipes + recipe_ingredients."""
    conn.execute(
        '''UPDATE recipes SET batch_no=?,name=?,style=?,volume=?,brew_date=?,bottling_date=?,
           mash_temp=?,mash_time=?,boil_time=?,mash_ratio=?,evap_rate=?,grain_absorption=?,
           brewhouse_efficiency=?,ferm_temp=?,ferm_time=?,ferm_profile=?,notes=?,rating=?,draft_id=?
           WHERE id=?''',
        (d.get('batch_no'), d.get('name'), d.get('style'), d.get('volume', 20),
         d.get('brew_date'), d.get('bottling_date'), d.get('mash_temp', 66),
         d.get('mash_time', 60), d.get('boil_time', 60), d.get('mash_ratio', 3.0),
         d.get('evap_rate', 3.0), d.get('grain_absorption', 0.8),
         d.get('brewhouse_efficiency', 72),
         d.get('ferm_temp', 20), d.get('ferm_time', 14), d.get('ferm_profile'),
         d.get('notes'), d.get('rating'), d.get('draft_id'), recipe_id)
    )
    conn.execute('DELETE FROM recipe_ingredients WHERE recipe_id=?', (recipe_id,))
    for ing in d.get('ingredients', []):
        conn.execute(
            '''INSERT INTO recipe_ingredients
               (recipe_id,inventory_item_id,name,category,quantity,unit,
                hop_time,hop_type,hop_days,other_type,other_time,ebc,alpha,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (recipe_id, ing.get('inventory_item_id'), ing.get('name'), ing.get('category'),
             ing.get('quantity'), ing.get('unit', 'g'), ing.get('hop_time'),
             ing.get('hop_type'), ing.get('hop_days'),
             ing.get('other_type'), ing.get('other_time'),
             ing.get('ebc'), ing.get('alpha'), ing.get('notes'))
        )


def _recipe_with_ingredients(conn, recipe_id):
    r = conn.execute('SELECT * FROM recipes WHERE id=?', (recipe_id,)).fetchone()
    if not r:
        return None
    result = dict(r)
    ings = conn.execute(
        '''SELECT ri.*, ii.quantity as stock_qty, ii.unit as stock_unit
           FROM recipe_ingredients ri
           LEFT JOIN inventory_items ii ON ri.inventory_item_id = ii.id
           WHERE ri.recipe_id=?
           ORDER BY ri.category, ri.id''',
        (recipe_id,)
    ).fetchall()
    result['ingredients'] = [dict(i) for i in ings]
    return result


@bp.route('/api/recipes', methods=['GET'])
def get_recipes():
    with get_db() as conn:
        recipes = conn.execute(
            'SELECT * FROM recipes WHERE deleted_at IS NULL ORDER BY COALESCE(sort_order, 9999) ASC, created_at DESC'
        ).fetchall()
        if not recipes:
            return jsonify([])
        ids = [r['id'] for r in recipes]
        placeholders = ','.join('?' * len(ids))
        ings = conn.execute(
            f'''SELECT ri.*, ii.quantity as stock_qty, ii.unit as stock_unit
                FROM recipe_ingredients ri
                LEFT JOIN inventory_items ii ON ri.inventory_item_id = ii.id
                WHERE ri.recipe_id IN ({placeholders})
                ORDER BY ri.recipe_id, ri.category, ri.id''',
            ids
        ).fetchall()
        ings_by_recipe = defaultdict(list)
        for ing in ings:
            ings_by_recipe[ing['recipe_id']].append(dict(ing))
        return jsonify([
            {**dict(r), 'ingredients': ings_by_recipe[r['id']]}
            for r in recipes
        ])


@bp.route('/api/recipes/reorder', methods=['PUT'])
def reorder_recipes():
    items = request.json or []
    if any(not isinstance(it.get('sort_order'), int) or isinstance(it.get('sort_order'), bool) or it.get('sort_order') < 0
           for it in items if it.get('id') is not None):
        return api_error('validation', 400, detail='sort_order must be a non-negative integer')
    valid = [(it['sort_order'], it['id']) for it in items
             if it.get('id') is not None and it.get('sort_order') is not None]
    with get_db() as conn:
        conn.executemany('UPDATE recipes SET sort_order=? WHERE id=?', valid)
    return jsonify({'success': True})


@bp.route('/api/recipes', methods=['POST'])
def create_recipe():
    d = request.json or {}
    if not d.get('name'):
        return api_error('missing_field', 400, detail='name is required')
    errors = validate(d, _RECIPE_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        if request.args.get('force') != '1':
            dup = conn.execute(
                'SELECT id, name FROM recipes WHERE name=? AND deleted_at IS NULL', (d['name'],)
            ).fetchone()
            if dup:
                return api_error('duplicate', 409, name=dup['name'], id=dup['id'])
        cur = conn.execute(
            '''INSERT INTO recipes
               (batch_no,name,style,volume,brew_date,bottling_date,mash_temp,mash_time,
                boil_time,mash_ratio,evap_rate,grain_absorption,brewhouse_efficiency,
                ferm_temp,ferm_time,notes,rating,draft_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('batch_no'), d.get('name'), d.get('style'), d.get('volume', 20),
             d.get('brew_date'), d.get('bottling_date'), d.get('mash_temp', 66),
             d.get('mash_time', 60), d.get('boil_time', 60), d.get('mash_ratio', 3.0),
             d.get('evap_rate', 3.0), d.get('grain_absorption', 0.8),
             d.get('brewhouse_efficiency', 72),
             d.get('ferm_temp', 20), d.get('ferm_time', 14), d.get('notes'),
             d.get('rating'), d.get('draft_id'))
        )
        recipe_id = cur.lastrowid
        for ing in d.get('ingredients', []):
            conn.execute(
                '''INSERT INTO recipe_ingredients
                   (recipe_id,inventory_item_id,name,category,quantity,unit,
                    hop_time,hop_type,hop_days,other_type,other_time,ebc,alpha,notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (recipe_id, ing.get('inventory_item_id'), ing.get('name'), ing.get('category'),
                 ing.get('quantity'), ing.get('unit', 'g'), ing.get('hop_time'),
                 ing.get('hop_type'), ing.get('hop_days'),
                 ing.get('other_type'), ing.get('other_time'),
                 ing.get('ebc'), ing.get('alpha'), ing.get('notes'))
            )
        _log('recipe', 'created', json.dumps({'_i18n':'act.recipe_created','name':d.get('name','')}), recipe_id, conn)
        return jsonify(_recipe_with_ingredients(conn, recipe_id)), 201


@bp.route('/api/recipes/<int:recipe_id>', methods=['GET'])
def get_recipe(recipe_id):
    with get_db() as conn:
        result = _recipe_with_ingredients(conn, recipe_id)
        if not result:
            return api_error('not_found', 404)
        return jsonify(result)


@bp.route('/api/recipes/<int:recipe_id>', methods=['PUT'])
def update_recipe(recipe_id):
    d = request.json or {}
    errors = validate(d, _RECIPE_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        if not conn.execute('SELECT 1 FROM recipes WHERE id=?', (recipe_id,)).fetchone():
            return api_error('not_found', 404)
        _save_recipe_snapshot(conn, recipe_id)
        _apply_recipe_data(conn, recipe_id, d)
        result = _recipe_with_ingredients(conn, recipe_id)
        _log('recipe', 'updated', json.dumps({'_i18n':'act.recipe_updated','name':result['name']}), recipe_id, conn)
        return jsonify(result)


@bp.route('/api/recipes/<int:recipe_id>/history', methods=['GET'])
def get_recipe_history(recipe_id):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT id, saved_at, snapshot FROM recipe_history WHERE recipe_id=? ORDER BY id DESC',
            (recipe_id,)
        ).fetchall()
        result = []
        for row in rows:
            try:
                snap = json.loads(row['snapshot'])
            except (json.JSONDecodeError, TypeError):
                snap = {}
            result.append({
                'id':           row['id'],
                'saved_at':     row['saved_at'],
                'name':         snap.get('name', '?'),
                'style':        snap.get('style'),
                'volume':       snap.get('volume'),
                'n_ingredients': len(snap.get('ingredients', [])),
            })
        return jsonify(result)


@bp.route('/api/recipes/<int:recipe_id>/history/<int:version_id>/restore', methods=['POST'])
def restore_recipe_version(recipe_id, version_id):
    with get_db() as conn:
        row = conn.execute(
            'SELECT snapshot FROM recipe_history WHERE id=? AND recipe_id=?',
            (version_id, recipe_id)
        ).fetchone()
        if not row:
            return api_error('not_found', 404)
        try:
            snap = json.loads(row['snapshot'])
        except (json.JSONDecodeError, TypeError):
            return api_error('invalid_snapshot', 422, detail='snapshot data is corrupted')
        _save_recipe_snapshot(conn, recipe_id)
        _apply_recipe_data(conn, recipe_id, snap)
        result = _recipe_with_ingredients(conn, recipe_id)
        _log('recipe', 'restored', json.dumps({'_i18n':'act.recipe_updated','name':result['name']}), recipe_id, conn)
        return jsonify(result)


@bp.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
def delete_recipe(recipe_id):
    with get_db() as conn:
        row = conn.execute('SELECT name FROM recipes WHERE id=?', (recipe_id,)).fetchone()
        cur = conn.execute(
            'UPDATE recipes SET archived=1, deleted_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL',
            (recipe_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        if row:
            _log('recipe', 'deleted', json.dumps({'_i18n':'act.recipe_deleted','name':row['name']}), recipe_id, conn)
        return jsonify({'success': True})


@bp.route('/api/recipes/<int:recipe_id>/restore', methods=['POST'])
def restore_recipe(recipe_id):
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE recipes SET archived=0, deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL',
            (recipe_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/recipes/<int:recipe_id>/purge', methods=['DELETE'])
def purge_recipe(recipe_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM recipes WHERE id=? AND deleted_at IS NOT NULL', (recipe_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/recipes/<int:recipe_id>', methods=['PATCH'])
def patch_recipe(recipe_id):
    d = request.json
    with get_db() as conn:
        if 'archived' in d:
            conn.execute('UPDATE recipes SET archived=? WHERE id=?',
                         (1 if d['archived'] else 0, recipe_id))
        if 'rating' in d:
            conn.execute('UPDATE recipes SET rating=? WHERE id=?',
                         (d['rating'], recipe_id))
        row = conn.execute('SELECT id,name,archived,rating FROM recipes WHERE id=?', (recipe_id,)).fetchone()
        if not row:
            return api_error('not_found', 404)
        return jsonify(dict(row))
