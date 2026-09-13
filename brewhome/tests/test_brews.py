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


# ── Étapes de brassin ───────────────────────────────────────────────────────────

def test_add_brew_step(client, brew):
    r = client.post(f'/api/brews/{brew["id"]}/steps', json={
        'scheduled_date': '2025-01-20', 'title': 'Ajout houblon',
    })
    assert r.status_code == 201
    data = r.get_json()
    assert data['scheduled_date'] == '2025-01-20'
    assert data['title'] == 'Ajout houblon'
    assert data['telegram_notify'] == 1


def test_add_brew_step_missing_field(client, brew):
    r = client.post(f'/api/brews/{brew["id"]}/steps', json={'title': 'Ajout houblon'})
    assert r.status_code == 400


def test_add_brew_step_brew_not_found(client):
    r = client.post('/api/brews/9999/steps', json={
        'scheduled_date': '2025-01-20', 'title': 'Ajout houblon',
    })
    assert r.status_code == 404


def test_notify_new_brew_step_skips_without_telegram_config(client, brew):
    """Sans token/chat_id configurés (cas par défaut des tests), l'ajout
    d'une étape ne doit pas planter même si sa date est aujourd'hui."""
    from datetime import date
    r = client.post(f'/api/brews/{brew["id"]}/steps', json={
        'scheduled_date': date.today().isoformat(), 'title': 'Brassage',
    })
    assert r.status_code == 201


def test_notify_new_brew_step_if_due(monkeypatch):
    """Coeur du correctif : une étape créée pour AUJOURD'HUI après l'heure du
    rappel quotidien (8h) doit être rattrapée immédiatement (le job une-fois-
    par-jour ne la reverra jamais, sa date planifiée ne sera déjà plus
    "aujourd'hui" à son prochain passage) ; avant 8h, on laisse le job normal
    s'en charger pour ne pas notifier en double."""
    from datetime import datetime, timezone
    from blueprints import integrations

    sent = []
    monkeypatch.setattr(integrations, '_tg_get_settings', lambda: ('tok', 'chat', {}, 'UTC'))
    monkeypatch.setattr(integrations, '_tg_send', lambda token, chat_id, text: sent.append(text))

    # "Aujourd'hui" du point de vue du test = la date mockée ci-dessous
    # (2025-01-20), pas la vraie date du jour - scheduled_date doit y
    # correspondre pour tomber dans le cas "prevu aujourd'hui".
    step = {'id': 1, 'title': 'Ajout houblon', 'notes': None, 'scheduled_date': '2025-01-20', 'telegram_notify': 1}

    # Après 8h → rattrapage immédiat.
    monkeypatch.setattr(
        integrations, 'datetime',
        type('_DT', (), {'now': staticmethod(lambda tz=None: datetime(2025, 1, 20, 9, 0, tzinfo=timezone.utc))}),
    )
    integrations.notify_new_brew_step_if_due(step, 'Brassin Test')
    assert len(sent) == 1
    assert 'Ajout houblon' in sent[0]

    # Avant 8h → le job quotidien s'en charge, pas de doublon ici.
    sent.clear()
    monkeypatch.setattr(
        integrations, 'datetime',
        type('_DT', (), {'now': staticmethod(lambda tz=None: datetime(2025, 1, 20, 7, 0, tzinfo=timezone.utc))}),
    )
    integrations.notify_new_brew_step_if_due(step, 'Brassin Test')
    assert sent == []

    # telegram_notify désactivé → jamais de notification, quelle que soit l'heure.
    monkeypatch.setattr(
        integrations, 'datetime',
        type('_DT', (), {'now': staticmethod(lambda tz=None: datetime(2025, 1, 20, 9, 0, tzinfo=timezone.utc))}),
    )
    integrations.notify_new_brew_step_if_due({**step, 'telegram_notify': 0}, 'Brassin Test')
    assert sent == []


# ── Déduction de stock du dry hop ─────────────────────────────────────────────

def _inv_qty(client, item_id):
    for it in client.get('/api/inventory').get_json():
        if it['id'] == item_id:
            return it['quantity']
    return None


@pytest.fixture()
def dryhop_recipe(client):
    """Houblon en stock (100 g) + recette avec un dry hop lié (50 g, J-3, ferm 14 j)."""
    hop = client.post('/api/inventory', json={
        'name': 'Citra', 'category': 'houblon', 'quantity': 100.0, 'unit': 'g',
    }).get_json()
    recipe = client.post('/api/recipes', json={
        'name': 'NEIPA Test', 'volume': 20, 'ferm_time': 14,
        'ingredients': [{
            'inventory_item_id': hop['id'], 'name': 'Citra', 'category': 'houblon',
            'quantity': 50, 'unit': 'g', 'hop_type': 'dryhop', 'hop_days': 3,
        }],
    }).get_json()
    return {'hop_id': hop['id'], 'recipe': recipe}


def test_dryhop_not_deducted_at_brew_creation(client, dryhop_recipe):
    """Le dry hop ne doit PAS être déduit le jour du brassage."""
    r = client.post('/api/brews', json={
        'recipe_id': dryhop_recipe['recipe']['id'],
        'name': 'Brassin DH', 'brew_date': '2025-01-01',
        'deduct_stock': True,
    })
    assert r.status_code == 201
    assert _inv_qty(client, dryhop_recipe['hop_id']) == 100.0


def test_dryhop_deducted_when_marked_done(client, dryhop_recipe):
    """Marquer le dry hop fait déduit la quantité du stock, une seule fois."""
    brew = client.post('/api/brews', json={
        'recipe_id': dryhop_recipe['recipe']['id'],
        'name': 'Brassin DH', 'brew_date': '2025-01-01',
        'deduct_stock': True,
    }).get_json()
    # date du dry hop = brew_date + (ferm_time - hop_days) = 2025-01-01 + 11 j
    r = client.post(f'/api/brews/{brew["id"]}/dryhop_done', json={'date': '2025-01-12'})
    assert r.status_code == 200
    assert len(r.get_json()['deducted']) == 1
    assert _inv_qty(client, dryhop_recipe['hop_id']) == 50.0
    # Re-cliquer sur la même date ne re-déduit pas
    r2 = client.post(f'/api/brews/{brew["id"]}/dryhop_done', json={'date': '2025-01-12'})
    assert r2.get_json()['deducted'] == []
    assert _inv_qty(client, dryhop_recipe['hop_id']) == 50.0


def test_dryhop_wrong_date_no_deduction(client, dryhop_recipe):
    """Valider une date qui ne correspond à aucun dry hop ne déduit rien."""
    brew = client.post('/api/brews', json={
        'recipe_id': dryhop_recipe['recipe']['id'],
        'name': 'Brassin DH', 'brew_date': '2025-01-01',
        'deduct_stock': True,
    }).get_json()
    r = client.post(f'/api/brews/{brew["id"]}/dryhop_done', json={'date': '2025-06-30'})
    assert r.status_code == 200
    assert r.get_json()['deducted'] == []
    assert _inv_qty(client, dryhop_recipe['hop_id']) == 100.0


def test_dryhop_done_invalid_date(client, brew):
    r = client.post(f'/api/brews/{brew["id"]}/dryhop_done', json={'date': 'pas-une-date'})
    assert r.status_code == 400
