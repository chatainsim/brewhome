"""Bilan annuel « Wrapped » (/api/wrapped)."""
from datetime import date

import pytest

from db import get_db


@pytest.fixture()
def donnees(app):
    """Deux recettes, des brassins sur 2025 et 2026, bouteilles, dégustation, consommation."""
    with app.app_context(), get_db() as conn:
        ipa = conn.execute("INSERT INTO recipes (name, style, volume, created_at) VALUES ('IPA', 'American IPA', 20, '2025-01-05')").lastrowid
        stout = conn.execute("INSERT INTO recipes (name, style, volume, created_at) VALUES ('Stout', 'Irish Stout', 10, '2024-06-01')").lastrowid
        conn.executemany(
            'INSERT INTO recipe_ingredients (recipe_id, name, category, quantity, unit) VALUES (?, ?, ?, ?, ?)',
            [(ipa, 'Pale Ale', 'malt', 5, 'kg'), (ipa, 'Citra', 'houblon', 100, 'g'), (ipa, 'US-05', 'levure', 1, 'sachet'),
             (stout, 'Maris Otter', 'malt', 2500, 'g'), (stout, 'Fuggles', 'houblon', 20, 'g')])
        brews = [
            # recette, nom, date, volume, abv, statut, supprimé
            (ipa, 'IPA #1', '2025-03-08', 20, 6.0, 'completed', None),      # samedi
            (ipa, 'IPA #2', '2025-04-12', 10, 6.4, 'completed', None),      # samedi, demi-brassin
            (stout, 'Stout #1', '2025-05-18', 10, 4.2, 'fermenting', None), # dimanche
            (ipa, 'IPA #3', '2025-11-01', 20, 7.5, 'completed', None),
            (ipa, 'Planifiée', '2025-12-20', 20, None, 'planned', None),     # pas encore brassée
            (ipa, 'Supprimée', '2025-06-01', 20, 5.0, 'completed', '2025-06-02'),
            (stout, 'Stout 2024', '2024-02-10', 10, 4.0, 'completed', None),
            (ipa, 'IPA 2026', '2026-02-01', 20, 6.0, 'completed', None),
        ]
        for rid, name, d, vol, abv, status, deleted in brews:
            conn.execute('''INSERT INTO brews (recipe_id, name, brew_date, volume_brewed, abv, status, deleted_at, archived, cost_snapshot)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (rid, name, d, vol, abv, status, deleted, 1 if name == 'IPA #1' else 0, 40 if name == 'IPA #1' else None))
        conn.execute('''INSERT INTO beers (name, bottling_date, initial_33cl, initial_75cl, taste_rating, taste_date)
                        VALUES ('IPA #1', '2025-03-30', 30, 4, 4, '2025-04-20')''')
        conn.execute('''INSERT INTO beers (name, bottling_date, initial_33cl, keg_initial_liters, taste_rating, taste_date)
                        VALUES ('IPA #2', '2025-05-02', 12, 5, 5, '2025-06-01')''')
        conn.executemany('INSERT INTO consumption_log (beer_name, ts, qty_33cl, qty_75cl, keg_liters) VALUES (?, ?, ?, ?, ?)',
                         [('IPA #1', '2025-04-02', 6, 1, 0), ('IPA #2', '2025-05-10', 0, 0, 2.5), ('IPA #1', '2024-12-31', 50, 0, 0)])
        conn.execute("INSERT INTO brew_fermentation_readings (brew_id, recorded_at, gravity) VALUES (1, '2025-03-09 10:00:00', 1.050)")
    return app


def test_bilan_annee(donnees):
    from blueprints.wrapped import wrapped
    with donnees.app_context():
        w = wrapped(2025, today=date(2026, 9, 28))
    assert not w['empty'] and not w['in_progress']
    assert w['brews'] == 4                          # ni planifié, ni supprimé ; l'archivé compte
    assert w['liters'] == 60
    assert w['prev_liters'] == 10 and w['evolution_pct'] == 500
    assert w['first_brew'] == {'name': 'IPA #1', 'date': '2025-03-08'}
    assert w['last_brew']['name'] == 'IPA #3'
    assert w['by_month'][2] == 20 and w['by_month'][3] == 10 and w['by_month'][10] == 20
    assert w['months_active'] == 4 and w['month_streak'] == 3
    assert w['fav_weekday'] == 5                    # samedi (lundi = 0)
    assert w['styles'][0] == {'name': 'American IPA', 'count': 3}
    assert w['n_styles'] == 2
    assert w['top_recipe'] == {'name': 'IPA', 'count': 3}
    assert w['new_recipes'] == 1
    # malts à l'échelle du volume brassé : IPA 5 kg × (1 + 0,5 + 1) + stout 2,5 kg × 1
    assert w['malt_kg'] == 15
    assert w['hops_g'] == 270 and w['hops_per_liter'] == 4.5
    assert w['top_hops'][0] == {'name': 'Citra', 'grams': 250}
    assert w['top_malt'] == 'Pale Ale' and w['top_yeast'] == 'US-05'
    assert w['avg_abv'] == 6.0
    assert w['strongest'] == {'name': 'IPA #3', 'abv': 7.5}
    assert w['cost'] == 40 and w['cost_per_liter'] == 2.0
    assert w['bottled_beers'] == 2 and w['bottles'] == 46
    assert w['bottled_liters'] == round(42 * 0.33 + 4 * 0.75 + 5, 1)
    assert w['drunk_liters'] == round(6 * 0.33 + 0.75 + 2.5, 1)
    assert w['drunk_bottles'] == 7
    assert w['fav_beer'] == {'name': 'IPA #1', 'liters': 2.7}   # 6 × 33 cl + 75 cl > 2,5 L de fût
    assert w['best_tasted'] == {'name': 'IPA #2', 'rating': 5}
    assert w['readings'] == 1
    assert w['profile'] == 'perfection'             # la même recette 3 fois


def test_annee_en_cours_comparee_a_la_meme_date(donnees):
    from blueprints.wrapped import wrapped
    with donnees.app_context():
        w = wrapped(2026, today=date(2026, 3, 1))
    assert w['in_progress'] and w['until'] == '2026-03-01'
    assert w['brews'] == 1 and w['prev_same_date']
    assert w['prev_liters'] == 0 and w['evolution_pct'] is None   # rien avant le 1er mars 2025


def test_annee_vide(donnees):
    from blueprints.wrapped import wrapped
    with donnees.app_context():
        w = wrapped(2020, today=date(2026, 9, 28))
    assert w['empty']


def test_route(donnees):
    r = donnees.test_client().get('/api/wrapped?year=2025')
    assert r.status_code == 200
    body = r.get_json()
    assert body['brews'] == 4
    assert body['years'][0] == date.today().year and {2025, 2024} <= set(body['years'])
    assert donnees.test_client().get('/api/wrapped?year=abc').status_code == 200
