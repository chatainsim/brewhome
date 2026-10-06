"""Analyses de la page Statistiques (/api/stats/insights)."""
from datetime import date

import pytest

from db import get_db

AUJ = date(2026, 6, 30)


@pytest.fixture()
def donnees(app):
    with app.app_context(), get_db() as conn:
        ipa = conn.execute("INSERT INTO recipes (name, style, volume, created_at) VALUES ('IPA', 'American IPA', 20, '2025-01-05')").lastrowid
        ipa2 = conn.execute("INSERT INTO recipes (name, style, volume, parent_recipe_id, created_at) VALUES ('IPA v2', 'American IPA', 20, ?, '2025-06-01')", (ipa,)).lastrowid
        stout = conn.execute("INSERT INTO recipes (name, style, volume, created_at) VALUES ('Stout', 'Irish Stout', 10, '2025-02-01')").lastrowid
        conn.execute("INSERT INTO recipes (name, style, volume, created_at) VALUES ('Jamais brassée', 'Saison', 20, '2026-01-01')")
        conn.executemany('INSERT INTO recipe_ingredients (recipe_id, name, category, quantity, unit) VALUES (?, ?, ?, ?, ?)',
                         [(ipa, 'US-05', 'levure', 1, 'sachet'), (ipa2, 'US-05', 'levure', 1, 'sachet'),
                          (stout, 'S-04', 'levure', 1, 'sachet')])
        conn.execute("INSERT INTO ingredient_catalog (name, category, attenuation_min, attenuation_max) VALUES ('US-05', 'levure', 78, 82)")
        brews = [  # recette, nom, date, volume, og, fg, statut
            (ipa, 'IPA #1', '2025-03-08', 20, 1.060, 1.012, 'completed'),   # AA 80 %
            (ipa2, 'IPA #2', '2026-03-01', 20, 1.050, 1.015, 'completed'),  # AA 70 %
            (stout, 'Stout #1', '2026-04-01', 10, 1.040, 1.050, 'completed'),  # DF > DI : ignoré
            (stout, 'Planifié', '2026-07-10', 10, None, None, 'planned'),
            (ipa, 'En cours', '2026-06-20', 20, 1.055, None, 'fermenting'),
        ]
        ids = {}
        for rid, name, d, vol, og, fg, status in brews:
            ids[name] = conn.execute('INSERT INTO brews (recipe_id, name, brew_date, volume_brewed, og, fg, status) VALUES (?,?,?,?,?,?,?)',
                                     (rid, name, d, vol, og, fg, status)).lastrowid
        # IPA #1 : 30×33 cl + 4×75 cl = 12,9 L conditionnés, reste 10 bouteilles de 33 cl
        conn.execute('''INSERT INTO beers (name, brew_id, recipe_id, bottling_date, refermentation_days, initial_33cl, initial_75cl,
                                           stock_33cl, stock_75cl, taste_date, taste_rating,
                                           taste_score_aroma, taste_score_flavor, taste_score_finish)
                        VALUES ('IPA #1', ?, ?, '2025-03-30', 14, 30, 4, 10, 0, '2025-04-20', 4, 8, 7, 6)''', (ids['IPA #1'], ipa))
        # IPA #2 : fût de 18 L, reste 9 L
        conn.execute('''INSERT INTO beers (name, brew_id, recipe_id, bottling_date, keg_initial_liters, keg_liters)
                        VALUES ('IPA #2', ?, ?, '2026-03-21', 18, 9)''', (ids['IPA #2'], ipa2))
        # 56 derniers jours : 3,3 L + 4,7 L = 8 L → 1 L/semaine
        conn.executemany('INSERT INTO consumption_log (beer_id, beer_name, ts, qty_33cl, keg_liters) VALUES (?,?,?,?,?)',
                         [(1, 'IPA #1', '2026-05-15', 10, 0), (2, 'IPA #2', '2026-06-01', 0, 4.7),
                          (1, 'IPA #1', '2025-04-02', 10, 0)])
        # fermentation : 1,050 → 1,010 en 4 jours ; 90 % du chemin (1,014) atteint au bout de 3 jours
        readings = [('2026-03-01 12:00:00', 1.050), ('2026-03-02 12:00:00', 1.035), ('2026-03-03 12:00:00', 1.020),
                    ('2026-03-04 12:00:00', 1.013), ('2026-03-05 12:00:00', 1.010), ('2026-03-06 12:00:00', 1.010),
                    ('2026-03-06 13:00:00', 0.5)]                                   # relevé aberrant ignoré
        conn.executemany('INSERT INTO brew_fermentation_readings (brew_id, recorded_at, gravity) VALUES (?,?,?)',
                         [(ids['IPA #2'], t, g) for t, g in readings])
        # journal du jour de brassage (08:00 → 13:30) + un dry-hop 5 jours plus tard (hors durée)
        conn.executemany('INSERT INTO brew_log (brew_id, ts, step, note) VALUES (?,?,?,?)',
                         [(ids['IPA #2'], '2026-03-01T08:00', 'empatage', 'x'), (ids['IPA #2'], '2026-03-01T13:30', 'transfert', 'x'),
                          (ids['IPA #2'], '2026-03-06T20:00', 'houblonnage', 'x')])
        # inventaire : malt utilisé récemment, houblon dormant, levure qui périme
        malt = conn.execute("INSERT INTO inventory_items (name, category, quantity, unit, price_per_unit, created_at) VALUES ('Pale', 'malt', 5, 'kg', 2, '2025-01-01')").lastrowid
        conn.execute("INSERT INTO inventory_items (name, category, quantity, unit, price_per_unit, created_at) VALUES ('Citra', 'houblon', 100, 'g', 0.1, '2025-01-01')")
        conn.execute("INSERT INTO inventory_items (name, category, quantity, unit, price_per_unit, expiry_date, created_at) VALUES ('US-05', 'levure', 2, 'sachet', 4, '2026-07-10', '2026-06-01')")
        conn.execute("INSERT INTO inventory_log (inventory_item_id, ts, delta, old_qty, new_qty, reason) VALUES (?, '2026-06-01', -3, 8, 5, 'brew')", (malt,))
        conn.executemany("INSERT INTO soda_kegs (name, status, volume_total, current_liters, next_revision_date) VALUES (?,?,?,?,?)",
                         [('Fût 1', 'serving', 19, 9, '2026-07-15'), ('Fût 2', 'empty', 19, 0, None)])
    return app


def _ins(app, year=None):
    from blueprints.insights import insights
    with app.app_context():
        return insights(year, today=AUJ)


def test_vide(app):
    d = _ins(app)
    assert d['runway']['weeks_left'] is None and d['yeasts'] == [] and d['curves'] == []
    assert d['losses']['brews'] == [] and d['stock']['value_series'][-1]['value'] == 0


def test_autonomie_cave(donnees):
    r = _ins(donnees)['runway']
    assert r['stock_liters'] == 12.3                # 10 × 0,33 + 9 L de fût
    assert r['weekly_liters'] == 1.0                # 8 L sur 56 jours
    assert r['weeks_left'] == 12.3
    assert r['depletion_date'] == '2026-09-24'
    assert r['pipeline_days'] == 28                 # médiane de 36 (22 j + 14 j de refermentation) et 20 jours
    assert r['brew_before'] == '2026-08-27'
    assert r['active_brews'] == 1 and r['active_liters'] == 20


def test_attenuation_levures(donnees):
    y = {x['yeast']: x for x in _ins(donnees)['yeasts']}
    assert y['US-05']['n'] == 2 and y['US-05']['avg'] == 75.0 and y['US-05']['min'] == 70.0 and y['US-05']['max'] == 80.0
    assert (y['US-05']['catalog_min'], y['US-05']['catalog_max']) == (78, 82)
    assert 'S-04' not in y                          # seul brassin : DF > DI, écarté
    assert [x['yeast'] for x in _ins(donnees, 2025)['yeasts']] == ['US-05']


def test_courbes_fermentation(donnees):
    c = _ins(donnees)['curves']
    assert len(c) == 1 and c[0]['brew'] == 'IPA #2'
    assert c[0]['points'][0] == [0.0, 1.05] and c[0]['days_to_90'] == 3.0
    assert c[0]['drop'] == 0.04 and all(p[1] > 0.9 for p in c[0]['points'])


def test_pertes_et_delais(donnees):
    d = _ins(donnees)
    pertes = {x['brew']: x for x in d['losses']['brews']}
    assert pertes['IPA #1']['packaged'] == 12.9 and pertes['IPA #1']['loss_pct'] == 35.5
    assert pertes['IPA #2']['loss_pct'] == 10.0 and 'Stout #1' not in pertes
    assert d['pipeline']['avg_to_bottle'] == 21.0 and d['pipeline']['avg_to_taste'] == 43.0


def test_degustation_recettes_conso(donnees):
    d = _ins(donnees)
    assert d['tasting']['beers'][0]['scores'] == {'aroma': 8, 'flavor': 7, 'finish': 6}
    assert d['tasting']['by_style'][0]['style'] == 'American IPA'
    assert d['recipes']['rebrewed'][0] == {'recipe': 'IPA', 'style': 'American IPA', 'brews': 3, 'last': '2026-06-20'}  # v2 comptée avec sa recette d'origine
    assert d['recipes']['never_brewed'] == 1
    assert d['consumption']['weekday_liters'][4] == 3.3     # 2026-05-15 = vendredi
    assert d['consumption']['month_liters'][5] == 4.7


def test_cave_stock_futs(donnees):
    d = _ins(donnees)
    ages = {a['beer']: a for a in d['cellar']['ages']}
    assert ages['IPA #1']['age_days'] == 457 and d['cellar']['ages'][0]['beer'] == 'IPA #1'
    s = d['stock']
    assert [x['item'] for x in s['dormant']] == ['Citra'] and s['dormant_value'] == 10.0    # 100 g × 0,10 €/g
    assert [x['item'] for x in s['expiring']] == ['US-05'] and s['expiring_value'] == 8.0
    assert s['value_series'][-1]['value'] == 28.0                                          # 10 + 10 + 8
    may = next(p for p in s['value_series'] if p['month'] == '2026-05')
    assert may['value'] == 26.0                     # avant l'utilisation de 3 kg du 1er juin, sans la levure (créée le 1er juin)
    k = d['kegs']
    assert k['occupancy_pct'] == 50 and k['fill_pct'] == 24 and k['revisions'][0]['days'] == 15


def test_journee_de_brassage(donnees):
    b = _ins(donnees)['brew_days']
    assert b['brews'] == [{'brew': 'IPA #2', 'brew_date': '2026-03-01', 'start': '08:00', 'end': '13:30', 'steps': 2, 'hours': 5.5}]


def test_historique_des_prix(client):
    r = client.post('/api/inventory', json={'name': 'Pils', 'category': 'malt', 'quantity': 5, 'unit': 'kg', 'price_per_unit': 2.0})
    iid = r.get_json()['id']
    client.put(f'/api/inventory/{iid}', json={'price_per_unit': 2.5})
    client.put(f'/api/inventory/{iid}', json={'quantity': 4})              # prix inchangé : rien de noté
    p = client.get('/api/stats/insights').get_json()['prices']
    assert p['tracked_items'] == 1
    assert p['changes'][0]['item'] == 'Pils' and p['changes'][0]['change_pct'] == 25.0
    assert [pt[1] for pt in p['changes'][0]['points']] == [2.0, 2.5]


def test_route_et_filtre_annee(donnees):
    c = donnees.test_client()
    assert c.get('/api/stats/insights').status_code == 200
    d = c.get('/api/stats/insights?year=2025').get_json()
    assert d['year'] == 2025 and [x['brew'] for x in d['losses']['brews']] == ['IPA #1']
