def test_secret_keys_masked_on_get(client):
    resp = client.put('/api/app-settings', json={
        'telegram_token': 'secret-tg-token',
        'ai_api_key': 'secret-ai-key',
        'theme_mode': 'dark',
    })
    assert resp.status_code == 200

    resp = client.get('/api/app-settings')
    data = resp.get_json()
    assert data['telegram_token'] == '***'
    assert data['ai_api_key'] == '***'
    # Une clé non sensible n'est pas masquée
    assert data['theme_mode'] == 'dark'


def test_saving_masked_placeholder_does_not_overwrite_secret(client):
    client.put('/api/app-settings', json={'telegram_token': 'secret-tg-token'})

    # Le client renvoie tel quel le placeholder reçu au GET précédent (cas normal :
    # l'utilisateur modifie un autre réglage sans toucher au champ token)
    resp = client.put('/api/app-settings', json={'telegram_token': '***'})
    assert resp.status_code == 200

    resp = client.get('/api/app-settings')
    # La vraie valeur doit être préservée, pas écrasée par le littéral '***'
    assert resp.get_json()['telegram_token'] == '***'  # toujours masquée au GET...
    from db import get_db
    with client.application.app_context():
        with get_db() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key='telegram_token'"
            ).fetchone()
    assert row['value'] == 'secret-tg-token'  # ...mais la vraie valeur est intacte en base
