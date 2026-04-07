"""Tests d'intégration — recettes (/api/recipes)."""


def test_list_recipes_empty(client):
    r = client.get('/api/recipes')
    assert r.status_code == 200
    assert r.get_json() == []


def test_create_recipe(client):
    r = client.post('/api/recipes', json={'name': 'IPA Test', 'style': 'IPA', 'volume': 20})
    assert r.status_code == 201
    data = r.get_json()
    assert data['name'] == 'IPA Test'
    assert data['style'] == 'IPA'
    assert data['volume'] == 20
    assert data['ingredients'] == []


def test_create_recipe_missing_name(client):
    r = client.post('/api/recipes', json={'style': 'IPA'})
    assert r.status_code == 400


def test_create_recipe_duplicate(client):
    client.post('/api/recipes', json={'name': 'Stout'})
    r = client.post('/api/recipes', json={'name': 'Stout'})
    assert r.status_code == 409
    assert r.get_json()['duplicate'] is True


def test_create_recipe_duplicate_forced(client):
    client.post('/api/recipes', json={'name': 'Stout'})
    r = client.post('/api/recipes?force=1', json={'name': 'Stout'})
    assert r.status_code == 201


def test_get_recipe(client):
    created = client.post('/api/recipes', json={'name': 'Blonde'}).get_json()
    r = client.get(f'/api/recipes/{created["id"]}')
    assert r.status_code == 200
    assert r.get_json()['name'] == 'Blonde'


def test_get_recipe_not_found(client):
    r = client.get('/api/recipes/9999')
    assert r.status_code == 404


def test_update_recipe(client):
    created = client.post('/api/recipes', json={'name': 'Blonde'}).get_json()
    r = client.put(f'/api/recipes/{created["id"]}', json={'name': 'Blonde V2', 'volume': 25})
    assert r.status_code == 200
    data = r.get_json()
    assert data['name'] == 'Blonde V2'
    assert data['volume'] == 25


def test_update_recipe_not_found(client):
    r = client.put('/api/recipes/9999', json={'name': 'X', 'volume': 20})
    assert r.status_code == 404


def test_delete_recipe_soft(client):
    created = client.post('/api/recipes', json={'name': 'Draft'}).get_json()
    r = client.delete(f'/api/recipes/{created["id"]}')
    assert r.status_code == 200
    # Doit disparaître de la liste
    ids = [rec['id'] for rec in client.get('/api/recipes').get_json()]
    assert created['id'] not in ids


def test_delete_recipe_not_found(client):
    r = client.delete('/api/recipes/9999')
    assert r.status_code == 404


def test_restore_recipe(client):
    created = client.post('/api/recipes', json={'name': 'Draft'}).get_json()
    client.delete(f'/api/recipes/{created["id"]}')
    r = client.post(f'/api/recipes/{created["id"]}/restore')
    assert r.status_code == 200
    ids = [rec['id'] for rec in client.get('/api/recipes').get_json()]
    assert created['id'] in ids


def test_create_recipe_with_ingredients(client):
    payload = {
        'name': 'Houblon Test',
        'volume': 20,
        'ingredients': [
            {'name': 'Pale Ale Malt', 'category': 'malt',    'quantity': 4000, 'unit': 'g'},
            {'name': 'Cascade',       'category': 'houblon', 'quantity': 30,   'unit': 'g', 'hop_time': 60},
        ],
    }
    r = client.post('/api/recipes', json=payload)
    assert r.status_code == 201
    data = r.get_json()
    assert len(data['ingredients']) == 2
    names = {i['name'] for i in data['ingredients']}
    assert names == {'Pale Ale Malt', 'Cascade'}


def test_recipe_history_saved_on_update(client):
    created = client.post('/api/recipes', json={'name': 'Historic'}).get_json()
    client.put(f'/api/recipes/{created["id"]}', json={'name': 'Historic V2', 'volume': 20})
    r = client.get(f'/api/recipes/{created["id"]}/history')
    assert r.status_code == 200
    assert len(r.get_json()) >= 1


def test_patch_recipe_rating(client):
    created = client.post('/api/recipes', json={'name': 'Ratable'}).get_json()
    r = client.patch(f'/api/recipes/{created["id"]}', json={'rating': 4})
    assert r.status_code == 200
    assert r.get_json()['rating'] == 4


def test_list_contains_created_recipes(client):
    client.post('/api/recipes', json={'name': 'R1'})
    client.post('/api/recipes', json={'name': 'R2'})
    data = client.get('/api/recipes').get_json()
    names = {r['name'] for r in data}
    assert {'R1', 'R2'}.issubset(names)
