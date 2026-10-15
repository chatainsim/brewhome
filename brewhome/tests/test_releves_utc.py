"""Relevés de fermentation en UTC : ceux des densimètres et des sondes l'étaient déjà, les
relevés manuels étaient stockés à l'heure locale — décalage d'1 à 2 h quand les deux se
mélangeaient (courbe, dernier relevé, widget de l'appli)."""

import pytest

import db as db_module


@pytest.fixture()
def brew(client):
    recipe = client.post('/api/recipes', json={'name': 'Recette Test', 'volume': 20}).get_json()
    return client.post('/api/brews', json={'recipe_id': recipe['id'], 'name': 'Brassin Test',
                                           'deduct_stock': False}).get_json()


def _fuseau(tz):
    with db_module.get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('telegram_tz', ?)", (tz,))


def _stockes(brew_id):
    with db_module.get_db() as conn:
        return [r[0] for r in conn.execute(
            'SELECT recorded_at FROM brew_fermentation_readings WHERE brew_id=? ORDER BY id', (brew_id,))]


def test_saisie_convertie_en_utc(client, brew):
    _fuseau('Europe/Paris')
    url = f'/api/brews/{brew["id"]}/fermentation'
    for ts in ('2026-10-13T18:14',            # formulaire / ancienne appli : heure locale (été, UTC+2)
               '2026-01-15 10:00:00',         # hiver, UTC+1
               '2026-10-13T16:14:00.000Z',    # site : toISOString()
               '2026-10-13T18:14:00+02:00'):  # appli : heure avec décalage
        assert client.post(url, json={'recorded_at': ts, 'gravity': 1.02}).status_code == 201
    assert _stockes(brew['id']) == ['2026-10-13 16:14:00', '2026-01-15 09:00:00',
                                    '2026-10-13 16:14:00', '2026-10-13 16:14:00']
    assert client.post(url, json={'recorded_at': 'hier', 'gravity': 1.02}).status_code == 400


def test_sans_fuseau_regle_heure_gardee(client, brew):
    client.post(f'/api/brews/{brew["id"]}/fermentation', json={'recorded_at': '2026-10-13T18:14', 'gravity': 1.02})
    assert _stockes(brew['id']) == ['2026-10-13 18:14:00']


def test_migration_des_releves_manuels_existants(app, brew):
    with db_module.get_db() as conn:
        conn.execute("DELETE FROM app_settings WHERE key='manual_readings_utc'")
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('telegram_tz', 'Europe/Paris')")
        conn.executemany(
            'INSERT INTO brew_fermentation_readings (brew_id, recorded_at, gravity, source) VALUES (?,?,?,?)',
            [(brew['id'], '2026-04-23T17:31', 1.01, 'manual'),
             (brew['id'], '2026-04-23 15:00:00', 1.02, 'spindle')])   # déjà en UTC : intact
    with app.app_context():
        db_module.migrate_db()
        db_module.migrate_db()                                          # une seule conversion
    assert _stockes(brew['id']) == ['2026-04-23 15:31:00', '2026-04-23 15:00:00']
