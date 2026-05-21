"""Tests d'intégration — brassins (/api/brews)."""
import pytest


@pytest.fixture()
def recipe(client):
    """Recette minimale pour les tests de brassin."""
    r = client.post('/api/recipes', json={'name': 'Recette Test', 'volume': 20})
    return r.get_json()


@pytest.fixture()
def brew(client, recipe):
    """Brassin minimal (sans déduction de stock)."""
    r = client.post('/api/brews', json={
        'recipe_id': recipe['id'],
        'name': 'Brassin Test',
        'deduct_stock': False,
    })
    return r.get_json()


# ── Liste ─────────────────────────────────────────────────────────────────────

def test_list_brews_empty(client):
    r = client.get('/api/brews')
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_brews_after_create(client, brew):
    r = client.get('/api/brews')
    assert r.status_code == 200
    assert len(r.get_json()) == 1


# ── Création ──────────────────────────────────────────────────────────────────

def test_create_brew(client, recipe):
    r = client.post('/api/brews', json={
        'recipe_id': recipe['id'],
        'name': 'Brassin 1',
        'deduct_stock': False,
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['name'] == 'Brassin 1'
    assert data['recipe_id'] == recipe['id']


def test_create_brew_no_recipe_id(client):
    r = client.post('/api/brews', json={'name': 'Sans recette'})
    assert r.status_code == 400


def test_create_brew_insufficient_stock_blocked(client, recipe):
    """Sans force=True, un stock insuffisant renvoie 409."""
    r = client.post('/api/brews', json={
        'recipe_id': recipe['id'],
        'name': 'Brassin Stock',
        'deduct_stock': True,
        'force': False,
    })
    # La recette n'a pas d'ingrédients liés à l'inventaire → pas d'insuffisance → 201
    assert r.status_code == 201


# ── Mise à jour ───────────────────────────────────────────────────────────────

def test_update_brew(client, brew):
    r = client.put(f'/api/brews/{brew["id"]}', json={
        'name': 'Brassin Mis à jour',
        'og': 1.060,
        'fg': 1.010,
        'abv': 6.5,
        'status': 'fermenting',
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data['name'] == 'Brassin Mis à jour'
    assert data['og'] == 1.060
    assert data['status'] == 'fermenting'


def test_update_brew_not_found(client):
    r = client.put('/api/brews/9999', json={'name': 'X', 'status': 'fermenting'})
    assert r.status_code == 404


def test_patch_brew_notes(client, brew):
    r = client.patch(f'/api/brews/{brew["id"]}', json={'notes': 'Bonne fermentation'})
    assert r.status_code == 200
    assert r.get_json()['notes'] == 'Bonne fermentation'


# ── Suppression / restauration ────────────────────────────────────────────────

def test_delete_brew_soft(client, brew):
    r = client.delete(f'/api/brews/{brew["id"]}')
    assert r.status_code == 200
    ids = [b['id'] for b in client.get('/api/brews').get_json()]
    assert brew['id'] not in ids


def test_delete_brew_not_found(client):
    r = client.delete('/api/brews/9999')
    assert r.status_code == 404


def test_restore_brew(client, brew):
    client.delete(f'/api/brews/{brew["id"]}')
    r = client.post(f'/api/brews/{brew["id"]}/restore')
    assert r.status_code == 200
    ids = [b['id'] for b in client.get('/api/brews').get_json()]
    assert brew['id'] in ids


# ── Lectures de fermentation ──────────────────────────────────────────────────

def test_add_fermentation_reading(client, brew):
    r = client.post(f'/api/brews/{brew["id"]}/fermentation', json={
        'recorded_at': '2025-01-15 10:00:00',
        'gravity': 1.045,
        'temperature': 20.0,
    })
    assert r.status_code == 201
    assert 'id' in r.get_json()


def test_add_fermentation_missing_recorded_at(client, brew):
    r = client.post(f'/api/brews/{brew["id"]}/fermentation', json={'gravity': 1.045})
    assert r.status_code == 400


def test_add_fermentation_missing_gravity(client, brew):
    r = client.post(f'/api/brews/{brew["id"]}/fermentation', json={
        'recorded_at': '2025-01-15 10:00:00',
    })
    assert r.status_code == 400


def test_get_fermentation_readings(client, brew):
    for ts, sg in [('2025-01-15 10:00:00', 1.045), ('2025-01-17 10:00:00', 1.020)]:
        client.post(f'/api/brews/{brew["id"]}/fermentation', json={
            'recorded_at': ts, 'gravity': sg,
        })
    r = client.get(f'/api/brews/{brew["id"]}/fermentation')
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_delete_manual_fermentation_reading(client, brew):
    reading = client.post(f'/api/brews/{brew["id"]}/fermentation', json={
        'recorded_at': '2025-01-15 10:00:00', 'gravity': 1.045,
    }).get_json()
    r = client.delete(f'/api/brews/{brew["id"]}/fermentation/{reading["id"]}')
    assert r.status_code == 200
    assert client.get(f'/api/brews/{brew["id"]}/fermentation').get_json() == []


def test_delete_fermentation_reading_not_found(client, brew):
    r = client.delete(f'/api/brews/{brew["id"]}/fermentation/9999')
    assert r.status_code == 404
