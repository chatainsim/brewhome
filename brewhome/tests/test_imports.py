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
