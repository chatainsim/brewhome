import json


def test_import_beerxml_valid_recipe(client):
    xml = b'<RECIPE><NAME>Recette BeerXML</NAME><BATCH_SIZE>20</BATCH_SIZE></RECIPE>'
    r = client.post('/api/import/beerxml', data=xml, content_type='application/xml')
    assert r.status_code == 200
    assert r.get_json()['imported'] == 1


def test_import_beerxml_rejects_entity_expansion(client):
    """Un fichier BeerXML uploadé est potentiellement malveillant - un DOCTYPE
    avec entités internes imbriquées ("billion laughs") doit être rejeté
    proprement (400) par defusedxml plutôt que de faire exploser mémoire/CPU
    avec le parseur XML stdlib nu."""
    xml = b'''<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ELEMENT lolz (#PCDATA)>
]>
<lolz>&lol;</lolz>'''
    r = client.post('/api/import/beerxml', data=xml, content_type='application/xml')
    assert r.status_code == 400


def test_import_recipes_rejects_invalid_ingredient_unit(client):
    payload = {
        'items': [{
            'name': 'Recette importée',
            'ingredients': [
                {'name': 'Pilsner', 'category': 'malt', 'quantity': 1, 'unit': "n'importe quoi"},
            ],
        }],
    }
    r = client.post('/api/import/recipes', json=payload)
    assert r.status_code == 200
    assert r.get_json()['imported'] == 1

    r = client.get('/api/recipes')
    recipe = next(x for x in r.get_json() if x['name'] == 'Recette importée')
    assert recipe['ingredients'][0]['unit'] == 'g'


_BEERXML_DEUX = '''<?xml version="1.0" encoding="UTF-8"?>
<RECIPES>
 <RECIPE>
  <NAME>Session IPA</NAME><VERSION>1</VERSION><TYPE>All Grain</TYPE>
  <STYLE><NAME>American IPA</NAME></STYLE>
  <BATCH_SIZE>21</BATCH_SIZE><BOIL_TIME>60</BOIL_TIME><EFFICIENCY>75</EFFICIENCY>
  <EST_OG>1.048</EST_OG><EST_FG>1.010</EST_FG><EST_ABV>5.0</EST_ABV><IBU>45.2</IBU><EST_COLOR>6</EST_COLOR>
  <PRIMARY_TEMP>19</PRIMARY_TEMP><PRIMARY_AGE>14</PRIMARY_AGE>
  <NOTES>Recette d'essai.</NOTES>
  <FERMENTABLES>
   <FERMENTABLE><NAME>Pale Ale</NAME><AMOUNT>4.2</AMOUNT><COLOR>3</COLOR></FERMENTABLE>
   <FERMENTABLE><NAME>Carapils</NAME><AMOUNT>0.25</AMOUNT><COLOR>2</COLOR></FERMENTABLE>
  </FERMENTABLES>
  <HOPS>
   <HOP><NAME>Magnum</NAME><AMOUNT>0.015</AMOUNT><ALPHA>12</ALPHA><USE>Boil</USE><TIME>60</TIME></HOP>
   <HOP><NAME>Citra</NAME><AMOUNT>0.04</AMOUNT><ALPHA>13</ALPHA><USE>Aroma</USE><TIME>15</TIME></HOP>
   <HOP><NAME>Mosaic</NAME><AMOUNT>0.05</AMOUNT><ALPHA>11.5</ALPHA><USE>Dry Hop</USE><TIME>4320</TIME></HOP>
  </HOPS>
  <YEASTS><YEAST><NAME>WLP001</NAME><FORM>Liquid</FORM><AMOUNT>0.125</AMOUNT></YEAST></YEASTS>
  <MISCS><MISC><NAME>Irish Moss</NAME><USE>Boil</USE><TIME>10</TIME><AMOUNT>0.005</AMOUNT></MISC></MISCS>
  <MASH><MASH_STEPS>
   <MASH_STEP><NAME>Saccharification</NAME><STEP_TEMP>66</STEP_TEMP><STEP_TIME>60</STEP_TIME></MASH_STEP>
   <MASH_STEP><NAME>Mash out</NAME><STEP_TEMP>76</STEP_TEMP><STEP_TIME>10</STEP_TIME></MASH_STEP>
  </MASH_STEPS></MASH>
 </RECIPE>
 <RECIPE><NAME>Stout</NAME><BATCH_SIZE>10</BATCH_SIZE></RECIPE>
</RECIPES>'''.encode()


def test_import_beerxml_en_brouillons(client):
    """Un brouillon par recette, sans créer de recette ; les détails sans champ
    dédié dans le brouillon (profil, empâtage, houblonnage) vont dans les notes."""
    avant = len(client.get('/api/recipes').get_json())
    r = client.post('/api/import/beerxml/drafts', data=_BEERXML_DEUX, content_type='application/xml')
    assert r.status_code == 200
    body = r.get_json()
    assert body['imported'] == 2
    assert len(client.get('/api/recipes').get_json()) == avant

    d = body['drafts'][0]
    assert (d['title'], d['style'], d['volume'], d['status']) == ('Session IPA', 'American IPA', 21, 'idea')
    ings = {i['name']: i for i in json.loads(d['ingredients'])}
    assert (ings['Pale Ale']['quantity'], ings['Pale Ale']['unit']) == (4.2, 'kg')
    assert (ings['Carapils']['quantity'], ings['Carapils']['unit']) == (250, 'g')
    assert ings['Magnum'] == {'category': 'houblon', 'name': 'Magnum', 'quantity': 15, 'unit': 'g',
                                    'hop_type': 'ebullition', 'hop_time': 60, 'alpha': 12}
    assert ings['Citra']['hop_type'] == 'whirlpool'
    assert (ings['Mosaic']['hop_type'], ings['Mosaic']['hop_days']) == ('dryhop', 3)
    assert (ings['WLP001']['quantity'], ings['WLP001']['unit']) == (1, 'sachet')
    assert (ings['Irish Moss']['other_type'], ings['Irish Moss']['other_time']) == ('ebullition', 10)
    notes = d['notes']
    for attendu in ('OG 1.048', 'FG 1.010', '5 % ABV', '45 IBU', '66 °C × 60 min, 76 °C × 10 min',
                    'Ébullition : 60 min', 'Rendement : 75 %', 'Fermentation : 19 °C · 14 j',
                    'Mosaic (11.5 % AA) : 50 g, dry hop 3 j', "Recette d'essai.", 'Importé depuis BeerXML'):
        assert attendu in notes, attendu

    ids = [x['id'] for x in client.get('/api/drafts').get_json()]
    assert d['id'] in ids and body['drafts'][1]['id'] in ids


def test_import_beerxml_brouillons_en_anglais(client):
    r = client.post('/api/import/beerxml/drafts?lang=en', data=_BEERXML_DEUX, content_type='application/xml')
    notes = r.get_json()['drafts'][0]['notes']
    assert 'Boil : 60 min' in notes and 'Imported from BeerXML' in notes


def test_import_beerxml_brouillons_fichier_invalide(client):
    assert client.post('/api/import/beerxml/drafts', data=b'<RECIPES><RECIPE>', content_type='application/xml').status_code == 400
    assert client.post('/api/import/beerxml/drafts', data=b'', content_type='application/xml').status_code == 400
    r = client.post('/api/import/beerxml/drafts', data=b'<RECIPES/>', content_type='application/xml')
    assert r.get_json() == {'imported': 0, 'drafts': [], 'repaired': False}


def test_import_beerxml_recette_etape_des_autres_ingredients(client):
    """<USE>Boil</USE> devient l'étape « ebullition » de l'application (le
    sélecteur de la recette ne connaissait pas la valeur brute « Boil »)."""
    client.post('/api/import/beerxml', data=_BEERXML_DEUX, content_type='application/xml')
    recipe = next(x for x in client.get('/api/recipes').get_json() if x['name'] == 'Session IPA')
    moss = next(i for i in recipe['ingredients'] if i['name'] == 'Irish Moss')
    assert (moss['other_type'], moss['other_time']) == ('ebullition', 10)


def test_import_beerxml_esperluette_non_echappee_corrigee(client):
    """« Barbe Rouge & Citra » : XML invalide, mais le seul défaut est le
    « & » isolé. L'import le corrige et le signale ; les entités valides
    (&amp;, &#38;) restent intactes."""
    xml = ('<RECIPES><RECIPE><NAME>IPA Hibiscus (Barbe Rouge & Citra)</NAME><BATCH_SIZE>20</BATCH_SIZE>'
           '<NOTES>Malt &amp; houblon &#38; baies</NOTES></RECIPE></RECIPES>').encode()
    r = client.post('/api/import/beerxml/drafts', data=xml, content_type='application/xml')
    assert r.status_code == 200
    body = r.get_json()
    assert body['repaired'] is True and body['imported'] == 1
    d = body['drafts'][0]
    assert d['title'] == 'IPA Hibiscus (Barbe Rouge & Citra)'
    assert 'Malt & houblon & baies' in d['notes']

    r = client.post('/api/import/beerxml', data=xml, content_type='application/xml')
    assert r.status_code == 200 and r.get_json() == {'imported': 1, 'repaired': True}


def test_import_beerxml_fichier_valide_non_modifie(client):
    r = client.post('/api/import/beerxml/drafts', data=_BEERXML_DEUX, content_type='application/xml')
    assert r.get_json()['repaired'] is False


def test_import_beerxml_erreur_situee(client):
    """Une autre erreur XML n'est pas « réparée » : la réponse donne ligne,
    colonne et extrait pour que l'interface dise où est le problème."""
    xml = b'<RECIPES>\n  <RECIPE>\n    <NAME>Sans fin</NAM>\n  </RECIPE>\n</RECIPES>'
    r = client.post('/api/import/beerxml/drafts', data=xml, content_type='application/xml')
    assert r.status_code == 400
    body = r.get_json()
    assert body['error'] == 'xml_parse_error'
    assert body['line'] == 3 and body['column'] > 1
    assert body['excerpt'] == '<NAME>Sans fin</NAM>'


def test_import_beerxml_entites_toujours_refusees(client):
    """La réparation des « & » ne doit pas rouvrir la porte aux entités."""
    xml = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "y">]><RECIPES><RECIPE><NAME>&x; & co</NAME></RECIPE></RECIPES>'
    r = client.post('/api/import/beerxml/drafts', data=xml, content_type='application/xml')
    assert r.status_code == 400
    assert r.get_json()['error'] == 'xml_forbidden'
