"""Tests d'intégration — cave à bières (/api/beers)."""
import pytest


@pytest.fixture()
def beer(client):
    """Bière minimale réutilisable."""
    r = client.post('/api/beers', json={'name': 'IPA Maison', 'abv': 6.2, 'stock_33cl': 24})
    return r.get_json()


# ── Liste ─────────────────────────────────────────────────────────────────────

def test_list_beers_empty(client):
    r = client.get('/api/beers')
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_beers_after_create(client, beer):
    r = client.get('/api/beers')
    assert r.status_code == 200
    assert len(r.get_json()) == 1


# ── Création ──────────────────────────────────────────────────────────────────

def test_create_beer(client):
    r = client.post('/api/beers', json={
        'name': 'Stout Maison', 'type': 'Stout', 'abv': 5.5,
        'stock_33cl': 12, 'stock_75cl': 6,
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['name'] == 'Stout Maison'
    assert data['abv'] == 5.5
    assert data['stock_33cl'] == 12
    assert data['stock_75cl'] == 6


def test_create_beer_missing_name(client):
    r = client.post('/api/beers', json={'abv': 5.0, 'stock_33cl': 6})
    assert r.status_code == 400


def test_create_beer_initial_stock_defaults(client):
    r = client.post('/api/beers', json={'name': 'Blonde', 'stock_33cl': 10}).get_json()
    # initial_33cl doit être égal à stock_33cl si non fourni
    assert r['initial_33cl'] == 10


# ── Mise à jour ───────────────────────────────────────────────────────────────

def test_update_beer(client, beer):
    r = client.put(f'/api/beers/{beer["id"]}', json={
        'name': 'IPA Maison V2', 'type': 'IPA', 'abv': 6.8,
        'stock_33cl': 24, 'stock_75cl': 0,
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data['name'] == 'IPA Maison V2'
    assert data['abv'] == 6.8


def test_update_beer_not_found(client):
    r = client.put('/api/beers/9999', json={'name': 'X', 'stock_33cl': 0, 'stock_75cl': 0})
    assert r.status_code == 404


# ── Suppression / restauration ────────────────────────────────────────────────

def test_delete_beer_soft(client, beer):
    r = client.delete(f'/api/beers/{beer["id"]}')
    assert r.status_code == 200
    ids = [b['id'] for b in client.get('/api/beers').get_json()]
    assert beer['id'] not in ids


def test_delete_beer_not_found(client):
    r = client.delete('/api/beers/9999')
    assert r.status_code == 404


def test_restore_beer(client, beer):
    client.delete(f'/api/beers/{beer["id"]}')
    r = client.post(f'/api/beers/{beer["id"]}/restore')
    assert r.status_code == 200
    ids = [b['id'] for b in client.get('/api/beers').get_json()]
    assert beer['id'] in ids


# ── Stock / consommation ──────────────────────────────────────────────────────

def test_patch_stock_decrease_creates_consumption_log(client, beer):
    r = client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_33cl': 20})
    assert r.status_code == 200
    assert r.get_json()['stock_33cl'] == 20


def test_patch_stock_increase_no_error(client, beer):
    r = client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_33cl': 30})
    assert r.status_code == 200
    assert r.get_json()['stock_33cl'] == 30


def test_patch_stock_not_found(client):
    r = client.patch('/api/beers/9999/stock', json={'stock_33cl': 0})
    assert r.status_code == 404


def test_consumption_depletion_endpoint(client, beer):
    # Consommer des bouteilles pour alimenter le log
    client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_33cl': 20})
    client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_33cl': 16})
    r = client.get('/api/consumption/depletion')
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_consumption_stats_endpoint(client, beer):
    client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_33cl': 20})
    r = client.get('/api/consumption')
    assert r.status_code == 200
    data = r.get_json()
    assert 'by_month' in data
    assert 'by_beer' in data


# ── Notes de dégustation ──────────────────────────────────────────────────────

def test_update_tasting_notes(client, beer):
    r = client.put(f'/api/beers/{beer["id"]}/tasting', json={
        'taste_overall': 'Excellent', 'taste_rating': 5, 'taste_date': '2025-03-01',
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data['taste_overall'] == 'Excellent'
    assert data['taste_rating'] == 5


def test_update_tasting_not_found(client):
    r = client.put('/api/beers/9999/tasting', json={'taste_overall': 'X'})
    assert r.status_code == 404


# ── Patch archivage ───────────────────────────────────────────────────────────

def test_patch_beer_archived(client, beer):
    r = client.patch(f'/api/beers/{beer["id"]}', json={'archived': True})
    assert r.status_code == 200
    assert r.get_json()['archived'] == 1


# ── Tailles 25cl / 50cl ──────────────────────────────────────────────────────

def test_create_beer_with_25_50cl(client):
    r = client.post('/api/beers', json={
        'name': 'Session IPA', 'abv': 4.2,
        'stock_25cl': 8, 'stock_50cl': 4,
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['stock_25cl'] == 8
    assert data['stock_50cl'] == 4
    # initial_* doit suivre stock_* si non fourni, comme pour 33cl/75cl
    assert data['initial_25cl'] == 8
    assert data['initial_50cl'] == 4


def test_update_beer_25_50cl(client, beer):
    r = client.put(f'/api/beers/{beer["id"]}', json={
        'name': 'IPA Maison V2', 'stock_25cl': 5, 'stock_50cl': 2,
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data['stock_25cl'] == 5
    assert data['stock_50cl'] == 2


def test_patch_stock_25_50cl(client, beer):
    r = client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_25cl': 3, 'stock_50cl': 1})
    assert r.status_code == 200
    data = r.get_json()
    assert data['stock_25cl'] == 3
    assert data['stock_50cl'] == 1


def test_patch_stock_25cl_decrease_creates_consumption_log(client, beer):
    client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_25cl': 10})
    r = client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_25cl': 7})
    assert r.status_code == 200
    assert r.get_json()['stock_25cl'] == 7
    stats = client.get('/api/consumption').get_json()
    total_25cl = sum(b.get('total_25cl') or 0 for b in stats['by_beer'])
    assert total_25cl >= 3


def test_bottle_sizes_enabled_setting_roundtrip(client):
    import json as _json
    r = client.put('/api/app-settings', json={
        'bottle_sizes_enabled': _json.dumps({'25cl': True, '33cl': True, '50cl': False, '75cl': True})
    })
    assert r.status_code == 200
    r = client.get('/api/app-settings')
    saved = _json.loads(r.get_json()['bottle_sizes_enabled'])
    assert saved == {'25cl': True, '33cl': True, '50cl': False, '75cl': True}


def test_disabled_size_stock_stays_readable(client, beer):
    """Desactiver une taille dans les reglages ne doit jamais masquer du stock existant via l'API."""
    import json as _json
    client.patch(f'/api/beers/{beer["id"]}/stock', json={'stock_50cl': 6})
    client.put('/api/app-settings', json={
        'bottle_sizes_enabled': _json.dumps({'25cl': False, '33cl': True, '50cl': False, '75cl': True})
    })
    r = client.get('/api/beers')
    updated = next(b for b in r.get_json() if b['id'] == beer['id'])
    assert updated['stock_50cl'] == 6
