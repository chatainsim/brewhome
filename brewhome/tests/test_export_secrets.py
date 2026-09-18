"""L'export SQL ne doit jamais laisser sortir de secret.

Ce chemin a déjà divergé de la sauvegarde GitHub, qui purgeait pendant que
l'export laissait filer les jetons en clair. Les deux partagent désormais
`strip_secret_settings`, et ces tests verrouillent le comportement.
"""

import json

import db as db_module


def _export(client, monkeypatch):
    import blueprints.admin as admin
    # admin.py lie DB_PATH à l'import ; on le recale sur la base du test,
    # sinon l'export viserait la base d'un test précédent.
    monkeypatch.setattr(admin, 'DB_PATH', db_module.DB_PATH)
    resp = client.get(f'/api/admin/export-sql?token={admin.EXPORT_TOKEN}')
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_sql_export_strips_plain_secrets(client, monkeypatch):
    client.put('/api/app-settings', json={
        'telegram_token': 'tg-secret-value',
        'ai_api_key':     'ai-secret-value',
        'gh_data_pat':    'ghp-secret-value',
        'gh_vitrine_pat': 'ghp-vitrine-secret',
        'app_name':       'BrewHome',
    })

    dump = _export(client, monkeypatch)

    for secret in ('tg-secret-value', 'ai-secret-value',
                   'ghp-secret-value', 'ghp-vitrine-secret'):
        assert secret not in dump
    # Les réglages non sensibles restent exportés : la purge doit être ciblée.
    assert 'BrewHome' in dump


def test_sql_export_strips_pats_nested_in_targets(client, monkeypatch):
    client.put('/api/app-settings', json={
        'gh_data_targets': json.dumps([
            {'repo': 'moi/sauvegarde', 'pat': 'ghp-nested-secret', 'branch': 'main'},
        ]),
    })

    dump = _export(client, monkeypatch)

    assert 'ghp-nested-secret' not in dump
    # Le reste de la cible survit : on purge le jeton, pas la configuration.
    assert 'moi/sauvegarde' in dump


def test_sql_export_drops_targets_it_cannot_parse(client, monkeypatch):
    """Un JSON illisible pourrait cacher un jeton : on préfère perdre le
    réglage que le laisser passer."""
    client.put('/api/app-settings', json={
        'gh_data_targets': 'pas du json {{{ ghp-hidden-secret',
    })

    dump = _export(client, monkeypatch)

    assert 'ghp-hidden-secret' not in dump


def test_sql_export_requires_the_token(client):
    assert client.get('/api/admin/export-sql').status_code == 403
    assert client.get('/api/admin/export-sql?token=mauvais').status_code == 403
