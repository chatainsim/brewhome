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


def _stored(client, key):
    from db import get_db
    with client.application.app_context():
        with get_db() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row['value'] if row else None


def test_sync_from_device_without_secret_keeps_it(client):
    """Bug : un autre appareil (sans le jeton en local, le serveur ne renvoyant
    que '***') synchronise tous ses réglages avec telegram_token=null → le jeton
    était supprimé et toutes les notifications Telegram cessaient en silence."""
    client.put('/api/app-settings', json={'telegram_token': 'secret-tg-token', 'telegram_chat_id': '42',
                                          'ai_api_key': 'secret-ai', 'gh_data_pat': 'ghp_x'})
    resp = client.put('/api/app-settings', json={'telegram_token': None, 'telegram_chat_id': '42',
                                                 'ai_api_key': '', 'gh_data_pat': None, 'theme_mode': 'dark'})
    assert resp.status_code == 200
    assert _stored(client, 'telegram_token') == 'secret-tg-token'
    assert _stored(client, 'ai_api_key') == 'secret-ai'
    assert _stored(client, 'gh_data_pat') == 'ghp_x'
    assert _stored(client, 'theme_mode') == 'dark'
    # Un réglage ordinaire envoyé à null reste supprimé, comme avant
    client.put('/api/app-settings', json={'theme_mode': None})
    assert _stored(client, 'theme_mode') is None


def test_notifications_still_scheduled_after_sync_without_token(client):
    from scheduler import _scheduler
    import json
    client.put('/api/app-settings', json={
        'telegram_token': '123:abc', 'telegram_chat_id': '42', 'telegram_tz': 'Europe/Paris',
        'telegram_notifs': json.dumps({'brews': {'enabled': True, 'hour': 8, 'minute': 0}})})
    assert _scheduler.get_job('tg_brews') is not None
    client.put('/api/app-settings', json={'telegram_token': None, 'telegram_chat_id': '42',
                                          'telegram_notifs': json.dumps({'brews': {'enabled': True, 'hour': 8, 'minute': 0}})})
    assert _scheduler.get_job('tg_brews') is not None
    assert _scheduler.get_job('tg_brew_steps') is not None


def test_db_error_keeps_existing_jobs_and_retries(client, monkeypatch):
    from scheduler import _scheduler
    import json
    import blueprints.integrations as integ
    client.put('/api/app-settings', json={
        'telegram_token': '123:abc', 'telegram_chat_id': '42',
        'telegram_notifs': json.dumps({'brews': {'enabled': True, 'hour': 8, 'minute': 0}})})
    assert _scheduler.get_job('tg_brews') is not None

    def locked():
        raise RuntimeError('database is locked')
    monkeypatch.setattr(integ, 'get_db', locked)
    with client.application.app_context():
        integ.reschedule_telegram()
    assert _scheduler.get_job('tg_brews') is not None           # pas retiré
    assert _scheduler.get_job('tg_reschedule_retry') is not None  # nouvel essai prévu
    _scheduler.remove_job('tg_reschedule_retry')


def test_late_jobs_are_not_dropped():
    from scheduler import _scheduler
    assert _scheduler._job_defaults['misfire_grace_time'] >= 600
    assert _scheduler._job_defaults['coalesce'] is True


def test_telegram_test_uses_stored_token_when_device_has_none(client, monkeypatch):
    import blueprints.integrations as integ
    sent = []
    monkeypatch.setattr(integ, '_tg_send', lambda token, chat, msg: sent.append((token, chat)))
    client.put('/api/app-settings', json={'telegram_token': 'stored-token', 'telegram_chat_id': '42'})
    resp = client.post('/api/telegram/test', json={'token': '', 'chat_id': '42'})
    assert resp.status_code == 200 and sent == [('stored-token', '42')]
