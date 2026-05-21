"""Tests d'intégration — inventaire (/api/inventory) + déduction stock."""
import pytest


@pytest.fixture()
def malt_item(client):
    """Malt en stock (1 kg)."""
    r = client.post('/api/inventory', json={
        'name': 'Pale Ale Malt', 'category': 'malt',
        'quantity': 1.0, 'unit': 'kg',
    })
    return r.get_json()


@pytest.fixture()
def hop_item(client):
    """Houblon en stock (100 g)."""
    r = client.post('/api/inventory', json={
        'name': 'Cascade', 'category': 'houblon',
        'quantity': 100.0, 'unit': 'g',
    })
    return r.get_json()


# ── Liste ─────────────────────────────────────────────────────────────────────

def test_list_inventory_empty(client):
    r = client.get('/api/inventory')
    assert r.status_code == 200
    assert r.get_json() == []


def test_list_inventory_after_create(client, malt_item, hop_item):
    data = client.get('/api/inventory').get_json()
    assert len(data) == 2


# ── Création ──────────────────────────────────────────────────────────────────

def test_create_inventory_item(client):
    r = client.post('/api/inventory', json={
        'name': 'Pilsner Malt', 'category': 'malt',
        'quantity': 2.5, 'unit': 'kg', 'ebc': 2,
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['name'] == 'Pilsner Malt'
    assert data['quantity'] == 2.5
    assert data['unit'] == 'kg'


def test_create_inventory_item_missing_name(client):
    r = client.post('/api/inventory', json={'category': 'malt', 'quantity': 1.0})
    assert r.status_code == 400


def test_create_inventory_item_missing_category(client):
    r = client.post('/api/inventory', json={'name': 'Malt X', 'quantity': 1.0})
    assert r.status_code == 400


def test_create_inventory_item_duplicate(client, malt_item):
    r = client.post('/api/inventory', json={
        'name': 'Pale Ale Malt', 'category': 'malt', 'quantity': 2.0,
    })
    assert r.status_code == 409
    assert r.get_json()['duplicate'] is True


def test_create_inventory_item_duplicate_forced(client, malt_item):
    r = client.post('/api/inventory?force=1', json={
        'name': 'Pale Ale Malt', 'category': 'malt', 'quantity': 2.0,
    })
    assert r.status_code == 201


# ── Mise à jour ───────────────────────────────────────────────────────────────

def test_update_inventory_item(client, malt_item):
    r = client.put(f'/api/inventory/{malt_item["id"]}', json={
        'name': 'Pale Ale Malt', 'category': 'malt',
        'quantity': 3.5, 'unit': 'kg', 'min_stock': 0.5,
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data['quantity'] == 3.5
    assert data['min_stock'] == 0.5


def test_update_inventory_item_not_found(client):
    r = client.put('/api/inventory/9999', json={
        'name': 'X', 'category': 'malt', 'quantity': 1.0,
    })
    assert r.status_code == 404


# ── PATCH quantité ────────────────────────────────────────────────────────────

def test_patch_qty(client, malt_item):
    r = client.patch(f'/api/inventory/{malt_item["id"]}/qty', json={'quantity': 0.5})
    assert r.status_code == 200
    assert r.get_json()['quantity'] == 0.5


def test_patch_qty_not_found(client):
    r = client.patch('/api/inventory/9999/qty', json={'quantity': 1.0})
    assert r.status_code == 404


# ── Suppression / restauration ────────────────────────────────────────────────

def test_delete_inventory_item_soft(client, malt_item):
    r = client.delete(f'/api/inventory/{malt_item["id"]}')
    assert r.status_code == 200
    ids = [i['id'] for i in client.get('/api/inventory').get_json()]
    assert malt_item['id'] not in ids


def test_delete_inventory_item_not_found(client):
    r = client.delete('/api/inventory/9999')
    assert r.status_code == 404


def test_restore_inventory_item(client, malt_item):
    client.delete(f'/api/inventory/{malt_item["id"]}')
    r = client.post(f'/api/inventory/{malt_item["id"]}/restore')
    assert r.status_code == 200
    ids = [i['id'] for i in client.get('/api/inventory').get_json()]
    assert malt_item['id'] in ids


def test_purge_inventory_item(client, malt_item):
    client.delete(f'/api/inventory/{malt_item["id"]}')
    r = client.delete(f'/api/inventory/{malt_item["id"]}/purge')
    assert r.status_code == 200


def test_purge_not_deleted_item_fails(client, malt_item):
    """On ne peut pas purger un item qui n'est pas soft-deleted."""
    r = client.delete(f'/api/inventory/{malt_item["id"]}/purge')
    assert r.status_code == 404


# ── Intégration : déduction de stock lors d'un brassin ───────────────────────

def test_brew_deducts_inventory_stock(client):
    """
    Crée un ingrédient en stock, une recette qui l'utilise,
    puis un brassin avec deduct_stock=True.
    Vérifie que la quantité en stock a été réduite.
    """
    # 1. Créer l'ingrédient en stock : 5 kg de malt
    item = client.post('/api/inventory', json={
        'name': 'Pilsner', 'category': 'malt', 'quantity': 5.0, 'unit': 'kg',
    }).get_json()

    # 2. Créer une recette qui utilise cet ingrédient (4 kg)
    recipe = client.post('/api/recipes', json={
        'name': 'Pils Test', 'volume': 20,
        'ingredients': [{
            'inventory_item_id': item['id'],
            'name': 'Pilsner', 'category': 'malt',
            'quantity': 4000, 'unit': 'g',
        }],
    }).get_json()

    # 3. Créer le brassin avec déduction
    r = client.post('/api/brews', json={
        'recipe_id': recipe['id'],
        'name': 'Pils Brassin 1',
        'deduct_stock': True,
    })
    assert r.status_code == 201

    # 4. Vérifier que le stock a diminué de 4 kg → reste 1 kg
    updated = client.get('/api/inventory').get_json()
    pilsner = next(i for i in updated if i['id'] == item['id'])
    assert abs(pilsner['quantity'] - 1.0) < 0.001


def test_brew_blocked_when_stock_insufficient(client):
    """
    Un brassin sans stock suffisant et sans force=True renvoie 409.
    """
    # Stock : 1 kg, recette : 4 kg
    item = client.post('/api/inventory', json={
        'name': 'Malt Rare', 'category': 'malt', 'quantity': 1.0, 'unit': 'kg',
    }).get_json()

    recipe = client.post('/api/recipes', json={
        'name': 'Recette Gourmande', 'volume': 20,
        'ingredients': [{
            'inventory_item_id': item['id'],
            'name': 'Malt Rare', 'category': 'malt',
            'quantity': 4000, 'unit': 'g',
        }],
    }).get_json()

    r = client.post('/api/brews', json={
        'recipe_id': recipe['id'],
        'name': 'Trop gros brassin',
        'deduct_stock': True,
        'force': False,
    })
    assert r.status_code == 409
    data = r.get_json()
    assert data['error'] == 'stock_insuffisant'
    assert any(i['name'] == 'Malt Rare' for i in data['items'])


def test_brew_forced_despite_insufficient_stock(client):
    """
    force=True permet de créer le brassin même sans stock suffisant.
    Le stock résultant est clampé à 0, pas négatif.
    """
    item = client.post('/api/inventory', json={
        'name': 'Malt Rare', 'category': 'malt', 'quantity': 1.0, 'unit': 'kg',
    }).get_json()

    recipe = client.post('/api/recipes', json={
        'name': 'Recette Gourmande', 'volume': 20,
        'ingredients': [{
            'inventory_item_id': item['id'],
            'name': 'Malt Rare', 'category': 'malt',
            'quantity': 4000, 'unit': 'g',
        }],
    }).get_json()

    r = client.post('/api/brews', json={
        'recipe_id': recipe['id'],
        'name': 'Brassin forcé',
        'deduct_stock': True,
        'force': True,
    })
    assert r.status_code == 201

    updated = client.get('/api/inventory').get_json()
    malt = next(i for i in updated if i['id'] == item['id'])
    assert malt['quantity'] == 0.0
