import os
import json
import base64
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request, current_app, Response
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError

from db import get_db, get_readings_db, _log
from constants import BrewStatus
from helpers import api_error
from scheduler import _scheduler

bp = Blueprint('integrations', __name__)

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def _tg_get_settings():
    """Récupère la config Telegram depuis la base de données."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_settings "
                "WHERE key IN ('telegram_token','telegram_chat_id','telegram_notifs','telegram_tz')"
            ).fetchall()
    except Exception as e:
        current_app.logger.warning(f"_tg_get_settings: DB error: {e}")
        return None, None, {}, 'UTC'
    s = {r['key']: r['value'] for r in rows}
    notifs = {}
    raw_notifs = s.get('telegram_notifs')
    if raw_notifs:
        try:
            notifs = json.loads(raw_notifs)
        except (json.JSONDecodeError, ValueError) as e:
            current_app.logger.warning(
                "_tg_get_settings: telegram_notifs JSON corrompu (valeur ignorée): %s", e
            )
    return s.get('telegram_token'), s.get('telegram_chat_id'), notifs, s.get('telegram_tz', 'UTC')


def _tg_send(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _tg_build_brews():
    with get_db() as conn:
        _active_ph = ','.join('?' * len(BrewStatus.ACTIVE))
        brews = conn.execute(
            f"SELECT id, name, status, og, fg, abv, brew_date FROM brews "
            f"WHERE archived=0 AND status IN ({_active_ph}) ORDER BY brew_date DESC",
            BrewStatus.ACTIVE
        ).fetchall()
        spindle_data = {}
        for b in brews:
            row = conn.execute(
                "SELECT r.gravity, r.temperature, r.recorded_at "
                "FROM spindles s "
                "JOIN rdb.spindle_readings r ON r.spindle_id = s.id "
                "WHERE s.brew_id = ? "
                "ORDER BY r.recorded_at DESC LIMIT 1",
                (b['id'],)
            ).fetchone()
            if row:
                spindle_data[b['id']] = row
    if not brews:
        return "🍺 <b>Brassins en cours</b>\n\nAucun brassin actif en ce moment."
    st_map = {
        BrewStatus.PLANNED:     '📋 Planifié',
        BrewStatus.IN_PROGRESS: '🔥 En cours',
        BrewStatus.FERMENTING:  '🧪 En fermentation',
    }
    lines = ["🍺 <b>Brassins en cours</b>"]
    for b in brews:
        st = st_map.get(b['status'], b['status'])
        line = f"\n• <b>{b['name']}</b> — {st}"
        if b['og']:
            line += f"\n  OG : {float(b['og']):.3f}"
            if b['fg']:
                line += f"  →  FG : {float(b['fg']):.3f}"
        if b['abv']:
            line += f"  |  ABV : {float(b['abv']):.1f} %"
        elif b['og'] and b['fg']:
            est_abv = (float(b['og']) - float(b['fg'])) * 131.25
            line += f"  |  ABV est. : ~{est_abv:.1f} %"
        if b['brew_date']:
            line += f"\n  Brassé le {b['brew_date']}"
        sr = spindle_data.get(b['id'])
        if sr:
            grav_str = f"{float(sr['gravity']):.3f}" if sr['gravity'] is not None else "—"
            temp_str = f"{float(sr['temperature']):.1f} °C" if sr['temperature'] is not None else "—"
            age = ""
            try:
                ts = datetime.fromisoformat(sr['recorded_at'].replace('Z', ''))
                diff = datetime.now() - ts
                mins = int(diff.total_seconds() // 60)
                if mins < 60:
                    age = f"{mins} min"
                elif mins < 1440:
                    age = f"{mins // 60} h"
                else:
                    age = f"{mins // 1440} j"
                age = f" <i>({age})</i>"
            except Exception as e:
                current_app.logger.debug(f"_tg_brews_msg: could not compute reading age: {e}")
            line += f"\n  📡 Densité : <b>{grav_str}</b>  |  🌡 Temp : <b>{temp_str}</b>{age}"
        lines.append(line)
    return "\n".join(lines)


def _tg_build_cave():
    with get_db() as conn:
        beers = conn.execute(
            "SELECT name, stock_33cl, stock_75cl, keg_liters "
            "FROM beers WHERE archived=0 ORDER BY name"
        ).fetchall()

    def _has_stock(b):
        return (b['stock_33cl'] or 0) + (b['stock_75cl'] or 0) > 0 or (b['keg_liters'] or 0) > 0

    in_stock  = [b for b in beers if     _has_stock(b)]
    out_stock = [b for b in beers if not _has_stock(b)]
    t33  = sum(b['stock_33cl'] or 0 for b in in_stock)
    t75  = sum(b['stock_75cl'] or 0 for b in in_stock)
    tkeg = sum(b['keg_liters'] or 0 for b in in_stock)
    lines = ["🍾 <b>État de la cave</b>",
             f"\n{len(beers)} bière(s)  —  {t33}×33cl  {t75}×75cl"]
    if tkeg:
        lines.append(f"  {tkeg:.1f} L en fût")
    if in_stock:
        lines.append("\n<b>En stock :</b>")
        for b in in_stock:
            parts = []
            if b['stock_33cl']:  parts.append(f"{b['stock_33cl']}×33cl")
            if b['stock_75cl']:  parts.append(f"{b['stock_75cl']}×75cl")
            if b['keg_liters']:  parts.append(f"{float(b['keg_liters']):.1f} L fût")
            lines.append(f"• {b['name']} : {', '.join(parts)}")
    if out_stock:
        lines.append("\n<b>Épuisées :</b>")
        for b in out_stock:
            lines.append(f"• {b['name']}")
    return "\n".join(lines)


def _tg_fire_low_stock(item_name, qty, unit, threshold):
    """Envoie une alerte Telegram quand un ingrédient passe sous son seuil."""
    token, chat_id, _, _ = _tg_get_settings()
    if not token or not chat_id:
        return
    text = (
        f"⚠️ <b>Stock bas</b>\n\n"
        f"• {item_name} : <b>{qty} {unit}</b>\n"
        f"Seuil d'alerte : {threshold} {unit}"
    )
    _tg_send(token, chat_id, text)


def _tg_build_inventory():
    """Retourne une liste de messages, un par catégorie présente."""
    with get_db() as conn:
        items = conn.execute(
            "SELECT name, category, quantity, unit "
            "FROM inventory_items WHERE archived=0 ORDER BY category, name"
        ).fetchall()
    if not items:
        return ["📦 <b>Inventaire</b>\n\nAucun article en stock."]
    labels = {
        'malt':    ('🌾', 'Malts'),
        'houblon': ('🌿', 'Houblons'),
        'levure':  ('🧫', 'Levures'),
        'autre':   ('🔮', 'Autres'),
    }
    order = ['malt', 'houblon', 'levure', 'autre']
    by_cat = {}
    for i in items:
        by_cat.setdefault(i['category'], []).append(i)
    messages = []
    for cat in order:
        cat_items = by_cat.get(cat)
        if not cat_items:
            continue
        icon, label = labels.get(cat, ('📦', cat.capitalize()))
        lines = [f"{icon} <b>Inventaire — {label}</b>", ""]
        for it in cat_items:
            lines.append(f"• {it['name']} : {it['quantity']} {it['unit']}")
        messages.append("\n".join(lines))
    for cat, cat_items in by_cat.items():
        if cat not in order:
            icon, label = labels.get(cat, ('📦', cat.capitalize()))
            lines = [f"{icon} <b>Inventaire — {label}</b>", ""]
            for it in cat_items:
                lines.append(f"• {it['name']} : {it['quantity']} {it['unit']}")
            messages.append("\n".join(lines))
    return messages


def _tg_build_ferm_reminders():
    """Rappels fermentation : J-2, J-1, J0, J+1 pour brassins actifs ; J-1/J0 dry hops ; J-2/J-1/J0/J+1 refermentation."""
    today = date.today()
    with get_db() as conn:
        _active_ph = ','.join('?' * len(BrewStatus.ACTIVE))
        brews = conn.execute(
            f"SELECT id, name, brew_date, ferm_time, volume_brewed "
            f"FROM brews WHERE archived=0 AND status IN ({_active_ph}) "
            "AND brew_date IS NOT NULL AND ferm_time IS NOT NULL",
            BrewStatus.ACTIVE
        ).fetchall()
        dry_hops = conn.execute(
            f'''SELECT b.name, b.brew_date, COALESCE(b.ferm_time, r.ferm_time) AS ferm_time,
                       b.dryhop_done_dates,
                       ri.name AS hop_name, ri.hop_days, ri.quantity, ri.unit
                FROM brews b
                LEFT JOIN recipes r ON r.id = b.recipe_id
                JOIN recipe_ingredients ri
                    ON ri.recipe_id = b.recipe_id
                    AND ri.category = 'houblon' AND ri.hop_type = 'dryhop' AND ri.hop_days > 0
                WHERE b.archived = 0 AND b.status IN ({_active_ph})
                  AND b.brew_date IS NOT NULL AND b.recipe_id IS NOT NULL
                  AND COALESCE(b.ferm_time, r.ferm_time) IS NOT NULL''',
            BrewStatus.ACTIVE
        ).fetchall()
    messages = []
    for b in brews:
        try:
            start    = date.fromisoformat(b['brew_date'])
            end_date = start + timedelta(days=int(b['ferm_time']))
            delta    = (end_date - today).days
            name     = b['name']
            if delta == 2:
                messages.append(f"🍺 <b>{name}</b>\n⏳ Fin de fermentation estimée dans <b>2 jours</b> ({end_date.strftime('%d/%m')})")
            elif delta == 1:
                messages.append(f"🍺 <b>{name}</b>\n⏳ Fin de fermentation estimée <b>demain</b> ({end_date.strftime('%d/%m')})")
            elif delta == 0:
                vol = b['volume_brewed']
                bottle_hint = ""
                if vol:
                    net = float(vol) * 0.9
                    s33 = int(net * 1000 / 330)
                    s75 = int(net * 1000 / 750)
                    bottle_hint = f"\n🍾 Volume : <b>{vol} L</b> → ~<b>{s33} bouteilles 33cl</b> ou ~<b>{s75} × 75cl</b>"
                messages.append(f"🍺 <b>{name}</b>\n🫙 Fermentation terminée aujourd'hui — <b>C'est le moment d'embouteiller !</b>{bottle_hint}")
            elif delta < 0 and delta >= -2:
                messages.append(f"🍺 <b>{name}</b>\n⚠️ Fermentation dépassée de <b>{abs(delta)} jour(s)</b> — pensez à embouteiller !")
        except Exception:
            continue

    # Dry hops — groupés par (brassin, date d'ajout)
    dh_by_key = {}
    for dh in dry_hops:
        try:
            ferm  = int(dh['ferm_time'])
            days  = int(dh['hop_days'])
            offset = ferm - days
            if offset < 0:
                continue
            dh_date = date.fromisoformat(dh['brew_date']) + timedelta(days=offset)
            key = (dh['name'], dh_date.isoformat())
            if key not in dh_by_key:
                dh_by_key[key] = {'brew': dh['name'], 'date': dh_date, 'hops': [],
                                  'dryhop_done_dates': dh['dryhop_done_dates']}
            dh_by_key[key]['hops'].append(f"{dh['quantity']}\u202f{dh['unit']} {dh['hop_name']}")
        except Exception:
            continue
    for entry in dh_by_key.values():
        try:
            done_dates = json.loads(entry.get('dryhop_done_dates') or '[]')
        except (json.JSONDecodeError, TypeError):
            done_dates = []
        if entry['date'].isoformat() in done_dates:
            continue
        delta = (entry['date'] - today).days
        name  = entry['brew']
        hops  = ', '.join(entry['hops'])
        ds    = entry['date'].strftime('%d/%m')
        if delta == 1:
            messages.append(f"🌿 <b>{name}</b>\n⏳ Dry hop demain ({ds}) — {hops}")
        elif delta == 0:
            messages.append(f"🌿 <b>{name}</b>\n🍃 Ajout dry hop aujourd'hui ! — {hops}")
        elif delta < 0 and delta >= -1:
            messages.append(f"🌿 <b>{name}</b>\n⚠️ Dry hop dépassé de {abs(delta)} jour(s) — {hops}")

    with get_db() as conn:
        cave_beers = conn.execute(
            "SELECT id, name, bottling_date, refermentation_days "
            "FROM beers WHERE refermentation=1 AND bottling_date IS NOT NULL AND refermentation_days IS NOT NULL"
        ).fetchall()
    for b in cave_beers:
        try:
            start    = date.fromisoformat(b['bottling_date'])
            end_date = start + timedelta(days=int(b['refermentation_days']))
            delta    = (end_date - today).days
            name     = b['name']
            if delta == 2:
                messages.append(f"🔄 <b>{name}</b>\n⏳ Fin de refermentation estimée dans <b>2 jours</b> ({end_date.strftime('%d/%m')})")
            elif delta == 1:
                messages.append(f"🔄 <b>{name}</b>\n⏳ Fin de refermentation estimée <b>demain</b> ({end_date.strftime('%d/%m')})")
            elif delta == 0:
                messages.append(f"🔄 <b>{name}</b>\n🍾 Refermentation terminée aujourd'hui — <b>Les bouteilles sont prêtes !</b>")
            elif delta < 0 and delta >= -2:
                messages.append(f"🔄 <b>{name}</b>\n⚠️ Refermentation dépassée de <b>{abs(delta)} jour(s)</b> — les bouteilles devraient être prêtes !")
        except Exception:
            continue

    if not messages:
        return []
    return messages


def _tg_fire_bottling(beer_name, s33, s75, keg_liters, bottling_date):
    """Notification immédiate lors de l'ajout d'une bière en cave depuis un brassin."""
    token, chat_id, notifs, _ = _tg_get_settings()
    if not token or not chat_id:
        return
    if not notifs.get('bottling', {}).get('enabled', True):
        return
    lines = [f"🍾 <b>{beer_name}</b> mis(e) en cave !"]
    if bottling_date:
        try:
            d = date.fromisoformat(bottling_date)
            lines.append(f"📅 Date d'embouteillage : <b>{d.strftime('%d/%m/%Y')}</b>")
        except ValueError:
            pass
    stocks = []
    if s33 and int(s33) > 0:
        stocks.append(f"<b>{s33}</b> × 33cl")
    if s75 and int(s75) > 0:
        stocks.append(f"<b>{s75}</b> × 75cl")
    if keg_liters:
        try:
            stocks.append(f"<b>{float(keg_liters):.1f} L</b> en fût")
        except (ValueError, TypeError):
            pass
    if stocks:
        lines.append(f"📦 Stock : {' + '.join(stocks)}")
    msg = "\n".join(lines)
    def _send():
        try:
            _tg_send(token, chat_id, msg)
        except Exception as e:
            current_app.logger.error(f"Telegram bottling notif error: {e}")
    threading.Thread(target=_send, daemon=True).start()


_TG_BUILDERS = {
    'brews':           _tg_build_brews,
    'cave':            _tg_build_cave,
    'inventory':       _tg_build_inventory,
    'ferm_reminders':  _tg_build_ferm_reminders,
}


def _tg_fire(notif_type):
    token, chat_id, _, _ = _tg_get_settings()
    if not token or not chat_id:
        return
    fn = _TG_BUILDERS.get(notif_type)
    if not fn:
        return
    try:
        result = fn()
        messages = result if isinstance(result, list) else [result]
        for msg in messages:
            _tg_send(token, chat_id, msg)
    except Exception as e:
        current_app.logger.error(f"Telegram send error ({notif_type}): {e}")


# ---------------------------------------------------------------------------
# Brewing calendar events
# ---------------------------------------------------------------------------

_BREW_EVENTS_FIXED = [
    (1,  1, "National Hangover Day",                "🤕"),
    (1, 17, "Baltic Porter Day",                    "🍺"),
    (1, 17, "National Bootlegger's Day",            "🥃"),
    (1, 24, "National Beer Can Day",                "🥫"),
    (2, 24, "World Bartender Day",                  "🍸"),
    (2, 28, "Open That Bottle Night",               "🍾"),
    (3,  8, "Pink Boots Collaboration Brew Day",    "👢"),
    (3, 16, "Orval International Day",              "🍺"),
    (3, 17, "St. Patrick's Day",                    "🍀"),
    (3, 20, "National Bock Day",                    "🐐"),
    (4,  6, "New Beer's Eve",                       "🍺"),
    (4,  7, "National Beer Day",                    "🍺"),
    (4, 11, "King Gambrinus Day",                   "👑"),
    (4, 23, "German Beer Day / Reinheitsgebot",     "🇩🇪"),
    (4, 25, "Beer-Clean Glass Day",                 "🥃"),
    (4, 26, "Saison Day",                           "🌾"),
    (5,  1, "National Rotate Your Beer Day",        "🔄"),
    (5,  2, "Beer Pong Day",                        "🏓"),
    (5,  5, "Cinco de Mayo",                        "🌮"),
    (5,  7, "National Homebrew Day",                "🍻"),
    (5, 11, "American Craft Beer Week (debut)",     "🇺🇸"),
    (6,  8, "Name Your Poison Day",                 "☠"),
    (6, 15, "Beer Day Britain",                     "🏴"),
    (7,  7, "National Dive Bar Day",                "🍺"),
    (7, 12, "National Michelada Day",               "🌶"),
    (7, 23, "National Refreshment Day",             "🥤"),
    (9,  7, "National Beer Lover's Day",            "🍺"),
    (9, 20, "Sour Beer Day",                        "🍋"),
    (9, 24, "Arthur Guinness Day",                  "🖤"),
    (9, 27, "National Crush-A-Can Day",             "🥫"),
    (9, 28, "National Drink A Beer Day",            "🍺"),
    (10,  2, "Barrel-Aged Beer Day",                "🛢"),
    (10,  4, "Buy A Stranger A Drink Day",          "🍺"),
    (10,  9, "Beer & Pizza Day",                    "🍕"),
    (10, 10, "National Black Brewers Day",          "✊"),
    (10, 14, "Homebrewing Legalization Day",        "⚖"),
    (10, 27, "National American Beer Day",          "🇺🇸"),
    (11,  5, "International Stout Day",             "🖤"),
    (11,  7, "Learn to Homebrew Day",               "🏠"),
    (11, 12, "National Happy Hour Day",             "🍺"),
    (11, 17, "International Happy Gose Day",        "🧂"),
    (11, 29, "Small Brewery Sunday",                "🏠"),
    (12,  4, "National Bartender Day",              "🍸"),
    (12,  5, "National Repeal Day",                 "🗽"),
    (12, 10, "National Lager Day",                  "🍺"),
    (12, 25, "Noel - Biere de Noel",                "🎄"),
]


def _calc_brewing_events(year):
    """Retourne [(date, label, emoji)] pour une année donnée."""
    def _nth_dow(y, m, dow, nth):
        d = date(y, m, 1)
        while d.weekday() != dow:
            d += timedelta(days=1)
        return d + timedelta(weeks=nth - 1)

    evs = []
    for mo, da, label, emoji in _BREW_EVENTS_FIXED:
        try:
            evs.append((date(year, mo, da), label, emoji))
        except ValueError:
            pass
    evs.append((_nth_dow(year, 8, 3, 1),  "IPA Day",               "🌿"))
    evs.append((_nth_dow(year, 8, 4, 1),  "International Beer Day","🍺"))
    evs.append((_nth_dow(year, 7, 5, 1),  "Sour Beer Day",         "🍋"))
    evs.append((_nth_dow(year, 11, 3, 3), "Beaujolais Nouveau",    "🍷"))
    okt = date(year, 9, 22)
    while okt.weekday() != 5:
        okt -= timedelta(days=1)
    evs.append((okt, "Début Oktoberfest", "🥨"))
    return sorted(evs, key=lambda x: x[0])


def _tg_brewing_events_fire():
    """Job quotidien : vérifie si aujourd'hui est un event ou un rappel J-N."""
    token, chat_id, _, _ = _tg_get_settings()
    if not token or not chat_id:
        return
    with get_db() as conn:
        row      = conn.execute("SELECT value FROM app_settings WHERE key='tg_brewing_events'").fetchone()
        days_row = conn.execute("SELECT value FROM app_settings WHERE key='default_brew_reminder_days'").fetchone()
    if not row:
        return
    try:
        cfg = json.loads(row['value'])
    except Exception as e:
        current_app.logger.warning(f"_tg_brewing_events_fire: invalid tg_brewing_events JSON: {e}")
        return
    if not cfg.get('enabled'):
        return

    today = date.today()
    try:
        remind_days = int(days_row['value']) if days_row and days_row['value'] else 45
    except (ValueError, TypeError):
        remind_days = 45

    for year in (today.year, today.year + 1):
        for ev_date, label, emoji in _calc_brewing_events(year):
            if cfg.get('event_day') and ev_date == today:
                try:
                    _tg_send(token, chat_id,
                        f'{emoji} <b>{label}</b>\n\n'
                        f'C\'est aujourd\'hui ! 🎉\nSanté et bonne dégustation ! 🍺')
                except Exception as e:
                    current_app.logger.warning(f"_tg_brewing_events_fire: send error (event_day {label!r}): {e}")
            if cfg.get('remind'):
                remind_date = ev_date - timedelta(days=remind_days)
                if remind_date == today:
                    try:
                        _tg_send(token, chat_id,
                            f'⏰ <b>Rappel brassage — {label}</b>\n\n'
                            f'{emoji} <b>{label}</b> est dans <b>{remind_days} jours</b> '
                            f'({ev_date.strftime("%d/%m/%Y")}).\n\n'
                            f'C\'est le moment idéal pour brasser une bière spéciale ! 🍺')
                    except Exception as e:
                        current_app.logger.warning(f"_tg_brewing_events_fire: send error (remind {label!r}): {e}")

    with get_db() as conn:
        custom_evs = conn.execute(
            'SELECT * FROM custom_calendar_events WHERE telegram_notify=1'
        ).fetchall()
        all_recipes = {r['id']: r for r in conn.execute('SELECT id, name, style FROM recipes').fetchall()}
        all_drafts  = {d['id']: d for d in conn.execute('SELECT id, title, style FROM draft_recipes').fetchall()}

    for ev in custom_evs:
        try:
            ev_date = date.fromisoformat(ev['event_date'])
        except Exception as e:
            current_app.logger.warning(f"_tg_brewing_events_fire: invalid event_date {ev.get('event_date')!r}: {e}")
            continue
        emoji = ev['emoji'] or '📅'
        label = ev['title']
        assoc_lines = []
        if ev['style']:
            assoc_lines.append(f'🍺 Style : <b>{ev["style"]}</b>')
        if ev['recipe_id'] and ev['recipe_id'] in all_recipes:
            r = all_recipes[ev['recipe_id']]
            line = f'📜 Recette : <b>{r["name"]}</b>'
            if r['style']:
                line += f' ({r["style"]})'
            assoc_lines.append(line)
        if ev['draft_id'] and ev['draft_id'] in all_drafts:
            d = all_drafts[ev['draft_id']]
            line = f'📓 Brouillon : <b>{d["title"] or "Sans titre"}</b>'
            if d['style']:
                line += f' ({d["style"]})'
            assoc_lines.append(line)
        assoc_block = ('\n' + '\n'.join(assoc_lines)) if assoc_lines else ''

        if ev_date == today:
            notes_line = f'\n\n{ev["notes"]}' if ev['notes'] else ''
            try:
                _tg_send(token, chat_id,
                    f'{emoji} <b>{label}</b>\n\n'
                    f'C\'est aujourd\'hui ! 🎉'
                    f'{assoc_block}'
                    f'{notes_line}')
            except Exception as e:
                current_app.logger.warning(f"_tg_brewing_events_fire: send error (custom event_day {label!r}): {e}")
        if ev['brew_reminder']:
            try:
                ev_remind_days = int(ev['brew_reminder_days']) if ev['brew_reminder_days'] else remind_days
            except (ValueError, TypeError):
                ev_remind_days = remind_days
            remind_date = ev_date - timedelta(days=ev_remind_days)
            if remind_date == today:
                try:
                    _tg_send(token, chat_id,
                        f'⏰ <b>Rappel brassage — {label}</b>\n\n'
                        f'{emoji} <b>{label}</b> est dans <b>{ev_remind_days} jours</b> '
                        f'({ev_date.strftime("%d/%m/%Y")}).'
                        f'{assoc_block}\n\n'
                        f'C\'est le moment idéal pour brasser une bière spéciale ! 🍺')
                except Exception as e:
                    current_app.logger.warning(f"_tg_brewing_events_fire: send error (custom remind {label!r}): {e}")


def _tg_check_spindle_stability():
    """Vérifie si des spindles actifs ont une densité stable depuis N jours et envoie une notif Telegram."""
    token, chat_id, notifs, _ = _tg_get_settings()
    if not token or not chat_id:
        return
    sp_cfg = notifs.get('spindle_stable', {})
    if not sp_cfg.get('enabled'):
        return
    days = max(1, int(sp_cfg.get('days', 3)))
    threshold = 0.002

    with get_db() as conn:
        _active_ph = ','.join('?' * len(BrewStatus.ACTIVE))
        spindles = conn.execute(
            f"SELECT s.id, s.name, s.brew_id, s.stable_notif_at, "
            f"b.name AS brew_name, b.fermenting_since, b.og "
            f"FROM spindles s JOIN brews b ON b.id = s.brew_id "
            f"WHERE s.brew_id IS NOT NULL AND b.status IN ({_active_ph})",
            BrewStatus.ACTIVE
        ).fetchall()

    if not spindles:
        return

    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    _grace = timedelta(days=3)
    with get_readings_db() as rconn:
        for sp in spindles:
            if sp['fermenting_since']:
                try:
                    since = datetime.strptime(sp['fermenting_since'][:19], '%Y-%m-%d %H:%M:%S')
                    if (datetime.utcnow() - since) < _grace:
                        continue  # période de grâce — pas encore de vérification
                except (ValueError, TypeError):
                    pass
            rows = rconn.execute(
                "SELECT gravity FROM spindle_readings "
                "WHERE spindle_id=? AND recorded_at >= ? AND gravity IS NOT NULL "
                "ORDER BY recorded_at ASC",
                (sp['id'], cutoff)
            ).fetchall()

            if len(rows) < 3:
                if sp['stable_notif_at']:
                    with get_db() as conn:
                        conn.execute("UPDATE spindles SET stable_notif_at=NULL WHERE id=?", (sp['id'],))
                continue

            gravities = [r['gravity'] for r in rows]
            g_range = max(gravities) - min(gravities)
            is_stable = g_range <= threshold

            if is_stable and not sp['stable_notif_at']:
                fg_avg = round(sum(gravities) / len(gravities), 4)

                # Fermentation duration
                ferm_days_str = ''
                if sp['fermenting_since']:
                    try:
                        since = datetime.strptime(sp['fermenting_since'][:19], '%Y-%m-%d %H:%M:%S')
                        ferm_days = (datetime.utcnow() - since).days
                        ferm_days_str = f"\n⏱ Fermentation : <b>{ferm_days} jour{'s' if ferm_days != 1 else ''}</b>"
                    except (ValueError, TypeError):
                        pass

                # Estimated ABV
                abv_str = ''
                if sp['og'] and sp['og'] > 1:
                    est_abv = round((float(sp['og']) - fg_avg) * 131.25, 1)
                    abv_str = f"\n🍶 ABV est. : <b>~{est_abv}%</b> (OG {float(sp['og']):.3f} → FG {fg_avg:.4f})"

                msg = (
                    f"🍺 <b>BrewHome — Densité stable</b>\n\n"
                    f"Le spindle <b>{sp['name']}</b> lié au brassin <b>{sp['brew_name']}</b> "
                    f"affiche une densité stable depuis <b>{days} jour{'s' if days > 1 else ''}</b>.\n"
                    f"🔵 FG moyenne : <b>{fg_avg:.4f}</b>  (Δ {g_range:.4f} sur {len(gravities)} mesures)"
                    f"{ferm_days_str}{abv_str}\n\n"
                    f"La fermentation semble terminée. Pensez à vérifier !"
                )
                try:
                    _tg_send(token, chat_id, msg)
                    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    with get_db() as conn:
                        conn.execute("UPDATE spindles SET stable_notif_at=? WHERE id=?", (now_str, sp['id']))
                except Exception as e:
                    current_app.logger.warning(f"_tg_check_spindle_stability: send error: {e}")
            elif not is_stable and sp['stable_notif_at']:
                with get_db() as conn:
                    conn.execute("UPDATE spindles SET stable_notif_at=NULL WHERE id=?", (sp['id'],))


def reschedule_telegram():
    """Recharge la config depuis la DB et re-planifie les jobs Telegram."""
    token, chat_id, notifs, tz_str = _tg_get_settings()
    for jid in ('tg_brews', 'tg_cave', 'tg_inventory', 'tg_brew_events', 'tg_ferm', 'tg_spindle_stable'):
        try:
            _scheduler.remove_job(jid)
        except JobLookupError:
            pass
    if not token or not chat_id:
        return
    try:
        tz = ZoneInfo(tz_str or 'UTC')
    except Exception as e:
        current_app.logger.warning(f"reschedule_telegram: invalid timezone {tz_str!r}, falling back to UTC: {e}")
        tz = timezone.utc

    def _add(jid, ntype, cfg, monthly):
        if not cfg.get('enabled'):
            return
        h = int(cfg.get('hour', 8))
        m = int(cfg.get('minute', 0))
        if monthly:
            d = max(1, min(28, int(cfg.get('day', 1))))
            trigger = CronTrigger(day=d, hour=h, minute=m, timezone=tz)
        else:
            trigger = CronTrigger(hour=h, minute=m, timezone=tz)
        _scheduler.add_job(_tg_fire, trigger, args=[ntype], id=jid, replace_existing=True)

    _add('tg_brews',     'brews',          notifs.get('brews', {}),          monthly=False)
    _add('tg_cave',      'cave',           notifs.get('cave', {}),           monthly=True)
    _add('tg_inventory', 'inventory',      notifs.get('inventory', {}),      monthly=True)
    _add('tg_ferm',      'ferm_reminders', notifs.get('ferm_reminders', {}), monthly=False)

    if notifs.get('spindle_stable', {}).get('enabled') and token and chat_id:
        _scheduler.add_job(_tg_check_spindle_stability, CronTrigger(hour='*/4', timezone=tz),
                           id='tg_spindle_stable', replace_existing=True)

    try:
        with get_db() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key='tg_brewing_events'").fetchone()
        ev_cfg = json.loads(row['value']) if row else {}
    except Exception as e:
        current_app.logger.warning(f"reschedule_telegram: invalid tg_brewing_events JSON: {e}")
        ev_cfg = {}
    if ev_cfg.get('enabled') and (ev_cfg.get('remind') or ev_cfg.get('event_day')):
        h = int(ev_cfg.get('hour', 8))
        m = int(ev_cfg.get('minute', 0))
        _scheduler.add_job(_tg_brewing_events_fire, CronTrigger(hour=h, minute=m, timezone=tz),
                           id='tg_brew_events', replace_existing=True)


# ---------------------------------------------------------------------------
# Telegram API routes
# ---------------------------------------------------------------------------

@bp.route('/api/telegram/test', methods=['POST'])
def telegram_test():
    d = request.json or {}
    token   = (d.get('token')   or '').strip()
    chat_id = (d.get('chat_id') or '').strip()
    if not token or not chat_id:
        return api_error('missing_field', 400, detail='Token et Chat ID requis')
    try:
        _tg_send(token, chat_id, '🍺 <b>BrewHome</b>\n\nConnexion Telegram configurée avec succès !')
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("telegram_test failed")
        return api_error('internal_error', 500)


@bp.route('/api/telegram/trigger/<notif_type>', methods=['POST'])
def telegram_trigger(notif_type):
    if notif_type not in _TG_BUILDERS:
        return api_error('invalid_type', 400)
    token, chat_id, _, _ = _tg_get_settings()
    if not token or not chat_id:
        return api_error('not_configured', 400, detail='Telegram non configuré (token ou chat_id manquant)')
    try:
        result = _TG_BUILDERS[notif_type]()
        messages = result if isinstance(result, list) else [result]
        for msg in messages:
            _tg_send(token, chat_id, msg)
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("telegram_trigger %s failed", notif_type)
        return api_error('internal_error', 500)


@bp.route('/api/notify/timer', methods=['POST'])
def notify_timer():
    d = request.get_json(force=True, silent=True) or {}
    name = d.get('name', 'Timer')
    kind = d.get('type', 'done')
    try:
        token, chat_id, _, _ = _tg_get_settings()
        if not token or not chat_id:
            return api_error('not_configured', 400, detail='Telegram non configuré')
        if kind == 'warning':
            msg = f'⏱ <b>Timer — 5 minutes restantes</b>\n{name}'
        else:
            msg = f'✅ <b>Timer terminé !</b>\n{name}'
        _tg_send(token, chat_id, msg)
        return jsonify({'ok': True})
    except Exception as e:
        current_app.logger.exception("notify_timer failed")
        return api_error('internal_error', 500)


# ---------------------------------------------------------------------------
# Static library updates
# ---------------------------------------------------------------------------

def _read_version_from_file(path):
    """Lit la version dans le commentaire d'entête d'un fichier JS/CSS."""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            head = f.read(512)
        import re
        m = re.search(r'v?(\d+\.\d+\.\d+)', head)
        return m.group(1) if m else None
    except Exception as e:
        current_app.logger.debug(f"_read_version_from_file({path}): {e}")
        return None


def _npm_latest(package):
    url = f'https://registry.npmjs.org/{urllib.parse.quote(package, safe="@/")}/latest'
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'BrewHome'})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())['version']


def _download(url, dest_path):
    req = urllib.request.Request(url, headers={'User-Agent': 'BrewHome'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    with open(dest_path, 'wb') as f:
        f.write(data)
    return len(data)


@bp.route('/api/static/check-updates')
def static_check_updates():
    result = {}
    cjs_path = os.path.join(STATIC_DIR, 'js', 'chart.umd.min.js')
    result['chartjs'] = {'current': _read_version_from_file(cjs_path), 'latest': None, 'error': None}
    try:
        result['chartjs']['latest'] = _npm_latest('chart.js')
    except Exception as e:
        result['chartjs']['error'] = str(e)
    fa_path = os.path.join(STATIC_DIR, 'fonts', 'fa', 'all.min.css')
    result['fontawesome'] = {'current': _read_version_from_file(fa_path), 'latest': None, 'error': None}
    try:
        result['fontawesome']['latest'] = _npm_latest('@fortawesome/fontawesome-free')
    except Exception as e:
        result['fontawesome']['error'] = str(e)
    gf_path = os.path.join(STATIC_DIR, 'fonts', 'google', 'fonts.css')
    try:
        st = os.stat(gf_path)
        result['googlefonts'] = {
            'current': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d'),
            'size': st.st_size,
        }
    except Exception as e:
        current_app.logger.debug(f"check_static_updates: cannot stat google fonts: {e}")
        result['googlefonts'] = {'current': None, 'size': 0}
    return jsonify(result)


@bp.route('/api/static/update/chartjs', methods=['POST'])
def update_chartjs():
    try:
        version = _npm_latest('chart.js')
        url = f'https://cdn.jsdelivr.net/npm/chart.js@{version}/dist/chart.umd.min.js'
        dest = os.path.join(STATIC_DIR, 'js', 'chart.umd.min.js')
        size = _download(url, dest)
        return jsonify({'version': version, 'size': size})
    except Exception as e:
        return api_error('internal_error', 500)


def _fix_fa_css_paths(css_path):
    import re
    with open(css_path, 'r', encoding='utf-8') as f:
        css = f.read()
    css = re.sub(r'url\(["\']?\.\.?/?webfonts/', 'url(/static/fonts/fa/webfonts/', css)
    css = re.sub(r'url\(["\']?webfonts/', 'url(/static/fonts/fa/webfonts/', css)
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(css)


@bp.route('/api/static/update/fontawesome', methods=['POST'])
def update_fontawesome():
    try:
        import re as _re
        version = _npm_latest('@fortawesome/fontawesome-free')
        base = f'https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@{version}'
        fa_dir = os.path.join(STATIC_DIR, 'fonts', 'fa')
        wf_dir = os.path.join(fa_dir, 'webfonts')
        os.makedirs(wf_dir, exist_ok=True)
        css_path = os.path.join(fa_dir, 'all.min.css')
        _download(f'{base}/css/all.min.css', css_path)
        _fix_fa_css_paths(css_path)
        with open(css_path, 'r', encoding='utf-8') as f:
            css_content = f.read()
        wf_names = set(_re.findall(r'(fa-[^/\s"\'()]+\.woff2)', css_content))
        if not wf_names:
            wf_names = {'fa-brands-400.woff2', 'fa-regular-400.woff2',
                        'fa-solid-900.woff2', 'fa-v4compatibility.woff2'}
        for wf in wf_names:
            try:
                _download(f'{base}/webfonts/{wf}', os.path.join(wf_dir, wf))
            except Exception as e:
                current_app.logger.debug(f"update_fontawesome: webfont {wf} unavailable: {e}")
        return jsonify({'version': version})
    except Exception as e:
        return api_error('internal_error', 500)


# ---------------------------------------------------------------------------
# Git proxy
# ---------------------------------------------------------------------------

_GIT_PROXY_ALLOWED_HOSTS = {
    'api.github.com',
    'gitlab.com',
    'codeberg.org',
}


def _git_proxy_url_allowed(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'https':
            return False
        host = parsed.netloc.lower().split(':')[0]
        if host in _GIT_PROXY_ALLOWED_HOSTS:
            return True
        with get_db() as conn:
            rows = conn.execute(
                "SELECT value FROM app_settings WHERE key IN ('gh_vitrine_api_url','gh_data_api_url')"
            ).fetchall()
        for r in rows:
            val = (r['value'] or '').strip().rstrip('/')
            if val:
                allowed_host = urllib.parse.urlparse(val).netloc.lower().split(':')[0]
                if host == allowed_host:
                    return True
        return False
    except Exception:
        return False


@bp.route('/api/git-proxy', methods=['POST'])
def git_proxy():
    """Proxifie les requêtes vers un provider Git custom (Gitea/Forgejo) côté serveur."""
    data = request.json or {}
    target_url = data.get('url', '').strip()
    method     = data.get('method', 'GET').upper()
    pat        = data.get('pat', '')
    body_data  = data.get('body')

    if not target_url:
        return api_error('missing_field', 400, detail='Missing url')

    if not _git_proxy_url_allowed(target_url):
        current_app.logger.warning(f"git_proxy: URL refusée (SSRF protection): {target_url[:200]}")
        return api_error('forbidden', 403, detail='URL non autorisée')

    headers = {
        'Authorization': f'Bearer {pat}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'BrewHome',
    }
    try:
        req_body = json.dumps(body_data).encode('utf-8') if body_data is not None else None
        req = urllib.request.Request(target_url, data=req_body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = resp.read()
            return current_app.response_class(response=resp_body, status=resp.status, mimetype='application/json')
    except urllib.error.HTTPError as e:
        err_body = e.read()
        try:
            json.loads(err_body)
            return current_app.response_class(response=err_body, status=e.code, mimetype='application/json')
        except Exception:
            return jsonify({'message': err_body.decode('utf-8', errors='replace') or str(e)}), e.code
    except Exception as e:
        return api_error('internal_error', 500)


# ---------------------------------------------------------------------------
# GitHub automatic backup
# ---------------------------------------------------------------------------

def _gh_push_file(repo, pat, branch, file_path, content_str, message, api_base='https://api.github.com'):
    """Pousse un fichier texte vers un dépôt Git via l'API. Retourne True si modifié."""
    encoded = base64.b64encode(content_str.encode('utf-8')).decode('ascii')
    api_base = (api_base or 'https://api.github.com').rstrip('/')
    base_url = f'{api_base}/repos/{repo}/contents/{file_path}'
    is_github = api_base == 'https://api.github.com'
    headers = {
        'Authorization': f'Bearer {pat}',
        'Accept': 'application/vnd.github+json' if is_github else 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'BrewHome',
    }

    def _fetch_sha():
        try:
            req = urllib.request.Request(
                f'{base_url}?ref={urllib.parse.quote(branch)}', headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                existing = json.loads(resp.read().decode())
            sha = existing.get('sha')
            existing_b64 = (existing.get('content') or '').replace('\n', '')
            unchanged = bool(sha and existing_b64 and existing_b64 == encoded)
            return sha, unchanged
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, False
            body_hint = ''
            try: body_hint = e.read().decode()[:200]
            except Exception: pass
            current_app.logger.warning(f'_gh_push_file GET {file_path} HTTP {e.code}: {body_hint}')
            raise

    sha, unchanged = _fetch_sha()
    if unchanged:
        return False

    def _read_body(exc):
        try: return exc.read().decode('utf-8', errors='replace')[:400]
        except Exception: return ''

    def _do_push(sha_val):
        method = 'PUT' if (is_github or sha_val) else 'POST'
        body = {'message': message, 'content': encoded, 'branch': branch}
        if sha_val:
            body['sha'] = sha_val
        req = urllib.request.Request(
            base_url, data=json.dumps(body).encode('utf-8'),
            headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()

    try:
        _do_push(sha)
    except urllib.error.HTTPError as e:
        body = _read_body(e)
        if e.code != 422:
            current_app.logger.warning(f'_gh_push_file {file_path} HTTP {e.code}: {body}')
            raise urllib.error.HTTPError(e.url, e.code, f'HTTP Error {e.code}: {e.reason} — {body}', e.headers, None)
        current_app.logger.warning(f'_gh_push_file 422 on {file_path} (sha={sha!r}), retrying. Detail: {body}')
        fresh_sha, unchanged2 = _fetch_sha()
        if unchanged2:
            return False
        try:
            _do_push(fresh_sha)
        except urllib.error.HTTPError as e2:
            body2 = _read_body(e2)
            current_app.logger.warning(f'_gh_push_file 422 retry failed {file_path}: {body2}')
            raise Exception(f'HTTP Error {e2.code}: {e2.reason} — {body2}')

    return True


def _gh_get_file(repo, pat, branch, file_path, api_base='https://api.github.com'):
    """Fetch raw content of a file from a Git repository via API."""
    api_base = (api_base or 'https://api.github.com').rstrip('/')
    url = f'{api_base}/repos/{repo}/contents/{urllib.parse.quote(file_path)}?ref={urllib.parse.quote(branch)}'
    is_github = api_base == 'https://api.github.com'
    headers = {
        'Authorization': f'Bearer {pat}',
        'Accept': 'application/vnd.github+json' if is_github else 'application/json',
        'User-Agent': 'BrewHome',
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    content_b64 = (result.get('content') or '').replace('\n', '')
    return base64.b64decode(content_b64).decode('utf-8')


def _github_data_backup():
    """Sauvegarde complète des données vers tous les dépôts configurés."""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key IN "
                            "('gh_data_repo','gh_data_branch','gh_data_pat','gh_data_api_url','gh_data_targets')").fetchall()
    cfg = {r['key']: r['value'] for r in rows}
    targets = []
    if cfg.get('gh_data_targets'):
        try:
            targets = [t for t in json.loads(cfg['gh_data_targets']) if t.get('repo') and t.get('pat')]
        except (json.JSONDecodeError, ValueError):
            pass
    if not targets:
        repo = cfg.get('gh_data_repo', '').strip()
        pat  = cfg.get('gh_data_pat',  '').strip()
        if repo and pat:
            targets = [{'repo': repo, 'pat': pat,
                        'branch':  cfg.get('gh_data_branch', 'main').strip() or 'main',
                        'apiUrl':  (cfg.get('gh_data_api_url') or 'https://api.github.com').rstrip('/')}]
    if not targets:
        current_app.logger.warning('GitHub backup: aucune destination configurée, sauvegarde ignorée')
        return

    date_str = datetime.now().strftime('%Y-%m-%d')
    try:
        with get_db() as conn:
            inventory = [dict(r) for r in conn.execute(
                'SELECT * FROM inventory_items ORDER BY category, name').fetchall()]
            recipes_raw = conn.execute('SELECT * FROM recipes ORDER BY name').fetchall()
            recipes = []
            for r in recipes_raw:
                rec = dict(r)
                rec['ingredients'] = [dict(i) for i in conn.execute(
                    'SELECT * FROM recipe_ingredients WHERE recipe_id=?', (r['id'],)).fetchall()]
                recipes.append(rec)
            brews_raw = conn.execute('SELECT * FROM brews ORDER BY created_at DESC').fetchall()
            brews = []
            for b in brews_raw:
                brew = dict(b)
                brew['fermentation'] = [dict(f) for f in conn.execute(
                    'SELECT * FROM brew_fermentation_readings WHERE brew_id=? ORDER BY recorded_at', (b['id'],)).fetchall()]
                brews.append(brew)
            beers = [dict(r) for r in conn.execute('SELECT * FROM beers ORDER BY name').fetchall()]
            spindles = [dict(r) for r in conn.execute('SELECT * FROM spindles ORDER BY name').fetchall()]
            catalog = [dict(r) for r in conn.execute(
                'SELECT * FROM ingredient_catalog ORDER BY category, name').fetchall()]
            drafts = [dict(r) for r in conn.execute(
                'SELECT * FROM draft_recipes ORDER BY sort_order ASC, updated_at DESC').fetchall()]
            calendar = [dict(r) for r in conn.execute(
                'SELECT * FROM custom_calendar_events ORDER BY event_date').fetchall()]
            settings_rows = conn.execute('SELECT key, value FROM app_settings').fetchall()
        settings_out = {r['key']: r['value'] for r in settings_rows}
        for k in ('gh_data_pat', 'gh_vitrine_pat', 'ai_api_key', 'telegram_token'):
            settings_out.pop(k, None)

        files = [
            ('inventaire.json',  inventory),
            ('recettes.json',    recipes),
            ('brassins.json',    brews),
            ('cave.json',        beers),
            ('densimetres.json', spindles),
            ('catalogue.json',   catalog),
            ('brouillons.json',  drafts),
            ('calendrier.json',  calendar),
            ('parametres.json',  settings_out),
        ]
        total_pushed = total_skipped = total_errors = 0
        push_errors = []
        for target in targets:
            t_repo   = target.get('repo', '').strip()
            t_pat    = target.get('pat',  '').strip()
            t_branch = target.get('branch', 'main').strip() or 'main'
            t_api    = (target.get('apiUrl') or 'https://api.github.com').rstrip('/')
            if not t_repo or not t_pat:
                continue
            for name, data in files:
                try:
                    changed = _gh_push_file(t_repo, t_pat, t_branch, f'backup_auto/{name}',
                                            json.dumps(data, ensure_ascii=False, indent=2),
                                            f'backup auto: {name.replace(".json","")} {date_str}',
                                            api_base=t_api)
                    if changed:
                        total_pushed += 1
                    else:
                        total_skipped += 1
                except Exception as push_err:
                    total_errors += 1
                    push_errors.append(f'[{t_repo}] {name}: {push_err}')
                    current_app.logger.warning(f'GitHub backup push error ({t_repo}/{name}): {push_err}')

        ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        repo_list = ', '.join(tgt.get('repo', '') for tgt in targets if tgt.get('repo'))
        with get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('gh_data_last_backup',?)", (ts,))
            notify = conn.execute("SELECT value FROM app_settings WHERE key='gh_data_backup_notify'").fetchone()
        current_app.logger.info(f'GitHub backup: {total_pushed} fichier(s) mis à jour, {total_skipped} inchangé(s), {total_errors} erreur(s)')
        _i18n_key = 'act.backup_auto_err' if total_errors else 'act.backup_auto'
        _log('backup', 'auto', json.dumps({'_i18n': _i18n_key, 'n': total_pushed, 'repos': repo_list, 'e': total_errors, 'errors': push_errors}))
        if notify and notify['value'] == 'true':
            try:
                tg_token, tg_chat, _, _ = _tg_get_settings()
                if tg_token and tg_chat:
                    if total_errors and not total_pushed and not total_skipped:
                        err_preview = push_errors[0] if push_errors else 'erreur inconnue'
                        _tg_send(tg_token, tg_chat,
                                 f'⚠️ <b>Backup automatique échoué</b>\n\n'
                                 f'❌ {total_errors} erreur(s)\n'
                                 f'🕐 {ts}\n'
                                 f'📁 {repo_list}\n'
                                 f'<code>{err_preview}</code>')
                    else:
                        skip_txt = f', {total_skipped} inchangé(s)' if total_skipped else ''
                        err_txt  = f', ⚠️ {total_errors} erreur(s)' if total_errors else ''
                        _tg_send(tg_token, tg_chat,
                                 f'☁️ <b>Backup automatique</b>\n\n'
                                 f'✅ {total_pushed} fichier(s) mis à jour{skip_txt}{err_txt}\n'
                                 f'🕐 {ts}\n'
                                 f'📁 {repo_list}')
            except Exception as te:
                current_app.logger.warning(f'GitHub backup Telegram notify error: {te}')
    except Exception as e:
        current_app.logger.error(f'GitHub backup error: {e}')


def reschedule_github_backup():
    """Recharge la config depuis la DB et re-planifie le job de backup GitHub."""
    try:
        _scheduler.remove_job('gh_backup')
    except JobLookupError:
        pass
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'gh_data_backup_%'").fetchall()
    cfg = {r['key']: r['value'] for r in rows}
    if cfg.get('gh_data_backup_enabled') != 'true':
        return
    freq   = cfg.get('gh_data_backup_freq', 'daily')
    hour   = int(cfg.get('gh_data_backup_hour',   '2'))
    minute = int(cfg.get('gh_data_backup_minute', '0'))
    if freq == 'daily':
        trigger = CronTrigger(hour=hour, minute=minute)
    elif freq == 'weekly':
        dow = int(cfg.get('gh_data_backup_weekday', '0'))
        trigger = CronTrigger(day_of_week=dow, hour=hour, minute=minute)
    else:
        day = max(1, min(28, int(cfg.get('gh_data_backup_day', '1'))))
        trigger = CronTrigger(day=day, hour=hour, minute=minute)
    _scheduler.add_job(_github_data_backup, trigger, id='gh_backup', replace_existing=True)
