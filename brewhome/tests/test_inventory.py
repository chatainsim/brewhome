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


def test_create_inventory_item_keeps_min_stock_and_expiry(client):
    r = client.post('/api/inventory', json={
        'name': 'Citra', 'category': 'houblon',
        'quantity': 100, 'unit': 'g', 'min_stock': 20, 'expiry_date': '2027-01-01',
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['min_stock'] == 20
    assert data['expiry_date'] == '2027-01-01'


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
    assert r.get_json()['error'] == 'duplicate'


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


# ── % max dans la facture de malts ────────────────────────────────────────────

def test_create_malt_with_max_usage_pct(client):
    r = client.post('/api/inventory', json={
        'name': 'Malt Torréfié', 'category': 'malt',
        'quantity': 1.0, 'unit': 'kg', 'max_usage_pct': 5,
    })
    assert r.status_code == 201
    assert r.get_json()['max_usage_pct'] == 5


def test_max_usage_pct_defaults_to_null(client, malt_item):
    assert malt_item['max_usage_pct'] is None


def test_update_malt_max_usage_pct(client, malt_item):
    r = client.put(f'/api/inventory/{malt_item["id"]}', json={
        'name': 'Pale Ale Malt', 'category': 'malt',
        'quantity': 1.0, 'unit': 'kg', 'max_usage_pct': 10,
    })
    assert r.status_code == 200
    assert r.get_json()['max_usage_pct'] == 10


def test_max_usage_pct_above_100_rejected(client):
    r = client.post('/api/inventory', json={
        'name': 'Malt Impossible', 'category': 'malt',
        'quantity': 1.0, 'max_usage_pct': 150,
    })
    assert r.status_code == 400


def test_max_usage_pct_negative_rejected(client):
    r = client.post('/api/inventory', json={
        'name': 'Malt Négatif', 'category': 'malt',
        'quantity': 1.0, 'max_usage_pct': -1,
    })
    assert r.status_code == 400


def test_max_usage_pct_cleared_on_update(client):
    """Vider le champ (None) doit effacer la contrainte, pas la conserver."""
    item = client.post('/api/inventory', json={
        'name': 'Malt Réglé', 'category': 'malt',
        'quantity': 1.0, 'unit': 'kg', 'max_usage_pct': 5,
    }).get_json()
    r = client.put(f'/api/inventory/{item["id"]}', json={
        'name': 'Malt Réglé', 'category': 'malt',
        'quantity': 1.0, 'unit': 'kg', 'max_usage_pct': None,
    })
    assert r.status_code == 200
    assert r.get_json()['max_usage_pct'] is None


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


# ── Corbeille (#20) ──────────────────────────────────────────────────────────

def test_restauration_garde_la_quantite(client, malt_item):
    client.delete(f'/api/inventory/{malt_item["id"]}')
    client.post(f'/api/inventory/{malt_item["id"]}/restore')
    item = next(i for i in client.get('/api/inventory').get_json() if i['id'] == malt_item['id'])
    assert item['quantity'] == 1.0


def test_export_sans_la_corbeille(client, malt_item, hop_item):
    client.delete(f'/api/inventory/{malt_item["id"]}')
    names = [i['name'] for i in client.get('/api/export/inventory').get_json()]
    assert names == ['Cascade']


# ── Inventaire de contrôle ───────────────────────────────────────────────────

def test_recomptage_corrige_et_journalise(client, malt_item, hop_item):
    r = client.post('/api/inventory/recount', json={'items': [
        {'id': malt_item['id'], 'quantity': 0.75},      # 1 kg affiché, 750 g comptés
        {'id': hop_item['id'], 'quantity': 100.0},      # identique : rien à faire
    ]})
    assert r.status_code == 200
    data = r.get_json()
    assert data['updated'] == 1 and data['changed_ids'] == [malt_item['id']]
    assert next(i for i in data['items'] if i['id'] == malt_item['id'])['quantity'] == 0.75
    entries = client.get(f'/api/inventory/{malt_item["id"]}/history').get_json()['entries']
    recounts = [e for e in entries if e['reason'] == 'recount']
    assert len(recounts) == 1 and abs(recounts[0]['delta'] + 0.25) < 1e-9
    hop_entries = client.get(f'/api/inventory/{hop_item["id"]}/history').get_json()['entries']
    assert not [e for e in hop_entries if e['reason'] == 'recount']


def test_recomptage_refuse_une_quantite_invalide(client, malt_item):
    r = client.post('/api/inventory/recount', json={'items': [{'id': malt_item['id'], 'quantity': -1}]})
    assert r.status_code == 400
    assert next(i for i in client.get('/api/inventory').get_json() if i['id'] == malt_item['id'])['quantity'] == 1.0


def test_recomptage_ignore_la_corbeille(client, malt_item):
    client.delete(f'/api/inventory/{malt_item["id"]}')
    r = client.post('/api/inventory/recount', json={'items': [{'id': malt_item['id'], 'quantity': 5}]})
    assert r.get_json()['updated'] == 0


# ── Modification partielle (appli Android, #24) ──────────────────────────────

def test_put_partiel_garde_peremption_et_levure(client):
    item = client.post('/api/inventory', json={
        'name': 'US-05', 'category': 'levure', 'quantity': 3, 'unit': 'sachet',
        'expiry_date': '2027-05-01', 'yeast_type': 'sec', 'yeast_mfg_date': '2026-05-01',
        'yeast_open_date': '2026-09-01', 'yeast_generation': 3,
    }).get_json()
    # Requête de l'appli Android (InventoryPost)
    r = client.put(f'/api/inventory/{item["id"]}', json={
        'name': 'US-05', 'category': 'levure', 'quantity': 2, 'unit': 'sachet',
        'origin': None, 'ebc': None, 'alpha': None, 'min_stock': 1, 'price_per_unit': 3.5, 'notes': None,
    })
    assert r.status_code == 200
    it = r.get_json()
    assert (it['quantity'], it['min_stock'], it['expiry_date'], it['yeast_type'],
            it['yeast_mfg_date'], it['yeast_open_date'], it['yeast_generation']) == \
           (2, 1, '2027-05-01', 'sec', '2026-05-01', '2026-09-01', 3)


def test_put_null_explicite_efface_la_peremption(client, malt_item):
    client.put(f'/api/inventory/{malt_item["id"]}', json={**malt_item, 'expiry_date': '2027-01-01'})
    r = client.put(f'/api/inventory/{malt_item["id"]}', json={**malt_item, 'expiry_date': None})
    assert r.get_json()['expiry_date'] is None
