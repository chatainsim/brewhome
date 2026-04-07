"""Tests d'intégration — catalogue d'ingrédients (/api/catalog)."""
import pytest


@pytest.fixture()
def hop(client):
    """Houblon minimal dans le catalogue."""
    r = client.post('/api/catalog', json={
        'name': 'Cascade', 'category': 'houblon', 'alpha': 6.5,
    })
    return r.get_json()


@pytest.fixture()
def malt(client):
    """Malt minimal dans le catalogue."""
    r = client.post('/api/catalog', json={
        'name': 'Pale Ale', 'category': 'malt', 'ebc': 6, 'default_unit': 'kg',
    })
    return r.get_json()


# ── Liste ─────────────────────────────────────────────────────────────────────

def test_list_catalog_empty(client):
    r = client.get('/api/catalog')
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_catalog_after_create(client, hop, malt):
    r = client.get('/api/catalog')
    assert r.status_code == 200
    assert len(r.get_json()) == 2


def test_list_catalog_filter_category(client, hop, malt):
    r = client.get('/api/catalog?category=houblon')
    data = r.get_json()
    assert len(data) == 1
    assert data[0]['name'] == 'Cascade'


def test_list_catalog_search_name(client, hop, malt):
    r = client.get('/api/catalog?q=pale')
    data = r.get_json()
    assert len(data) == 1
    assert data[0]['name'] == 'Pale Ale'


def test_list_catalog_search_no_match(client, hop):
    r = client.get('/api/catalog?q=zzz')
    assert r.get_json() == []


# ── Création ──────────────────────────────────────────────────────────────────

def test_create_catalog_item(client):
    r = client.post('/api/catalog', json={
        'name': 'Chinook', 'category': 'houblon', 'alpha': 12.0,
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['name'] == 'Chinook'
    assert data['category'] == 'houblon'
    assert data['alpha'] == 12.0


def test_create_catalog_item_missing_name(client):
    r = client.post('/api/catalog', json={'category': 'houblon'})
    assert r.status_code == 400


def test_create_catalog_item_missing_category(client):
    r = client.post('/api/catalog', json={'name': 'Chinook'})
    assert r.status_code == 400


def test_create_catalog_yeast(client):
    r = client.post('/api/catalog', json={
        'name': 'US-05', 'category': 'levure',
        'yeast_type': 'ale', 'attenuation_min': 73, 'attenuation_max': 77,
        'temp_min': 15, 'temp_max': 24, 'alcohol_tolerance': 11.0,
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['yeast_type'] == 'ale'
    assert data['attenuation_min'] == 73


# ── Mise à jour ───────────────────────────────────────────────────────────────

def test_update_catalog_item(client, hop):
    r = client.put(f'/api/catalog/{hop["id"]}', json={
        'name': 'Cascade Updated', 'alpha': 7.0,
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data['name'] == 'Cascade Updated'
    assert data['alpha'] == 7.0


def test_update_catalog_item_not_found(client):
    r = client.put('/api/catalog/9999', json={'name': 'X'})
    assert r.status_code == 404


# ── Suppression ───────────────────────────────────────────────────────────────

def test_delete_catalog_item(client, hop):
    r = client.delete(f'/api/catalog/{hop["id"]}')
    assert r.status_code == 200
    # Ne doit plus apparaître dans la liste
    items = client.get('/api/catalog').get_json()
    assert all(i['id'] != hop['id'] for i in items)


def test_delete_catalog_item_not_found(client):
    r = client.delete('/api/catalog/9999')
    assert r.status_code == 404


# ── Contenu des champs spécifiques ────────────────────────────────────────────

def test_catalog_item_aroma_spec(client):
    r = client.post('/api/catalog', json={
        'name': 'Simcoe', 'category': 'houblon',
        'alpha': 13.0, 'aroma_spec': 'Pine, citrus, passionfruit',
    })
    assert r.status_code == 201
    assert r.get_json()['aroma_spec'] == 'Pine, citrus, passionfruit'


def test_catalog_item_max_usage_pct(client):
    r = client.post('/api/catalog', json={
        'name': 'Roasted Barley', 'category': 'malt',
        'ebc': 1300, 'max_usage_pct': 10.0,
    })
    assert r.status_code == 201
    assert r.get_json()['max_usage_pct'] == 10.0
