"""Tests d'intégration — planification des notifications Telegram."""
import json


def _job_ids(client):
    return {j['id'] for j in client.get('/api/admin/scheduler-jobs').get_json()['jobs']}


def test_reschedule_registers_brew_steps_job(client):
    r = client.put('/api/app-settings', json={
        'telegram_token': 'tok',
        'telegram_chat_id': 'chat',
    })
    assert r.status_code == 200
    assert 'tg_brew_steps' in _job_ids(client)


def test_reschedule_survives_non_dict_notifs(client):
    """telegram_notifs peut contenir n'importe quel JSON valide - une valeur
    qui n'est PAS un objet (ex. une liste, suite à une corruption) ne doit
    pas empêcher tg_brew_steps (ni les autres) de se (re)planifier."""
    r = client.put('/api/app-settings', json={
        'telegram_token': 'tok',
        'telegram_chat_id': 'chat',
        'telegram_notifs': '[]',
    })
    assert r.status_code == 200
    assert 'tg_brew_steps' in _job_ids(client)


def test_reschedule_isolates_bad_notif_type_config(client):
    """Une config malformée pour UN type de notif (ex. 'hour' non numérique)
    ne doit faire échouer que ce type-là, pas empêcher les autres types (dont
    tg_brew_steps, enregistré en dernier) de se planifier derrière."""
    r = client.put('/api/app-settings', json={
        'telegram_token': 'tok',
        'telegram_chat_id': 'chat',
        'telegram_notifs': json.dumps({'brews': {'enabled': True, 'hour': 'oops'}}),
    })
    assert r.status_code == 200
    jobs = _job_ids(client)
    assert 'tg_brews' not in jobs       # config cassée pour ce type précis
    assert 'tg_brew_steps' in jobs      # pas d'effet domino sur les autres


def test_reschedule_removes_jobs_without_telegram_config(client):
    client.put('/api/app-settings', json={'telegram_token': 'tok', 'telegram_chat_id': 'chat'})
    assert 'tg_brew_steps' in _job_ids(client)
    client.put('/api/app-settings', json={'telegram_token': '', 'telegram_chat_id': ''})
    assert 'tg_brew_steps' not in _job_ids(client)


def test_scheduler_jobs_reports_missing_telegram_config(client):
    """Sans token/chat_id configurés, aucun job 'tg_*' ne doit apparaître -
    et le diagnostic doit le dire explicitement plutôt que de laisser
    deviner depuis une liste de jobs vide."""
    data = client.get('/api/admin/scheduler-jobs').get_json()
    assert data['telegram']['token_configured'] is False
    assert data['telegram']['chat_id_configured'] is False
    assert all(not j['id'].startswith('tg_') for j in data['jobs'])


def test_scheduler_jobs_reports_configured_telegram(client):
    client.put('/api/app-settings', json={'telegram_token': 'tok', 'telegram_chat_id': 'chat'})
    data = client.get('/api/admin/scheduler-jobs').get_json()
    assert data['telegram']['token_configured'] is True
    assert data['telegram']['chat_id_configured'] is True
