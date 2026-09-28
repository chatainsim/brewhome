"""Bilan annuel façon « Wrapped » : brassins, litres, styles, ingrédients,
mise en bouteille, dégustation et consommation d'une année.

Les textes sont traduits côté client : cette route ne renvoie que des
nombres, des noms (recettes, ingrédients, bières) et des clés de profil.
Un brassin compte pour l'année de sa date de brassage, dès qu'il n'est plus
seulement planifié ; les brassins archivés comptent (ils ont bien été
brassés), les brassins supprimés non.
"""
from collections import Counter, defaultdict
from datetime import date

from flask import Blueprint, jsonify, request

from constants import BottleSize, BrewStatus
from db import get_db

bp = Blueprint('wrapped', __name__)


def _period(year, today):
    """Bornes [début, fin] de l'année (fin = aujourd'hui pour l'année en cours)."""
    start = date(year, 1, 1)
    end = today if year == today.year else date(year, 12, 31)
    return start.isoformat(), end.isoformat()


def _brews(conn, start, end):
    return [dict(r) for r in conn.execute(
        '''SELECT b.id, b.name, b.brew_date, b.volume_brewed, b.og, b.fg, b.abv, b.status,
                  b.actual_efficiency, b.cost_snapshot, b.recipe_id,
                  r.name AS recipe_name, r.style, r.volume AS recipe_volume
           FROM brews b LEFT JOIN recipes r ON r.id = b.recipe_id
           WHERE b.deleted_at IS NULL AND b.status != ?
             AND b.brew_date IS NOT NULL AND substr(b.brew_date, 1, 10) BETWEEN ? AND ?
           ORDER BY b.brew_date''',
        (BrewStatus.PLANNED, start, end))]


def _liters(brews):
    return sum(b['volume_brewed'] or 0 for b in brews)


def _streak_months(months):
    """Plus longue suite de mois consécutifs avec au moins un brassin."""
    best = run = 0
    prev = None
    for m in sorted(months):
        run = run + 1 if prev is not None and m == prev + 1 else 1
        best = max(best, run)
        prev = m
    return best


def _profile(n_brews, liters, hops_g, n_styles, avg_abv, repeat_max, months_active):
    candidates = [
        ('brewery',    n_brews >= 12),
        ('hophead',    liters > 0 and hops_g / liters >= 8),
        ('perfection', repeat_max >= 3),
        ('explorer',   n_styles >= 5),
        ('strong',     avg_abv is not None and avg_abv >= 7),
        ('regular',    months_active >= 6),
    ]
    return next((key for key, ok in candidates if ok), 'passion')


def wrapped(year, today=None):
    today = today or date.today()
    start, end = _period(year, today)
    in_progress = year == today.year
    with get_db() as conn:
        brews = _brews(conn, start, end)

        # Année précédente, jusqu'à la même date pour l'année en cours
        prev_end = end.replace(str(year), str(year - 1), 1) if in_progress else f'{year - 1}-12-31'
        if prev_end.endswith('02-29'):
            prev_end = prev_end[:-2] + '28'
        prev = _brews(conn, f'{year - 1}-01-01', prev_end)

        recipe_ids = {b['recipe_id'] for b in brews if b['recipe_id']}
        ings = defaultdict(list)
        if recipe_ids:
            ph = ','.join('?' * len(recipe_ids))
            for r in conn.execute(
                    f'SELECT recipe_id, name, category, quantity, unit FROM recipe_ingredients WHERE recipe_id IN ({ph})',
                    tuple(recipe_ids)):
                ings[r['recipe_id']].append(dict(r))

        new_recipes = conn.execute(
            '''SELECT COUNT(*) FROM recipes WHERE deleted_at IS NULL
               AND substr(created_at, 1, 10) BETWEEN ? AND ?''', (start, end)).fetchone()[0]

        sizes = BottleSize.SIZES_CL
        bottled = conn.execute(
            'SELECT ' + ', '.join(f'COALESCE(SUM(initial_{s}), 0) AS n{s}' for s in sizes) +
            ', COALESCE(SUM(keg_initial_liters), 0) AS keg, COUNT(*) AS beers'
            ' FROM beers WHERE deleted_at IS NULL AND bottling_date IS NOT NULL'
            ' AND substr(bottling_date, 1, 10) BETWEEN ? AND ?', (start, end)).fetchone()

        drunk_rows = conn.execute(
            'SELECT beer_name, ' + ' + '.join(f'qty_{s} * {v}' for s, v in sizes.items()) +
            ' + keg_liters AS liters, ' + ' + '.join(f'qty_{s}' for s in sizes) + ' AS bottles, ts'
            ' FROM consumption_log WHERE substr(ts, 1, 10) BETWEEN ? AND ?', (start, end)).fetchall()

        best_tasted = conn.execute(
            '''SELECT name, taste_rating FROM beers
               WHERE deleted_at IS NULL AND taste_rating IS NOT NULL
                 AND substr(COALESCE(taste_date, ''), 1, 10) BETWEEN ? AND ?
               ORDER BY taste_rating DESC, taste_date DESC LIMIT 1''', (start, end)).fetchone()

        readings = conn.execute(
            '''SELECT COUNT(*) FROM brew_fermentation_readings
               WHERE substr(recorded_at, 1, 10) BETWEEN ? AND ?''', (start, end)).fetchone()[0]

    if not brews and not drunk_rows and not bottled['beers']:
        return {'year': year, 'empty': True, 'in_progress': in_progress, 'until': end}

    liters = _liters(brews)
    prev_liters = _liters(prev)

    # Brassins par mois / jour de la semaine
    by_month = [0.0] * 12
    months_count = [0] * 12
    weekdays = Counter()
    for b in brews:
        d = date.fromisoformat(b['brew_date'][:10])
        by_month[d.month - 1] += b['volume_brewed'] or 0
        months_count[d.month - 1] += 1
        weekdays[d.weekday()] += 1
    months_active = [i for i, n in enumerate(months_count) if n]

    # Styles et recettes
    styles = Counter(b['style'] for b in brews if b['style'])
    recipes = Counter(b['recipe_name'] for b in brews if b['recipe_name'])
    repeat_name, repeat_max = recipes.most_common(1)[0] if recipes else (None, 0)

    # Ingrédients, mis à l'échelle du volume réellement brassé
    malts, hops, yeasts = Counter(), Counter(), Counter()
    for b in brews:
        rv, bv = b['recipe_volume'], b['volume_brewed']
        k = bv / rv if bv and rv else 1
        for i in ings.get(b['recipe_id'], []):
            q = (i['quantity'] or 0) * k
            if i['category'] == 'malt':
                malts[i['name']] += q * 1000 if i['unit'] == 'kg' else q
            elif i['category'] == 'houblon':
                hops[i['name']] += q * 1000 if i['unit'] == 'kg' else q
            elif i['category'] == 'levure':
                yeasts[i['name']] += 1
    malt_g, hops_g = sum(malts.values()), sum(hops.values())

    abvs = [b['abv'] for b in brews if b['abv']]
    avg_abv = round(sum(abvs) / len(abvs), 1) if abvs else None
    strongest = max((b for b in brews if b['abv']), key=lambda b: b['abv'], default=None)
    effs = [b['actual_efficiency'] for b in brews if b['actual_efficiency']]
    costs = [b['cost_snapshot'] for b in brews if b['cost_snapshot']]
    cost_liters = sum(b['volume_brewed'] or 0 for b in brews if b['cost_snapshot'])

    # Consommation
    drunk_liters = sum(r['liters'] or 0 for r in drunk_rows)
    drunk_by_beer = Counter()
    for r in drunk_rows:
        drunk_by_beer[r['beer_name']] += r['liters'] or 0
    fav_beer = drunk_by_beer.most_common(1)[0] if drunk_by_beer else None

    bottles = sum(bottled[f'n{s}'] for s in sizes)
    bottled_liters = sum(bottled[f'n{s}'] * v for s, v in sizes.items()) + (bottled['keg'] or 0)

    return {
        'year': year,
        'empty': False,
        'in_progress': in_progress,
        'until': end,
        'brews': len(brews),
        'liters': round(liters, 1),
        'pints': round(liters / 0.5),
        'prev_year': year - 1,
        'prev_brews': len(prev),
        'prev_liters': round(prev_liters, 1),
        'prev_same_date': in_progress,
        'evolution_pct': round(100 * (liters - prev_liters) / prev_liters) if prev_liters else None,
        'first_brew': {'name': brews[0]['name'], 'date': brews[0]['brew_date'][:10]} if brews else None,
        'last_brew': {'name': brews[-1]['name'], 'date': brews[-1]['brew_date'][:10]} if brews else None,
        'by_month': [round(v, 1) for v in by_month],
        'best_month': max(range(12), key=lambda i: (by_month[i], months_count[i])) if brews else None,
        'months_active': len(months_active),
        'month_streak': _streak_months(months_active),
        'fav_weekday': weekdays.most_common(1)[0][0] if weekdays else None,
        'styles': [{'name': n, 'count': c} for n, c in styles.most_common(5)],
        'n_styles': len(styles),
        'top_recipe': {'name': repeat_name, 'count': repeat_max} if repeat_max > 1 else None,
        'new_recipes': new_recipes,
        'malt_kg': round(malt_g / 1000, 1),
        'hops_g': round(hops_g),
        'hops_per_liter': round(hops_g / liters, 1) if liters else None,
        'top_malt': malts.most_common(1)[0][0] if malts else None,
        'top_hops': [{'name': n, 'grams': round(g)} for n, g in hops.most_common(3)],
        'top_yeast': yeasts.most_common(1)[0][0] if yeasts else None,
        'avg_abv': avg_abv,
        'strongest': {'name': strongest['name'], 'abv': strongest['abv']} if strongest else None,
        'avg_efficiency': round(sum(effs) / len(effs), 1) if effs else None,
        'cost': round(sum(costs)) if costs else None,
        'cost_per_liter': round(sum(costs) / cost_liters, 2) if costs and cost_liters else None,
        'bottled_beers': bottled['beers'],
        'bottles': bottles,
        'bottled_liters': round(bottled_liters, 1),
        'drunk_liters': round(drunk_liters, 1),
        'drunk_bottles': sum(r['bottles'] or 0 for r in drunk_rows),
        'fav_beer': {'name': fav_beer[0], 'liters': round(fav_beer[1], 1)} if fav_beer else None,
        'best_tasted': {'name': best_tasted['name'], 'rating': best_tasted['taste_rating']} if best_tasted else None,
        'readings': readings,
        'profile': _profile(len(brews), liters, hops_g, len(styles), avg_abv, repeat_max, len(months_active)),
    }


def available_years(today=None):
    today = today or date.today()
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT DISTINCT substr(brew_date, 1, 4) FROM brews
               WHERE deleted_at IS NULL AND status != ? AND brew_date IS NOT NULL
               UNION SELECT DISTINCT substr(ts, 1, 4) FROM consumption_log''',
            (BrewStatus.PLANNED,)).fetchall()
    years = {int(r[0]) for r in rows if r[0] and r[0].isdigit()}
    years.add(today.year)
    return sorted((y for y in years if y <= today.year), reverse=True)


@bp.route('/api/wrapped')
def get_wrapped():
    today = date.today()
    try:
        year = int(request.args.get('year', today.year))
    except ValueError:
        year = today.year
    return jsonify({**wrapped(year, today), 'years': available_years(today)})
