"""Le rendu de la vitrine ne doit pas changer par inadvertance.

Les témoins `fixtures/vitrine_*.html` sont nés de la sortie des gabarits
JavaScript d'origine, sur le jeu de données `fixtures/vitrine_data.json`.
C'est ainsi que la fidélité du portage a été établie. Le JavaScript ayant été
supprimé depuis, ils servent désormais de référence de non-régression : toute
modification du rendu — un arrondi, un format de date, une espace — fait
échouer ces tests, et les mettre à jour doit être un geste délibéré.

Les primitives sont testées à part parce que c'est là qu'étaient les vrais
pièges : `toFixed` et `Math.round` n'arrondissent pas comme Python, et les
dates longues en français ne dépendent pas d'une locale installée.
"""

import json
import os

import pytest

import vitrine as V

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')


def _donnees():
    with open(os.path.join(FIXTURES, 'vitrine_data.json'), encoding='utf-8') as f:
        return json.load(f)


def _temoin(nom):
    with open(os.path.join(FIXTURES, nom), encoding='utf-8') as f:
        return f.read()


# ── Primitives ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('valeur, decimales, attendu', [
    (5.25, 1, '5.3'),      # Python donnerait « 5.2 » (arrondi au pair)
    (6.83, 1, '6.8'),
    (1.0595, 3, '1.060'),
    (6.6, 1, '6.6'),
    (72, 0, '72'),
])
def test_fixed_suit_tofixed(valeur, decimales, attendu):
    assert V.fixed(valeur, decimales) == attendu


@pytest.mark.parametrize('valeur, attendu', [(62.5, 63), (63.5, 64), (0.5, 1), (62.4, 62)])
def test_js_round_arrondit_au_superieur(valeur, attendu):
    assert V.js_round(valeur) == attendu


@pytest.mark.parametrize('valeur, attendu', [(8.5, '8.5'), (8.0, '8'), (19, '19'), (0.33, '0.33')])
def test_num_ecrit_les_nombres_comme_javascript(valeur, attendu):
    assert V.num(valeur) == attendu


@pytest.mark.parametrize('iso, attendu', [
    ('2026-07-04', '04 juillet 2026'),
    ('2026-11-01', '01 novembre 2026'),
    ('2026-01-15', '15 janvier 2026'),
    ('', ''),
    ('pas une date', 'pas une date'),
])
def test_date_longue_en_francais(iso, attendu):
    assert V.v_date(iso) == attendu


def test_esc_laisse_l_apostrophe():
    # L'original n'échappe pas l'apostrophe ; l'échapper changerait le rendu.
    assert V.esc('a & b < c > d " e \' f') == 'a &amp; b &lt; c &gt; d &quot; e \' f'


# ── Rendu complet ────────────────────────────────────────────────────────

def test_page_accueil_identique_au_javascript():
    d = _donnees()
    produit = V.generate_vitrine_html(
        d['beers'], {1: {'ext': 'jpg'}}, 'images/app-icon.png', d['settings'],
        today=__import__('datetime').date(2026, 9, 19))
    attendu = _temoin('vitrine_index.html')
    # La date du jour figure dans l'en-tête : on neutralise cette seule ligne,
    # le témoin ayant été produit un autre jour.
    import re
    norm = lambda s: re.sub(r'<div class="subtitle">[^<]*</div>', '', s, count=1)
    assert norm(produit) == norm(attendu)


def test_page_recette_identique_au_javascript():
    d = _donnees()
    rec, beer = d['recipes'][0], d['beers'][0]
    produit = V.generate_recipe_html(
        rec, beer, V.rec_theoretical(rec), '../images/beer-1.jpg', d['settings'])
    assert produit == _temoin('vitrine_recipe.html')


def test_recette_sans_biere_liee_ne_rend_pas_d_entete():
    d = _donnees()
    produit = V.generate_recipe_html(d['recipes'][0], None, None, None, d['settings'])
    assert '<div class="beer-head">' not in produit


def test_les_mesures_retombent_sur_l_abv_de_la_biere():
    d = _donnees()
    beer = dict(d['beers'][0])
    beer.pop('brew_abv'); beer.pop('brew_og'); beer.pop('brew_fg')
    produit = V.generate_recipe_html(d['recipes'][0], beer, None, None, d['settings'])
    assert 'ABV réel' in produit and 'DI mesurée' not in produit


# ── Volumes d'eau ────────────────────────────────────────────────────────

def _recette_eau(**extra):
    base = {'volume': 20, 'boil_time': 60, 'mash_ratio': 3, 'evap_rate': 3,
            'grain_absorption': 0.8,
            'ingredients': [{'category': 'malt', 'quantity': 5, 'unit': 'kg'}]}
    base.update(extra)
    return base


def test_eau_calculee_comme_dans_l_application():
    eau = V.rec_water(_recette_eau())
    assert round(eau['mash'], 1) == 15.0
    assert round(eau['sparge'], 1) == 12.0


def test_l_empatage_ne_descend_pas_sous_55_pour_cent_du_total():
    # Un ratio faible donnerait moins d'eau d'empâtage que de rinçage.
    eau = V.rec_water(_recette_eau(mash_ratio=1))
    assert eau['mash'] >= eau['total'] * 0.55 - 1e-9
    assert eau['mash'] >= eau['sparge']


def test_une_valeur_manuelle_prend_le_pas_et_le_rincage_s_ajuste():
    eau = V.rec_water(_recette_eau(water_mash_override=18))
    assert round(eau['mash'], 1) == 18.0
    assert round(eau['sparge'], 1) == 9.0   # le total reste inchangé
    assert eau['manual_mash'] and not eau['manual_sparge']


def test_un_rincage_manuel_ne_deplace_pas_l_empatage():
    eau = V.rec_water(_recette_eau(water_sparge_override=9))
    assert round(eau['mash'], 1) == 15.0
    assert round(eau['sparge'], 1) == 9.0


def test_pas_de_volume_d_eau_sans_grain():
    assert V.rec_water(_recette_eau(ingredients=[])) is None


def test_les_volumes_d_eau_apparaissent_sur_la_page():
    d = _donnees()
    produit = V.generate_recipe_html(d['recipes'][0], None, None, None, d['settings'])
    assert "Eau d'empâtage" in produit and 'Eau de rinçage' in produit
