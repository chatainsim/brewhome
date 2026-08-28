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
