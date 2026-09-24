"""Les fonctions IA sont désactivées par défaut (Paramètres → IA).

L'interface masque les boutons, mais le serveur refuse aussi : un appel
direct ne doit pas partir vers un fournisseur tant que l'utilisateur n'a
pas coché la case.
"""


def _suggest(client):
    return client.post('/api/ai/draft-suggest', json={'style': 'IPA', 'volume': 20})


def test_refus_par_defaut_meme_avec_une_cle(client):
    client.put('/api/app-settings', json={'ai_api_key': 'une-cle'})
    r = _suggest(client)
    assert r.status_code == 403


def test_refus_quand_explicitement_desactivee(client):
    client.put('/api/app-settings', json={'ai_api_key': 'une-cle', 'ai_enabled': 'false'})
    assert _suggest(client).status_code == 403


def test_activee_sans_cle_retombe_sur_non_configure(client):
    client.put('/api/app-settings', json={'ai_enabled': 'true'})
    r = _suggest(client)
    assert r.status_code == 400


def test_la_valeur_false_est_conservee(client):
    # « false » doit être stocké, pas supprimé : les autres appareils le relisent.
    client.put('/api/app-settings', json={'ai_enabled': 'false'})
    assert client.get('/api/app-settings').get_json()['ai_enabled'] == 'false'
