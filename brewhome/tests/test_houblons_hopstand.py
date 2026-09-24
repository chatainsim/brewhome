"""Hop stand, et vocabulaire des types d'ajout de houblon à l'import/export.

L'import BeerXML/Brewfather côté serveur écrivait « boil », « dry_hop » et
« first_wort », alors que toute l'application utilise « ebullition » et
« dryhop » : ces houblons sortaient du planning du jour de brassage, et un
dry-hop importé comptait dans l'amertume. L'export, à l'inverse, envoyait
les dry-hops de l'application comme houblons d'ébullition.
"""

import xml.etree.ElementTree as ET

import db as db_module
import vitrine as V
from blueprints.imports import _brewfather_to_recipe, _recipe_to_beerxml


def _beerxml(*houblons):
    hops = ''.join(f'<HOP><NAME>{n}</NAME><AMOUNT>0.03</AMOUNT><ALPHA>10</ALPHA>'
                   f'<USE>{u}</USE><TIME>{t}</TIME></HOP>' for n, u, t in houblons)
    return (f'<RECIPES><RECIPE><NAME>Import test</NAME><BATCH_SIZE>20</BATCH_SIZE>'
            f'<HOPS>{hops}</HOPS></RECIPE></RECIPES>').encode()


def _types_importes(client, *houblons):
    assert client.post('/api/import/beerxml', data=_beerxml(*houblons),
                       content_type='application/xml').status_code == 200
    with db_module.get_db() as conn:
        rows = conn.execute("SELECT name, hop_type, hop_time, hop_days FROM recipe_ingredients "
                            "WHERE category='houblon' ORDER BY id").fetchall()
    return {r['name']: dict(r) for r in rows}


def test_import_utilise_le_vocabulaire_de_l_application(client):
    t = _types_importes(client, ('Amer', 'Boil', 60), ('Sec', 'Dry Hop', 4320),
                        ('Premier', 'First Wort', 60), ('Arome', 'Aroma', 15))
    assert t['Amer']['hop_type'] == 'ebullition'
    assert t['Sec']['hop_type'] == 'dryhop' and t['Sec']['hop_days'] == 3
    # First wort : bout toute l'ébullition, donc un ajout d'ébullition.
    assert t['Premier']['hop_type'] == 'ebullition' and t['Premier']['hop_time'] == 60
    assert t['Arome']['hop_type'] == 'whirlpool'


def test_import_reconnait_le_hop_stand(client):
    t = _types_importes(client, ('Stand', 'Hop Stand', 30))
    assert t['Stand']['hop_type'] == 'hopstand' and t['Stand']['hop_time'] == 30


def test_export_distingue_les_dry_hops(client):
    ings = [
        {'category': 'houblon', 'name': 'Sec', 'quantity': 50, 'unit': 'g',
         'alpha': 12, 'hop_type': 'dryhop', 'hop_days': 4},
        {'category': 'houblon', 'name': 'Stand', 'quantity': 30, 'unit': 'g',
         'alpha': 12, 'hop_type': 'hopstand', 'hop_time': 20},
        {'category': 'houblon', 'name': 'Amer', 'quantity': 20, 'unit': 'g',
         'alpha': 12, 'hop_type': 'ebullition', 'hop_time': 60},
    ]
    xml = _recipe_to_beerxml({'name': 'R', 'volume': 20}, ings)
    root = xml if hasattr(xml, 'iter') else ET.fromstring(xml)
    usages = {h.findtext('NAME'): h.findtext('USE') for h in root.iter('HOP')}
    assert usages == {'Sec': 'Dry Hop', 'Stand': 'Aroma', 'Amer': 'Boil'}


def test_la_migration_realigne_les_anciens_imports(client):
    with db_module.get_db() as conn:
        rid = conn.execute("INSERT INTO recipes (name) VALUES ('Ancienne')").lastrowid
        for ht in ('boil', 'first_wort', 'dry_hop'):
            conn.execute("INSERT INTO recipe_ingredients (recipe_id, name, category, quantity, unit, hop_type) "
                         "VALUES (?, ?, 'houblon', 10, 'g', ?)", (rid, ht, ht))
    from db import _MIGRATIONS
    with db_module.get_db() as conn:
        for sql in _MIGRATIONS:
            if 'recipe_ingredients SET hop_type' in sql:
                conn.execute(sql)
        types = {r['name']: r['hop_type'] for r in conn.execute(
            'SELECT name, hop_type FROM recipe_ingredients WHERE recipe_id=?', (rid,))}
    assert types == {'boil': 'ebullition', 'first_wort': 'ebullition', 'dry_hop': 'dryhop'}


def test_amertume_du_hop_stand_sur_la_vitrine():
    """Même houblon : le hop stand, vers 80 °C, amertume moins qu'un whirlpool."""
    def ibu(ht, t):
        rec = {'volume': 20, 'ingredients': [
            {'category': 'malt', 'name': 'Pale', 'quantity': 5, 'unit': 'kg', 'gu': 300},
            {'category': 'houblon', 'name': 'H', 'quantity': 50, 'unit': 'g',
             'alpha': 12, 'hop_type': ht, 'hop_time': t}]}
        return V.rec_estimations(rec)['ibu']
    assert ibu('hopstand', 30) < ibu('whirlpool', 30) < ibu('ebullition', 60)
    assert ibu('hopstand', 30) > 0
