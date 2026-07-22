"""Tests — vérification de version (/api/version/check) et son cache."""
import io
import json
import time

import pytest

import blueprints.admin as admin


@pytest.fixture(autouse=True)
def _reset_cache():
    """Le cache est un dict de module : le vider avant/après chaque test."""
    admin._version_cache.update({'github': None, 'ts': 0})
    yield
    admin._version_cache.update({'github': None, 'ts': 0})


def _fake_urlopen(tag, counter):
    """Remplace urllib.request.urlopen et compte les appels réseau."""
    def _open(req, timeout=None):
        counter['n'] += 1
        payload = json.dumps({
            'tag_name': tag,
            'html_url': f'https://github.com/chatainsim/brewhome/releases/tag/{tag}',
        }).encode()
        stream = io.BytesIO(payload)
        stream.__enter__ = lambda: stream
        stream.__exit__ = lambda *a: None
        return stream
    return _open


def test_reports_latest_tag(client, monkeypatch):
    counter = {'n': 0}
    monkeypatch.setattr(admin.urllib.request, 'urlopen', _fake_urlopen('9.9.9', counter))
    d = client.get('/api/version/check').get_json()
    assert d['latest'] == '9.9.9'
    assert d['current'] == admin.APP_VERSION
    assert d['update_available'] is True


def test_no_update_when_same_version(client, monkeypatch):
    counter = {'n': 0}
    monkeypatch.setattr(admin.urllib.request, 'urlopen',
                        _fake_urlopen(admin.APP_VERSION, counter))
    assert client.get('/api/version/check').get_json()['update_available'] is False


def test_second_call_uses_cache(client, monkeypatch):
    """Sans force, un 2e appel ne doit pas retoucher le réseau."""
    counter = {'n': 0}
    monkeypatch.setattr(admin.urllib.request, 'urlopen', _fake_urlopen('9.9.9', counter))
    client.get('/api/version/check')
    client.get('/api/version/check')
    assert counter['n'] == 1


def test_force_bypasses_cache(client, monkeypatch):
    """?force=1 doit refaire l'appel réseau — c'est le bouton « Vérifier à nouveau »."""
    counter = {'n': 0}
    monkeypatch.setattr(admin.urllib.request, 'urlopen', _fake_urlopen('9.9.9', counter))
    client.get('/api/version/check')
    client.get('/api/version/check?force=1')
    assert counter['n'] == 2


def test_force_sees_newly_published_release(client, monkeypatch):
    """Le cas réel : une release publiée après une 1re vérification."""
    counter = {'n': 0}
    monkeypatch.setattr(admin.urllib.request, 'urlopen',
                        _fake_urlopen(admin.APP_VERSION, counter))
    assert client.get('/api/version/check').get_json()['update_available'] is False

    monkeypatch.setattr(admin.urllib.request, 'urlopen', _fake_urlopen('9.9.9', counter))
    # sans force : toujours la valeur en cache
    assert client.get('/api/version/check').get_json()['latest'] == admin.APP_VERSION
    # avec force : la nouvelle release est vue
    d = client.get('/api/version/check?force=1').get_json()
    assert d['latest'] == '9.9.9'
    assert d['update_available'] is True


def test_error_is_cached_only_briefly(client, monkeypatch):
    """Un échec réseau ne doit pas aveugler la détection 6 h."""
    def _boom(req, timeout=None):
        raise OSError('réseau indisponible')
    monkeypatch.setattr(admin.urllib.request, 'urlopen', _boom)
    d = client.get('/api/version/check').get_json()
    assert d['latest'] is None
    assert d['update_available'] is False

    # Simule l'expiration du TTL court des erreurs, puis un réseau revenu
    admin._version_cache['ts'] = time.time() - (admin._VERSION_TTL_ERR + 1)
    counter = {'n': 0}
    monkeypatch.setattr(admin.urllib.request, 'urlopen', _fake_urlopen('9.9.9', counter))
    assert client.get('/api/version/check').get_json()['latest'] == '9.9.9'


def test_success_is_cached_long(client, monkeypatch):
    """À l'inverse, un succès reste en cache bien au-delà du TTL d'erreur."""
    counter = {'n': 0}
    monkeypatch.setattr(admin.urllib.request, 'urlopen', _fake_urlopen('9.9.9', counter))
    client.get('/api/version/check')
    admin._version_cache['ts'] = time.time() - (admin._VERSION_TTL_ERR + 1)
    client.get('/api/version/check')
    assert counter['n'] == 1
