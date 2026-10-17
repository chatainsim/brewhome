"""Nettoyage du graphe de fermentation, et refus de relier une sonde à un
brassin terminé.

Une sonde de température reliée à un brassin déjà terminé continue d'y
déverser des relevés : la courbe de fermentation s'allonge de mois de
température de cuve qui n'ont rien à voir avec elle. Le garde-fou empêche le
cas, le nettoyage répare celui qui s'est déjà produit — l'ancien endpoint de
suppression ne portait que sur les mesures saisies à la main.
"""

import sqlite3

import pytest

import db as db_module


def _brassin(client, statut='fermenting', nom='Essai'):
    """Un brassin rattaché à une recette : la clé étrangère l'exige."""
    with db_module.get_db() as conn:
        rid = conn.execute("SELECT id FROM recipes LIMIT 1").fetchone()
        if not rid:
            rid = [conn.execute("INSERT INTO recipes (name) VALUES ('Recette test')").lastrowid]
        cur = conn.execute('INSERT INTO brews (recipe_id, name, status) VALUES (?, ?, ?)',
                           (rid[0], nom, statut))
        return cur.lastrowid


def _releves(brew_id, source, n, jour='2026-09-04'):
    with db_module.get_db() as conn:
        conn.executemany(
            'INSERT INTO brew_fermentation_readings (brew_id, recorded_at, temperature, source) '
            'VALUES (?,?,?,?)',
            [(brew_id, f'{jour} {h:02d}:00:00', 20.0, source) for h in range(n)])


# ── Garde-fou ────────────────────────────────────────────────────────────

def test_une_sonde_ne_peut_pas_etre_reliee_a_un_brassin_termine(client):
    termine = _brassin(client, 'completed', 'Fini')
    sonde = client.post('/api/temperature', json={'name': 'Cuve'}).get_json()
    r = client.patch(f'/api/temperature/{sonde["id"]}', json={'brew_id': termine})
    assert r.status_code == 400
    assert 'terminé' in r.get_json()['detail']


def test_une_sonde_peut_etre_reliee_a_un_brassin_en_cours(client):
    actif = _brassin(client, 'fermenting')
    sonde = client.post('/api/temperature', json={'name': 'Cuve'}).get_json()
    assert client.patch(f'/api/temperature/{sonde["id"]}', json={'brew_id': actif}).status_code == 200


def test_un_densimetre_non_plus(client):
    termine = _brassin(client, 'completed')
    sp = client.post('/api/spindles', json={'name': 'iSpindel'}).get_json()
    assert client.patch(f'/api/spindles/{sp["id"]}', json={'brew_id': termine}).status_code == 400


def test_detacher_une_sonde_reste_possible(client):
    # Le garde-fou ne doit pas empêcher de retirer une association.
    actif = _brassin(client, 'fermenting')
    sonde = client.post('/api/temperature', json={'name': 'Cuve'}).get_json()
    client.patch(f'/api/temperature/{sonde["id"]}', json={'brew_id': actif})
    assert client.patch(f'/api/temperature/{sonde["id"]}', json={'brew_id': None}).status_code == 200


# ── Nettoyage ────────────────────────────────────────────────────────────

def test_origines_des_releves(client):
    b = _brassin(client)
    _releves(b, 'spindle', 5)
    _releves(b, 'temp_sensor', 8)
    sources = {s['source']: s['count'] for s in
               client.get(f'/api/brews/{b}/fermentation/sources').get_json()}
    assert sources == {'spindle': 5, 'temp_sensor': 8}


def test_supprimer_une_origine_laisse_les_autres(client):
    b = _brassin(client)
    _releves(b, 'spindle', 5)
    _releves(b, 'temp_sensor', 8)
    r = client.delete(f'/api/brews/{b}/fermentation', json={'source': 'temp_sensor'})
    assert r.get_json()['deleted'] == 8
    assert {s['source']: s['count'] for s in
            client.get(f'/api/brews/{b}/fermentation/sources').get_json()} == {'spindle': 5}


def test_une_requete_sans_filtre_ne_vide_rien(client):
    b = _brassin(client)
    _releves(b, 'spindle', 5)
    assert client.delete(f'/api/brews/{b}/fermentation', json={}).status_code == 400
    assert len(client.get(f'/api/brews/{b}/fermentation').get_json()) == 5


def test_tout_supprimer_demande_a_etre_explicite(client):
    b = _brassin(client)
    _releves(b, 'spindle', 5)
    assert client.delete(f'/api/brews/{b}/fermentation', json={'all': True}).get_json()['deleted'] == 5


def test_la_borne_de_fin_inclut_sa_journee(client):
    # Les horodatages portent l'heure : « <= 2026-09-04 » exclurait tout
    # relevé de ce jour-là, ce qui rendrait un filtre par date inopérant.
    b = _brassin(client)
    _releves(b, 'spindle', 6, jour='2026-09-04')
    _releves(b, 'spindle', 3, jour='2026-09-05')
    r = client.delete(f'/api/brews/{b}/fermentation',
                      json={'from': '2026-09-04', 'to': '2026-09-04'})
    assert r.get_json()['deleted'] == 6


def test_suppression_ciblee_par_identifiants(client):
    b = _brassin(client)
    _releves(b, 'spindle', 4)
    ids = [r['id'] for r in client.get(f'/api/brews/{b}/fermentation').get_json()][:2]
    assert client.delete(f'/api/brews/{b}/fermentation', json={'ids': ids}).get_json()['deleted'] == 2


def test_brassin_inexistant(client):
    assert client.delete('/api/brews/999999/fermentation', json={'all': True}).status_code == 404


# ── Liste filtrable, pour choisir les points à retirer ───────────────────

def test_liste_paginee(client):
    b = _brassin(client)
    _releves(b, 'spindle', 12)
    r = client.get(f'/api/brews/{b}/fermentation/readings?limit=5').get_json()
    assert r['total'] == 12 and len(r['rows']) == 5


def test_liste_filtree_par_origine(client):
    b = _brassin(client)
    _releves(b, 'spindle', 4)
    _releves(b, 'temp_sensor', 7)
    r = client.get(f'/api/brews/{b}/fermentation/readings?source=temp_sensor').get_json()
    assert r['total'] == 7
    assert {x['source'] for x in r['rows']} == {'temp_sensor'}


def test_liste_filtree_par_dates(client):
    b = _brassin(client)
    _releves(b, 'spindle', 5, jour='2026-09-10')
    _releves(b, 'spindle', 3, jour='2026-09-12')
    r = client.get(f'/api/brews/{b}/fermentation/readings?from=2026-09-12').get_json()
    assert r['total'] == 3


def test_la_liste_est_triee_du_plus_recent_au_plus_ancien(client):
    # L'utilisateur cherche d'abord ce qui vient d'être ajouté par erreur.
    b = _brassin(client)
    _releves(b, 'spindle', 3, jour='2026-09-10')
    rows = client.get(f'/api/brews/{b}/fermentation/readings').get_json()['rows']
    assert rows[0]['recorded_at'] > rows[-1]['recorded_at']


def test_supprimer_les_points_choisis(client):
    b = _brassin(client)
    _releves(b, 'spindle', 6)
    rows = client.get(f'/api/brews/{b}/fermentation/readings').get_json()['rows']
    choisis = [rows[0]['id'], rows[3]['id']]
    assert client.delete(f'/api/brews/{b}/fermentation', json={'ids': choisis}).get_json()['deleted'] == 2
    restants = [r['id'] for r in client.get(f'/api/brews/{b}/fermentation/readings').get_json()['rows']]
    assert not set(choisis) & set(restants)


def test_limite_de_pagination_bornee(client):
    b = _brassin(client)
    _releves(b, 'spindle', 2)
    # Une limite démesurée ne doit pas devenir un moyen de tout charger.
    r = client.get(f'/api/brews/{b}/fermentation/readings?limit=99999').get_json()
    assert r['total'] == 2
    assert client.get(f'/api/brews/{b}/fermentation/readings?limit=abc').status_code == 400


# ── Fermentation en cours : relevés en direct du densimètre relié ─────────

def _densimetre_relie(client, brew_id, n=4, jour='2026-10-10'):
    """Un densimètre relié au brassin, avec n relevés en direct (pas encore copiés dans le brassin)."""
    sp = client.post('/api/spindles', json={'name': 'iSpindel cuve'}).get_json()
    assert client.patch(f'/api/spindles/{sp["id"]}', json={'brew_id': brew_id}).status_code == 200
    with db_module.get_db() as conn:
        conn.executemany(
            'INSERT INTO rdb.spindle_readings (spindle_id, recorded_at, gravity, temperature) VALUES (?,?,?,?)',
            [(sp['id'], f'{jour} {h:02d}:00:00', 1.060 - h * 0.001 if h else 1.000, 19.0) for h in range(n)])
    return sp['id']


def _live(spindle_id):
    with db_module.get_db() as conn:
        return [r[0] for r in conn.execute(
            'SELECT recorded_at FROM rdb.spindle_readings WHERE spindle_id=? ORDER BY recorded_at', (spindle_id,))]


def test_releves_en_direct_listes_et_supprimables_pendant_la_fermentation(client):
    b = _brassin(client, 'fermenting')
    sp = _densimetre_relie(client, b)
    rows = client.get(f'/api/brews/{b}/fermentation/readings').get_json()
    assert rows['total'] == 4 and all(r['key'].startswith('s') and r['source'] == 'spindle' for r in rows['rows'])
    premier = min(rows['rows'], key=lambda r: r['recorded_at'])          # mesure prise hors de la cuve (1.000)
    assert premier['gravity'] == 1.000
    r = client.delete(f'/api/brews/{b}/fermentation', json={'keys': [premier['key']]})
    assert r.get_json() == {'deleted': 1, 'deleted_stored': 0}
    assert _live(sp) == ['2026-10-10 01:00:00', '2026-10-10 02:00:00', '2026-10-10 03:00:00']
    courbe = client.get(f'/api/brews/{b}/fermentation').get_json()
    assert [p['gravity'] for p in courbe] == [pytest.approx(1.059), pytest.approx(1.058), pytest.approx(1.057)]


def test_sources_comptent_les_releves_en_direct(client):
    b = _brassin(client, 'fermenting')
    _densimetre_relie(client, b, n=3)
    _releves(b, 'manual', 2)
    src = {s['source']: s['count'] for s in client.get(f'/api/brews/{b}/fermentation/sources').get_json()}
    assert src == {'spindle': 3, 'manual': 2}


def test_double_enregistre_et_en_direct_supprime_ensemble(client):
    """Relié à nouveau, un densimètre reçoit une copie des relevés enregistrés : le relevé existe en double,
    le graphe n'en montre qu'un — le supprimer doit faire disparaître les deux."""
    b = _brassin(client, 'fermenting')
    with db_module.get_db() as conn:
        conn.execute("INSERT INTO brew_fermentation_readings (brew_id, recorded_at, gravity, source) "
                     "VALUES (?, '2026-10-10 00:00:00', 1.000, 'spindle')", (b,))
    sp = _densimetre_relie(client, b, n=2)            # recopie + relevé en direct au même horodatage
    rows = client.get(f'/api/brews/{b}/fermentation/readings').get_json()['rows']
    assert sorted(r['recorded_at'] for r in rows) == ['2026-10-10 00:00:00', '2026-10-10 01:00:00']     # pas de doublon
    double = next(r for r in rows if r['recorded_at'] == '2026-10-10 00:00:00')
    assert double['key'].startswith('f')
    client.delete(f'/api/brews/{b}/fermentation', json={'keys': [double['key']]})
    assert '2026-10-10 00:00:00' not in _live(sp)
    assert [p['recorded_at'] for p in client.get(f'/api/brews/{b}/fermentation').get_json()] == ['2026-10-10 01:00:00']


def test_periode_et_autre_densimetre(client):
    b = _brassin(client, 'fermenting')
    autre = _brassin(client, 'fermenting', 'Autre')
    sp = _densimetre_relie(client, b, n=4)
    sp2 = _densimetre_relie(client, autre, n=4)
    r = client.delete(f'/api/brews/{b}/fermentation',
                      json={'from': '2026-10-10 00:00:00', 'to': '2026-10-10 01:30:00'})
    assert r.get_json()['deleted'] == 2
    assert len(_live(sp)) == 2 and len(_live(sp2)) == 4        # l'autre brassin n'est pas touché
    # une clé d'un relevé de l'autre densimètre ne supprime rien ici
    with db_module.get_db() as conn:
        rid = conn.execute('SELECT id FROM rdb.spindle_readings WHERE spindle_id=? LIMIT 1', (sp2,)).fetchone()[0]
    assert client.delete(f'/api/brews/{b}/fermentation', json={'keys': [f's{rid}']}).get_json()['deleted'] == 0
    assert len(_live(sp2)) == 4


def test_cles_invalides_refusees(client):
    b = _brassin(client, 'fermenting')
    for keys in (['x1'], ['s'], [12], ['s1; DROP TABLE brews']):
        assert client.delete(f'/api/brews/{b}/fermentation', json={'keys': keys}).status_code == 400
