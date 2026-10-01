"""Tests d'intégration — brouillons (/api/drafts) : ordre stable et archivage."""


def _new(client, title):
    r = client.post('/api/drafts', json={'title': title})
    assert r.status_code in (200, 201)
    return r.get_json()


def _titles(client, qs=''):
    return [d['title'] for d in client.get('/api/drafts' + qs).get_json()]


def test_ordre_stable_apres_modification(client):
    a, b, c = (_new(client, t) for t in ('A', 'B', 'C'))
    assert _titles(client) == ['C', 'B', 'A']          # plus récents d'abord
    # Modifier un brouillon (date de modification changée) ne le déplace plus
    client.put(f"/api/drafts/{a['id']}", json={'title': 'A', 'notes': 'modifié'})
    assert _titles(client) == ['C', 'B', 'A']


def test_ordre_manuel_respecte(client):
    a, b, c = (_new(client, t) for t in ('A', 'B', 'C'))
    client.put('/api/drafts/reorder', json=[
        {'id': a['id'], 'sort_order': 0}, {'id': c['id'], 'sort_order': 1}, {'id': b['id'], 'sort_order': 2}])
    client.put(f"/api/drafts/{b['id']}", json={'title': 'B', 'notes': 'x'})
    assert _titles(client) == ['A', 'C', 'B']


def test_archiver_puis_desarchiver(client):
    a, b = _new(client, 'A'), _new(client, 'B')
    before = client.get('/api/drafts').get_json()[1]['updated_at']

    r = client.put(f"/api/drafts/{a['id']}/archive", json={'archived': True})
    assert r.status_code == 200
    assert r.get_json()['archived'] == 1 and r.get_json()['archived_at']
    assert _titles(client) == ['B']                    # masqué de la liste (et de l'appli Android)
    assert _titles(client, '?archived=1') == ['A']
    assert sorted(_titles(client, '?archived=all')) == ['A', 'B']

    r = client.put(f"/api/drafts/{a['id']}/archive", json={'archived': False})
    assert r.get_json()['archived'] == 0 and r.get_json()['archived_at'] is None
    assert r.get_json()['updated_at'] == before         # le contenu n'est pas « modifié »
    assert _titles(client) == ['B', 'A']
    assert _titles(client, '?archived=1') == []


def test_archiver_brouillon_inconnu(client):
    assert client.put('/api/drafts/999/archive', json={'archived': True}).status_code == 404


def test_modifier_ne_desarchive_pas(client):
    a = _new(client, 'A')
    client.put(f"/api/drafts/{a['id']}/archive", json={'archived': True})
    client.put(f"/api/drafts/{a['id']}", json={'title': 'A', 'notes': 'x'})
    assert _titles(client, '?archived=1') == ['A']


def test_export_import_garde_l_archivage(client):
    a, _b = _new(client, 'A'), _new(client, 'B')
    client.put(f"/api/drafts/{a['id']}/archive", json={'archived': True})
    exported = client.get('/api/export/drafts').get_json()
    assert {d['title']: d['archived'] for d in exported} == {'A': 1, 'B': 0}

    r = client.post('/api/import/drafts', json={'mode': 'replace', 'items': exported})
    assert r.status_code == 200
    assert _titles(client) == ['B']
    assert _titles(client, '?archived=1') == ['A']


def test_import_ancien_fichier_garde_l_etat_actuel(client):
    a = _new(client, 'A')
    client.put(f"/api/drafts/{a['id']}/archive", json={'archived': True})
    # Fichier exporté avant l'archivage : pas de champ archived
    client.post('/api/import/drafts', json=[{'title': 'A', 'notes': 'importé'}, {'title': 'N'}])
    assert _titles(client, '?archived=1') == ['A']
    assert _titles(client) == ['N']


def test_image_etrangere_jamais_rattachee(client, app):
    """#22 : seule une image de brouillon générée par le serveur peut être rattachée."""
    import os
    import db as db_module
    os.makedirs(db_module.PHOTOS_DIR, exist_ok=True)
    foreign = os.path.join(db_module.PHOTOS_DIR, 'beer_photo_test.jpg')
    open(foreign, 'wb').write(b'x')
    try:
        a = _new(client, 'A')
        r = client.put(f"/api/drafts/{a['id']}", json={
            'title': 'A', 'images': '["/api/draft-images/beer_photo_test.jpg"]'})
        assert r.get_json()['images'] == '[]'
        client.delete(f"/api/drafts/{a['id']}")
        assert os.path.exists(foreign)
    finally:
        os.remove(foreign)
