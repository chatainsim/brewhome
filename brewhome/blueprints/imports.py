import json
import os
import secrets
import xml.etree.ElementTree as ET
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, current_app
from db import get_db, get_readings_db, PHOTOS_DIR
from helpers import _to_kg, api_error
from constants import BrewStatus

bp = Blueprint('imports', __name__)


def _purge_brew_photos(conn):
    """Supprime toutes les photos du disque puis les lignes en base."""
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
# Catalog export / import
# ---------------------------------------------------------------------------

@bp.route('/api/export/catalog')
def export_catalog():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM ingredient_catalog ORDER BY category, subcategory, name').fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/import/catalog', methods=['POST'])
def import_catalog():
    body = request.json or {}
    if isinstance(body, list):
        items, mode = body, 'merge'
    else:
        items, mode = body.get('items', []), body.get('mode', 'merge')
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
                    '''UPDATE ingredient_catalog
                       SET subcategory=?, ebc=?, gu=?, alpha=?, yeast_type=?, default_unit=?,
                           temp_min=?, temp_max=?, dosage_per_liter=?,
                           attenuation_min=?, attenuation_max=?, alcohol_tolerance=?, max_usage_pct=?
                       WHERE id=?''',
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
    return jsonify({'imported': imported})


# ---------------------------------------------------------------------------
# Inventory export / import
# ---------------------------------------------------------------------------

@bp.route('/api/export/inventory')
def export_inventory():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM inventory_items ORDER BY category, name').fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/import/inventory', methods=['POST'])
def import_inventory():
    body = request.json or {}
    if isinstance(body, list):
        items, mode = body, 'merge'
    else:
        items, mode = body.get('items', []), body.get('mode', 'merge')
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
                        '''UPDATE inventory_items SET quantity=?,unit=?,origin=?,ebc=?,alpha=?,notes=?
                           WHERE id=?''',
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
                current_app.logger.warning(f"import_inventory: skipped item {item.get('name')!r}: {e}")
    return jsonify({'imported': imported})


# ---------------------------------------------------------------------------
# Recipes export / import
# ---------------------------------------------------------------------------

@bp.route('/api/export/recipes')
def export_recipes():
    with get_db() as conn:
        recipes = conn.execute('SELECT * FROM recipes ORDER BY id').fetchall()
        ings_rows = conn.execute(
            'SELECT * FROM recipe_ingredients ORDER BY recipe_id, id'
        ).fetchall()
    ings_by_recipe: dict = {}
    for i in ings_rows:
        ings_by_recipe.setdefault(i['recipe_id'], []).append(dict(i))
    result = []
    for r in recipes:
        recipe = dict(r)
        recipe['ingredients'] = ings_by_recipe.get(r['id'], [])
        result.append(recipe)
    return jsonify(result)


@bp.route('/api/import/recipes', methods=['POST'])
def import_recipes():
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
            conn.execute('DELETE FROM recipe_ingredients')
            conn.execute('DELETE FROM recipes')
        for recipe in data:
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
                        (rid, ing.get('name', '?'), ing.get('category', 'autre'),
                         ing.get('quantity', 0), ing.get('unit', 'g'),
                         ing.get('hop_time'), ing.get('hop_type'), ing.get('hop_days'),
                         ing.get('other_type'), ing.get('other_time'),
                         ing.get('ebc'), ing.get('alpha'), ing.get('notes'))
                    )
                imported += 1
            except Exception as e:
                current_app.logger.warning(f"import_recipes: skipped recipe {recipe.get('name')!r}: {e}")
    return jsonify({'imported': imported})


# ---------------------------------------------------------------------------
# BeerXML helpers
# ---------------------------------------------------------------------------

def _beerxml_to_recipe(rx):
    """Convert a BeerXML <RECIPE> Element to a recipe dict + ingredients list."""
    def _f(tag, default=None):
        el = rx.find(tag)
        return el.text.strip() if el is not None and el.text else default
    def _float(tag, default=0.0):
        try: return float(_f(tag, default))
        except (ValueError, TypeError): return float(default)
    def _int(tag, default=0):
        try: return int(float(_f(tag, default)))
        except (ValueError, TypeError): return int(default)

    name = _f('NAME', 'BeerXML Recipe')
    style_el = rx.find('STYLE/NAME')
    style = style_el.text.strip() if style_el is not None and style_el.text else None
    volume = _float('BATCH_SIZE', 20)
    boil_time = _int('BOIL_TIME', 60)
    efficiency = _float('EFFICIENCY', 72)
    mash_temp = 66.0
    mash_time = 60
    mash_step = rx.find('MASH/MASH_STEPS/MASH_STEP')
    if mash_step is not None:
        st = mash_step.find('STEP_TEMP')
        sm = mash_step.find('STEP_TIME')
        if st is not None and st.text:
            mash_temp = float(st.text)
        if sm is not None and sm.text:
            mash_time = int(float(sm.text))
    ferm_temp = None
    ferm_time = None
    pt = rx.find('PRIMARY_TEMP')
    pa = rx.find('PRIMARY_AGE')
    if pt is not None and pt.text:
        ferm_temp = float(pt.text)
    if pa is not None and pa.text:
        ferm_time = int(float(pa.text))
    notes_el = rx.find('NOTES')
    notes = notes_el.text.strip() if notes_el is not None and notes_el.text else None

    ingredients = []
    for fe in rx.findall('FERMENTABLES/FERMENTABLE'):
        def _fe(t, d=None, _fe=fe): el = _fe.find(t); return el.text.strip() if el is not None and el.text else d
        kg = float(_fe('AMOUNT') or 0)
        srm = float(_fe('COLOR') or 0)
        ebc = round(srm * 1.97, 1) if srm else None
        ingredients.append({
            'name': _fe('NAME', '?'), 'category': 'malt',
            'quantity': round(kg * 1000, 1), 'unit': 'g', 'ebc': ebc
        })
    for ho in rx.findall('HOPS/HOP'):
        def _ho(t, d=None, _ho=ho): el = _ho.find(t); return el.text.strip() if el is not None and el.text else d
        kg = float(_ho('AMOUNT') or 0)
        use = (_ho('USE') or '').lower()
        time_val = float(_ho('TIME') or 0)
        alpha_val = float(_ho('ALPHA') or 0)
        hop_type = 'boil'
        hop_time = int(time_val)
        hop_days = None
        if 'dry' in use:
            hop_type = 'dry_hop'
            hop_days = max(1, int(round(time_val / 1440))) if time_val > 60 else int(time_val)
            hop_time = None
        elif 'whirlpool' in use or 'aroma' in use:
            hop_type = 'whirlpool'
        elif 'first' in use:
            hop_type = 'first_wort'
        ingredients.append({
            'name': _ho('NAME', '?'), 'category': 'houblon',
            'quantity': round(kg * 1000, 1), 'unit': 'g',
            'hop_type': hop_type, 'hop_time': hop_time, 'hop_days': hop_days,
            'alpha': alpha_val if alpha_val else None
        })
    for ye in rx.findall('YEASTS/YEAST'):
        def _ye(t, d=None, _ye=ye): el = _ye.find(t); return el.text.strip() if el is not None and el.text else d
        form = (_ye('FORM') or '').lower()
        kg = float(_ye('AMOUNT') or 0)
        unit = 'sachet' if 'dry' in form else 'ml'
        qty = 1.0 if 'dry' in form else round(kg * 1000, 1)
        ingredients.append({'name': _ye('NAME', '?'), 'category': 'levure', 'quantity': qty, 'unit': unit})
    for mi in rx.findall('MISCS/MISC'):
        def _mi(t, d=None, _mi=mi): el = _mi.find(t); return el.text.strip() if el is not None and el.text else d
        kg = float(_mi('AMOUNT') or 0)
        ingredients.append({
            'name': _mi('NAME', '?'), 'category': 'autre',
            'quantity': round(kg * 1000, 1), 'unit': 'g', 'other_type': _mi('USE', '')
        })

    return {
        'name': name, 'style': style, 'volume': volume, 'boil_time': boil_time,
        'brewhouse_efficiency': efficiency, 'mash_temp': mash_temp, 'mash_time': mash_time,
        'ferm_temp': ferm_temp, 'ferm_time': ferm_time, 'notes': notes, 'ingredients': ingredients
    }


def _brewfather_to_recipe(bf):
    """Convert a Brewfather recipe dict to our internal format."""
    name = bf.get('name', 'Brewfather Recipe')
    style = (bf.get('style') or {}).get('name')
    volume = float(bf.get('batchSize') or 20)
    boil_time = int(bf.get('boilTime') or 60)
    efficiency = float(bf.get('efficiency') or 72)

    mash_temp = 66.0
    mash_time = 60
    for step in ((bf.get('mash') or {}).get('steps') or []):
        if step.get('stepTemp'):
            mash_temp = float(step['stepTemp'])
        if step.get('stepTime'):
            mash_time = int(step['stepTime'])
        break

    ferm_temp = None
    ferm_time = None
    for step in ((bf.get('fermentation') or {}).get('steps') or []):
        if (step.get('type') or '').lower() in ('primary', ''):
            if step.get('stepTemp'):
                ferm_temp = float(step['stepTemp'])
            if step.get('stepTime'):
                ferm_time = int(step['stepTime'])
            break

    notes = bf.get('notes') or bf.get('description')
    ings = bf.get('ingredients') or {}
    ingredients = []

    for fe in (ings.get('fermentables') or []):
        kg = float(fe.get('amount') or 0)
        ebc = float(fe.get('color') or 0) or None
        ingredients.append({
            'name': fe.get('name', '?'), 'category': 'malt',
            'quantity': round(kg * 1000, 1), 'unit': 'g', 'ebc': ebc
        })

    for ho in (ings.get('hops') or []):
        amt_g = float(ho.get('amount') or 0)
        use = (ho.get('use') or '').lower()
        time_val = float(ho.get('time') or 0)
        alpha = float(ho.get('alpha') or 0)
        hop_type = 'boil'
        hop_time = int(time_val)
        hop_days = None
        if 'dry' in use:
            hop_type = 'dry_hop'
            hop_days = int(time_val) if time_val else 3
            hop_time = None
        elif 'whirlpool' in use or 'aroma' in use:
            hop_type = 'whirlpool'
        elif 'first' in use:
            hop_type = 'first_wort'
        ingredients.append({
            'name': ho.get('name', '?'), 'category': 'houblon',
            'quantity': round(amt_g, 1), 'unit': 'g',
            'hop_type': hop_type, 'hop_time': hop_time, 'hop_days': hop_days,
            'alpha': alpha if alpha else None
        })

    for ye in (ings.get('yeasts') or []):
        ye_type = (ye.get('type') or '').lower()
        unit_raw = (ye.get('unit') or 'pkg').lower()
        amt = float(ye.get('amount') or 1)
        if 'ml' in unit_raw:
            unit, qty = 'ml', amt
        elif 'dry' in ye_type or 'pkg' in unit_raw:
            unit, qty = 'sachet', amt
        else:
            unit, qty = 'sachet', amt
        ingredients.append({'name': ye.get('name', '?'), 'category': 'levure', 'quantity': qty, 'unit': unit})

    for mi in (ings.get('miscs') or []):
        amt = float(mi.get('amount') or 0)
        unit_raw = (mi.get('unit') or 'g').lower()
        if 'oz' in unit_raw:
            amt_g = round(amt * 28.35, 1)
        elif 'tbsp' in unit_raw:
            amt_g = round(amt * 12.6, 1)
        elif 'tsp' in unit_raw:
            amt_g = round(amt * 4.2, 1)
        else:
            amt_g = amt
        ingredients.append({
            'name': mi.get('name', '?'), 'category': 'autre',
            'quantity': round(amt_g, 1), 'unit': 'g',
            'other_type': mi.get('use', '')
        })

    return {
        'name': name, 'style': style, 'volume': volume, 'boil_time': boil_time,
        'brewhouse_efficiency': efficiency, 'mash_temp': mash_temp, 'mash_time': mash_time,
        'ferm_temp': ferm_temp, 'ferm_time': ferm_time, 'notes': notes, 'ingredients': ingredients
    }


def _recipe_to_beerxml(recipe, ingredients):
    """Generate a BeerXML <RECIPE> Element for a recipe dict."""
    def _sub(parent, tag, text):
        el = ET.SubElement(parent, tag)
        el.text = str(text) if text is not None else ''
        return el

    rx = ET.Element('RECIPE')
    _sub(rx, 'NAME', recipe.get('name') or '')
    _sub(rx, 'VERSION', '1')
    _sub(rx, 'TYPE', 'All Grain')
    _sub(rx, 'BREWER', 'BrewHome')
    _sub(rx, 'BATCH_SIZE', recipe.get('volume') or 20)
    _sub(rx, 'BOIL_SIZE', round((recipe.get('volume') or 20) * 1.15, 2))
    _sub(rx, 'BOIL_TIME', recipe.get('boil_time') or 60)
    _sub(rx, 'EFFICIENCY', recipe.get('brewhouse_efficiency') or 72)
    if recipe.get('notes'):
        _sub(rx, 'NOTES', recipe['notes'])
    if recipe.get('style'):
        st = ET.SubElement(rx, 'STYLE')
        _sub(st, 'NAME', recipe['style'])
        _sub(st, 'VERSION', '1')
        _sub(st, 'CATEGORY', recipe['style'])
        _sub(st, 'CATEGORY_NUMBER', '0')
        _sub(st, 'STYLE_LETTER', 'A')
        _sub(st, 'STYLE_GUIDE', 'BJCP')
        _sub(st, 'TYPE', 'Ale')
    malts = [i for i in ingredients if i.get('category') == 'malt']
    if malts:
        fs = ET.SubElement(rx, 'FERMENTABLES')
        for ing in malts:
            fe = ET.SubElement(fs, 'FERMENTABLE')
            _sub(fe, 'NAME', ing['name'])
            _sub(fe, 'VERSION', '1')
            _sub(fe, 'TYPE', 'Grain')
            _sub(fe, 'AMOUNT', round(_to_kg(ing.get('quantity'), ing.get('unit')), 4))
            ebc = ing.get('ebc')
            _sub(fe, 'COLOR', round(ebc / 1.97, 1) if ebc else 0)
            _sub(fe, 'YIELD', '75')
    hops = [i for i in ingredients if i.get('category') == 'houblon']
    if hops:
        hs = ET.SubElement(rx, 'HOPS')
        for ing in hops:
            ho = ET.SubElement(hs, 'HOP')
            _sub(ho, 'NAME', ing['name'])
            _sub(ho, 'VERSION', '1')
            _sub(ho, 'AMOUNT', round(_to_kg(ing.get('quantity'), ing.get('unit')), 4))
            _sub(ho, 'ALPHA', ing.get('alpha') or 5.0)
            ht = (ing.get('hop_type') or 'boil').lower()
            use_map = {'boil': 'Boil', 'dry_hop': 'Dry Hop', 'whirlpool': 'Aroma', 'first_wort': 'First Wort'}
            _sub(ho, 'USE', use_map.get(ht, 'Boil'))
            if ht == 'dry_hop':
                _sub(ho, 'TIME', int(ing.get('hop_days') or 3) * 1440)
            else:
                _sub(ho, 'TIME', ing.get('hop_time') or 0)
    yeasts = [i for i in ingredients if i.get('category') == 'levure']
    if yeasts:
        ys_el = ET.SubElement(rx, 'YEASTS')
        for ing in yeasts:
            ye = ET.SubElement(ys_el, 'YEAST')
            _sub(ye, 'NAME', ing['name'])
            _sub(ye, 'VERSION', '1')
            _sub(ye, 'TYPE', 'Ale')
            unit = (ing.get('unit') or '').lower()
            _sub(ye, 'FORM', 'Dry' if 'sachet' in unit else 'Liquid')
            _sub(ye, 'LABORATORY', '')
            _sub(ye, 'PRODUCT_ID', '')
            qty = float(ing.get('quantity') or 1)
            if 'ml' in unit:
                amt_y = round(qty / 1000, 4)
            elif 'sachet' in unit:
                amt_y = round(qty * 0.011, 4)
            else:
                amt_y = round(_to_kg(ing.get('quantity'), ing.get('unit')), 4)
            _sub(ye, 'AMOUNT', amt_y)
            _sub(ye, 'ATTENUATION', '75')
    miscs = [i for i in ingredients if i.get('category') == 'autre']
    if miscs:
        ms_el = ET.SubElement(rx, 'MISCS')
        for ing in miscs:
            mi = ET.SubElement(ms_el, 'MISC')
            _sub(mi, 'NAME', ing['name'])
            _sub(mi, 'VERSION', '1')
            _sub(mi, 'TYPE', 'Other')
            _sub(mi, 'USE', ing.get('other_type') or 'Boil')
            unit_m = (ing.get('unit') or '').lower()
            if unit_m in ('l', 'ml'):
                amt_m = float(ing.get('quantity') or 0) / (1 if unit_m == 'l' else 1000)
            else:
                amt_m = _to_kg(ing.get('quantity'), ing.get('unit'))
            _sub(mi, 'AMOUNT', round(amt_m, 4))
            _sub(mi, 'TIME', 0)
    mash = ET.SubElement(rx, 'MASH')
    _sub(mash, 'NAME', 'Mash')
    _sub(mash, 'VERSION', '1')
    _sub(mash, 'GRAIN_TEMP', 18)
    steps = ET.SubElement(mash, 'MASH_STEPS')
    step = ET.SubElement(steps, 'MASH_STEP')
    _sub(step, 'NAME', 'Saccharification')
    _sub(step, 'VERSION', '1')
    _sub(step, 'TYPE', 'Infusion')
    _sub(step, 'STEP_TEMP', recipe.get('mash_temp') or 66)
    _sub(step, 'STEP_TIME', recipe.get('mash_time') or 60)
    if recipe.get('ferm_temp'):
        _sub(rx, 'PRIMARY_TEMP', recipe['ferm_temp'])
    if recipe.get('ferm_time'):
        _sub(rx, 'PRIMARY_AGE', recipe['ferm_time'])
    return rx


def _upsert_recipe(conn, recipe):
    """Insert or update a recipe + its ingredients. Returns the recipe id."""
    existing = conn.execute('SELECT id FROM recipes WHERE name=?', (recipe['name'],)).fetchone()
    if existing:
        rid = existing['id']
        conn.execute(
            '''UPDATE recipes SET style=?,volume=?,mash_temp=?,mash_time=?,boil_time=?,
               brewhouse_efficiency=?,ferm_temp=?,ferm_time=?,notes=? WHERE id=?''',
            (recipe.get('style'), recipe.get('volume', 20),
             recipe.get('mash_temp', 66), recipe.get('mash_time', 60),
             recipe.get('boil_time', 60), recipe.get('brewhouse_efficiency', 72),
             recipe.get('ferm_temp'), recipe.get('ferm_time'),
             recipe.get('notes'), rid)
        )
        conn.execute('DELETE FROM recipe_ingredients WHERE recipe_id=?', (rid,))
    else:
        cur = conn.execute(
            '''INSERT INTO recipes (name,style,volume,mash_temp,mash_time,boil_time,
               brewhouse_efficiency,ferm_temp,ferm_time,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (recipe['name'], recipe.get('style'), recipe.get('volume', 20),
             recipe.get('mash_temp', 66), recipe.get('mash_time', 60),
             recipe.get('boil_time', 60), recipe.get('brewhouse_efficiency', 72),
             recipe.get('ferm_temp'), recipe.get('ferm_time'), recipe.get('notes'))
        )
        rid = cur.lastrowid
    for ing in recipe.get('ingredients', []):
        conn.execute(
            '''INSERT INTO recipe_ingredients
               (recipe_id,name,category,quantity,unit,hop_time,hop_type,
                hop_days,other_type,ebc,alpha)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (rid, ing.get('name', '?'), ing.get('category', 'autre'),
             ing.get('quantity', 0), ing.get('unit', 'g'),
             ing.get('hop_time'), ing.get('hop_type'), ing.get('hop_days'),
             ing.get('other_type'), ing.get('ebc'), ing.get('alpha'))
        )
    return rid


# ---------------------------------------------------------------------------
# BeerXML export / import routes
# ---------------------------------------------------------------------------

@bp.route('/api/export/beerxml')
def export_beerxml():
    with get_db() as conn:
        recipes = conn.execute(
            'SELECT * FROM recipes WHERE archived IS NOT 1 ORDER BY id'
        ).fetchall()
        ings_rows = conn.execute(
            'SELECT * FROM recipe_ingredients ORDER BY recipe_id, id'
        ).fetchall()
    ings_by_recipe: dict = {}
    for i in ings_rows:
        ings_by_recipe.setdefault(i['recipe_id'], []).append(dict(i))
    root = ET.Element('RECIPES')
    for r in recipes:
        root.append(_recipe_to_beerxml(dict(r), ings_by_recipe.get(r['id'], [])))
    try:
        ET.indent(root, space='  ')
    except AttributeError:
        pass  # Python < 3.9
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')
    filename = f'recettes_{datetime.now().strftime("%Y-%m-%d")}.xml'
    return Response(xml_str, mimetype='application/xml',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@bp.route('/api/import/beerxml', methods=['POST'])
def import_beerxml():
    xml_bytes = request.data
    if not xml_bytes:
        return api_error('no_data', 400)
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return api_error('xml_parse_error', 400, detail=str(e))
    recipe_els = [root] if root.tag == 'RECIPE' else root.findall('RECIPE')
    imported = 0
    with get_db() as conn:
        for rx_el in recipe_els:
            try:
                recipe = _beerxml_to_recipe(rx_el)
                if not recipe.get('name'):
                    continue
                _upsert_recipe(conn, recipe)
                imported += 1
            except Exception as e:
                current_app.logger.warning(f'import_beerxml: skipped recipe: {e}')
    return jsonify({'imported': imported})


@bp.route('/api/import/brewfather', methods=['POST'])
def import_brewfather():
    body = request.json
    if body is None:
        return api_error('no_data', 400)
    recipes_data = body if isinstance(body, list) else [body]
    imported = 0
    with get_db() as conn:
        for bf in recipes_data:
            try:
                recipe = _brewfather_to_recipe(bf)
                if not recipe.get('name'):
                    continue
                _upsert_recipe(conn, recipe)
                imported += 1
            except Exception as e:
                current_app.logger.warning(f"import_brewfather: skipped {bf.get('name')!r}: {e}")
    return jsonify({'imported': imported})


# ---------------------------------------------------------------------------
# Brews export / import
# ---------------------------------------------------------------------------

@bp.route('/api/export/brews')
def export_brews():
    with get_db() as conn:
        brews = conn.execute(
            '''SELECT b.*, r.name as recipe_name
               FROM brews b LEFT JOIN recipes r ON b.recipe_id=r.id
               ORDER BY b.created_at DESC'''
        ).fetchall()
        ferm_rows = conn.execute(
            'SELECT * FROM brew_fermentation_readings ORDER BY brew_id, recorded_at'
        ).fetchall()
    ferm_by_brew: dict = {}
    for f in ferm_rows:
        ferm_by_brew.setdefault(f['brew_id'], []).append(dict(f))
    result = []
    for b in brews:
        brew = dict(b)
        brew['fermentation'] = ferm_by_brew.get(b['id'], [])
        result.append(brew)
    return jsonify(result)


@bp.route('/api/import/brews', methods=['POST'])
def import_brews():
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
            conn.execute('DELETE FROM brew_fermentation_readings')
            _purge_brew_photos(conn)
            conn.execute('DELETE FROM brews')
        for brew in data:
            if not brew.get('name'):
                continue
            try:
                recipe_id = None
                if brew.get('recipe_name'):
                    row = conn.execute('SELECT id FROM recipes WHERE name=?', (brew['recipe_name'],)).fetchone()
                    if row:
                        recipe_id = row['id']
                if not recipe_id and brew.get('recipe_id'):
                    row = conn.execute('SELECT id FROM recipes WHERE id=?', (brew['recipe_id'],)).fetchone()
                    if row:
                        recipe_id = row['id']
                existing = conn.execute('SELECT id FROM brews WHERE name=?', (brew['name'],)).fetchone()
                if existing:
                    brew_id = existing['id']
                    conn.execute(
                        '''UPDATE brews SET brew_date=?,volume_brewed=?,og=?,fg=?,abv=?,
                           notes=?,status=?,archived=? WHERE id=?''',
                        (brew.get('brew_date'), brew.get('volume_brewed'),
                         brew.get('og'), brew.get('fg'), brew.get('abv'),
                         brew.get('notes'), brew.get('status', BrewStatus.COMPLETED),
                         brew.get('archived', 0), brew_id)
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
                current_app.logger.warning(f"import_brews: skipped brew {brew.get('name')!r}: {e}")
    return jsonify({'imported': imported})


# ---------------------------------------------------------------------------
# Beers export / import
# ---------------------------------------------------------------------------

@bp.route('/api/export/beers')
def export_beers():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM beers ORDER BY id').fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/import/beers', methods=['POST'])
def import_beers():
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
            conn.execute('DELETE FROM beers')
        for beer in data:
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
                         beer.get('origin'), beer.get('description'),
                         beer.get('archived', 0),
                         beer.get('initial_33cl') or beer.get('stock_33cl', 0),
                         beer.get('initial_75cl') or beer.get('stock_75cl', 0),
                         beer.get('brew_date'), beer.get('bottling_date'), existing['id'])
                    )
                else:
                    conn.execute(
                        '''INSERT INTO beers
                           (name, type, abv, stock_33cl, stock_75cl, origin, description, photo,
                            archived, initial_33cl, initial_75cl, brew_date, bottling_date)
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
                current_app.logger.warning(f"import_beers: skipped beer {beer.get('name')!r}: {e}")
    return jsonify({'imported': imported})


# ---------------------------------------------------------------------------
# Spindles export / import
# ---------------------------------------------------------------------------

@bp.route('/api/export/spindles')
def export_spindles():
    from blueprints.spindles import _SPINDLE_SELECT_LIST
    with get_db() as conn:
        spindles = conn.execute(
            _SPINDLE_SELECT_LIST + ' ORDER BY COALESCE(s.sort_order, 9999) ASC, s.created_at DESC'
        ).fetchall()
    with get_readings_db() as rconn:
        all_readings = rconn.execute(
            'SELECT * FROM spindle_readings ORDER BY spindle_id, recorded_at'
        ).fetchall()
    readings_by_spindle: dict = {}
    for r in all_readings:
        readings_by_spindle.setdefault(r['spindle_id'], []).append(dict(r))
    result = []
    for s in spindles:
        sp = dict(s)
        sp['readings'] = readings_by_spindle.get(s['id'], [])
        result.append(sp)
    return jsonify(result)


@bp.route('/api/import/spindles', methods=['POST'])
def import_spindles():
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
            spindle_ids = [r['id'] for r in conn.execute('SELECT id FROM spindles').fetchall()]
            with get_readings_db() as rconn:
                for sid in spindle_ids:
                    rconn.execute('DELETE FROM spindle_readings WHERE spindle_id=?', (sid,))
            conn.execute('DELETE FROM spindles')
        for spindle in data:
            if not spindle.get('name'):
                continue
            try:
                existing = conn.execute('SELECT id FROM spindles WHERE name=?', (spindle['name'],)).fetchone()
                if existing:
                    spindle_id = existing['id']
                    conn.execute('UPDATE spindles SET notes=? WHERE id=?', (spindle.get('notes'), spindle_id))
                else:
                    token = secrets.token_urlsafe(16)
                    cur = conn.execute(
                        'INSERT INTO spindles (name, token, notes) VALUES (?,?,?)',
                        (spindle['name'], token, spindle.get('notes'))
                    )
                    spindle_id = cur.lastrowid
                    with get_readings_db() as rconn:
                        for reading in spindle.get('readings', []):
                            rconn.execute(
                                '''INSERT INTO spindle_readings
                                   (spindle_id, gravity, temperature, battery, angle, rssi, recorded_at)
                                   VALUES (?,?,?,?,?,?,?)''',
                                (spindle_id, reading.get('gravity'), reading.get('temperature'),
                                 reading.get('battery'), reading.get('angle'), reading.get('rssi'),
                                 reading.get('recorded_at'))
                            )
                imported += 1
            except Exception as e:
                current_app.logger.warning(f"import_spindles: skipped spindle {spindle.get('name')!r}: {e}")
    return jsonify({'imported': imported})
