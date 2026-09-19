"""Rendu de la vitrine, côté serveur.

Porté du JavaScript (`generateVitrineHtml` / `generateRecipeHtml` /
`_vBeerHeader` dans `script_ui.html`) pour qu'un travail planifié puisse
produire la vitrine sans navigateur — le JS ne pouvait tourner que dans une
page ouverte, ce qui interdisait toute publication automatique.

Le HTML et le CSS ne sont pas retapés : ils vivent dans
`templates/vitrine/*.tpl`, extraits tels quels des gabarits JavaScript, avec
des marqueurs `@@n@@` aux emplacements calculés. Seule la logique est portée
ici. La fidélité du rendu est vérifiée par comparaison octet par octet avec
la sortie du JavaScript (voir `tests/test_vitrine_rendu.py`).
"""

import decimal
import json
import math
import os
import re

TPL_DIR = os.path.join(os.path.dirname(__file__), 'templates', 'vitrine')

BOTTLE_SIZES = ['25cl', '33cl', '50cl', '75cl']
BOTTLE_SIZE_LITERS = {'25cl': 0.25, '33cl': 0.33, '50cl': 0.50, '75cl': 0.75}
DEFAULT_BOTTLE_SIZES = {'25cl': False, '33cl': True, '50cl': False, '75cl': True}

#: Noms de mois tels que les produit `toLocaleDateString('fr', …)`. Écrits en
#: dur plutôt que via `locale` : la locale fr_FR n'est pas garantie présente
#: sur la machine, et une date mal formée changerait l'affichage sans erreur.
_MOIS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
            'août', 'septembre', 'octobre', 'novembre', 'décembre']


# ── Primitives alignées sur leurs équivalents JavaScript ──────────────────

def esc(value):
    """Équivalent de `esc()` : n'échappe pas l'apostrophe, comme l'original."""
    if value is None:
        return ''
    return (str(value).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def num(value):
    """Rend un nombre comme JavaScript : 8.5 → « 8.5 », 8.0 → « 8 »."""
    if value is None:
        return ''
    f = float(value)
    return str(int(f)) if f == int(f) else repr(f)


def js_round(value):
    """Arrondi de `Math.round` : 62.5 → 63. `round()` de Python arrondit au
    pair le plus proche et donnerait 62, soit une barre de progression
    différente d'un pourcent sur la moitié des cas limites."""
    return math.floor(float(value) + 0.5)


def fixed(value, decimals):
    """Équivalent de `Number.toFixed()`.

    Le formatage de Python arrondit au pair le plus proche : 5.25 donnerait
    « 5.2 » là où JavaScript écrit « 5.3 ». On arrondit donc au supérieur sur
    la valeur binaire exacte, comme le fait toFixed.
    """
    q = decimal.Decimal(1).scaleb(-decimals)
    return str(decimal.Decimal(float(value)).quantize(q, rounding=decimal.ROUND_HALF_UP))


def v_date(iso):
    """Date longue en français, format de `toLocaleDateString('fr', …)`."""
    if not iso:
        return ''
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', str(iso))
    if not m:
        return str(iso)
    an, mois, jour = m.group(1), int(m.group(2)), m.group(3)
    if not 1 <= mois <= 12:
        return str(iso)
    return f'{jour} {_MOIS_FR[mois - 1]} {an}'


def bottle_sizes_enabled(settings):
    sizes = dict(DEFAULT_BOTTLE_SIZES)
    sizes.update(settings.get('bottleSizes') or {})
    return sizes


def is_size_enabled(size, settings):
    return bool(bottle_sizes_enabled(settings).get(size))


def beer_liters(beer):
    if not beer:
        return 0
    return (sum((beer.get(f'stock_{s}') or 0) * BOTTLE_SIZE_LITERS[s] for s in BOTTLE_SIZES)
            + (beer.get('keg_liters') or 0))


def _tpl(nom):
    with open(os.path.join(TPL_DIR, nom + '.tpl'), encoding='utf-8') as f:
        return f.read()


def _remplir(gabarit, valeurs):
    """Substitue les marqueurs @@n@@ du gabarit.

    Remplacement direct et non `str.format` : le CSS est truffé d'accolades,
    que `format` prendrait pour des champs.
    """
    for k, v in enumerate(valeurs):
        gabarit = gabarit.replace(f'@@{k}@@', v if v is not None else '')
    return gabarit


# ── Valeurs théoriques d'une recette ─────────────────────────────────────

def rec_max_extract(rec, catalog):
    """Extrait maximal en points de gravité, à 100 % de rendement."""
    total = 0.0
    par_nom = {(c.get('name') or '').lower(): c for c in (catalog or [])}
    for ing in (rec.get('ingredients') or []):
        if ing.get('category') != 'malt':
            continue
        gu = ing.get('gu')
        if gu is None:
            cat = par_nom.get((ing.get('name') or '').lower())
            gu = cat.get('gu') if cat else None
        if gu is None:
            continue
        qte = float(ing.get('quantity') or 0)
        total += (qte if ing.get('unit') == 'kg' else qte / 1000) * float(gu)
    return total


def rec_theoretical(rec, catalog=None):
    vol = rec.get('volume') or 20
    eff = rec.get('brewhouse_efficiency') or 72
    max_pts = rec_max_extract(rec, catalog)
    if not max_pts:
        return None
    og = 1 + (max_pts * (eff / 100) / vol) / 1000
    fg = 1 + (og - 1) * 0.25
    return {'og': og, 'fg': fg, 'abv': (og - fg) * 131.25, 'eff': eff, 'maxPts': max_pts}


def rec_water(rec):
    """Volumes d'eau d'empâtage et de rinçage, en litres.

    Même calcul que la fiche de recette de l'application : l'eau totale est
    le pré-ébullition augmenté de ce que le grain absorbe, et l'empâtage est
    le ratio demandé, relevé au besoin à 55 % du total pour qu'il reste
    supérieur au rinçage. Une valeur saisie à la main prend le pas sur le
    calcul, séparément pour chacun des deux.

    Renvoie None sans grain : il n'y a alors rien à empâter.
    """
    grain_kg = sum((float(i.get('quantity') or 0) if i.get('unit') == 'kg'
                    else float(i.get('quantity') or 0) / 1000)
                   for i in (rec.get('ingredients') or []) if i.get('category') == 'malt')
    if grain_kg <= 0:
        return None

    vol = float(rec.get('volume') or 20)
    boil = float(rec.get('boil_time') or 60)
    ratio = float(rec.get('mash_ratio') or 3)
    evap = float(rec.get('evap_rate') or 3)
    absorption = float(rec.get('grain_absorption') or 0.8)

    preboil = vol + evap * (boil / 60)
    total_auto = preboil + grain_kg * absorption
    auto_mash = max(grain_kg * ratio, total_auto * 0.55)

    mash_ov = float(rec.get('water_mash_override') or 0)
    sparge_ov = float(rec.get('water_sparge_override') or 0)
    mash = mash_ov if mash_ov > 0 else auto_mash
    sparge = sparge_ov if sparge_ov > 0 else max(0.0, total_auto - mash)
    return {'mash': mash, 'sparge': sparge, 'total': mash + sparge,
            'manual_mash': mash_ov > 0, 'manual_sparge': sparge_ov > 0}


# ── Carte d'une bière (page d'accueil) ───────────────────────────────────

def _stock_item(count, label, cls, pct):
    barre = (f'<div class="si-bar"><div class="si-fill" style="width:{pct}%"></div></div>'
             if count > 0 and pct >= 0 else '')
    vide = '<div class="si-empty">épuisé</div>' if count == 0 else ''
    return (f'\n      <div class="si {cls}">\n'
            f'        <div class="si-n">{count if count > 0 else "–"}</div>\n'
            f'        <div class="si-l">{label}</div>\n'
            f'        {barre}\n'
            f'        {vide}\n'
            f'      </div>')


def _referm_badge(beer):
    from datetime import date, timedelta
    if not beer.get('bottling_date') or not beer.get('refermentation_days'):
        return 'Refermentation en cours'
    d = date.fromisoformat(str(beer['bottling_date'])[:10]) + timedelta(days=int(beer['refermentation_days']))
    delta = (d - date.today()).days
    if delta > 0:
        # Date volontairement juste : le JavaScript passait par toISOString()
        # sur une date à minuit locale, ce qui la ramenait à la veille. Seul
        # écart assumé avec la sortie d'origine.
        return f'Prête dans {delta} j ({v_date(d.isoformat())})'
    if delta == 0:
        return 'Prête aujourd’hui ! 🎉'.replace('’', "'")
    return f'Prête depuis {-delta} j'


def make_card(beer, photo_map, vitrine_sizes, settings):
    photo = (photo_map or {}).get(beer['id'])
    img_src = f'images/beer-{beer["id"]}.{photo["ext"]}' if photo else None
    abv = f'{fixed(beer["abv"], 1)} %' if beer.get('abv') is not None else None
    keg_l = beer.get('keg_liters') or 0
    keg_i = beer.get('keg_initial_liters') or 0
    pct_keg = js_round(min(100, keg_l / keg_i * 100)) if keg_i > 0 else -1

    if keg_l > 0 or keg_i > 0:
        couleur = '#333' if keg_l == 0 else ('#f59e0b' if 0 <= pct_keg <= 40 else 'var(--amber)')
        barre = (f'<div class="keg-bar"><div class="keg-fill" style="width:{pct_keg}%;background:{couleur}"></div></div>'
                 if keg_i > 0 and keg_i > keg_l else '')
        init = f'<span class="keg-init">/ {num(keg_i)} L</span>' if keg_i > 0 else ''
        keg_block = (f'\n      <div class="keg-row">\n        <span class="keg-icon">🛢</span>\n'
                     f'        <div class="keg-info">\n          <span class="keg-val">{num(keg_l)} L</span>\n'
                     f'          <span class="keg-lbl">en fût</span>\n          {barre}\n        </div>\n'
                     f'        {init}\n      </div>')
    else:
        keg_block = ''

    brew_info = [x for x in (
        f'🍺 Brassée le {v_date(beer["brew_date"])}' if beer.get('brew_date') else '',
        f'🍾 Embouteillée le {v_date(beer["bottling_date"])}' if beer.get('bottling_date') else '',
        ((f'<a class="recipe-link" href="recipes/{beer["recipe_id"]}.html">📋 {esc(beer["recipe_name"])}</a>'
          if beer.get('recipe_id') else f'📋 {esc(beer["recipe_name"])}') if beer.get('recipe_name') else ''),
        (f'<a class="recipe-link" href="{esc(beer["brew_photos_url"])}" target="_blank" rel="noopener">📷 Photos</a>'
         if beer.get('brew_photos_url') else ''),
    ) if x]

    lignes = []
    for size in vitrine_sizes:
        count = beer.get(f'stock_{size}') or 0
        init = beer.get(f'initial_{size}') or 0
        pct = js_round(min(100, count / init * 100)) if init > 0 else -1
        cls = 'zero' if count == 0 else ('low' if 0 <= pct <= 40 else 'ok')
        lignes.append(_stock_item(count, f'{size.replace("cl", "")} cl', cls, pct))

    app_name = settings.get('appName')
    return _remplir(_tpl('card'), [
        str(beer['id']),
        (f'<img class="card-img" src="{img_src}" loading="lazy" alt="{esc(beer["name"])}" '
         f'data-name="{esc(beer["name"])}" onclick="openLb(this,this.dataset.name)">'
         if img_src else '<div class="card-img-ph">🍺</div>'),
        esc(beer['name']),
        f'<div class="card-type">{esc(beer["type"])}</div>' if beer.get('type') else '',
        f'<div class="card-abv">ABV <strong>{abv}</strong></div>' if abv else '',
        f'<div class="referm-badge">🔄 {_referm_badge(beer)}</div>' if beer.get('refermentation') else '',
        keg_block,
        '<div class="stock-sep"></div>'.join(lignes),
        f'<div class="card-origin">📍 {esc(beer["origin"])}</div>' if beer.get('origin') else '',
        f'<p class="card-desc">{esc(beer["description"])}</p>' if beer.get('description') else '',
        ('<div class="card-foot">' + '<span class="sep">·</span>'.join(brew_info) + '</div>') if brew_info else '',
        f'<div class="card-brand">{esc(app_name)}</div>' if app_name else '',
    ])


# ── Page d'accueil ───────────────────────────────────────────────────────

def generate_vitrine_html(beers, photo_map, icon_path, settings, today=None):
    from datetime import date
    jour = today or date.today()
    date_str = f'{jour.day:02d} {_MOIS_FR[jour.month - 1]} {jour.year}'

    vitrine_sizes = [s for s in BOTTLE_SIZES
                     if is_size_enabled(s, settings) or any((b.get(f'stock_{s}') or 0) > 0 for b in beers)]
    total_by_s = {s: sum(b.get(f'stock_{s}') or 0 for b in beers) for s in vitrine_sizes}
    total_keg = sum(b.get('keg_liters') or 0 for b in beers)

    in_stock = [b for b in beers if beer_liters(b) > 0]
    exhausted = [b for b in beers if beer_liters(b) == 0]
    cards_active = ''.join(make_card(b, photo_map, vitrine_sizes, settings) for b in in_stock)
    cards_exhausted = ''.join(make_card(b, photo_map, vitrine_sizes, settings) for b in exhausted)

    if not in_stock and not exhausted:
        grille = '<div class="grid"><div class="empty">Aucune bière disponible pour le moment.</div></div>'
    else:
        # Le « \n     » suit la grille dans tous les cas : il appartient au
        # gabarit, avant l'insertion conditionnelle de la section « Épuisées ».
        suite = ('\n     <div class="section-divider">\n'
                 '       <div class="section-divider-line"></div>\n'
                 f'       <div class="section-divider-label">Épuisées ({len(exhausted)})</div>\n'
                 '       <div class="section-divider-line"></div>\n'
                 '     </div>\n'
                 f'     <div class="grid grid-exhausted">{cards_exhausted}</div>') if exhausted else ''
        grille = f'<div class="grid">{cards_active}</div>\n     {suite}'

    app_name = settings.get('appName')
    return _remplir(_tpl('index'), [
        settings.get('accentColor') or '#f5a623',
        (f'<img src="{icon_path}" alt="" style="width:56px;height:56px;object-fit:contain;'
         'border-radius:12px;margin-bottom:8px;display:block;margin-left:auto;margin-right:auto">'
         if icon_path else ''),
        f'<div class="appname">{esc(app_name)}</div>' if app_name else '',
        date_str,
        str(len(beers)),
        ''.join(f'<div><div class="stat-val">{total_by_s[s]}</div>'
                f'<div class="stat-lbl">Bouteilles {s.replace("cl", "")} cl</div></div>' for s in vitrine_sizes),
        (f'<div><div class="stat-val">{num(total_keg)}</div>'
         '<div class="stat-lbl">Litres en fût</div></div>') if total_keg > 0 else '',
        grille,
        esc(app_name or 'BrewHome'),
        'Fermer',
    ])


# ── En-tête « bière » des pages de recette ───────────────────────────────

def beer_header(beer, photo_src, settings):
    if not beer:
        return ''
    abv = f'{fixed(beer["abv"], 1)} %' if beer.get('abv') is not None else None
    keg_l = beer.get('keg_liters') or 0
    keg_i = beer.get('keg_initial_liters') or 0

    sizes = [s for s in BOTTLE_SIZES
             if is_size_enabled(s, settings) or (beer.get(f'stock_{s}') or 0) > 0]
    stock = ''
    for s in sizes:
        count = beer.get(f'stock_{s}') or 0
        init = beer.get(f'initial_{s}') or 0
        pct = js_round(min(100, count / init * 100)) if init > 0 else -1
        cls = 'zero' if count == 0 else ('low' if 0 <= pct <= 40 else 'ok')
        barre = f'<div class="bsi-bar"><div class="bsi-fill" style="width:{pct}%"></div></div>' if count > 0 and pct >= 0 else ''
        stock += (f'<div class="bsi {cls}">\n      <div class="bsi-n">{count if count > 0 else "–"}</div>\n'
                  f'      <div class="bsi-l">{esc(s.replace("cl", ""))} cl</div>\n      {barre}\n    </div>')

    keg = ''
    if keg_l > 0 or keg_i > 0:
        barre = (f'<div class="bsi-bar"><div class="bsi-fill" style="width:{js_round(min(100, keg_l / keg_i * 100))}%"></div></div>'
                 if keg_i > 0 and keg_i > keg_l else '')
        keg = (f'<div class="bsi {"zero" if keg_l == 0 else "ok"}">\n      <div class="bsi-n">{num(keg_l)} L</div>\n'
               f'      <div class="bsi-l">en fût</div>\n      {barre}\n    </div>')

    dates = '<span class="bh-sep">·</span>'.join([x for x in (
        f'🍺 Brassée le {v_date(beer["brew_date"])}' if beer.get('brew_date') else '',
        f'🍾 Embouteillée le {v_date(beer["bottling_date"])}' if beer.get('bottling_date') else '',
        f'📍 {esc(beer["origin"])}' if beer.get('origin') else '',
    ) if x])

    image = (f'<img class="bh-img" src="{esc(photo_src)}" alt="{esc(beer["name"])}" loading="lazy">'
             if photo_src else '<div class="bh-img bh-img-ph">🍺</div>')
    type_html = f'<span class="bh-type">{esc(beer["type"])}</span>' if beer.get('type') else ''
    abv_html = f'<span class="bh-abv">ABV <strong>{abv}</strong></span>' if abv else ''
    stock_html = f'<div class="bh-stock">{stock}{keg}</div>' if (stock or keg) else ''
    desc_html = f'<p class="bh-desc">{esc(beer["description"])}</p>' if beer.get('description') else ''
    dates_html = f'<div class="bh-dates">{dates}</div>' if dates else ''
    return (
        '\n  <div class="beer-head">\n'
        f'    {image}\n'
        '    <div class="bh-body">\n'
        f'      <div class="bh-name">{esc(beer["name"])}</div>\n'
        '      <div class="bh-meta">\n'
        f'        {type_html}\n'
        f'        {abv_html}\n'
        '      </div>\n'
        f'      {stock_html}\n'
        f'      {desc_html}\n'
        f'      {dates_html}\n'
        f'      <a class="bh-link" href="../index.html#beer-{beer["id"]}">Voir dans la cave →</a>\n'
        '    </div>\n'
        '  </div>')


# ── Page d'une recette ───────────────────────────────────────────────────

_HOP_TYPE = {'ebullition': 'Ébullition', 'whirlpool': 'Whirlpool',
             'flameout': 'Flameout', 'dryhop': 'Dry-hop'}


def _mc(val, lbl, cls=''):
    return (f'<div class="mc{cls}"><div class="mc-val">{esc(val)}</div>'
            f'<div class="mc-lbl">{esc(lbl)}</div></div>')


def _tbl(thead, tbody):
    entetes = ''.join(f'<th>{h}</th>' for h in thead)
    return f'<table><thead><tr>{entetes}</tr></thead><tbody>{tbody}</tbody></table>'


def _sec(lbl):
    return f'<div class="section">{lbl}</div>'


def _qte(ing):
    """Quantité telle que l'écrivait le JavaScript : sans décimale inutile."""
    return f'{num(ing.get("quantity"))} {esc(ing.get("unit"))}'


def generate_recipe_html(rec, beer, theo, photo_src, settings):
    ings = rec.get('ingredients') or []
    malts = [i for i in ings if i.get('category') == 'malt']
    hops = sorted([i for i in ings if i.get('category') == 'houblon'],
                  key=lambda h: -(h.get('hop_time') or 0))
    yeasts = [i for i in ings if i.get('category') == 'levure']
    misc = [i for i in ings if i.get('category') == 'autre']

    accent = settings.get('accentColor') or '#f5a623'
    app_name = settings.get('appName') or 'BrewHome'
    total_kg = sum((float(m.get('quantity') or 0) if m.get('unit') == 'kg'
                    else float(m.get('quantity') or 0) / 1000) for m in malts)

    malt_rows = ''.join(
        f'<tr><td>{esc(m.get("name"))}</td><td>{_qte(m)}</td>'
        f'<td>{num(m["ebc"]) if m.get("ebc") is not None else "–"}</td></tr>' for m in malts)
    hop_rows = ''.join(
        f'<tr><td>{esc(h.get("name"))}</td><td>{_qte(h)}</td>'
        f'<td>{num(h["alpha"]) + " %" if h.get("alpha") is not None else "–"}</td>'
        f'<td>{str(num(h["hop_time"])) + " min " if h.get("hop_time") is not None else ""} '
        f'{esc(_HOP_TYPE.get(h.get("hop_type"), h.get("hop_type") or ""))}</td></tr>' for h in hops)
    yeast_rows = ''.join(
        f'<tr><td>{esc(y.get("name"))}</td><td>{_qte(y)}</td></tr>' for y in yeasts)
    misc_rows = ''.join(
        f'<tr><td>{esc(m.get("name"))}</td><td>{_qte(m)}</td>'
        f'<td>{esc(m.get("other_type") or "–")}</td></tr>' for m in misc)

    rendement = f'{num(rec.get("brewhouse_efficiency") or 72)} %'
    if theo:
        metrics = (_mc(fixed(theo['og'], 3), 'DI théo.') + _mc(fixed(theo['fg'], 3), 'DF théo.')
                   + _mc(fixed(theo['abv'], 1) + ' %', 'ABV théo.') + _mc(rendement, 'Rendement'))
    else:
        metrics = _mc(rendement, 'Rendement')

    # Mesures du brassin, sous les théoriques. L'ABV retombe sur celui de la
    # bière quand le brassin n'en porte pas : les deux champs sont distincts.
    real_og = beer.get('brew_og') if beer else None
    real_fg = beer.get('brew_fg') if beer else None
    real_abv = (beer.get('brew_abv') if beer and beer.get('brew_abv') is not None
                else (beer.get('abv') if beer else None))
    parts = [p for p in (
        _mc(fixed(real_og, 3), 'DI mesurée', ' mc-real') if real_og is not None else '',
        _mc(fixed(real_fg, 3), 'DF mesurée', ' mc-real') if real_fg is not None else '',
        _mc(fixed(real_abv, 1) + ' %', 'ABV réel', ' mc-real') if real_abv is not None else '',
    ) if p]
    real_html = f'<div class="metrics metrics-real">{"".join(parts)}</div>' if parts else ''

    sous_titre = ' · '.join([x for x in (rec.get('style') or '',
                                         f'{num(rec["volume"])} L' if rec.get('volume') else '') if x])

    eau = rec_water(rec)
    brassage = ''
    if rec.get('mash_temp') or rec.get('mash_time') or rec.get('boil_time') or eau:
        cases = [
            f'<div><div class="mi-val">{num(rec["mash_temp"])} °C</div><div class="mi-lbl">T° empâtage</div></div>' if rec.get('mash_temp') else '',
            f'<div><div class="mi-val">{num(rec["mash_time"])} min</div><div class="mi-lbl">Durée empâtage</div></div>' if rec.get('mash_time') else '',
            f'<div><div class="mi-val">{num(rec["boil_time"])} min</div><div class="mi-lbl">Ébullition</div></div>' if rec.get('boil_time') else '',
            f'<div><div class="mi-val">{num(rec["volume"])} L</div><div class="mi-lbl">Volume cible</div></div>' if rec.get('volume') else '',
            f'<div><div class="mi-val">{fixed(eau["mash"], 1)} L</div><div class="mi-lbl">Eau d\'empâtage</div></div>' if eau else '',
            f'<div><div class="mi-val">{fixed(eau["sparge"], 1)} L</div><div class="mi-lbl">Eau de rinçage</div></div>' if eau else '',
        ]
        # Une entrée par ligne, y compris vide : le gabarit les sépare par des
        # retours à la ligne, qu'une jointure simple supprimerait.
        lignes_brassage = ''.join('\n    ' + c for c in cases)
        brassage = f'\n  {_sec("Brassage")}\n  <div class="mash-info">{lignes_brassage}\n  </div>'

    beer_link = (f'<div class="beer-link-row"><a href="../index.html#beer-{beer["id"]}" '
                 f'class="back-beer">🍺 {esc(beer["name"])}</a></div>') if beer else ''

    return _remplir(_tpl('recipe'), [
        esc(rec.get('name')), accent, beer_header(beer, photo_src, settings), esc(rec.get('name')),
        f'<div class="subtitle">{esc(sous_titre)}</div>' if sous_titre else '',
        metrics, real_html,
        (_sec(f'Fermentescibles ({fixed(total_kg, 2)} kg)') + _tbl(['Malt', 'Quantité', 'EBC'], malt_rows)) if malts else '',
        (_sec('Houblons') + _tbl(['Houblon', 'Quantité', 'Alpha', 'Addition'], hop_rows)) if hops else '',
        (_sec('Levure') + _tbl(['Levure', 'Quantité'], yeast_rows)) if yeasts else '',
        (_sec('Divers') + _tbl(['Ingrédient', 'Quantité', 'Type'], misc_rows)) if misc else '',
        brassage,
        (_sec('Notes') + f'<div class="notes">{esc(rec.get("notes"))}</div>') if rec.get('notes') else '',
        beer_link, esc(app_name),
    ])
