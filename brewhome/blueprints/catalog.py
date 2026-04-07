import json
import urllib.request
from flask import Blueprint, jsonify, request
from db import get_db
from helpers import validate, api_error

bp = Blueprint('catalog', __name__)

_CATALOG_SCHEMA = {
    'name':             {'type': str,          'max_len': 200},
    'subcategory':      {'type': str,          'max_len': 100},
    'default_unit':     {'type': str,          'max_len': 20},
    'aroma_spec':       {'type': str,          'max_len': 1000},
    'ebc':              {'type': (int, float), 'min_val': 0,   'max_val': 100000},
    'gu':               {'type': (int, float), 'min_val': 0,   'max_val': 400},
    'alpha':            {'type': (int, float), 'min_val': 0,   'max_val': 100},
    'temp_min':         {'type': (int, float), 'min_val': -10, 'max_val': 50},
    'temp_max':         {'type': (int, float), 'min_val': -10, 'max_val': 50},
    'dosage_per_liter': {'type': (int, float), 'min_val': 0,   'max_val': 100},
    'attenuation_min':  {'type': (int, float), 'min_val': 0,   'max_val': 100},
    'attenuation_max':  {'type': (int, float), 'min_val': 0,   'max_val': 100},
    'alcohol_tolerance':{'type': (int, float), 'min_val': 0,   'max_val': 25},
    'max_usage_pct':    {'type': (int, float), 'min_val': 0,   'max_val': 100},
}


@bp.route('/api/catalog')
def get_catalog():
    cat = request.args.get('category')
    q   = request.args.get('q', '').strip()
    with get_db() as conn:
        sql  = 'SELECT * FROM ingredient_catalog WHERE 1=1'
        args = []
        if cat:
            sql += ' AND category=?'; args.append(cat)
        if q:
            sql += ' AND name LIKE ?'; args.append(f'%{q}%')
        sql += ' ORDER BY subcategory, name'
        rows = conn.execute(sql, args).fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/catalog', methods=['POST'])
def create_catalog_item():
    d = request.json or {}
    if not d.get('name') or not d.get('category'):
        return api_error('missing_field', 400, detail='name and category are required')
    errors = validate(d, _CATALOG_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO ingredient_catalog
               (name,category,subcategory,ebc,gu,alpha,yeast_type,default_unit,
                temp_min,temp_max,dosage_per_liter,attenuation_min,attenuation_max,alcohol_tolerance,max_usage_pct,aroma_spec)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('name'), d.get('category'), d.get('subcategory'), d.get('ebc'), d.get('gu'),
             d.get('alpha'), d.get('yeast_type'), d.get('default_unit', 'g'),
             d.get('temp_min'), d.get('temp_max'), d.get('dosage_per_liter'),
             d.get('attenuation_min'), d.get('attenuation_max'), d.get('alcohol_tolerance'),
             d.get('max_usage_pct'), d.get('aroma_spec'))
        )
        row = conn.execute('SELECT * FROM ingredient_catalog WHERE id=?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@bp.route('/api/catalog/<int:item_id>', methods=['PUT'])
def update_catalog_item(item_id):
    d = request.json or {}
    errors = validate(d, _CATALOG_SCHEMA)
    if errors:
        return api_error('validation', 400, fields=errors)
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE ingredient_catalog
               SET name=?, subcategory=?, ebc=?, gu=?, alpha=?, yeast_type=?, default_unit=?,
                   temp_min=?, temp_max=?, dosage_per_liter=?,
                   attenuation_min=?, attenuation_max=?, alcohol_tolerance=?,
                   max_usage_pct=?, aroma_spec=?
               WHERE id=?''',
            (d.get('name'), d.get('subcategory'), d.get('ebc'), d.get('gu'), d.get('alpha'),
             d.get('yeast_type'), d.get('default_unit', 'g'),
             d.get('temp_min'), d.get('temp_max'), d.get('dosage_per_liter'),
             d.get('attenuation_min'), d.get('attenuation_max'), d.get('alcohol_tolerance'),
             d.get('max_usage_pct'), d.get('aroma_spec'), item_id)
        )
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        row = conn.execute('SELECT * FROM ingredient_catalog WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row))


@bp.route('/api/catalog/<int:item_id>', methods=['DELETE'])
def delete_catalog_item(item_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM ingredient_catalog WHERE id=?', (item_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


@bp.route('/api/catalog/import-hopsteiner', methods=['POST'])
def import_hopsteiner():
    """Importe les houblons depuis la base Hopsteiner (GitHub kasperg3/HopDatabase)."""
    url = 'https://raw.githubusercontent.com/kasperg3/HopDatabase/refs/heads/main/hop_database/data/hopsteiner_raw_data.json'
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return api_error('upstream_error', 502)

    hops = data.get('hops', data) if isinstance(data, dict) else data

    def _avg_alpha(low, high):
        try:
            vals = [float(v) for v in [low, high] if v is not None]
            return round(sum(vals) / len(vals), 1) if vals else None
        except (ValueError, TypeError):
            return None

    imported = updated = 0
    with get_db() as conn:
        for h in hops:
            if not isinstance(h, dict):
                continue
            name = (h.get('name') or '').strip()
            if not name:
                continue
            alpha    = _avg_alpha(h.get('acid_alpha_low'), h.get('acid_alpha_high'))
            aroma    = (h.get('aroma_spec') or '').strip() or None
            existing = conn.execute(
                'SELECT id, alpha FROM ingredient_catalog WHERE name=? AND category=?',
                (name, 'houblon')
            ).fetchone()
            if existing:
                conn.execute(
                    'UPDATE ingredient_catalog SET aroma_spec=?, alpha=COALESCE(alpha,?) WHERE id=?',
                    (aroma, alpha, existing['id'])
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO ingredient_catalog (name,category,alpha,aroma_spec,default_unit) VALUES (?,?,?,?,'g')",
                    (name, 'houblon', alpha, aroma)
                )
                imported += 1
    return jsonify({'imported': imported, 'updated': updated})
