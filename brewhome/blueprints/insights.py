"""Analyses de la page Statistiques (section « Analyses ») : tout ce qui demande des données que la page ne charge pas
(relevés de fermentation, journaux de consommation, d'inventaire, de prix et de brassage) ou un calcul plus simple
côté serveur. Les comparaisons à la théorie des recettes (DI/DF/ABV prévus) restent côté client, qui a déjà le calcul
(_recipeStats).

Les textes sont traduits côté client : la route ne renvoie que des nombres, des dates ISO, des noms et des clés.
Filtre ?year=AAAA (défaut : toutes les années) sur ce qui est daté par un brassin ou une consommation ; l'état actuel
(cave, stock, fûts) n'est jamais filtré.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median

from flask import Blueprint, jsonify, request

from constants import BottleSize, BrewStatus
from db import get_db
from helpers import beer_liters

bp = Blueprint('insights', __name__)

# Unité dans laquelle le prix est saisi, par catégorie (= CANONICAL_PRICE_UNIT côté client)
CANONICAL_PRICE_UNIT = {'malt': 'kg', 'houblon': 'g', 'levure': 'sachet'}
TASTE_CRITERIA = ('appearance', 'aroma', 'flavor', 'bitterness', 'mouthfeel', 'finish')
RUNWAY_WINDOW_DAYS = 56          # rythme de consommation : 8 dernières semaines
DORMANT_DAYS = 180
EXPIRY_DAYS = 30
CURVE_BUCKET_HOURS = 6
CURVE_MAX_BREWS = 12


def _d(value):
    """Date ISO (« AAAA-MM-JJ », avec ou sans heure) → date, ou None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _dt(value):
    if not value:
        return None
    s = str(value).replace('T', ' ')[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _round(v, n=1):
    return None if v is None else round(v, n)


def _avg(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _convert(qty, unit, to):
    if qty is None:
        return None
    if unit == to:
        return qty
    if unit == 'g' and to == 'kg':
        return qty / 1000
    if unit == 'kg' and to == 'g':
        return qty * 1000
    if unit in ('ml', 'mL') and to == 'L':
        return qty / 1000
    if unit == 'L' and to in ('ml', 'mL'):
        return qty * 1000
    return None


def _item_value(item, qty=None):
    """Valeur en € d'une quantité (par défaut le stock) d'un article d'inventaire, prix dans l'unité canonique."""
    price = item['price_per_unit']
    if price is None:
        return None
    q = _convert(item['quantity'] if qty is None else qty, item['unit'],
                 CANONICAL_PRICE_UNIT.get(item['category'], item['unit']))
    return None if q is None else q * price


def _consumed_liters_sql(alias='c'):
    return ' + '.join(f'COALESCE({alias}.qty_{s},0)*{l}' for s, l in BottleSize.SIZES_CL.items()) + \
        f' + COALESCE({alias}.keg_liters,0)'


def _in_year(d, year):
    return year is None or (d is not None and d.year == year)


# ── Sections ──────────────────────────────────────────────────────────────────

def _runway(conn, beers, today):
    stock = sum(beer_liters(b) for b in beers)
    since = (today - timedelta(days=RUNWAY_WINDOW_DAYS)).isoformat()
    row = conn.execute(f'SELECT COALESCE(SUM({_consumed_liters_sql()}),0) AS l, MIN(ts) AS first FROM consumption_log c '
                       'WHERE substr(c.ts,1,10) >= ?', (since,)).fetchone()
    consumed = row['l'] or 0
    first = _d(conn.execute('SELECT MIN(ts) FROM consumption_log').fetchone()[0])
    # historique plus court que la fenêtre : rythme calculé sur la durée réellement couverte (au moins 14 jours)
    window = RUNWAY_WINDOW_DAYS if not first else max(14, min(RUNWAY_WINDOW_DAYS, (today - first).days + 1))
    daily = consumed / window if consumed else 0
    pipeline = []
    for b in beers:
        brew_d, bottle_d = _d(b['eff_brew_date']), _d(b['bottling_date'])
        if brew_d and bottle_d and bottle_d >= brew_d:
            pipeline.append((bottle_d - brew_d).days + (b['refermentation_days'] or 0))
    pipeline_days = int(median(pipeline)) if pipeline else None
    active = conn.execute('SELECT COUNT(*), COALESCE(SUM(COALESCE(volume_brewed, 0)),0) FROM brews '
                          f'WHERE deleted_at IS NULL AND archived=0 AND status IN ({",".join("?" * 2)})',
                          (BrewStatus.IN_PROGRESS, BrewStatus.FERMENTING)).fetchone()
    out = {'stock_liters': _round(stock, 1), 'weekly_liters': _round(daily * 7, 2), 'window_days': window,
           'pipeline_days': pipeline_days, 'active_brews': active[0], 'active_liters': _round(active[1], 1),
           'weeks_left': None, 'depletion_date': None, 'brew_before': None}
    if daily > 0:
        days_left = stock / daily
        depletion = today + timedelta(days=int(days_left))
        out.update(weeks_left=_round(days_left / 7, 1), depletion_date=depletion.isoformat())
        if pipeline_days is not None:
            out['brew_before'] = (depletion - timedelta(days=pipeline_days)).isoformat()
    return out


def _brews(conn):
    return [dict(r) for r in conn.execute(
        '''SELECT b.id, b.name, b.brew_date, b.status, b.og, b.fg, b.abv, b.volume_brewed, b.recipe_id,
                  r.name AS recipe_name, r.style, r.volume AS recipe_volume, r.parent_recipe_id
           FROM brews b LEFT JOIN recipes r ON r.id = b.recipe_id
           WHERE b.deleted_at IS NULL AND b.status != ?''', (BrewStatus.PLANNED,))]


def _yeast_attenuation(conn, brews, year):
    yeasts = defaultdict(list)
    for r in conn.execute("SELECT recipe_id, name FROM recipe_ingredients WHERE category='levure' AND name IS NOT NULL"):
        yeasts[r['recipe_id']].append(r['name'].strip())
    catalog = {r['name'].strip().lower(): r for r in conn.execute(
        "SELECT name, attenuation_min, attenuation_max FROM ingredient_catalog WHERE category='levure'")}
    per = defaultdict(list)
    for b in brews:
        if not _in_year(_d(b['brew_date']), year) or not b['og'] or not b['fg'] or b['og'] <= 1:
            continue
        aa = (b['og'] - b['fg']) / (b['og'] - 1) * 100
        if not 0 < aa <= 110:
            continue                                       # saisie aberrante (DF > DI, densités inversées…)
        for y in set(yeasts.get(b['recipe_id'], [])):
            per[y].append({'brew': b['name'], 'aa': aa})
    out = []
    for name, rows in per.items():
        values = [r['aa'] for r in rows]
        cat = catalog.get(name.lower())
        out.append({'yeast': name, 'n': len(values), 'avg': _round(_avg(values)), 'min': _round(min(values)),
                    'max': _round(max(values)), 'brews': [r['brew'] for r in rows],
                    'catalog_min': cat['attenuation_min'] if cat else None, 'catalog_max': cat['attenuation_max'] if cat else None})
    out.sort(key=lambda y: (-y['n'], y['yeast'].lower()))
    return out


def _ferment_curves(conn, brews, year):
    by_id = {b['id']: b for b in brews if _in_year(_d(b['brew_date']), year)}
    if not by_id:
        return []
    rows = conn.execute(
        f'''SELECT brew_id, recorded_at, gravity FROM brew_fermentation_readings
            WHERE gravity BETWEEN 0.98 AND 1.2 AND brew_id IN ({",".join("?" * len(by_id))})
            ORDER BY brew_id, recorded_at''', list(by_id)).fetchall()
    series = defaultdict(list)
    for r in rows:
        t = _dt(r['recorded_at'])
        if t:
            series[r['brew_id']].append((t, r['gravity']))
    curves = []
    for brew_id, pts in series.items():
        if len(pts) < 5:
            continue
        t0 = pts[0][0]
        buckets = defaultdict(list)
        for t, g in pts:
            buckets[int((t - t0).total_seconds() // (CURVE_BUCKET_HOURS * 3600))].append(g)
        points = [[_round(k * CURVE_BUCKET_HOURS / 24, 2), round(sum(v) / len(v), 4)] for k, v in sorted(buckets.items())]
        start, final = points[0][1], min(p[1] for p in points[-4:])
        days_90 = None
        if start - final > 0.003:
            threshold = start - 0.9 * (start - final)
            days_90 = next((p[0] for p in points if p[1] <= threshold), None)
        b = by_id[brew_id]
        curves.append({'brew_id': brew_id, 'brew': b['name'], 'style': b['style'], 'brew_date': b['brew_date'],
                       'start_date': t0.date().isoformat(), 'points': points, 'days_to_90': days_90,
                       'drop': round(start - final, 4), 'duration_days': points[-1][0]})
    curves.sort(key=lambda c: c['start_date'], reverse=True)
    return curves[:CURVE_MAX_BREWS]


def _losses(conn, brews, beers_all, year):
    packaged = defaultdict(float)
    for b in beers_all:
        if b['brew_id']:
            packaged[b['brew_id']] += sum((b[f'initial_{s}'] or 0) * l for s, l in BottleSize.SIZES_CL.items()) \
                + (b['keg_initial_liters'] or 0)
    out = []
    for b in brews:
        if b['status'] != BrewStatus.COMPLETED or not _in_year(_d(b['brew_date']), year) or not b['volume_brewed']:
            continue
        p = packaged.get(b['id'], 0)
        if p <= 0:
            continue
        out.append({'brew': b['name'], 'brew_date': b['brew_date'], 'target': b['recipe_volume'],
                    'brewed': b['volume_brewed'], 'packaged': _round(p, 1),
                    'loss_pct': _round((b['volume_brewed'] - p) / b['volume_brewed'] * 100)})
    out.sort(key=lambda x: x['brew_date'] or '')
    return {'brews': out, 'avg_loss_pct': _round(_avg([x['loss_pct'] for x in out]))}


def _pipeline(beers_all, styles, year):
    rows = []
    for b in beers_all:
        brew_d, bottle_d, taste_d = _d(b['eff_brew_date']), _d(b['bottling_date']), _d(b['taste_date'])
        if not brew_d or not _in_year(brew_d, year):
            continue
        to_bottle = (bottle_d - brew_d).days if bottle_d and bottle_d >= brew_d else None
        to_taste = (taste_d - brew_d).days if taste_d and taste_d >= brew_d else None
        if to_bottle is None and to_taste is None:
            continue
        rows.append({'style': styles.get(b['recipe_id']) or None, 'to_bottle': to_bottle, 'to_taste': to_taste})
    per_style = defaultdict(list)
    for r in rows:
        per_style[r['style'] or '—'].append(r)
    return {'avg_to_bottle': _round(_avg([r['to_bottle'] for r in rows])),
            'avg_to_taste': _round(_avg([r['to_taste'] for r in rows])), 'n': len(rows),
            'by_style': sorted(({'style': s, 'n': len(v), 'to_bottle': _round(_avg([r['to_bottle'] for r in v])),
                                 'to_taste': _round(_avg([r['to_taste'] for r in v]))} for s, v in per_style.items()),
                               key=lambda x: -x['n'])}


def _tasting(beers_all, styles, year):
    beers, per_style = [], defaultdict(lambda: defaultdict(list))
    for b in beers_all:
        scores = {c: b[f'taste_score_{c}'] for c in TASTE_CRITERIA if b[f'taste_score_{c}'] is not None}
        if not scores or not _in_year(_d(b['eff_brew_date']) or _d(b['taste_date']), year):
            continue
        style = styles.get(b['recipe_id']) or b['type'] or '—'
        beers.append({'beer': b['name'], 'style': style, 'scores': scores, 'rating': b['taste_rating']})
        for c, v in scores.items():
            per_style[style][c].append(v)
    return {'criteria': list(TASTE_CRITERIA), 'beers': beers,
            'by_style': [{'style': s, 'n': max(len(v) for v in d.values()),
                          'scores': {c: _round(_avg(v), 2) for c, v in d.items()}} for s, d in per_style.items()]}


def _recipes(conn, brews, year):
    recipes = {r['id']: dict(r) for r in conn.execute(
        'SELECT id, name, style, parent_recipe_id, archived, created_at FROM recipes WHERE deleted_at IS NULL')}

    def root(rid, seen=()):
        r = recipes.get(rid)
        if not r or not r['parent_recipe_id'] or r['parent_recipe_id'] in seen or r['parent_recipe_id'] not in recipes:
            return rid
        return root(r['parent_recipe_id'], seen + (rid,))
    counts, last = defaultdict(int), {}
    brewed_ids = set()
    for b in brews:
        if not b['recipe_id']:
            continue
        brewed_ids.add(b['recipe_id'])
        if not _in_year(_d(b['brew_date']), year):
            continue
        key = root(b['recipe_id'])
        counts[key] += 1
        last[key] = max(last.get(key) or '', b['brew_date'] or '')
    top = sorted(({'recipe': recipes[k]['name'] if k in recipes else '?', 'style': recipes.get(k, {}).get('style'),
                   'brews': n, 'last': last.get(k) or None} for k, n in counts.items()),
                 key=lambda x: (-x['brews'], x['recipe'].lower()))
    never = sorted((r for r in recipes.values() if not r['archived'] and r['id'] not in brewed_ids),
                   key=lambda r: r['created_at'] or '', reverse=True)
    return {'rebrewed': [x for x in top if x['brews'] > 1][:10], 'brewed_once': sum(1 for x in top if x['brews'] == 1),
            'never_brewed': len(never), 'never_brewed_list': [{'recipe': r['name'], 'style': r['style']} for r in never[:10]]}


def _consumption_patterns(conn, year):
    weekday, month = [0.0] * 7, [0.0] * 12
    for r in conn.execute(f'SELECT ts, {_consumed_liters_sql()} AS l FROM consumption_log c'):
        d = _d(r['ts'])
        if d and _in_year(d, year) and r['l']:
            weekday[d.weekday()] += r['l']
            month[d.month - 1] += r['l']
    return {'weekday_liters': [round(v, 2) for v in weekday], 'month_liters': [round(v, 2) for v in month]}


def _cellar(conn, beers, beers_all, styles, today, year):
    ages = []
    for b in beers:
        liters = beer_liters(b)
        bottle_d = _d(b['bottling_date'])
        if liters <= 0 or not bottle_d:
            continue
        ages.append({'beer': b['name'], 'style': styles.get(b['recipe_id']) or b['type'], 'liters': round(liters, 2),
                     'bottling_date': bottle_d.isoformat(), 'age_days': (today - bottle_d).days})
    ages.sort(key=lambda x: -x['age_days'])
    last_conso = {r[0]: _d(r[1]) for r in conn.execute(
        'SELECT beer_id, MAX(ts) FROM consumption_log WHERE beer_id IS NOT NULL GROUP BY beer_id')}
    # Rotation : durée pour vider un lot (mise en bouteille → dernière consommation). Lot pas encore vidé mais
    # entamé à 20 % ou plus : durée projetée au rythme observé depuis la mise en bouteille.
    turnover = defaultdict(list)
    for b in beers_all:
        initial = sum((b[f'initial_{s}'] or 0) * l for s, l in BottleSize.SIZES_CL.items()) + (b['keg_initial_liters'] or 0)
        bottle_d = _d(b['bottling_date'])
        if initial <= 0 or not bottle_d or not _in_year(bottle_d, year):
            continue
        left, end = beer_liters(b), last_conso.get(b['id'])
        if left <= 0 and end and end >= bottle_d:
            turnover[styles.get(b['recipe_id']) or b['type'] or '—'].append(((end - bottle_d).days, False))
        else:
            used = 1 - left / initial
            elapsed = (today - bottle_d).days
            if used >= 0.2 and elapsed > 0:
                turnover[styles.get(b['recipe_id']) or b['type'] or '—'].append((elapsed / used, True))
    return {'ages': ages, 'avg_age_days': _round(_avg([a['age_days'] for a in ages]), 0),
            'turnover': sorted(({'style': s, 'n': len(v), 'avg_days': _round(_avg([d for d, _ in v]), 0),
                                 'projected': sum(1 for _, p in v if p)} for s, v in turnover.items()),
                               key=lambda x: -x['n'])}


def _stock(conn, today):
    items = [dict(r) for r in conn.execute(
        'SELECT id, name, category, quantity, unit, price_per_unit, expiry_date, created_at FROM inventory_items '
        'WHERE archived=0 AND deleted_at IS NULL')]
    last_use = {r[0]: _d(r[1]) for r in conn.execute(
        'SELECT inventory_item_id, MAX(ts) FROM inventory_log WHERE delta < 0 GROUP BY inventory_item_id')}
    dormant, expiring, expired = [], [], []
    for it in items:
        value = _item_value(it)
        if not it['quantity'] or it['quantity'] <= 0:
            continue
        used = last_use.get(it['id'])
        ref = used or _d(it['created_at'])
        if ref and (today - ref).days >= DORMANT_DAYS:
            dormant.append({'item': it['name'], 'category': it['category'], 'value': _round(value, 2),
                            'last_used': used.isoformat() if used else None, 'idle_days': (today - ref).days})
        exp = _d(it['expiry_date'])
        if exp:
            entry = {'item': it['name'], 'category': it['category'], 'value': _round(value, 2), 'expiry_date': exp.isoformat()}
            if exp < today:
                expired.append(entry)
            elif (exp - today).days <= EXPIRY_DAYS:
                expiring.append(entry)
    dormant.sort(key=lambda x: -(x['value'] or 0))
    expiring.sort(key=lambda x: x['expiry_date'])

    # Valeur du stock fin de mois sur 12 mois : quantités reconstituées à rebours depuis le journal d'inventaire,
    # valorisées au prix actuel (l'historique des prix ne démarre qu'avec inventory_price_log).
    priced = {it['id']: it for it in items if it['price_per_unit'] is not None}
    deltas = defaultdict(list)
    if priced:
        for r in conn.execute(f'SELECT inventory_item_id, ts, delta FROM inventory_log WHERE inventory_item_id IN '
                              f'({",".join("?" * len(priced))})', list(priced)):
            t = _d(r['ts'])
            if t and r['delta']:
                deltas[r['inventory_item_id']].append((t, r['delta']))
    months, y, m = [], today.year, today.month
    for _ in range(12):
        months.insert(0, (y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    series = []
    for (y, m) in months:
        end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        end = min(end, today)
        total = 0.0
        for iid, it in priced.items():
            qty = (it['quantity'] or 0) - sum(dl for t, dl in deltas.get(iid, []) if t > end)
            created = _d(it['created_at'])
            if created and created > end:
                continue
            v = _item_value(it, max(qty, 0))
            total += v or 0
        series.append({'month': f'{y:04d}-{m:02d}', 'value': round(total, 2)})
    return {'dormant': dormant, 'dormant_value': _round(sum(x['value'] or 0 for x in dormant), 2),
            'expiring': expiring, 'expiring_value': _round(sum(x['value'] or 0 for x in expiring), 2),
            'expired': expired, 'expired_value': _round(sum(x['value'] or 0 for x in expired), 2),
            'value_series': series}


def _prices(conn):
    rows = conn.execute('SELECT inventory_item_id, item_name, category, old_price, new_price, ts '
                        'FROM inventory_price_log ORDER BY ts').fetchall()
    per = defaultdict(list)
    for r in rows:
        if r['new_price'] is not None:
            per[(r['inventory_item_id'], r['item_name'])].append((r['ts'], r['new_price'], r['category']))
    changes = []
    for (iid, name), pts in per.items():
        if len(pts) < 2 or not pts[0][1]:
            continue
        first, lastp = pts[0][1], pts[-1][1]
        changes.append({'item': name, 'category': pts[-1][2], 'first': first, 'last': lastp,
                        'change_pct': _round((lastp - first) / first * 100), 'since': str(pts[0][0])[:10],
                        'points': [[str(t)[:10], p] for t, p, _ in pts]})
    changes.sort(key=lambda x: -abs(x['change_pct'] or 0))
    since = rows[0]['ts'] if rows else None
    return {'since': str(since)[:10] if since else None, 'tracked_items': len(per), 'changes': changes[:15]}


def _brew_days(conn, brews, year):
    names = {b['id']: (b['name'], b['brew_date']) for b in brews}
    per = defaultdict(list)
    for r in conn.execute('SELECT brew_id, ts FROM brew_log'):
        t = _dt(r['ts'])
        if t and r['brew_id'] in names:
            per[r['brew_id']].append(t)
    out = []
    for bid, ts in per.items():
        name, brew_date = names[bid]
        day = _d(brew_date) or min(ts).date()
        if not _in_year(day, year):
            continue
        same_day = sorted(t for t in ts if t.date() == day)    # le jour de brassage seulement (pas les dry-hops)
        if len(same_day) < 2:
            continue
        out.append({'brew': name, 'brew_date': day.isoformat(), 'start': same_day[0].strftime('%H:%M'),
                    'end': same_day[-1].strftime('%H:%M'), 'steps': len(same_day),
                    'hours': round((same_day[-1] - same_day[0]).total_seconds() / 3600, 2)})
    out.sort(key=lambda x: x['brew_date'])
    return {'brews': out, 'avg_hours': _round(_avg([x['hours'] for x in out]), 2)}


def _kegs(conn, today):
    kegs = [dict(r) for r in conn.execute(
        'SELECT name, status, volume_total, current_liters, next_revision_date FROM soda_kegs WHERE archived=0')]
    status = defaultdict(int)
    for k in kegs:
        status[k['status'] or 'empty'] += 1
    revisions = []
    for k in kegs:
        nxt = _d(k['next_revision_date'])
        if nxt:
            revisions.append({'keg': k['name'], 'date': nxt.isoformat(), 'days': (nxt - today).days})
    revisions.sort(key=lambda x: x['date'])
    busy = sum(n for s, n in status.items() if s != 'empty')
    capacity = sum(k['volume_total'] or 0 for k in kegs)
    filled = sum(k['current_liters'] or 0 for k in kegs)
    return {'count': len(kegs), 'by_status': dict(status), 'occupancy_pct': _round(busy / len(kegs) * 100, 0) if kegs else None,
            'fill_pct': _round(filled / capacity * 100, 0) if capacity else None, 'revisions': revisions[:10]}


def insights(year=None, today=None):
    """Toutes les analyses ; *today* fixable pour les tests."""
    today = today or date.today()
    with get_db() as conn:
        beers_all = [dict(r) for r in conn.execute(
            '''SELECT be.*, COALESCE(be.brew_date, br.brew_date) AS eff_brew_date
               FROM beers be LEFT JOIN brews br ON br.id = be.brew_id
               WHERE be.deleted_at IS NULL''')]
        beers = [b for b in beers_all if not b['archived']]
        styles = {r['id']: r['style'] for r in conn.execute('SELECT id, style FROM recipes')}
        brews = _brews(conn)
        return {
            'year': year,
            'runway': _runway(conn, beers, today),
            'yeasts': _yeast_attenuation(conn, brews, year),
            'curves': _ferment_curves(conn, brews, year),
            'losses': _losses(conn, brews, beers_all, year),
            'pipeline': _pipeline(beers_all, styles, year),
            'tasting': _tasting(beers_all, styles, year),
            'recipes': _recipes(conn, brews, year),
            'consumption': _consumption_patterns(conn, year),
            'cellar': _cellar(conn, beers, beers_all, styles, today, year),
            'stock': _stock(conn, today),
            'prices': _prices(conn),
            'brew_days': _brew_days(conn, brews, year),
            'kegs': _kegs(conn, today),
        }


@bp.route('/api/stats/insights')
def get_insights():
    year = request.args.get('year', 'all')
    return jsonify(insights(int(year) if year.isdigit() else None))
