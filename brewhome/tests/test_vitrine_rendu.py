"""Le rendu Python de la vitrine doit rester identique à celui du JavaScript.

Les témoins `fixtures/vitrine_*.html` ont été produits par les gabarits
JavaScript d'origine (`generateVitrineHtml` / `generateRecipeHtml`) sur le jeu
de données `fixtures/vitrine_data.json`. Toute divergence de rendu — un
arrondi, un format de date, une espace — fait échouer ces tests.

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
