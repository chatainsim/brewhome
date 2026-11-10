"""PAT imbriqués dans gh_data_targets / gh_vitrine_targets : jamais renvoyés au navigateur, jamais écrasés par
le '***' qu'il renvoie, et sauvegarde manuelle faite par le serveur."""
import json

from db import get_db


def _stored(client, key):
    with client.application.app_context():
        with get_db() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return json.loads(row['value']) if row else None


def _targets(*items):
    return json.dumps([{'provider': 'github', 'apiUrl': '', 'branch': 'main', **t} for t in items])


def test_nested_pats_masked_on_get(client):
    client.put('/api/app-settings', json={'gh_data_targets': _targets({'repo': 'a/b', 'pat': 'ghp_secret1'}),
                                          'gh_vitrine_targets': _targets({'repo': 'a/a.github.io', 'pat': 'ghp_s2'})})
    data = client.get('/api/app-settings').get_json()
    assert 'ghp_' not in json.dumps(data)
    assert json.loads(data['gh_data_targets'])[0] == {'provider': 'github', 'apiUrl': '', 'branch': 'main',
                                                      'repo': 'a/b', 'pat': '***'}
    assert json.loads(data['gh_vitrine_targets'])[0]['repo'] == 'a/a.github.io'   # l'appli Android s'en sert


def test_masked_pat_sent_back_keeps_stored_one(client):
    client.put('/api/app-settings', json={'gh_data_targets': _targets({'repo': 'a/b', 'pat': 'ghp_one'},
                                                                      {'repo': 'c/d', 'pat': 'ghp_two'})})
    renvoye = client.get('/api/app-settings').get_json()['gh_data_targets']
    # l'utilisateur inverse l'ordre, change une branche et ajoute une cible sans PAT
    cibles = json.loads(renvoye)[::-1]
    cibles[0]['branch'] = 'dev'
    cibles.append({'provider': 'github', 'apiUrl': '', 'branch': 'main', 'repo': 'e/f', 'pat': ''})
    client.put('/api/app-settings', json={'gh_data_targets': json.dumps(cibles)})
    stored = _stored(client, 'gh_data_targets')
    assert [(t['repo'], t.get('pat'), t['branch']) for t in stored] == [
        ('c/d', 'ghp_two', 'dev'), ('a/b', 'ghp_one', 'main'), ('e/f', None, 'main')]


def test_new_pat_replaces_old(client):
    client.put('/api/app-settings', json={'gh_data_targets': _targets({'repo': 'a/b', 'pat': 'ghp_old'})})
    client.put('/api/app-settings', json={'gh_data_targets': _targets({'repo': 'a/b', 'pat': 'ghp_new'})})
    assert _stored(client, 'gh_data_targets')[0]['pat'] == 'ghp_new'


def test_renamed_repo_keeps_pat_by_position(client):
    client.put('/api/app-settings', json={'gh_data_targets': _targets({'repo': 'a/b', 'pat': 'ghp_x'})})
    client.put('/api/app-settings', json={'gh_data_targets': _targets({'repo': 'a/renomme', 'pat': '***'})})
    assert _stored(client, 'gh_data_targets')[0]['pat'] == 'ghp_x'


def test_git_proxy_removed(client):
    assert client.post('/api/git-proxy', json={'url': 'https://api.github.com/x', 'pat': 'p'}).status_code in (404, 405)


def test_manual_backup_needs_target(client):
    assert client.post('/api/github/backup', json={}).status_code == 400


def test_manual_backup_pushed_by_server(client, monkeypatch):
    import blueprints.integrations as integ
    pushes = []

    def fake_push(repo, pat, branch, path, content, msg, api_base=None):
        pushes.append((repo, pat, path))
        return path != 'cave.json'
    monkeypatch.setattr(integ, '_gh_push_file', fake_push)
    client.put('/api/app-settings', json={'gh_data_targets': _targets({'repo': 'a/b', 'pat': 'ghp_srv'})})
    res = client.post('/api/github/backup', json={})
    assert res.status_code == 200
    body = res.get_json()
    assert body['skipped'] == 1 and body['pushed'] == len(pushes) - 1 and body['errors'] == 0
    assert all(p[1] == 'ghp_srv' and not p[2].startswith('backup_auto/') for p in pushes)
    assert 'ghp_srv' not in json.dumps(body)
