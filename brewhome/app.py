import sqlite3
import os
import secrets
import json
import base64
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, date, timedelta
from flask import Flask, jsonify, request, render_template, make_response
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
DB_PATH          = os.path.join(os.path.dirname(__file__), 'brewhome.db')
READINGS_DB_PATH = os.path.join(os.path.dirname(__file__), 'brewhome_readings.db')
APP_VERSION      = "0.0.5"

# ── Limite taille image base64 ───────────────────────────────────────────────
# 2 Mo de données brutes ≈ 2,7 Mo en base64 ; on bloque à 3 Mo de chaîne base64
_MAX_IMAGE_B64_BYTES = 3 * 1024 * 1024

def _image_too_large(image: str | None) -> bool:
    return image is not None and len(image.encode()) > _MAX_IMAGE_B64_BYTES

def _shrink_image_b64(data_url: str) -> str:
    """Réduit une image base64 jusqu'à passer sous _MAX_IMAGE_B64_BYTES.
    Convertit en JPEG, réduit la qualité puis les dimensions si nécessaire.
    Retourne le data URL réduit, ou le data URL original en cas d'échec."""
    try:
        from PIL import Image
        import io
        # Extraire le base64 pur (data:image/xxx;base64,<data>)
        if ',' in data_url:
            header, b64data = data_url.split(',', 1)
        else:
            header, b64data = 'data:image/jpeg;base64', data_url
        raw = base64.b64decode(b64data)
        img = Image.open(io.BytesIO(raw)).convert('RGB')

        # Réduire qualité JPEG par paliers
        for quality in (85, 70, 55, 40):
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            result = f'data:image/jpeg;base64,{b64}'
            if len(result.encode()) <= _MAX_IMAGE_B64_BYTES:
                return result

        # Toujours trop grand : réduire aussi les dimensions (50 %, puis 35 %)
        for scale in (0.5, 0.35):
            w = max(1, int(img.width  * scale))
            h = max(1, int(img.height * scale))
            small = img.resize((w, h), Image.LANCZOS)
            buf = io.BytesIO()
            small.save(buf, format='JPEG', quality=60, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            result = f'data:image/jpeg;base64,{b64}'
            if len(result.encode()) <= _MAX_IMAGE_B64_BYTES:
                return result

        return result  # dernière tentative même si encore grande
    except Exception as e:
        app.logger.warning(f"_shrink_image_b64 failed: {e}")
        return data_url

# ── Rate limiter capteurs ─────────────────────────────────────────────────────
# Sliding-window par token : 1 requête toutes les SENSOR_RL_MIN_INTERVAL secondes.
# Les capteurs physiques envoient typiquement toutes les 2–30 minutes, donc
# 30 s est largement suffisant pour bloquer les abus sans gêner les devices.
SENSOR_RL_MIN_INTERVAL = 30  # secondes
_rl_lock  = threading.Lock()
_rl_cache: dict[str, float] = {}  # token → timestamp dernière requête acceptée

def _sensor_rate_limit(token: str) -> bool:
    """Retourne True si la requête est autorisée, False si elle doit être rejetée."""
    now = time.monotonic()
    with _rl_lock:
        last = _rl_cache.get(token, 0.0)
        if now - last < SENSOR_RL_MIN_INTERVAL:
            return False
        _rl_cache[token] = now
        return True


def get_db():
    """Connexion principale + base de mesures attachée en tant que 'rdb'."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("ATTACH DATABASE ? AS rdb", (READINGS_DB_PATH,))
    return conn


def get_readings_db():
    """Connexion directe à la base de mesures densimètre."""
    conn = sqlite3.connect(READINGS_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_readings_db():
    """Crée les tables et index dans la base de mesures si nécessaire."""
    with get_readings_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS spindle_readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                spindle_id  INTEGER NOT NULL,
                gravity     REAL,
                temperature REAL,
                battery     REAL,
                angle       REAL,
                rssi        INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sr_spindle ON spindle_readings(spindle_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sr_date    ON spindle_readings(recorded_at)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sr_spindle_date ON spindle_readings(spindle_id, recorded_at DESC)')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS temperature_readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id   INTEGER NOT NULL,
                temperature REAL,
                humidity    REAL,
                target_temp REAL,
                hvac_mode   TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tr_sensor ON temperature_readings(sensor_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tr_date   ON temperature_readings(recorded_at)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tr_sensor_date ON temperature_readings(sensor_id, recorded_at DESC)')


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS inventory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'kg',
                origin TEXT,
                ebc REAL,
                alpha REAL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_no INTEGER,
                name TEXT NOT NULL,
                style TEXT,
                volume REAL DEFAULT 20,
                brew_date DATE,
                bottling_date DATE,
                mash_temp REAL DEFAULT 66,
                mash_time INTEGER DEFAULT 60,
                boil_time INTEGER DEFAULT 60,
                mash_ratio REAL DEFAULT 3.0,
                evap_rate REAL DEFAULT 3.0,
                grain_absorption REAL DEFAULT 0.8,
                brewhouse_efficiency REAL DEFAULT 72,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recipe_ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                inventory_item_id INTEGER,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL DEFAULT 'g',
                hop_time INTEGER,
                hop_type TEXT,
                ebc REAL,
                alpha REAL,
                notes TEXT,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
                FOREIGN KEY (inventory_item_id) REFERENCES inventory_items(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS brews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                brew_date DATE,
                volume_brewed REAL,
                og REAL,
                fg REAL,
                abv REAL,
                notes TEXT,
                status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id)
            );

            CREATE TABLE IF NOT EXISTS beers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT,
                abv REAL,
                stock_33cl INTEGER DEFAULT 0,
                stock_75cl INTEGER DEFAULT 0,
                origin TEXT,
                description TEXT,
                photo TEXT,
                brew_id INTEGER,
                recipe_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (brew_id) REFERENCES brews(id) ON DELETE SET NULL,
                FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS ingredient_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT,
                ebc REAL,
                gu REAL,
                alpha REAL,
                yeast_type TEXT,
                default_unit TEXT
            );

            CREATE TABLE IF NOT EXISTS bjcp_styles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                og_min REAL, og_max REAL,
                fg_min REAL, fg_max REAL,
                abv_min REAL, abv_max REAL,
                ibu_min REAL, ibu_max REAL,
                ebc_min REAL, ebc_max REAL
            );

            CREATE TABLE IF NOT EXISTS spindles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                brew_id INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (brew_id) REFERENCES brews(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS brew_fermentation_readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                brew_id     INTEGER NOT NULL,
                recorded_at TIMESTAMP NOT NULL,
                gravity     REAL,
                temperature REAL,
                battery     REAL,
                angle       REAL,
                FOREIGN KEY (brew_id) REFERENCES brews(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS temperature_sensors (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                token      TEXT UNIQUE NOT NULL,
                notes      TEXT,
                temp_min   REAL,
                temp_max   REAL,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_catalog_name ON ingredient_catalog(name)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_catalog_cat  ON ingredient_catalog(category)')
        # Migration: add hop_days if missing (safe to run on existing DB)
        try:
            conn.execute('ALTER TABLE recipe_ingredients ADD COLUMN hop_days INTEGER')
        except Exception as e:
            pass  # colonne déjà existante
        _seed_catalog(conn)
        _seed_catalog_extras(conn)
        _seed_bjcp(conn)


def migrate_db():
    with get_db() as conn:
        for sql in [
            "ALTER TABLE inventory_items ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE recipes ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE brews ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE brews ADD COLUMN ferm_time INTEGER",
            "ALTER TABLE beers ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE beers ADD COLUMN initial_33cl INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE beers ADD COLUMN initial_75cl INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE recipes ADD COLUMN ferm_temp REAL",
            "ALTER TABLE recipes ADD COLUMN ferm_time INTEGER",
            "ALTER TABLE recipe_ingredients ADD COLUMN other_type TEXT",
            "ALTER TABLE recipe_ingredients ADD COLUMN other_time REAL",
            "ALTER TABLE beers ADD COLUMN brew_date DATE",
            "ALTER TABLE beers ADD COLUMN bottling_date DATE",
            "ALTER TABLE ingredient_catalog ADD COLUMN temp_min REAL",
            "ALTER TABLE ingredient_catalog ADD COLUMN temp_max REAL",
            "ALTER TABLE ingredient_catalog ADD COLUMN dosage_per_liter REAL",
            "ALTER TABLE ingredient_catalog ADD COLUMN attenuation_min REAL",
            "ALTER TABLE ingredient_catalog ADD COLUMN attenuation_max REAL",
            "ALTER TABLE ingredient_catalog ADD COLUMN alcohol_tolerance REAL",
            "ALTER TABLE ingredient_catalog ADD COLUMN max_usage_pct REAL",
            "ALTER TABLE ingredient_catalog ADD COLUMN aroma_spec TEXT",
            "ALTER TABLE inventory_items ADD COLUMN price_per_unit REAL",
            "ALTER TABLE recipes ADD COLUMN rating INTEGER",
            "ALTER TABLE spindles ADD COLUMN sort_order INTEGER DEFAULT 0",
            "ALTER TABLE recipes ADD COLUMN sort_order INTEGER DEFAULT 0",
            "ALTER TABLE recipes ADD COLUMN draft_id INTEGER REFERENCES draft_recipes(id) ON DELETE SET NULL",
            "ALTER TABLE brews ADD COLUMN sort_order INTEGER DEFAULT 0",
            "ALTER TABLE beers ADD COLUMN sort_order INTEGER DEFAULT 0",
            "ALTER TABLE inventory_items ADD COLUMN sort_order INTEGER DEFAULT 0",
            "ALTER TABLE spindles ADD COLUMN device_type TEXT NOT NULL DEFAULT 'ispindel'",
            "ALTER TABLE temperature_sensors ADD COLUMN sensor_type TEXT NOT NULL DEFAULT 'sensor'",
            "ALTER TABLE temperature_sensors ADD COLUMN ha_entity TEXT",
            "ALTER TABLE temperature_sensors ADD COLUMN ha_entity_hum TEXT",
            "ALTER TABLE temperature_sensors ADD COLUMN brew_id INTEGER REFERENCES brews(id) ON DELETE SET NULL",
            "ALTER TABLE beers ADD COLUMN keg_liters REAL",
            "ALTER TABLE beers ADD COLUMN keg_initial_liters REAL",
            "ALTER TABLE beers ADD COLUMN taste_appearance TEXT",
            "ALTER TABLE beers ADD COLUMN taste_aroma TEXT",
            "ALTER TABLE beers ADD COLUMN taste_flavor TEXT",
            "ALTER TABLE beers ADD COLUMN taste_bitterness TEXT",
            "ALTER TABLE beers ADD COLUMN taste_mouthfeel TEXT",
            "ALTER TABLE beers ADD COLUMN taste_overall TEXT",
            "ALTER TABLE beers ADD COLUMN taste_rating INTEGER",
            "ALTER TABLE beers ADD COLUMN taste_date TEXT",
            """CREATE TABLE IF NOT EXISTS draft_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'Nouveau brouillon',
                style TEXT,
                volume REAL,
                ingredients TEXT,
                notes TEXT,
                color TEXT,
                target_date TEXT,
                event_label TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "ALTER TABLE draft_recipes ADD COLUMN target_date TEXT",
            "ALTER TABLE draft_recipes ADD COLUMN event_label TEXT",
            "ALTER TABLE draft_recipes ADD COLUMN sort_order INTEGER DEFAULT 0",
            "ALTER TABLE draft_recipes ADD COLUMN image TEXT",
            """CREATE TABLE IF NOT EXISTS custom_calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                emoji TEXT DEFAULT '📅',
                event_date TEXT NOT NULL,
                color TEXT DEFAULT '#f59e0b',
                notes TEXT,
                brew_reminder INTEGER NOT NULL DEFAULT 0,
                telegram_notify INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "ALTER TABLE custom_calendar_events ADD COLUMN style TEXT",
            "ALTER TABLE custom_calendar_events ADD COLUMN recipe_id INTEGER",
            "ALTER TABLE custom_calendar_events ADD COLUMN draft_id INTEGER",
            "ALTER TABLE custom_calendar_events ADD COLUMN recurrence TEXT",
            "ALTER TABLE custom_calendar_events ADD COLUMN brew_reminder_days INTEGER",
            """CREATE TABLE IF NOT EXISTS soda_kegs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                keg_type TEXT,
                volume_total REAL,
                volume_ferment REAL,
                weight_empty REAL,
                status TEXT DEFAULT 'empty',
                current_liters REAL,
                beer_id INTEGER,
                brew_id INTEGER,
                notes TEXT,
                color TEXT DEFAULT '#f59e0b',
                photo TEXT,
                archived INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (beer_id) REFERENCES beers(id) ON DELETE SET NULL,
                FOREIGN KEY (brew_id) REFERENCES brews(id) ON DELETE SET NULL
            )""",
            "ALTER TABLE soda_kegs ADD COLUMN manufacturer TEXT",
            "ALTER TABLE soda_kegs ADD COLUMN next_revision_date TEXT",
            "ALTER TABLE soda_kegs ADD COLUMN last_revision_date TEXT",
            "ALTER TABLE soda_kegs ADD COLUMN revision_interval_months INTEGER DEFAULT 12",
        ]:
            try:
                conn.execute(sql)
            except Exception as e:
                pass  # colonne déjà existante
    # Migrations base de mesures
    with get_readings_db() as rconn:
        for sql in [
            "ALTER TABLE temperature_readings ADD COLUMN target_temp REAL",
            "ALTER TABLE temperature_readings ADD COLUMN hvac_mode TEXT",
        ]:
            try:
                rconn.execute(sql)
            except Exception as e:
                pass  # colonne déjà existante
        # Backfill initial counts for existing beers that don't have them yet
        conn.execute('UPDATE beers SET initial_33cl=stock_33cl WHERE initial_33cl=0 AND stock_33cl>0')
        conn.execute('UPDATE beers SET initial_75cl=stock_75cl WHERE initial_75cl=0 AND stock_75cl>0')
        # Migration readings : déplacer spindle_readings de la DB principale vers brewhome_readings.db
        try:
            rows = conn.execute('SELECT * FROM main.spindle_readings').fetchall()
            if rows:
                with get_readings_db() as rconn:
                    rconn.executemany(
                        'INSERT OR IGNORE INTO spindle_readings'
                        ' (id,spindle_id,gravity,temperature,battery,angle,rssi,recorded_at)'
                        ' VALUES (?,?,?,?,?,?,?,?)',
                        [(r['id'], r['spindle_id'], r['gravity'], r['temperature'],
                          r['battery'], r['angle'], r['rssi'], r['recorded_at']) for r in rows]
                    )
            conn.execute('DROP TABLE IF EXISTS main.spindle_readings')
        except Exception as e:
            pass  # table absente = déjà migrée ou installation neuve


def _seed_catalog(conn):
    """Inserts reference ingredients if the catalog is empty."""
    if conn.execute('SELECT COUNT(*) FROM ingredient_catalog').fetchone()[0] > 0:
        return

    rows = []

    # ── MALTS ────────────────────────────────────────────────────────────────
    malts = [
        # Base Malts
        ('Pilsner Malt',               'malt', 'Base Malts',            3.5,  308, None, None, 'kg'),
        ('Pale Ale Malt',              'malt', 'Base Malts',            5,    300, None, None, 'kg'),
        ('Pale Malt 2-Row',            'malt', 'Base Malts',            4,    300, None, None, 'kg'),
        ('Pale Malt 6-Row',            'malt', 'Base Malts',            4,    292, None, None, 'kg'),
        ('Maris Otter',                'malt', 'Base Malts',            5.5,  300, None, None, 'kg'),
        ('Golden Promise',             'malt', 'Base Malts',            5,    300, None, None, 'kg'),
        ('Vienna Malt',                'malt', 'Base Malts',            8,    292, None, None, 'kg'),
        ('Munich Malt Type I (10L)',   'malt', 'Base Malts',            20,   284, None, None, 'kg'),
        ('Munich Malt Type II (20L)',  'malt', 'Base Malts',            40,   275, None, None, 'kg'),
        ('Wheat Malt',                 'malt', 'Base Malts',            4,    308, None, None, 'kg'),
        ('Rye Malt',                   'malt', 'Base Malts',            5,    284, None, None, 'kg'),
        ('Oat Malt',                   'malt', 'Base Malts',            4,    270, None, None, 'kg'),
        ('Smoked Malt',                'malt', 'Base Malts',            6,    292, None, None, 'kg'),
        ('Acidulated Malt',            'malt', 'Base Malts',            3,    284, None, None, 'kg'),
        # Crystal/Caramel
        ('Caramel/Crystal 10L',        'malt', 'Crystal/Caramel',       20,   292, None, None, 'kg'),
        ('Caramel/Crystal 20L',        'malt', 'Crystal/Caramel',       40,   284, None, None, 'kg'),
        ('Caramel/Crystal 30L',        'malt', 'Crystal/Caramel',       60,   275, None, None, 'kg'),
        ('Caramel/Crystal 40L',        'malt', 'Crystal/Caramel',       80,   275, None, None, 'kg'),
        ('Caramel/Crystal 60L',        'malt', 'Crystal/Caramel',       120,  267, None, None, 'kg'),
        ('Caramel/Crystal 80L',        'malt', 'Crystal/Caramel',       160,  259, None, None, 'kg'),
        ('Caramel/Crystal 120L',       'malt', 'Crystal/Caramel',       240,  250, None, None, 'kg'),
        ('Caramel Wheat',              'malt', 'Crystal/Caramel',       100,  267, None, None, 'kg'),
        ('Caramel Munich',             'malt', 'Crystal/Caramel',       120,  267, None, None, 'kg'),
        ('CaraRed',                    'malt', 'Crystal/Caramel',       40,   275, None, None, 'kg'),
        ('CaraAroma',                  'malt', 'Crystal/Caramel',       260,  250, None, None, 'kg'),
        ('CaraHell',                   'malt', 'Crystal/Caramel',       20,   292, None, None, 'kg'),
        ('CaraMunich I',               'malt', 'Crystal/Caramel',       70,   275, None, None, 'kg'),
        ('CaraMunich II',              'malt', 'Crystal/Caramel',       90,   267, None, None, 'kg'),
        ('CaraMunich III',             'malt', 'Crystal/Caramel',       120,  259, None, None, 'kg'),
        ('CaraVienna',                 'malt', 'Crystal/Caramel',       50,   275, None, None, 'kg'),
        ('Special B',                  'malt', 'Crystal/Caramel',       300,  242, None, None, 'kg'),
        # Roasted
        ('Chocolate Malt',             'malt', 'Malts torréfiés',       900,  217, None, None, 'kg'),
        ('Pale Chocolate',             'malt', 'Malts torréfiés',       500,  225, None, None, 'kg'),
        ('Chocolate Wheat',            'malt', 'Malts torréfiés',       900,  217, None, None, 'kg'),
        ('Carafa I',                   'malt', 'Malts torréfiés',       800,  217, None, None, 'kg'),
        ('Carafa II',                  'malt', 'Malts torréfiés',       1100, 209, None, None, 'kg'),
        ('Carafa III',                 'malt', 'Malts torréfiés',       1400, 200, None, None, 'kg'),
        ('Carafa Special I',           'malt', 'Malts torréfiés',       800,  217, None, None, 'kg'),
        ('Carafa Special II',          'malt', 'Malts torréfiés',       1100, 209, None, None, 'kg'),
        ('Carafa Special III',         'malt', 'Malts torréfiés',       1400, 200, None, None, 'kg'),
        ('Black Patent Malt',          'malt', 'Malts torréfiés',       1300, 200, None, None, 'kg'),
        ('Black Malt',                 'malt', 'Malts torréfiés',       1300, 200, None, None, 'kg'),
        ('Roasted Barley',             'malt', 'Malts torréfiés',       1300, 200, None, None, 'kg'),
        ('Coffee Malt',                'malt', 'Malts torréfiés',       400,  225, None, None, 'kg'),
        ('Midnight Wheat',             'malt', 'Malts torréfiés',       1400, 200, None, None, 'kg'),
        # Specialty
        ('Biscuit Malt',               'malt', 'Malts spéciaux',        50,   275, None, None, 'kg'),
        ('Victory Malt',               'malt', 'Malts spéciaux',        50,   275, None, None, 'kg'),
        ('Amber Malt',                 'malt', 'Malts spéciaux',        50,   259, None, None, 'kg'),
        ('Brown Malt',                 'malt', 'Malts spéciaux',        130,  242, None, None, 'kg'),
        ('Aromatic Malt',              'malt', 'Malts spéciaux',        40,   275, None, None, 'kg'),
        ('Melanoidin Malt',            'malt', 'Malts spéciaux',        50,   275, None, None, 'kg'),
        ('Honey Malt',                 'malt', 'Malts spéciaux',        50,   284, None, None, 'kg'),
        ('Dextrin Malt (Cara-Pils)',   'malt', 'Malts spéciaux',        3,    284, None, None, 'kg'),
        ('Flaked Barley',              'malt', 'Malts spéciaux',        4,    284, None, None, 'kg'),
        ('Flaked Oats',                'malt', 'Malts spéciaux',        2,    259, None, None, 'kg'),
        ('Flaked Wheat',               'malt', 'Malts spéciaux',        4,    292, None, None, 'kg'),
        ('Flaked Rye',                 'malt', 'Malts spéciaux',        6,    267, None, None, 'kg'),
        ('Flaked Corn',                'malt', 'Malts spéciaux',        2,    317, None, None, 'kg'),
        ('Flaked Rice',                'malt', 'Malts spéciaux',        1,    309, None, None, 'kg'),
        ('Torrified Wheat',            'malt', 'Malts spéciaux',        4,    292, None, None, 'kg'),
        ('Torrified Barley',           'malt', 'Malts spéciaux',        4,    275, None, None, 'kg'),
    ]
    rows.extend(malts)

    # ── HOUBLONS ─────────────────────────────────────────────────────────────
    hops = [
        ('Adeena',            'houblon', 'Hops A', None, None, 4.3,  None, 'g'),
        ('Admiral',           'houblon', 'Hops A', None, None, 14.6, None, 'g'),
        ('African Queen',     'houblon', 'Hops A', None, None, 13.5, None, 'g'),
        ('Agnus',             'houblon', 'Hops A', None, None, 11.5, None, 'g'),
        ('Ahtanum',           'houblon', 'Hops A', None, None, 5.0,  None, 'g'),
        ('Akoya',             'houblon', 'Hops A', None, None, 9.5,  None, 'g'),
        ('Alora',             'houblon', 'Hops A', None, None, 10.0, None, 'g'),
        ('Altus',             'houblon', 'Hops A', None, None, 16.8, None, 'g'),
        ('Amarillo',          'houblon', 'Hops A', None, None, 9.0,  None, 'g'),
        ('Amethyst',          'houblon', 'Hops A', None, None, 4.8,  None, 'g'),
        ('Apollo',            'houblon', 'Hops A', None, None, 17.8, None, 'g'),
        ('Apolon',            'houblon', 'Hops A', None, None, 11.0, None, 'g'),
        ('Aquila',            'houblon', 'Hops A', None, None, 7.7,  None, 'g'),
        ('Aramis',            'houblon', 'Hops A', None, None, 8.1,  None, 'g'),
        ('Archer',            'houblon', 'Hops A', None, None, 5.0,  None, 'g'),
        ('Ariana',            'houblon', 'Hops A', None, None, 11.0, None, 'g'),
        ('Astra',             'houblon', 'Hops A', None, None, 8.5,  None, 'g'),
        ('Atlas',             'houblon', 'Hops A', None, None, 8.0,  None, 'g'),
        ('Aurora',            'houblon', 'Hops A', None, None, 10.0, None, 'g'),
        ('Azacca',            'houblon', 'Hops A', None, None, 15.0, None, 'g'),
        ('Banner',            'houblon', 'Hops B', None, None, 10.8, None, 'g'),
        ('Barbe Rouge',       'houblon', 'Hops B', None, None, 6.9,  None, 'g'),
        ('Beata',             'houblon', 'Hops B', None, None, 6.0,  None, 'g'),
        ('Belma',             'houblon', 'Hops B', None, None, 10.3, None, 'g'),
        ('Bianca',            'houblon', 'Hops B', None, None, 7.5,  None, 'g'),
        ('Bitter Gold',       'houblon', 'Hops B', None, None, 15.4, None, 'g'),
        ('Boadicea',          'houblon', 'Hops B', None, None, 8.8,  None, 'g'),
        ('Bobek',             'houblon', 'Hops B', None, None, 6.4,  None, 'g'),
        ('Boomerang',         'houblon', 'Hops B', None, None, 12.0, None, 'g'),
        ('Bouclier',          'houblon', 'Hops B', None, None, 8.2,  None, 'g'),
        ('Bramling Cross',    'houblon', 'Hops B', None, None, 6.5,  None, 'g'),
        ('Bravo',             'houblon', 'Hops B', None, None, 15.5, None, 'g'),
        ("Brewer's Gold (GR)",'houblon', 'Hops B', None, None, 6.2,  None, 'g'),
        ("Brewer's Gold (US)",'houblon', 'Hops B', None, None, 9.5,  None, 'g'),
        ('Bullion',           'houblon', 'Hops B', None, None, 8.9,  None, 'g'),
        ('CTZ',               'houblon', 'Hops C', None, None, 15.8, None, 'g'),
        ('Caliente',          'houblon', 'Hops C', None, None, 15.0, None, 'g'),
        ('Callista',          'houblon', 'Hops C', None, None, 3.5,  None, 'g'),
        ('Calypso',           'houblon', 'Hops C', None, None, 14.0, None, 'g'),
        ('Cascade',           'houblon', 'Hops C', None, None, 7.0,  None, 'g'),
        ('Cashmere',          'houblon', 'Hops C', None, None, 8.4,  None, 'g'),
        ('Celeia',            'houblon', 'Hops C', None, None, 4.5,  None, 'g'),
        ('Centennial',        'houblon', 'Hops C', None, None, 9.5,  None, 'g'),
        ('Challenger',        'houblon', 'Hops C', None, None, 7.8,  None, 'g'),
        ('Chelan',            'houblon', 'Hops C', None, None, 13.5, None, 'g'),
        ('Chinook',           'houblon', 'Hops C', None, None, 13.3, None, 'g'),
        ('Citra',             'houblon', 'Hops C', None, None, 12.5, None, 'g'),
        ('Cluster',           'houblon', 'Hops C', None, None, 7.3,  None, 'g'),
        ('Columbus',          'houblon', 'Hops C', None, None, 16.0, None, 'g'),
        ('Comet',             'houblon', 'Hops C', None, None, 10.2, None, 'g'),
        ('Crystal',           'houblon', 'Hops C', None, None, 4.4,  None, 'g'),
        ('Dana',              'houblon', 'Hops D', None, None, 10.1, None, 'g'),
        ('Delta',             'houblon', 'Hops D', None, None, 6.3,  None, 'g'),
        ('Dr. Rudi',          'houblon', 'Hops D', None, None, 11.0, None, 'g'),
        ('East Kent Goldings','houblon', 'Hops E', None, None, 5.3,  None, 'g'),
        ('Ekuanot',           'houblon', 'Hops E', None, None, 14.3, None, 'g'),
        ('El Dorado',         'houblon', 'Hops E', None, None, 15.0, None, 'g'),
        ('Ella',              'houblon', 'Hops E', None, None, 16.3, None, 'g'),
        ('Enigma',            'houblon', 'Hops E', None, None, 16.5, None, 'g'),
        ('Equinox',           'houblon', 'Hops E', None, None, 15.0, None, 'g'),
        ('Eureka',            'houblon', 'Hops E', None, None, 18.5, None, 'g'),
        ("Falconer's Flight", 'houblon', 'Hops F', None, None, 10.8, None, 'g'),
        ('First Gold',        'houblon', 'Hops F', None, None, 7.8,  None, 'g'),
        ('Fuggle',            'houblon', 'Hops F', None, None, 4.3,  None, 'g'),
        ('Galaxy',            'houblon', 'Hops G', None, None, 13.5, None, 'g'),
        ('Galena',            'houblon', 'Hops G', None, None, 13.8, None, 'g'),
        ('Glacier',           'houblon', 'Hops G', None, None, 6.5,  None, 'g'),
        ('Golding',           'houblon', 'Hops G', None, None, 5.0,  None, 'g'),
        ('Green Bullet',      'houblon', 'Hops G', None, None, 13.0, None, 'g'),
        ('Hallertau Blanc',       'houblon', 'Hops H', None, None, 10.5, None, 'g'),
        ('Hallertau Mittelfrüh',  'houblon', 'Hops H', None, None, 4.3,  None, 'g'),
        ('Hallertau Tradition',   'houblon', 'Hops H', None, None, 5.8,  None, 'g'),
        ('Hallertau Taurus',      'houblon', 'Hops H', None, None, 15.0, None, 'g'),
        ('Harlequin',         'houblon', 'Hops H', None, None, 10.5, None, 'g'),
        ('Herkules',          'houblon', 'Hops H', None, None, 14.5, None, 'g'),
        ('Hersbrucker',       'houblon', 'Hops H', None, None, 3.3,  None, 'g'),
        ('Horizon',           'houblon', 'Hops H', None, None, 12.7, None, 'g'),
        ('Huell Melon',       'houblon', 'Hops H', None, None, 7.5,  None, 'g'),
        ('Idaho 7',           'houblon', 'Hops I', None, None, 12.2, None, 'g'),
        ('Jarryllo',          'houblon', 'Hops J', None, None, 16.0, None, 'g'),
        ('Jester',            'houblon', 'Hops J', None, None, 8.0,  None, 'g'),
        ('Kazbek',            'houblon', 'Hops K', None, None, 6.5,  None, 'g'),
        ('Lemondrop',         'houblon', 'Hops L', None, None, 6.0,  None, 'g'),
        ('Liberty',           'houblon', 'Hops L', None, None, 4.8,  None, 'g'),
        ('Loral',             'houblon', 'Hops L', None, None, 13.5, None, 'g'),
        ('Magnum (GR)',       'houblon', 'Hops M', None, None, 13.5, None, 'g'),
        ('Magnum (US)',       'houblon', 'Hops M', None, None, 13.0, None, 'g'),
        ('Mandarina Bavaria', 'houblon', 'Hops M', None, None, 8.8,  None, 'g'),
        ('Mosaic',            'houblon', 'Hops M', None, None, 12.5, None, 'g'),
        ('Motueka',           'houblon', 'Hops M', None, None, 6.8,  None, 'g'),
        ('Nectaron',          'houblon', 'Hops N', None, None, 10.8, None, 'g'),
        ('Nelson Sauvin',     'houblon', 'Hops N', None, None, 12.2, None, 'g'),
        ('Newport',           'houblon', 'Hops N', None, None, 13.8, None, 'g'),
        ('Northern Brewer (GR)','houblon','Hops N',None, None, 8.0,  None, 'g'),
        ('Northern Brewer (US)','houblon','Hops N',None, None, 8.5,  None, 'g'),
        ('Nugget',            'houblon', 'Hops N', None, None, 12.8, None, 'g'),
        ('Opal',              'houblon', 'Hops O', None, None, 9.5,  None, 'g'),
        ('Pacific Gem',       'houblon', 'Hops P', None, None, 14.0, None, 'g'),
        ('Pacific Jade',      'houblon', 'Hops P', None, None, 13.0, None, 'g'),
        ('Palisade',          'houblon', 'Hops P', None, None, 7.8,  None, 'g'),
        ('Pekko',             'houblon', 'Hops P', None, None, 14.5, None, 'g'),
        ('Perle (GR)',        'houblon', 'Hops P', None, None, 6.5,  None, 'g'),
        ('Perle (US)',        'houblon', 'Hops P', None, None, 6.5,  None, 'g'),
        ('Phoenix',           'houblon', 'Hops P', None, None, 10.8, None, 'g'),
        ('Pioneer',           'houblon', 'Hops P', None, None, 9.3,  None, 'g'),
        ('Polaris',           'houblon', 'Hops P', None, None, 20.5, None, 'g'),
        ('Premiant',          'houblon', 'Hops P', None, None, 8.0,  None, 'g'),
        ('Rakau',             'houblon', 'Hops R', None, None, 10.5, None, 'g'),
        ('Riwaka',            'houblon', 'Hops R', None, None, 5.5,  None, 'g'),
        ('Saaz (CZ)',         'houblon', 'Hops S', None, None, 3.5,  None, 'g'),
        ('Saaz (US)',         'houblon', 'Hops S', None, None, 3.8,  None, 'g'),
        ('Sabro',             'houblon', 'Hops S', None, None, 14.5, None, 'g'),
        ('Saphir',            'houblon', 'Hops S', None, None, 3.3,  None, 'g'),
        ('Simcoe',            'houblon', 'Hops S', None, None, 13.0, None, 'g'),
        ('Sorachi Ace',       'houblon', 'Hops S', None, None, 13.5, None, 'g'),
        ('Spalter Select',    'houblon', 'Hops S', None, None, 4.8,  None, 'g'),
        ('Sterling',          'houblon', 'Hops S', None, None, 7.0,  None, 'g'),
        ('Strisselspalt',     'houblon', 'Hops S', None, None, 2.5,  None, 'g'),
        ('Styrian Golding',   'houblon', 'Hops S', None, None, 5.0,  None, 'g'),
        ('Summit',            'houblon', 'Hops S', None, None, 16.3, None, 'g'),
        ('Super Galena',      'houblon', 'Hops S', None, None, 14.5, None, 'g'),
        ('Tahoma',            'houblon', 'Hops T', None, None, 7.6,  None, 'g'),
        ('Target',            'houblon', 'Hops T', None, None, 11.0, None, 'g'),
        ('Tettnanger',        'houblon', 'Hops T', None, None, 4.2,  None, 'g'),
        ('Tomahawk',          'houblon', 'Hops T', None, None, 16.3, None, 'g'),
        ('Topaz',             'houblon', 'Hops T', None, None, 16.9, None, 'g'),
        ('Triskel',           'houblon', 'Hops T', None, None, 8.5,  None, 'g'),
        ('Vic Secret',        'houblon', 'Hops V', None, None, 17.9, None, 'g'),
        ('Wai-iti',           'houblon', 'Hops W', None, None, 3.0,  None, 'g'),
        ('Waimea',            'houblon', 'Hops W', None, None, 16.8, None, 'g'),
        ('Wakatu',            'houblon', 'Hops W', None, None, 7.5,  None, 'g'),
        ('Warrior',           'houblon', 'Hops W', None, None, 16.3, None, 'g'),
        ('Willamette',        'houblon', 'Hops W', None, None, 5.6,  None, 'g'),
        ('Yakima Cluster',    'houblon', 'Hops Y', None, None, 7.1,  None, 'g'),
        ('Zappa',             'houblon', 'Hops Z', None, None, 7.5,  None, 'g'),
        ('Zythos',            'houblon', 'Hops Z', None, None, 11.3, None, 'g'),
    ]
    rows.extend(hops)

    # ── LEVURES ──────────────────────────────────────────────────────────────
    yeasts = [
        # Fermentis
        ('Fermentis K-97',       'levure', 'Fermentis', None, None, None, 'ale',   'sachet'),
        ('Fermentis S-04',       'levure', 'Fermentis', None, None, None, 'ale',   'sachet'),
        ('Fermentis S-33',       'levure', 'Fermentis', None, None, None, 'ale',   'sachet'),
        ('Fermentis T-58',       'levure', 'Fermentis', None, None, None, 'ale',   'sachet'),
        ('Fermentis US-05',      'levure', 'Fermentis', None, None, None, 'ale',   'sachet'),
        ('Fermentis WB-06',      'levure', 'Fermentis', None, None, None, 'ale',   'sachet'),
        ('Fermentis S-189',      'levure', 'Fermentis', None, None, None, 'lager', 'sachet'),
        ('Fermentis S-23',       'levure', 'Fermentis', None, None, None, 'lager', 'sachet'),
        ('Fermentis W-34/70',    'levure', 'Fermentis', None, None, None, 'lager', 'sachet'),
        # Lallemand
        ('Lallemand BRY-97',     'levure', 'Lallemand', None, None, None, 'ale',   'sachet'),
        ('Lallemand Voss Kveik', 'levure', 'Lallemand', None, None, None, 'kveik', 'sachet'),
        ('Lallemand New England','levure', 'Lallemand', None, None, None, 'ale',   'sachet'),
        ('Lallemand Verdant IPA','levure', 'Lallemand', None, None, None, 'ale',   'sachet'),
        ('Lallemand Nottingham', 'levure', 'Lallemand', None, None, None, 'ale',   'sachet'),
        ('Lallemand Abbaye',     'levure', 'Lallemand', None, None, None, 'ale',   'sachet'),
        ('Lallemand Farmhouse',  'levure', 'Lallemand', None, None, None, 'ale',   'sachet'),
        ('Lallemand Wit',        'levure', 'Lallemand', None, None, None, 'ale',   'sachet'),
        ('Lallemand Windsor',    'levure', 'Lallemand', None, None, None, 'ale',   'sachet'),
        ('Lallemand Novalager',  'levure', 'Lallemand', None, None, None, 'lager', 'sachet'),
        ('Lallemand Diamond Lager','levure','Lallemand',None, None, None, 'lager', 'sachet'),
        # White Labs
        ('White Labs WLP001 California Ale',   'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP002 English Ale',      'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP004 Irish Ale',        'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP007 Dry English Ale',  'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP029 German Ale Kolsch','levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP300 Hefeweizen',       'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP400 Belgian Wit',      'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP500 Trappist Ale',     'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP530 Abbey Ale',        'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP550 Belgian Ale',      'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP565 Belgian Saison I', 'levure', 'White Labs', None, None, None, 'ale',   'sachet'),
        ('White Labs WLP800 Pilsner Lager',    'levure', 'White Labs', None, None, None, 'lager', 'sachet'),
        ('White Labs WLP820 Oktoberfest',      'levure', 'White Labs', None, None, None, 'lager', 'sachet'),
        ('White Labs WLP830 German Lager',     'levure', 'White Labs', None, None, None, 'lager', 'sachet'),
        # Wyeast
        ('Wyeast WY1056 American Ale',         'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY1084 Irish Ale',            'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY1272 American Ale II',      'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY1318 London Ale III',       'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY1388 Belgian Strong Ale',   'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY1728 Scottish Ale',         'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY3068 Weihenstephan Weizen', 'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY3711 French Saison',        'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY3724 Belgian Saison',       'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY3787 Trappist High Gravity','levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY3944 Belgian Witbier',      'levure', 'Wyeast', None, None, None, 'ale',   'sachet'),
        ('Wyeast WY2124 Bohemian Lager',       'levure', 'Wyeast', None, None, None, 'lager', 'sachet'),
        ('Wyeast WY2206 Bavarian Lager',       'levure', 'Wyeast', None, None, None, 'lager', 'sachet'),
        ('Wyeast WY2278 Czech Pils',           'levure', 'Wyeast', None, None, None, 'lager', 'sachet'),
        # Mangrove Jack's
        ("Mangrove Jack's M07 British Ale",    'levure', "Mangrove Jack's", None, None, None, 'ale',   'sachet'),
        ("Mangrove Jack's M20 Bavarian Wheat", 'levure', "Mangrove Jack's", None, None, None, 'ale',   'sachet'),
        ("Mangrove Jack's M27 Belgian Ale",    'levure', "Mangrove Jack's", None, None, None, 'ale',   'sachet'),
        ("Mangrove Jack's M44 US West Coast",  'levure', "Mangrove Jack's", None, None, None, 'ale',   'sachet'),
        ("Mangrove Jack's M84 Bohemian Lager", 'levure', "Mangrove Jack's", None, None, None, 'lager', 'sachet'),
    ]
    rows.extend(yeasts)

    # ── AUTRES (épices, clarifiants, sucres, fruits...) ──────────────────────
    others = [
        # Épices
        ('Coriandre',           'autre', 'Épices',       None, None, None, None, 'g'),
        ("Écorce d'orange",     'autre', 'Épices',       None, None, None, None, 'g'),
        ('Gingembre',           'autre', 'Épices',       None, None, None, None, 'g'),
        ('Cannelle',            'autre', 'Épices',       None, None, None, None, 'g'),
        ('Cardamome',           'autre', 'Épices',       None, None, None, None, 'g'),
        ('Anis étoilé',         'autre', 'Épices',       None, None, None, None, 'g'),
        ('Poivre',              'autre', 'Épices',       None, None, None, None, 'g'),
        ('Vanille',             'autre', 'Épices',       None, None, None, None, 'g'),
        # Clarifiants
        ('Protafloc',           'autre', 'Clarifiants',  None, None, None, None, 'g'),
        ('Irish Moss',          'autre', 'Clarifiants',  None, None, None, None, 'g'),
        ('Whirlfloc',           'autre', 'Clarifiants',  None, None, None, None, 'pièce'),
        ('Gélatine',            'autre', 'Clarifiants',  None, None, None, None, 'g'),
        # Agents
        ('Levure nutritive',      'autre', 'Agents',    None, None, None, None, 'g'),
        ('Acide lactique',        'autre', 'Agents',    None, None, None, None, 'mL'),
        ('Acide lactique 80%',    'autre', 'Agents',    None, None, None, None, 'mL'),
        ('Acide lactique 88%',    'autre', 'Agents',    None, None, None, None, 'mL'),
        ('Acide phosphorique 75%','autre', 'Agents',    None, None, None, None, 'mL'),
        ('Acide phosphorique 85%','autre', 'Agents',    None, None, None, None, 'mL'),
        ('Acide citrique',        'autre', 'Agents',    None, None, None, None, 'g'),
        ('Gypse (CaSO4)',         'autre', 'Agents',    None, None, None, None, 'g'),
        # Minéraux
        ('Sulfate de calcium',    'autre', 'Minéraux',  None, None, None, None, 'g'),
        ('Sulfate de magnésium',  'autre', 'Minéraux',  None, None, None, None, 'g'),
        ('Chlorure de calcium',   'autre', 'Minéraux',  None, None, None, None, 'g'),
        ('Chlorure de sodium',    'autre', 'Minéraux',  None, None, None, None, 'g'),
        ('Carbonate de calcium',  'autre', 'Minéraux',  None, None, None, None, 'g'),
        ('Bicarbonate de sodium', 'autre', 'Minéraux',  None, None, None, None, 'g'),
        # Fruits
        ('Purée de fruits',     'autre', 'Fruits',       None, None, None, None, 'kg'),
        ('Zeste de citron',     'autre', 'Fruits',       None, None, None, None, 'g'),
        ('Zeste de lime',       'autre', 'Fruits',       None, None, None, None, 'g'),
        ('Orange amère',        'autre', 'Fruits',       None, None, None, None, 'g'),
        ('Cerise',              'autre', 'Fruits',       None, None, None, None, 'kg'),
        # Sucres
        ('Sucre candi',         'autre', 'Sucres',       None, None, None, None, 'g'),
        ('Miel',                'autre', 'Sucres',       None, None, None, None, 'g'),
        ("Sirop d'érable",      'autre', 'Sucres',       None, None, None, None, 'ml'),
        ('Lactose',             'autre', 'Sucres',       None, None, None, None, 'g'),
        ('Dextrose',            'autre', 'Sucres',       None, None, None, None, 'g'),
        # Autres
        ('Café',                'autre', 'Divers',       None, None, None, None, 'g'),
        ('Cacao',               'autre', 'Divers',       None, None, None, None, 'g'),
        ('Thé',                 'autre', 'Divers',       None, None, None, None, 'g'),
        ('Bois de chêne',       'autre', 'Divers',       None, None, None, None, 'g'),
        ('Copeaux de bois',     'autre', 'Divers',       None, None, None, None, 'g'),
    ]
    rows.extend(others)

    conn.executemany(
        'INSERT INTO ingredient_catalog (name,category,subcategory,ebc,gu,alpha,yeast_type,default_unit) VALUES (?,?,?,?,?,?,?,?)',
        rows
    )


def _seed_catalog_extras(conn):
    """Inserts catalog entries that may be missing from existing installations."""
    # Normalise 'ml' → 'mL' in catalog and recipe_ingredients (case consistency)
    conn.execute("UPDATE ingredient_catalog SET default_unit='mL' WHERE default_unit='ml'")
    conn.execute("UPDATE recipe_ingredients SET unit='mL' WHERE unit='ml'")
    # Ensure existing generic 'Acide lactique' also uses mL
    conn.execute("UPDATE ingredient_catalog SET default_unit='mL' WHERE name='Acide lactique' AND category='autre'")

    extras = [
        ('Acide lactique 80%',    'autre', 'Agents',   None, None, None, None, 'mL'),
        ('Acide lactique 88%',    'autre', 'Agents',   None, None, None, None, 'mL'),
        ('Acide phosphorique 75%','autre', 'Agents',   None, None, None, None, 'mL'),
        ('Acide phosphorique 85%','autre', 'Agents',   None, None, None, None, 'mL'),
        ('Sulfate de calcium',    'autre', 'Minéraux', None, None, None, None, 'g'),
        ('Sulfate de magnésium',  'autre', 'Minéraux', None, None, None, None, 'g'),
        ('Chlorure de calcium',   'autre', 'Minéraux', None, None, None, None, 'g'),
        ('Chlorure de sodium',    'autre', 'Minéraux', None, None, None, None, 'g'),
        ('Carbonate de calcium',  'autre', 'Minéraux', None, None, None, None, 'g'),
        ('Bicarbonate de sodium', 'autre', 'Minéraux', None, None, None, None, 'g'),
    ]
    for item in extras:
        conn.execute(
            'INSERT INTO ingredient_catalog (name,category,subcategory,ebc,gu,alpha,yeast_type,default_unit)'
            ' SELECT ?,?,?,?,?,?,?,? WHERE NOT EXISTS'
            ' (SELECT 1 FROM ingredient_catalog WHERE name=? AND category=?)',
            (*item, item[0], item[1])
        )


# ── ROUTES ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    resp = make_response(render_template('index.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


# ── CATALOG ──────────────────────────────────────────────────────────────────

@app.route('/api/catalog')
def get_catalog():
    cat = request.args.get('category')
    q   = request.args.get('q', '').strip()
    with get_db() as conn:
        sql  = 'SELECT * FROM ingredient_catalog WHERE 1=1'
        args = []
        if cat:
            sql += ' AND category=?'; args.append(cat)
        if q:
            sql += ' AND name LIKE ?'; args.append(f'%{q}%')
        sql += ' ORDER BY subcategory, name'
        rows = conn.execute(sql, args).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/catalog', methods=['POST'])
def create_catalog_item():
    d = request.json or {}
    if not d.get('name') or not d.get('category'):
        return jsonify({'error': 'name and category are required'}), 400
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO ingredient_catalog
               (name,category,subcategory,ebc,gu,alpha,yeast_type,default_unit,
                temp_min,temp_max,dosage_per_liter,attenuation_min,attenuation_max,alcohol_tolerance,max_usage_pct,aroma_spec)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('name'), d.get('category'), d.get('subcategory'), d.get('ebc'), d.get('gu'),
             d.get('alpha'), d.get('yeast_type'), d.get('default_unit', 'g'),
             d.get('temp_min'), d.get('temp_max'), d.get('dosage_per_liter'),
             d.get('attenuation_min'), d.get('attenuation_max'), d.get('alcohol_tolerance'),
             d.get('max_usage_pct'), d.get('aroma_spec'))
        )
        row = conn.execute('SELECT * FROM ingredient_catalog WHERE id=?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@app.route('/api/catalog/<int:item_id>', methods=['PUT'])
def update_catalog_item(item_id):
    d = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE ingredient_catalog
               SET name=?, subcategory=?, ebc=?, alpha=?, yeast_type=?, default_unit=?,
                   temp_min=?, temp_max=?, dosage_per_liter=?,
                   attenuation_min=?, attenuation_max=?, alcohol_tolerance=?,
                   max_usage_pct=?, aroma_spec=?
               WHERE id=?''',
            (d.get('name'), d.get('subcategory'), d.get('ebc'), d.get('alpha'),
             d.get('yeast_type'), d.get('default_unit', 'g'),
             d.get('temp_min'), d.get('temp_max'), d.get('dosage_per_liter'),
             d.get('attenuation_min'), d.get('attenuation_max'), d.get('alcohol_tolerance'),
             d.get('max_usage_pct'), d.get('aroma_spec'), item_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute('SELECT * FROM ingredient_catalog WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row))


@app.route('/api/catalog/<int:item_id>', methods=['DELETE'])
def delete_catalog_item(item_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM ingredient_catalog WHERE id=?', (item_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True})


# ── INVENTORY ────────────────────────────────────────────────────────────────

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM inventory_items ORDER BY COALESCE(sort_order, 9999) ASC, category, name'
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/inventory', methods=['POST'])
def create_inventory_item():
    d = request.json or {}
    if not d.get('name') or not d.get('category'):
        return jsonify({'error': 'name and category are required'}), 400
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO inventory_items (name,category,quantity,unit,origin,ebc,alpha,notes,price_per_unit) VALUES (?,?,?,?,?,?,?,?,?)',
            (d.get('name'), d.get('category'), d.get('quantity', 0), d.get('unit', 'kg'),
             d.get('origin'), d.get('ebc'), d.get('alpha'), d.get('notes'),
             d.get('price_per_unit'))
        )
        row = conn.execute('SELECT * FROM inventory_items WHERE id=?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@app.route('/api/inventory/<int:item_id>', methods=['PUT'])
def update_inventory_item(item_id):
    d = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE inventory_items
               SET name=?,category=?,quantity=?,unit=?,origin=?,ebc=?,alpha=?,notes=?,
                   price_per_unit=?,updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (d.get('name'), d.get('category'), d.get('quantity'), d.get('unit', 'kg'),
             d.get('origin'), d.get('ebc'), d.get('alpha'), d.get('notes'),
             d.get('price_per_unit'), item_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row))


@app.route('/api/inventory/reorder', methods=['PUT'])
def reorder_inventory():
    items = request.json or []
    with get_db() as conn:
        for item in items:
            if item.get('id') is None or item.get('sort_order') is None:
                continue
            conn.execute('UPDATE inventory_items SET sort_order=? WHERE id=?',
                         (item['sort_order'], item['id']))
    return jsonify({'success': True})


@app.route('/api/inventory/<int:item_id>', methods=['DELETE'])
def delete_inventory_item(item_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM inventory_items WHERE id=?', (item_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True})


@app.route('/api/inventory/<int:item_id>/qty', methods=['PATCH'])
def patch_inventory_qty(item_id):
    d = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE inventory_items SET quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
            (d.get('quantity'), item_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row))


@app.route('/api/inventory/<int:item_id>', methods=['PATCH'])
def patch_inventory_item(item_id):
    d = request.json
    with get_db() as conn:
        cur = conn.execute('UPDATE inventory_items SET archived=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                           (1 if d.get('archived') else 0, item_id))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute('SELECT * FROM inventory_items WHERE id=?', (item_id,)).fetchone()
        return jsonify(dict(row))


# ── RECIPES ──────────────────────────────────────────────────────────────────

def _recipe_with_ingredients(conn, recipe_id):
    r = conn.execute('SELECT * FROM recipes WHERE id=?', (recipe_id,)).fetchone()
    if not r:
        return None
    result = dict(r)
    ings = conn.execute(
        '''SELECT ri.*, ii.quantity as stock_qty, ii.unit as stock_unit
           FROM recipe_ingredients ri
           LEFT JOIN inventory_items ii ON ri.inventory_item_id = ii.id
           WHERE ri.recipe_id=?
           ORDER BY ri.category, ri.id''',
        (recipe_id,)
    ).fetchall()
    result['ingredients'] = [dict(i) for i in ings]
    return result


@app.route('/api/recipes', methods=['GET'])
def get_recipes():
    with get_db() as conn:
        recipes = conn.execute('SELECT * FROM recipes ORDER BY COALESCE(sort_order, 9999) ASC, created_at DESC').fetchall()
        result = []
        for r in recipes:
            result.append(_recipe_with_ingredients(conn, r['id']))
        return jsonify(result)


@app.route('/api/recipes/reorder', methods=['PUT'])
def reorder_recipes():
    items = request.json or []
    with get_db() as conn:
        for item in items:
            if item.get('id') is None or item.get('sort_order') is None:
                continue
            conn.execute('UPDATE recipes SET sort_order=? WHERE id=?',
                         (item['sort_order'], item['id']))
    return jsonify({'success': True})


@app.route('/api/recipes', methods=['POST'])
def create_recipe():
    d = request.json or {}
    if not d.get('name'):
        return jsonify({'error': 'name is required'}), 400
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO recipes
               (batch_no,name,style,volume,brew_date,bottling_date,mash_temp,mash_time,
                boil_time,mash_ratio,evap_rate,grain_absorption,brewhouse_efficiency,
                ferm_temp,ferm_time,notes,rating,draft_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('batch_no'), d.get('name'), d.get('style'), d.get('volume', 20),
             d.get('brew_date'), d.get('bottling_date'), d.get('mash_temp', 66),
             d.get('mash_time', 60), d.get('boil_time', 60), d.get('mash_ratio', 3.0),
             d.get('evap_rate', 3.0), d.get('grain_absorption', 0.8),
             d.get('brewhouse_efficiency', 72),
             d.get('ferm_temp', 20), d.get('ferm_time', 14), d.get('notes'),
             d.get('rating'), d.get('draft_id'))
        )
        recipe_id = cur.lastrowid
        for ing in d.get('ingredients', []):
            conn.execute(
                '''INSERT INTO recipe_ingredients
                   (recipe_id,inventory_item_id,name,category,quantity,unit,
                    hop_time,hop_type,hop_days,other_type,other_time,ebc,alpha,notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (recipe_id, ing.get('inventory_item_id'), ing.get('name'), ing.get('category'),
                 ing.get('quantity'), ing.get('unit', 'g'), ing.get('hop_time'),
                 ing.get('hop_type'), ing.get('hop_days'),
                 ing.get('other_type'), ing.get('other_time'),
                 ing.get('ebc'), ing.get('alpha'), ing.get('notes'))
            )
        return jsonify(_recipe_with_ingredients(conn, recipe_id)), 201


@app.route('/api/recipes/<int:recipe_id>', methods=['GET'])
def get_recipe(recipe_id):
    with get_db() as conn:
        result = _recipe_with_ingredients(conn, recipe_id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(result)


@app.route('/api/recipes/<int:recipe_id>', methods=['PUT'])
def update_recipe(recipe_id):
    d = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE recipes SET batch_no=?,name=?,style=?,volume=?,brew_date=?,bottling_date=?,
               mash_temp=?,mash_time=?,boil_time=?,mash_ratio=?,evap_rate=?,grain_absorption=?,
               brewhouse_efficiency=?,ferm_temp=?,ferm_time=?,notes=?,rating=?,draft_id=?
               WHERE id=?''',
            (d.get('batch_no'), d.get('name'), d.get('style'), d.get('volume', 20),
             d.get('brew_date'), d.get('bottling_date'), d.get('mash_temp', 66),
             d.get('mash_time', 60), d.get('boil_time', 60), d.get('mash_ratio', 3.0),
             d.get('evap_rate', 3.0), d.get('grain_absorption', 0.8),
             d.get('brewhouse_efficiency', 72),
             d.get('ferm_temp', 20), d.get('ferm_time', 14), d.get('notes'),
             d.get('rating'), d.get('draft_id'), recipe_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        conn.execute('DELETE FROM recipe_ingredients WHERE recipe_id=?', (recipe_id,))
        for ing in d.get('ingredients', []):
            conn.execute(
                '''INSERT INTO recipe_ingredients
                   (recipe_id,inventory_item_id,name,category,quantity,unit,
                    hop_time,hop_type,hop_days,other_type,other_time,ebc,alpha,notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (recipe_id, ing.get('inventory_item_id'), ing.get('name'), ing.get('category'),
                 ing.get('quantity'), ing.get('unit', 'g'), ing.get('hop_time'),
                 ing.get('hop_type'), ing.get('hop_days'),
                 ing.get('other_type'), ing.get('other_time'),
                 ing.get('ebc'), ing.get('alpha'), ing.get('notes'))
            )
        result = _recipe_with_ingredients(conn, recipe_id)
        if not result:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(result)


@app.route('/api/recipes/<int:recipe_id>', methods=['DELETE'])
def delete_recipe(recipe_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM recipes WHERE id=?', (recipe_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True})


@app.route('/api/recipes/<int:recipe_id>', methods=['PATCH'])
def patch_recipe(recipe_id):
    d = request.json
    with get_db() as conn:
        if 'archived' in d:
            conn.execute('UPDATE recipes SET archived=? WHERE id=?',
                         (1 if d['archived'] else 0, recipe_id))
        if 'rating' in d:
            conn.execute('UPDATE recipes SET rating=? WHERE id=?',
                         (d['rating'], recipe_id))
        row = conn.execute('SELECT id,name,archived,rating FROM recipes WHERE id=?', (recipe_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(row))


# ── BREWS ────────────────────────────────────────────────────────────────────

def _to_base(qty, unit):
    """Convert quantity to base unit (g for solids, ml for liquids)."""
    if unit == 'kg': return float(qty) * 1000
    if unit == 'g':  return float(qty)
    if unit == 'L':  return float(qty) * 1000
    if unit in ('ml', 'mL'): return float(qty)
    return float(qty)  # sachet, pièce — unitless

def _from_base(qty_base, unit):
    """Convert from base unit back to the given unit."""
    if unit == 'kg': return qty_base / 1000
    if unit == 'g':  return qty_base
    if unit == 'L':  return qty_base / 1000
    if unit in ('ml', 'mL'): return qty_base
    return qty_base

@app.route('/api/brews', methods=['GET'])
def get_brews():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT b.*, r.name as recipe_name, r.style as recipe_style,
                      COALESCE(b.ferm_time, r.ferm_time) as ferm_time,
                      b.ferm_time as brew_ferm_time,
                      r.ferm_time as recipe_ferm_time,
                      (SELECT COUNT(*) FROM brew_fermentation_readings WHERE brew_id=b.id) as fermentation_count,
                      (SELECT MIN(bottling_date) FROM beers WHERE brew_id=b.id AND bottling_date IS NOT NULL) as bottling_date
               FROM brews b LEFT JOIN recipes r ON b.recipe_id=r.id
               ORDER BY COALESCE(b.sort_order, 9999) ASC, b.created_at DESC'''
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/brews/reorder', methods=['PUT'])
def reorder_brews():
    items = request.json or []
    with get_db() as conn:
        for item in items:
            if item.get('id') is None or item.get('sort_order') is None:
                continue
            conn.execute('UPDATE brews SET sort_order=? WHERE id=?',
                         (item['sort_order'], item['id']))
    return jsonify({'success': True})


@app.route('/api/brews', methods=['POST'])
def create_brew():
    try:
        return _do_create_brew()
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e) or type(e).__name__}), 500

def _do_create_brew():
    d = request.json or {}
    recipe_id = d.get('recipe_id')
    if not recipe_id:
        return jsonify({'error': 'recipe_id required'}), 400
    deduct = d.get('deduct_stock', True)

    with get_db() as conn:
        if deduct:
            ings = conn.execute(
                '''SELECT ri.*, ii.quantity as stock_qty, ii.unit as inv_unit
                   FROM recipe_ingredients ri
                   LEFT JOIN inventory_items ii ON ri.inventory_item_id=ii.id
                   WHERE ri.recipe_id=?''',
                (recipe_id,)
            ).fetchall()

            insufficient = []
            for i in ings:
                if not i['inventory_item_id']:
                    continue
                inv_unit     = i['inv_unit'] or i['unit']
                needed_base  = _to_base(i['quantity'], i['unit'])
                stock_base   = _to_base(i['stock_qty'] or 0, inv_unit)
                if stock_base < needed_base:
                    available_disp = round(_from_base(stock_base, i['unit']), 6)
                    insufficient.append({
                        'name': i['name'],
                        'needed': i['quantity'],
                        'available': available_disp,
                        'unit': i['unit'],
                    })

            if insufficient and not d.get('force', False):
                return jsonify({'error': 'stock_insuffisant', 'items': insufficient}), 409

            for ing in ings:
                if ing['inventory_item_id']:
                    inv_unit    = ing['inv_unit'] or ing['unit']
                    needed_base = _to_base(ing['quantity'], ing['unit'])
                    stock_base  = _to_base(ing['stock_qty'] or 0, inv_unit)
                    new_base    = max(0.0, stock_base - needed_base)
                    new_qty     = round(_from_base(new_base, inv_unit), 6)
                    conn.execute(
                        'UPDATE inventory_items SET quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                        (new_qty, ing['inventory_item_id'])
                    )

        cur = conn.execute(
            '''INSERT INTO brews (recipe_id,name,brew_date,volume_brewed,og,fg,abv,notes,status)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            (recipe_id, d.get('name'), d.get('brew_date'), d.get('volume_brewed'),
             d.get('og'), d.get('fg'), d.get('abv'), d.get('notes'),
             d.get('status', 'completed'))
        )
        brew_id = cur.lastrowid
        row = conn.execute(
            '''SELECT b.*, r.name as recipe_name FROM brews b
               LEFT JOIN recipes r ON b.recipe_id=r.id WHERE b.id=?''',
            (brew_id,)
        ).fetchone()
        return jsonify(dict(row)), 201


@app.route('/api/brews/<int:brew_id>', methods=['PUT'])
def update_brew(brew_id):
    d = request.json
    with get_db() as conn:
        cur = conn.execute(
            'UPDATE brews SET name=?,brew_date=?,volume_brewed=?,og=?,fg=?,abv=?,notes=?,status=?,ferm_time=? WHERE id=?',
            (d.get('name'), d.get('brew_date'), d.get('volume_brewed'),
             d.get('og'), d.get('fg'), d.get('abv'), d.get('notes'),
             d.get('status', 'completed'),
             int(d['ferm_time']) if d.get('ferm_time') is not None else None,
             brew_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        # Quand un brassin passe en "terminé", archiver les mesures du densimètre puis le délier
        if d.get('status') == 'completed':
            sp = conn.execute('SELECT id FROM spindles WHERE brew_id=?', (brew_id,)).fetchone()
            if sp:
                # Copier les mesures dans l'historique de fermentation du brassin
                readings = conn.execute(
                    '''SELECT recorded_at, gravity, temperature, battery, angle
                       FROM rdb.spindle_readings WHERE spindle_id=? ORDER BY recorded_at''',
                    (sp['id'],)
                ).fetchall()
                if readings:
                    conn.executemany(
                        '''INSERT INTO brew_fermentation_readings
                           (brew_id, recorded_at, gravity, temperature, battery, angle)
                           VALUES (?,?,?,?,?,?)''',
                        [(brew_id, r['recorded_at'], r['gravity'], r['temperature'],
                          r['battery'], r['angle']) for r in readings]
                    )
                # Délier le densimètre et purger ses mesures temps-réel
                conn.execute('UPDATE spindles SET brew_id=NULL WHERE brew_id=?', (brew_id,))
                conn.execute('DELETE FROM rdb.spindle_readings WHERE spindle_id=?', (sp['id'],))
            # La sonde de température reste liée après complétion (refermentation, garde…)
        row = conn.execute(
            '''SELECT b.*, r.name as recipe_name, r.style as recipe_style,
                      COALESCE(b.ferm_time, r.ferm_time) as ferm_time,
                      b.ferm_time as brew_ferm_time,
                      r.ferm_time as recipe_ferm_time,
                      (SELECT MIN(bottling_date) FROM beers WHERE brew_id=b.id AND bottling_date IS NOT NULL) as bottling_date
               FROM brews b LEFT JOIN recipes r ON b.recipe_id=r.id WHERE b.id=?''',
            (brew_id,)
        ).fetchone()
        return jsonify(dict(row))


@app.route('/api/brews/<int:brew_id>', methods=['DELETE'])
def delete_brew(brew_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM brews WHERE id=?', (brew_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True})


@app.route('/api/brews/<int:brew_id>', methods=['PATCH'])
def patch_brew(brew_id):
    d = request.json
    with get_db() as conn:
        cur = conn.execute('UPDATE brews SET archived=? WHERE id=?',
                           (1 if d.get('archived') else 0, brew_id))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute(
            'SELECT b.*, r.name as recipe_name FROM brews b LEFT JOIN recipes r ON b.recipe_id=r.id WHERE b.id=?',
            (brew_id,)).fetchone()
        return jsonify(dict(row))


@app.route('/api/brews/<int:brew_id>/fermentation', methods=['GET'])
def get_brew_fermentation(brew_id):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM brew_fermentation_readings WHERE brew_id=? ORDER BY recorded_at',
            (brew_id,)
        ).fetchall()
        return jsonify([dict(r) for r in rows])


# ── BEERS ────────────────────────────────────────────────────────────────────

@app.route('/api/beers', methods=['GET'])
def get_beers():
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT b.*, br.brew_date, r.name as recipe_name
               FROM beers b
               LEFT JOIN brews br ON b.brew_id=br.id
               LEFT JOIN recipes r ON b.recipe_id=r.id
               ORDER BY COALESCE(b.sort_order, 9999) ASC, b.created_at DESC'''
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/beers/reorder', methods=['PUT'])
def reorder_beers():
    items = request.json or []
    with get_db() as conn:
        for item in items:
            if item.get('id') is None or item.get('sort_order') is None:
                continue
            conn.execute('UPDATE beers SET sort_order=? WHERE id=?',
                         (item['sort_order'], item['id']))
    return jsonify({'success': True})


@app.route('/api/beers', methods=['POST'])
def create_beer():
    d = request.json or {}
    if not d.get('name'):
        return jsonify({'error': 'name is required'}), 400
    with get_db() as conn:
        s33 = d.get('stock_33cl', 0)
        s75 = d.get('stock_75cl', 0)
        keg = d.get('keg_liters')
        cur = conn.execute(
            '''INSERT INTO beers (name,type,abv,stock_33cl,stock_75cl,initial_33cl,initial_75cl,keg_liters,keg_initial_liters,origin,description,photo,brew_id,recipe_id,brew_date,bottling_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('name'), d.get('type'), d.get('abv'), s33, s75,
             d.get('initial_33cl', s33), d.get('initial_75cl', s75),
             keg, d.get('keg_initial_liters', keg),
             d.get('origin'), d.get('description'),
             d.get('photo'), d.get('brew_id'), d.get('recipe_id'),
             d.get('brew_date'), d.get('bottling_date'))
        )
        row = conn.execute('SELECT * FROM beers WHERE id=?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@app.route('/api/beers/<int:beer_id>', methods=['PUT'])
def update_beer(beer_id):
    d = request.json or {}
    with get_db() as conn:
        # Preserve existing initial values if not provided by client
        existing = conn.execute('SELECT initial_33cl, initial_75cl, keg_initial_liters FROM beers WHERE id=?', (beer_id,)).fetchone()
        if not existing:
            return jsonify({'error': 'Not found'}), 404
        init33 = d['initial_33cl'] if 'initial_33cl' in d else existing['initial_33cl']
        init75 = d['initial_75cl'] if 'initial_75cl' in d else existing['initial_75cl']
        keg_init = d['keg_initial_liters'] if 'keg_initial_liters' in d else existing['keg_initial_liters']
        conn.execute(
            '''UPDATE beers SET name=?,type=?,abv=?,stock_33cl=?,stock_75cl=?,
               initial_33cl=?,initial_75cl=?,keg_liters=?,keg_initial_liters=?,origin=?,description=?,photo=?,
               brew_date=?,bottling_date=? WHERE id=?''',
            (d.get('name'), d.get('type'), d.get('abv'), d.get('stock_33cl', 0),
             d.get('stock_75cl', 0), init33, init75,
             d.get('keg_liters'), keg_init,
             d.get('origin'), d.get('description'),
             d.get('photo'), d.get('brew_date'), d.get('bottling_date'), beer_id)
        )
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        return jsonify(dict(row))


@app.route('/api/beers/<int:beer_id>/tasting', methods=['PUT'])
def update_beer_tasting(beer_id):
    d = request.json
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE beers SET
               taste_appearance=?, taste_aroma=?, taste_flavor=?,
               taste_bitterness=?, taste_mouthfeel=?, taste_overall=?,
               taste_rating=?, taste_date=?
               WHERE id=?''',
            (d.get('taste_appearance'), d.get('taste_aroma'), d.get('taste_flavor'),
             d.get('taste_bitterness'), d.get('taste_mouthfeel'), d.get('taste_overall'),
             d.get('taste_rating'), d.get('taste_date'), beer_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        return jsonify(dict(row))


@app.route('/api/beers/<int:beer_id>', methods=['DELETE'])
def delete_beer(beer_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM beers WHERE id=?', (beer_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True})


@app.route('/api/beers/<int:beer_id>/stock', methods=['PATCH'])
def patch_beer_stock(beer_id):
    d = request.json
    with get_db() as conn:
        if 'stock_33cl' in d:
            conn.execute('UPDATE beers SET stock_33cl=? WHERE id=?', (d['stock_33cl'], beer_id))
        if 'stock_75cl' in d:
            conn.execute('UPDATE beers SET stock_75cl=? WHERE id=?', (d['stock_75cl'], beer_id))
        if 'keg_liters' in d:
            conn.execute('UPDATE beers SET keg_liters=? WHERE id=?', (d['keg_liters'], beer_id))
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(row))


@app.route('/api/beers/<int:beer_id>', methods=['PATCH'])
def patch_beer(beer_id):
    d = request.json
    with get_db() as conn:
        cur = conn.execute('UPDATE beers SET archived=? WHERE id=?',
                           (1 if d.get('archived') else 0, beer_id))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute('SELECT * FROM beers WHERE id=?', (beer_id,)).fetchone()
        return jsonify(dict(row))


# ── SODA KEGS ─────────────────────────────────────────────────────────────────

_SODA_KEGS_SELECT = '''
    SELECT k.*,
           b.name AS beer_name,
           br.name AS brew_name
    FROM soda_kegs k
    LEFT JOIN beers b ON k.beer_id = b.id
    LEFT JOIN brews br ON k.brew_id = br.id
'''

@app.route('/api/soda-kegs', methods=['GET'])
def get_soda_kegs():
    with get_db() as conn:
        rows = conn.execute(
            _SODA_KEGS_SELECT +
            ' ORDER BY COALESCE(k.sort_order, 9999) ASC, k.created_at DESC'
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/soda-kegs/reorder', methods=['PUT'])
def reorder_soda_kegs():
    items = request.json or []
    with get_db() as conn:
        for item in items:
            if item.get('id') is None or item.get('sort_order') is None:
                continue
            conn.execute('UPDATE soda_kegs SET sort_order=? WHERE id=?',
                         (item['sort_order'], item['id']))
    return jsonify({'success': True})


@app.route('/api/soda-kegs', methods=['POST'])
def create_soda_keg():
    d = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO soda_kegs
               (name, keg_type, manufacturer, volume_total, volume_ferment, weight_empty,
                status, current_liters, beer_id, brew_id, notes, color, photo,
                last_revision_date, revision_interval_months, next_revision_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('name'), d.get('keg_type'), d.get('manufacturer'),
             d.get('volume_total'), d.get('volume_ferment'), d.get('weight_empty'),
             d.get('status', 'empty'), d.get('current_liters'),
             d.get('beer_id'), d.get('brew_id'),
             d.get('notes'), d.get('color', '#f59e0b'), d.get('photo'),
             d.get('last_revision_date') or None,
             d.get('revision_interval_months') or 12,
             d.get('next_revision_date') or None)
        )
        row = conn.execute(
            _SODA_KEGS_SELECT + ' WHERE k.id=?', (cur.lastrowid,)
        ).fetchone()
        return jsonify(dict(row)), 201


@app.route('/api/soda-kegs/<int:keg_id>', methods=['PUT'])
def update_soda_keg(keg_id):
    d = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE soda_kegs SET
               name=?, keg_type=?, manufacturer=?, volume_total=?, volume_ferment=?,
               weight_empty=?, status=?, current_liters=?, beer_id=?,
               brew_id=?, notes=?, color=?, photo=?,
               last_revision_date=?, revision_interval_months=?, next_revision_date=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (d.get('name'), d.get('keg_type'), d.get('manufacturer'),
             d.get('volume_total'), d.get('volume_ferment'), d.get('weight_empty'),
             d.get('status', 'empty'), d.get('current_liters'),
             d.get('beer_id'), d.get('brew_id'),
             d.get('notes'), d.get('color', '#f59e0b'), d.get('photo'),
             d.get('last_revision_date') or None,
             d.get('revision_interval_months') or 12,
             d.get('next_revision_date') or None,
             keg_id)
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute(
            _SODA_KEGS_SELECT + ' WHERE k.id=?', (keg_id,)
        ).fetchone()
        return jsonify(dict(row))


@app.route('/api/soda-kegs/<int:keg_id>', methods=['DELETE'])
def delete_soda_keg(keg_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM soda_kegs WHERE id=?', (keg_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'success': True})


# ── SPINDLES ─────────────────────────────────────────────────────────────────

# Champs autorisés pour PATCH /api/spindles/<id>
_SPINDLE_PATCH_FIELDS: frozenset[str] = frozenset({'name', 'brew_id', 'notes', 'device_type'})

# Requête single-row : correlated subqueries (utilisée après POST/PATCH, 1 seule ligne)
_SPINDLE_SELECT = '''
    SELECT s.*,
           b.name as brew_name,
           (SELECT gravity     FROM rdb.spindle_readings WHERE spindle_id=s.id ORDER BY recorded_at DESC LIMIT 1) as last_gravity,
           (SELECT temperature FROM rdb.spindle_readings WHERE spindle_id=s.id ORDER BY recorded_at DESC LIMIT 1) as last_temperature,
           (SELECT battery     FROM rdb.spindle_readings WHERE spindle_id=s.id ORDER BY recorded_at DESC LIMIT 1) as last_battery,
           (SELECT recorded_at FROM rdb.spindle_readings WHERE spindle_id=s.id ORDER BY recorded_at DESC LIMIT 1) as last_reading_at,
           (SELECT COUNT(*)    FROM rdb.spindle_readings WHERE spindle_id=s.id) as reading_count
    FROM spindles s LEFT JOIN brews b ON s.brew_id=b.id
'''

# Requête list : CTE + window function — une seule passe sur spindle_readings
_SPINDLE_SELECT_LIST = '''
    WITH lr AS (
        SELECT spindle_id, gravity, temperature, battery, recorded_at,
               ROW_NUMBER() OVER (PARTITION BY spindle_id ORDER BY recorded_at DESC) AS rn
        FROM rdb.spindle_readings
    ),
    rc AS (
        SELECT spindle_id, COUNT(*) AS reading_count
        FROM rdb.spindle_readings
        GROUP BY spindle_id
    )
    SELECT s.*,
           b.name AS brew_name,
           lr.gravity        AS last_gravity,
           lr.temperature    AS last_temperature,
           lr.battery        AS last_battery,
           lr.recorded_at    AS last_reading_at,
           COALESCE(rc.reading_count, 0) AS reading_count
    FROM spindles s
    LEFT JOIN brews b ON s.brew_id = b.id
    LEFT JOIN lr ON lr.spindle_id = s.id AND lr.rn = 1
    LEFT JOIN rc ON rc.spindle_id = s.id
'''


@app.route('/api/spindles', methods=['GET'])
def get_spindles():
    with get_db() as conn:
        rows = conn.execute(_SPINDLE_SELECT_LIST + ' ORDER BY COALESCE(s.sort_order, 9999) ASC, s.created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/spindles', methods=['POST'])
def create_spindle():
    d = request.json or {}
    token = secrets.token_urlsafe(16)
    device_type = d.get('device_type', 'ispindel')
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO spindles (name,token,brew_id,notes,device_type) VALUES (?,?,?,?,?)',
            (d.get('name'), token, d.get('brew_id'), d.get('notes'), device_type)
        )
        row = conn.execute(_SPINDLE_SELECT + ' WHERE s.id=?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@app.route('/api/spindles/<int:spindle_id>', methods=['PATCH'])
def patch_spindle(spindle_id):
    d = request.json or {}
    # Seuls les champs de la whitelist peuvent mettre à jour la base
    updates = {col: d[col] for col in _SPINDLE_PATCH_FIELDS if col in d}
    with get_db() as conn:
        if updates:
            sql = 'UPDATE spindles SET ' + ', '.join(f'{col}=?' for col in updates) + ' WHERE id=?'
            conn.execute(sql, [*updates.values(), spindle_id])
        row = conn.execute(_SPINDLE_SELECT + ' WHERE s.id=?', (spindle_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(row))


@app.route('/api/spindles/<int:spindle_id>', methods=['DELETE'])
def delete_spindle(spindle_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM spindles WHERE id=?', (spindle_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
    with get_readings_db() as rconn:
        rconn.execute('DELETE FROM spindle_readings WHERE spindle_id=?', (spindle_id,))
    return jsonify({'success': True})


@app.route('/api/spindles/reorder', methods=['PUT'])
def reorder_spindles():
    items = request.json or []
    with get_db() as conn:
        for item in items:
            if item.get('id') is None or item.get('sort_order') is None:
                continue
            conn.execute('UPDATE spindles SET sort_order=? WHERE id=?',
                         (item['sort_order'], item['id']))
    return jsonify({'success': True})


@app.route('/api/spindles/<int:spindle_id>/readings', methods=['GET'])
def get_spindle_readings(spindle_id):
    limit   = request.args.get('limit', 2000, type=int)
    hours   = request.args.get('hours',  type=int)
    from_ts = request.args.get('from')
    to_ts   = request.args.get('to')
    with get_readings_db() as conn:
        if hours:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM spindle_readings WHERE spindle_id=? AND recorded_at >= datetime('now',?) ORDER BY recorded_at DESC LIMIT ?) ORDER BY recorded_at ASC",
                (spindle_id, f'-{hours} hours', limit)
            ).fetchall()
        elif from_ts and to_ts:
            rows = conn.execute(
                'SELECT * FROM (SELECT * FROM spindle_readings WHERE spindle_id=? AND recorded_at >= ? AND recorded_at <= ? ORDER BY recorded_at DESC LIMIT ?) ORDER BY recorded_at ASC',
                (spindle_id, from_ts, to_ts, limit)
            ).fetchall()
        elif from_ts:
            rows = conn.execute(
                'SELECT * FROM (SELECT * FROM spindle_readings WHERE spindle_id=? AND recorded_at >= ? ORDER BY recorded_at DESC LIMIT ?) ORDER BY recorded_at ASC',
                (spindle_id, from_ts, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM (SELECT * FROM spindle_readings WHERE spindle_id=? ORDER BY recorded_at DESC LIMIT ?) ORDER BY recorded_at ASC',
                (spindle_id, limit)
            ).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/spindle/data', methods=['POST', 'GET'])
def receive_spindle_data():
    """Endpoint universel densimètres — POST ou GET /api/spindle/data?token=TOKEN.

    Appareils supportés : iSpindel, Tilt (TiltBridge), GravityMon, générique.
    Le token peut être passé en query param (?token=) ou dans le corps JSON.
    """
    d = request.json or {}
    # Token : query param > corps JSON
    token = request.args.get('token') or d.get('token') or d.get('Token') or ''
    if not token:
        return jsonify({'error': 'token manquant'}), 401
    if not _sensor_rate_limit(f's:{token}'):
        return jsonify({'error': 'trop de requêtes'}), 429

    with get_db() as conn:
        spindle = conn.execute(
            'SELECT id, brew_id, device_type FROM spindles WHERE token=?', (token,)
        ).fetchone()
        if not spindle:
            return jsonify({'error': 'token invalide'}), 401
        sid        = spindle['id']
        brew_id    = spindle['brew_id']
        device_type = spindle['device_type'] or 'ispindel'

    def _f(v):
        try: return float(v) if v is not None else None
        except (ValueError, TypeError): return None

    # ── Gravité ───────────────────────────────────────────────────────────────
    gravity = _f(d.get('gravity') or d.get('Gravity') or d.get('SG') or
                 d.get('specific_gravity') or d.get('og'))

    # ── Température ───────────────────────────────────────────────────────────
    # Le Tilt (via TiltBridge) envoie la température en Fahrenheit dans "Temp"
    if device_type == 'tilt':
        temp_raw = _f(d.get('Temp') or d.get('temp'))
        temp_c = round((temp_raw - 32) * 5 / 9, 2) if temp_raw is not None else None
    else:
        temp_c = _f(d.get('temperature') or d.get('Temperature') or
                    d.get('temp') or d.get('celsius'))
        if temp_c is None:
            # Fahrenheit explicite (champ temp_f)
            temp_f = _f(d.get('temp_f') or d.get('Fahrenheit') or d.get('fahrenheit'))
            if temp_f is not None:
                temp_c = round((temp_f - 32) * 5 / 9, 2)

    # ── Batterie ──────────────────────────────────────────────────────────────
    battery = _f(d.get('battery') or d.get('Battery') or
                 d.get('battery_level') or d.get('voltage') or d.get('Voltage'))

    # ── Angle ─────────────────────────────────────────────────────────────────
    angle = _f(d.get('angle') or d.get('Angle') or d.get('tilt'))

    # ── RSSI ──────────────────────────────────────────────────────────────────
    rssi_raw = d.get('RSSI') or d.get('rssi') or d.get('signal') or d.get('Signal')
    try: rssi = int(rssi_raw)
    except (ValueError, TypeError): rssi = None

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_readings_db() as rconn:
        if not brew_id:
            # Non lié à un brassin : conserver uniquement la dernière mesure
            rconn.execute('DELETE FROM spindle_readings WHERE spindle_id=?', (sid,))
        rconn.execute(
            'INSERT INTO spindle_readings (spindle_id,gravity,temperature,battery,angle,rssi,recorded_at) VALUES (?,?,?,?,?,?,?)',
            (sid, gravity, temp_c, battery, angle, rssi, now)
        )
    return jsonify({'ok': True}), 201


@app.route('/api/spindle/readings/stats')
def spindle_readings_stats():
    with get_readings_db() as conn:
        total  = conn.execute('SELECT COUNT(*) FROM spindle_readings').fetchone()[0]
        oldest = conn.execute('SELECT MIN(recorded_at) FROM spindle_readings').fetchone()[0]
        newest = conn.execute('SELECT MAX(recorded_at) FROM spindle_readings').fetchone()[0]
    size = os.path.getsize(READINGS_DB_PATH) if os.path.exists(READINGS_DB_PATH) else 0
    return jsonify({'total': total, 'oldest': oldest, 'newest': newest, 'db_size': size})


@app.route('/api/spindle/readings/purge', methods=['DELETE'])
def purge_spindle_readings():
    days = request.args.get('days', 30, type=int)
    with get_readings_db() as conn:
        cur = conn.execute(
            "DELETE FROM spindle_readings WHERE recorded_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        deleted = cur.rowcount
        remaining = conn.execute('SELECT COUNT(*) FROM spindle_readings').fetchone()[0]
    # VACUUM doit s'exécuter hors transaction (isolation_level=None = autocommit)
    vac = sqlite3.connect(READINGS_DB_PATH)
    try:
        vac.isolation_level = None
        vac.execute('VACUUM')
    finally:
        vac.close()
    return jsonify({'deleted': deleted, 'remaining': remaining})


# ── SONDES DE TEMPÉRATURE ──────────────────────────────────────

# Champs autorisés pour PATCH /api/temperature/<id>
_TEMP_PATCH_FIELDS: frozenset[str] = frozenset({'name', 'notes', 'temp_min', 'temp_max', 'sensor_type', 'ha_entity', 'ha_entity_hum', 'brew_id'})

# Requête single-row : correlated subqueries (utilisée après POST/PATCH, 1 seule ligne)
_TEMP_SELECT = '''
    SELECT ts.*,
           b.name as brew_name,
           (SELECT temperature FROM rdb.temperature_readings WHERE sensor_id=ts.id ORDER BY recorded_at DESC LIMIT 1) as last_temperature,
           (SELECT humidity    FROM rdb.temperature_readings WHERE sensor_id=ts.id ORDER BY recorded_at DESC LIMIT 1) as last_humidity,
           (SELECT target_temp FROM rdb.temperature_readings WHERE sensor_id=ts.id ORDER BY recorded_at DESC LIMIT 1) as last_target_temp,
           (SELECT hvac_mode   FROM rdb.temperature_readings WHERE sensor_id=ts.id ORDER BY recorded_at DESC LIMIT 1) as last_hvac_mode,
           (SELECT recorded_at FROM rdb.temperature_readings WHERE sensor_id=ts.id ORDER BY recorded_at DESC LIMIT 1) as last_reading_at,
           (SELECT COUNT(*)    FROM rdb.temperature_readings WHERE sensor_id=ts.id) as reading_count
    FROM temperature_sensors ts LEFT JOIN brews b ON ts.brew_id=b.id
'''

# Requête list : CTE + window function — une seule passe sur temperature_readings
_TEMP_SELECT_LIST = '''
    WITH lr AS (
        SELECT sensor_id, temperature, humidity, target_temp, hvac_mode, recorded_at,
               ROW_NUMBER() OVER (PARTITION BY sensor_id ORDER BY recorded_at DESC) AS rn
        FROM rdb.temperature_readings
    ),
    rc AS (
        SELECT sensor_id, COUNT(*) AS reading_count
        FROM rdb.temperature_readings
        GROUP BY sensor_id
    )
    SELECT ts.*,
           b.name AS brew_name,
           lr.temperature  AS last_temperature,
           lr.humidity     AS last_humidity,
           lr.target_temp  AS last_target_temp,
           lr.hvac_mode    AS last_hvac_mode,
           lr.recorded_at  AS last_reading_at,
           COALESCE(rc.reading_count, 0) AS reading_count
    FROM temperature_sensors ts
    LEFT JOIN brews b ON ts.brew_id = b.id
    LEFT JOIN lr ON lr.sensor_id = ts.id AND lr.rn = 1
    LEFT JOIN rc ON rc.sensor_id = ts.id
'''


@app.route('/api/temperature', methods=['GET'])
def get_temp_sensors():
    with get_db() as conn:
        rows = conn.execute(_TEMP_SELECT_LIST + ' ORDER BY COALESCE(ts.sort_order,9999) ASC, ts.created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/temperature', methods=['POST'])
def create_temp_sensor():
    d = request.json or {}
    token = secrets.token_urlsafe(16)
    sensor_type = d.get('sensor_type', 'sensor')
    if sensor_type not in ('sensor', 'thermostat'):
        sensor_type = 'sensor'
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO temperature_sensors (name,token,notes,temp_min,temp_max,sensor_type,ha_entity,ha_entity_hum) VALUES (?,?,?,?,?,?,?,?)',
            (d.get('name'), token, d.get('notes'), d.get('temp_min'), d.get('temp_max'), sensor_type,
             d.get('ha_entity') or None, d.get('ha_entity_hum') or None)
        )
        row = conn.execute(_TEMP_SELECT + ' WHERE ts.id=?', (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201


@app.route('/api/temperature/<int:sensor_id>', methods=['PATCH'])
def patch_temp_sensor(sensor_id):
    d = request.json or {}
    # Seuls les champs de la whitelist peuvent mettre à jour la base
    updates = {col: d[col] for col in _TEMP_PATCH_FIELDS if col in d}
    with get_db() as conn:
        if updates:
            sql = 'UPDATE temperature_sensors SET ' + ', '.join(f'{col}=?' for col in updates) + ' WHERE id=?'
            conn.execute(sql, [*updates.values(), sensor_id])
        row = conn.execute(_TEMP_SELECT + ' WHERE ts.id=?', (sensor_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(row))


@app.route('/api/temperature/<int:sensor_id>', methods=['DELETE'])
def delete_temp_sensor(sensor_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM temperature_sensors WHERE id=?', (sensor_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
    with get_readings_db() as rconn:
        rconn.execute('DELETE FROM temperature_readings WHERE sensor_id=?', (sensor_id,))
    return jsonify({'success': True})


@app.route('/api/temperature/reorder', methods=['PUT'])
def reorder_temp_sensors():
    items = request.json or []
    with get_db() as conn:
        for item in items:
            if item.get('id') is None or item.get('sort_order') is None:
                continue
            conn.execute('UPDATE temperature_sensors SET sort_order=? WHERE id=?',
                         (item['sort_order'], item['id']))
    return jsonify({'success': True})


@app.route('/api/temperature/data', methods=['POST', 'GET'])
def receive_temp_data():
    """Endpoint Home Assistant : POST /api/temperature/data?token=TOKEN
    Corps JSON : {"temperature": 18.5, "humidity": 65.0}
    Le token peut aussi être passé dans le corps JSON.
    """
    d = request.json or {}
    token = request.args.get('token') or d.get('token') or d.get('Token') or ''
    if not token:
        return jsonify({'error': 'token manquant'}), 401
    if not _sensor_rate_limit(f't:{token}'):
        return jsonify({'error': 'trop de requêtes'}), 429

    with get_db() as conn:
        sensor = conn.execute('SELECT id FROM temperature_sensors WHERE token=?', (token,)).fetchone()
        if not sensor:
            return jsonify({'error': 'token invalide'}), 401
        sid = sensor['id']

    def _f(v):
        try: return float(v) if v is not None else None
        except (ValueError, TypeError): return None

    temperature = _f(d.get('temperature') or d.get('Temperature') or
                     d.get('temp') or d.get('value'))
    # Conversion Fahrenheit si nécessaire
    if temperature is None:
        temp_f = _f(d.get('temp_f') or d.get('fahrenheit') or d.get('Fahrenheit'))
        if temp_f is not None:
            temperature = round((temp_f - 32) * 5 / 9, 2)
    humidity    = _f(d.get('humidity') or d.get('Humidity') or d.get('hum'))
    target_temp = _f(d.get('target_temp') or d.get('target_temperature') or d.get('setpoint'))
    hvac_mode   = d.get('hvac_mode') or d.get('mode') or None
    if hvac_mode:
        hvac_mode = str(hvac_mode)[:32]

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_readings_db() as rconn:
        rconn.execute(
            'INSERT INTO temperature_readings (sensor_id,temperature,humidity,target_temp,hvac_mode,recorded_at) VALUES (?,?,?,?,?,?)',
            (sid, temperature, humidity, target_temp, hvac_mode, now)
        )
    return jsonify({'ok': True}), 201


@app.route('/api/temperature/<int:sensor_id>/readings', methods=['GET'])
def get_temp_readings(sensor_id):
    limit   = request.args.get('limit', 2000, type=int)
    hours   = request.args.get('hours', type=int)
    from_ts = request.args.get('from')
    to_ts   = request.args.get('to')
    with get_readings_db() as conn:
        if hours:
            rows = conn.execute(
                "SELECT * FROM temperature_readings WHERE sensor_id=? AND recorded_at >= datetime('now',?) ORDER BY recorded_at ASC LIMIT ?",
                (sensor_id, f'-{hours} hours', limit)
            ).fetchall()
        elif from_ts and to_ts:
            rows = conn.execute(
                'SELECT * FROM temperature_readings WHERE sensor_id=? AND recorded_at BETWEEN ? AND ? ORDER BY recorded_at ASC LIMIT ?',
                (sensor_id, from_ts, to_ts, limit)
            ).fetchall()
        elif from_ts:
            rows = conn.execute(
                'SELECT * FROM temperature_readings WHERE sensor_id=? AND recorded_at >= ? ORDER BY recorded_at ASC LIMIT ?',
                (sensor_id, from_ts, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM temperature_readings WHERE sensor_id=? ORDER BY recorded_at ASC LIMIT ?',
                (sensor_id, limit)
            ).fetchall()
        return jsonify([dict(r) for r in rows])


@app.route('/api/temperature/readings/stats')
def temp_readings_stats():
    with get_readings_db() as conn:
        total  = conn.execute('SELECT COUNT(*) FROM temperature_readings').fetchone()[0]
        oldest = conn.execute('SELECT MIN(recorded_at) FROM temperature_readings').fetchone()[0]
        newest = conn.execute('SELECT MAX(recorded_at) FROM temperature_readings').fetchone()[0]
    size = os.path.getsize(READINGS_DB_PATH) if os.path.exists(READINGS_DB_PATH) else 0
    return jsonify({'total': total, 'oldest': oldest, 'newest': newest, 'db_size': size})


@app.route('/api/temperature/readings/purge', methods=['DELETE'])
def purge_temp_readings():
    days = request.args.get('days', 30, type=int)
    with get_readings_db() as conn:
        cur = conn.execute(
            "DELETE FROM temperature_readings WHERE recorded_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        deleted  = cur.rowcount
        remaining = conn.execute('SELECT COUNT(*) FROM temperature_readings').fetchone()[0]
    return jsonify({'deleted': deleted, 'remaining': remaining})


# ── IMPORT / EXPORT ────────────────────────────────────────────

@app.route('/api/catalog/import-hopsteiner', methods=['POST'])
def import_hopsteiner():
    """Importe les houblons depuis la base Hopsteiner (GitHub kasperg3/HopDatabase)."""
    url = 'https://raw.githubusercontent.com/kasperg3/HopDatabase/refs/heads/main/hop_database/data/hopsteiner_raw_data.json'
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return jsonify({'error': str(e)}), 502

    # Le JSON est { "hops": [...] }
    hops = data.get('hops', data) if isinstance(data, dict) else data

    def _avg_alpha(low, high):
        try:
            vals = [float(v) for v in [low, high] if v is not None]
            return round(sum(vals) / len(vals), 1) if vals else None
        except (ValueError, TypeError):
            return None

    imported = updated = 0
    with get_db() as conn:
        for h in hops:
            if not isinstance(h, dict):
                continue
            name = (h.get('name') or '').strip()
            if not name:
                continue
            alpha     = _avg_alpha(h.get('acid_alpha_low'), h.get('acid_alpha_high'))
            aroma     = (h.get('aroma_spec') or '').strip() or None
            existing  = conn.execute(
                'SELECT id, alpha FROM ingredient_catalog WHERE name=? AND category=?',
                (name, 'houblon')
            ).fetchone()
            if existing:
                # Toujours mettre à jour aroma_spec ; alpha seulement si absent
                conn.execute(
                    'UPDATE ingredient_catalog SET aroma_spec=?, alpha=COALESCE(alpha,?) WHERE id=?',
                    (aroma, alpha, existing['id'])
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO ingredient_catalog (name,category,alpha,aroma_spec,default_unit) VALUES (?,?,?,?,'g')",
                    (name, 'houblon', alpha, aroma)
                )
                imported += 1
    return jsonify({'imported': imported, 'updated': updated})


@app.route('/api/export/catalog')
def export_catalog():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM ingredient_catalog ORDER BY category, subcategory, name').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/import/catalog', methods=['POST'])
def import_catalog():
    items = request.json or []
    imported = 0
    with get_db() as conn:
        for d in items:
            if not d.get('name') or not d.get('category'):
                continue
            existing = conn.execute(
                'SELECT id FROM ingredient_catalog WHERE name=? AND category=?',
                (d['name'], d['category'])
            ).fetchone()
            if existing:
                conn.execute(
                    '''UPDATE ingredient_catalog
                       SET subcategory=?, ebc=?, gu=?, alpha=?, yeast_type=?, default_unit=?,
                           temp_min=?, temp_max=?, dosage_per_liter=?,
                           attenuation_min=?, attenuation_max=?, alcohol_tolerance=?, max_usage_pct=?
                       WHERE id=?''',
                    (d.get('subcategory'), d.get('ebc'), d.get('gu'), d.get('alpha'),
                     d.get('yeast_type'), d.get('default_unit', 'g'),
                     d.get('temp_min'), d.get('temp_max'), d.get('dosage_per_liter'),
                     d.get('attenuation_min'), d.get('attenuation_max'), d.get('alcohol_tolerance'),
                     d.get('max_usage_pct'), existing['id'])
                )
            else:
                conn.execute(
                    '''INSERT INTO ingredient_catalog
                       (name,category,subcategory,ebc,gu,alpha,yeast_type,default_unit,
                        temp_min,temp_max,dosage_per_liter,attenuation_min,attenuation_max,alcohol_tolerance,max_usage_pct)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (d['name'], d['category'], d.get('subcategory'), d.get('ebc'), d.get('gu'),
                     d.get('alpha'), d.get('yeast_type'), d.get('default_unit', 'g'),
                     d.get('temp_min'), d.get('temp_max'), d.get('dosage_per_liter'),
                     d.get('attenuation_min'), d.get('attenuation_max'), d.get('alcohol_tolerance'),
                     d.get('max_usage_pct'))
                )
            imported += 1
    return jsonify({'imported': imported})


@app.route('/api/export/inventory')
def export_inventory():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM inventory_items ORDER BY category, name').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/import/inventory', methods=['POST'])
def import_inventory():
    items = request.json or []
    imported = 0
    with get_db() as conn:
        for item in items:
            if not item.get('name') or not item.get('category'):
                continue
            try:
                conn.execute(
                    'INSERT INTO inventory_items (name,category,quantity,unit,origin,ebc,alpha,notes) VALUES (?,?,?,?,?,?,?,?)',
                    (item['name'], item['category'], item.get('quantity', 0), item.get('unit', 'g'),
                     item.get('origin'), item.get('ebc'), item.get('alpha'), item.get('notes'))
                )
                imported += 1
            except Exception as e:
                app.logger.warning(f"import_inventory: skipped item {item.get('name')!r}: {e}")
    return jsonify({'imported': imported})


@app.route('/api/export/recipes')
def export_recipes():
    with get_db() as conn:
        recipes = conn.execute('SELECT * FROM recipes ORDER BY id').fetchall()
        ings_rows = conn.execute(
            'SELECT * FROM recipe_ingredients ORDER BY recipe_id, id'
        ).fetchall()
    ings_by_recipe: dict = {}
    for i in ings_rows:
        ings_by_recipe.setdefault(i['recipe_id'], []).append(dict(i))
    result = []
    for r in recipes:
        recipe = dict(r)
        recipe['ingredients'] = ings_by_recipe.get(r['id'], [])
        result.append(recipe)
    return jsonify(result)


@app.route('/api/export/brews')
def export_brews():
    with get_db() as conn:
        brews = conn.execute(
            '''SELECT b.*, r.name as recipe_name
               FROM brews b LEFT JOIN recipes r ON b.recipe_id=r.id
               ORDER BY b.created_at DESC'''
        ).fetchall()
        # Charger toutes les lectures de fermentation en une seule requête
        ferm_rows = conn.execute(
            'SELECT * FROM brew_fermentation_readings ORDER BY brew_id, recorded_at'
        ).fetchall()
    ferm_by_brew: dict = {}
    for f in ferm_rows:
        ferm_by_brew.setdefault(f['brew_id'], []).append(dict(f))
    result = []
    for b in brews:
        brew = dict(b)
        brew['fermentation'] = ferm_by_brew.get(b['id'], [])
        result.append(brew)
    return jsonify(result)


@app.route('/api/export/beers')
def export_beers():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM beers ORDER BY id').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/export/spindles')
def export_spindles():
    with get_db() as conn:
        spindles = conn.execute(_SPINDLE_SELECT_LIST + ' ORDER BY COALESCE(s.sort_order, 9999) ASC, s.created_at DESC').fetchall()
    # Charger toutes les lectures en une seule requête hors de la connexion principale
    with get_readings_db() as rconn:
        all_readings = rconn.execute(
            'SELECT * FROM spindle_readings ORDER BY spindle_id, recorded_at'
        ).fetchall()
    readings_by_spindle: dict = {}
    for r in all_readings:
        readings_by_spindle.setdefault(r['spindle_id'], []).append(dict(r))
    result = []
    for s in spindles:
        sp = dict(s)
        sp['readings'] = readings_by_spindle.get(s['id'], [])
        result.append(sp)
    return jsonify(result)


@app.route('/api/import/beers', methods=['POST'])
def import_beers():
    data = request.json or []
    if isinstance(data, dict):
        data = [data]
    imported = 0
    with get_db() as conn:
        for beer in data:
            if not beer.get('name'):
                continue
            try:
                conn.execute(
                    '''INSERT INTO beers
                       (name, type, abv, stock_33cl, stock_75cl, origin, description, photo,
                        archived, initial_33cl, initial_75cl, brew_date, bottling_date)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (beer['name'], beer.get('type'), beer.get('abv'),
                     beer.get('stock_33cl', 0), beer.get('stock_75cl', 0),
                     beer.get('origin'), beer.get('description'), beer.get('photo'),
                     beer.get('archived', 0),
                     beer.get('initial_33cl') or beer.get('stock_33cl', 0),
                     beer.get('initial_75cl') or beer.get('stock_75cl', 0),
                     beer.get('brew_date'), beer.get('bottling_date'))
                )
                imported += 1
            except Exception as e:
                app.logger.warning(f"import_beers: skipped beer {beer.get('name')!r}: {e}")
    return jsonify({'imported': imported})


@app.route('/api/import/brews', methods=['POST'])
def import_brews():
    data = request.json or []
    if isinstance(data, dict):
        data = [data]
    imported = 0
    with get_db() as conn:
        for brew in data:
            if not brew.get('name'):
                continue
            try:
                # Résoudre la recette liée : d'abord par nom, puis par id
                recipe_id = None
                if brew.get('recipe_name'):
                    row = conn.execute('SELECT id FROM recipes WHERE name=?', (brew['recipe_name'],)).fetchone()
                    if row:
                        recipe_id = row['id']
                if not recipe_id and brew.get('recipe_id'):
                    row = conn.execute('SELECT id FROM recipes WHERE id=?', (brew['recipe_id'],)).fetchone()
                    if row:
                        recipe_id = row['id']
                if not recipe_id:
                    # Créer une recette fantôme pour satisfaire la FK
                    cur = conn.execute(
                        'INSERT INTO recipes (name, volume, brewhouse_efficiency) VALUES (?,?,?)',
                        (brew.get('recipe_name') or brew['name'], brew.get('volume_brewed') or 20, 72)
                    )
                    recipe_id = cur.lastrowid

                cur = conn.execute(
                    '''INSERT INTO brews
                       (recipe_id, name, brew_date, volume_brewed, og, fg, abv, notes, status, archived)
                       VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (recipe_id, brew['name'], brew.get('brew_date'),
                     brew.get('volume_brewed'), brew.get('og'), brew.get('fg'), brew.get('abv'),
                     brew.get('notes'), brew.get('status', 'completed'), brew.get('archived', 0))
                )
                new_brew_id = cur.lastrowid

                for reading in brew.get('fermentation', []):
                    conn.execute(
                        '''INSERT INTO brew_fermentation_readings
                           (brew_id, recorded_at, gravity, temperature, battery, angle)
                           VALUES (?,?,?,?,?,?)''',
                        (new_brew_id, reading.get('recorded_at'), reading.get('gravity'),
                         reading.get('temperature'), reading.get('battery'), reading.get('angle'))
                    )
                imported += 1
            except Exception as e:
                app.logger.warning(f"import_brews: skipped brew {brew.get('name')!r}: {e}")
    return jsonify({'imported': imported})


@app.route('/api/import/spindles', methods=['POST'])
def import_spindles():
    data = request.json or []
    if isinstance(data, dict):
        data = [data]
    imported = 0
    with get_db() as conn:
        for spindle in data:
            if not spindle.get('name'):
                continue
            try:
                token = secrets.token_urlsafe(16)
                cur = conn.execute(
                    'INSERT INTO spindles (name, token, notes) VALUES (?,?,?)',
                    (spindle['name'], token, spindle.get('notes'))
                )
                new_spindle_id = cur.lastrowid
                with get_readings_db() as rconn:
                    for reading in spindle.get('readings', []):
                        rconn.execute(
                            '''INSERT INTO spindle_readings
                               (spindle_id, gravity, temperature, battery, angle, rssi, recorded_at)
                               VALUES (?,?,?,?,?,?,?)''',
                            (new_spindle_id, reading.get('gravity'), reading.get('temperature'),
                             reading.get('battery'), reading.get('angle'), reading.get('rssi'),
                             reading.get('recorded_at'))
                        )
                imported += 1
            except Exception as e:
                app.logger.warning(f"import_spindles: skipped spindle {spindle.get('name')!r}: {e}")
    return jsonify({'imported': imported})


@app.route('/api/import/recipes', methods=['POST'])
def import_recipes():
    data = request.json or []
    if isinstance(data, dict):
        data = [data]
    imported = 0
    with get_db() as conn:
        for recipe in data:
            if not recipe.get('name'):
                continue
            try:
                cur = conn.execute(
                    '''INSERT INTO recipes
                       (name,style,volume,brew_date,mash_temp,mash_time,boil_time,
                        mash_ratio,evap_rate,grain_absorption,brewhouse_efficiency,
                        ferm_temp,ferm_time,notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (recipe['name'], recipe.get('style'), recipe.get('volume', 20),
                     recipe.get('brew_date'), recipe.get('mash_temp', 66), recipe.get('mash_time', 60),
                     recipe.get('boil_time', 60), recipe.get('mash_ratio', 3.0),
                     recipe.get('evap_rate', 3.0), recipe.get('grain_absorption', 0.8),
                     recipe.get('brewhouse_efficiency', 72), recipe.get('ferm_temp'),
                     recipe.get('ferm_time'), recipe.get('notes'))
                )
                rid = cur.lastrowid
                for ing in recipe.get('ingredients', []):
                    conn.execute(
                        '''INSERT INTO recipe_ingredients
                           (recipe_id,name,category,quantity,unit,hop_time,hop_type,
                            hop_days,other_type,other_time,ebc,alpha,notes)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (rid, ing.get('name','?'), ing.get('category','autre'),
                         ing.get('quantity', 0), ing.get('unit', 'g'),
                         ing.get('hop_time'), ing.get('hop_type'), ing.get('hop_days'),
                         ing.get('other_type'), ing.get('other_time'),
                         ing.get('ebc'), ing.get('alpha'), ing.get('notes'))
                    )
                imported += 1
            except Exception as e:
                app.logger.warning(f"import_recipes: skipped recipe {recipe.get('name')!r}: {e}")
    return jsonify({'imported': imported})


def _seed_bjcp(conn):
    """Insert BJCP 2021 styles with ranges if the table is empty."""
    if conn.execute('SELECT COUNT(*) FROM bjcp_styles').fetchone()[0] > 0:
        return
    # (name, category, og_min, og_max, fg_min, fg_max, abv_min, abv_max, ibu_min, ibu_max, ebc_min, ebc_max)
    styles = [
        # 1. Standard American Beer
        ('1A. American Light Lager',        '1. Standard American Beer',        1.028,1.040,0.998,1.008,2.8,4.2,  8, 12, 3.9, 5.9),
        ('1B. American Lager',              '1. Standard American Beer',        1.040,1.050,1.006,1.010,4.2,5.3,  8, 18, 3.9, 9.9),
        ('1C. Cream Ale',                   '1. Standard American Beer',        1.042,1.055,1.006,1.012,4.2,5.6,  8, 20, 5.0,10.0),
        ('1D. American Wheat Beer',         '1. Standard American Beer',        1.042,1.055,1.006,1.012,4.2,5.6,  8, 20, 3.9, 9.8),
        # 2. International Lager
        ('2A. International Pale Lager',    '2. International Lager',           1.042,1.050,1.008,1.012,4.5,6.0, 18, 25, 3.9,11.8),
        ('2B. International Amber Lager',   '2. International Lager',           1.042,1.055,1.008,1.014,4.5,6.0, 18, 25,11.8,27.6),
        ('2C. International Dark Lager',    '2. International Lager',           1.044,1.056,1.008,1.012,4.2,6.0,  8, 20,27.6,59.1),
        # 3. Czech Lager
        ('3A. Czech Pale Lager',            '3. Czech Lager',                   1.028,1.044,1.008,1.014,3.0,4.1, 20, 35, 5.9,11.8),
        ('3B. Czech Premium Pale Lager',    '3. Czech Lager',                   1.044,1.060,1.013,1.017,4.2,5.8, 30, 45, 7.0,14.0),
        ('3C. Czech Amber Lager',           '3. Czech Lager',                   1.044,1.060,1.013,1.017,4.4,5.8, 20, 35,19.7,31.5),
        ('3D. Czech Dark Lager',            '3. Czech Lager',                   1.044,1.060,1.013,1.017,4.4,5.8, 18, 34,33.5,69.0),
        # 4. Pale Malty European Lager
        ('4A. Munich Helles',               '4. Pale Malty European Lager',     1.044,1.048,1.006,1.012,4.7,5.4, 16, 22, 6.0,12.0),
        ('4B. Festbier',                    '4. Pale Malty European Lager',     1.054,1.057,1.010,1.014,5.8,6.3, 18, 25, 5.9, 9.8),
        ('4C. Helles Bock',                 '4. Pale Malty European Lager',     1.064,1.072,1.011,1.018,6.3,7.4, 23, 35,11.8,17.7),
        # 5. Pale Bitter European Beer
        ('5A. German Leichtbier',           '5. Pale Bitter European Beer',     1.026,1.034,1.006,1.010,2.4,3.6, 15, 28, 3.9, 7.9),
        ('5B. Kölsch',                      '5. Pale Bitter European Beer',     1.044,1.050,1.007,1.011,4.4,5.2, 18, 30, 6.9, 9.9),
        ('5C. German Helles Exportbier',    '5. Pale Bitter European Beer',     1.048,1.056,1.010,1.015,4.8,6.0, 20, 30, 7.9,11.8),
        ('5D. German Pils',                 '5. Pale Bitter European Beer',     1.044,1.050,1.008,1.013,4.4,5.2, 22, 40, 4.0,10.0),
        # 6. Amber Malty European Lager
        ('6A. Märzen',                      '6. Amber Malty European Lager',    1.054,1.060,1.010,1.014,5.6,6.3, 18, 24,16.0,34.0),
        ('6B. Rauchbier',                   '6. Amber Malty European Lager',    1.050,1.057,1.012,1.016,4.8,6.0, 20, 30,23.6,43.3),
        ('6C. Dunkles Bock',                '6. Amber Malty European Lager',    1.064,1.072,1.013,1.019,6.3,7.2, 20, 27,27.6,43.3),
        # 7. Amber Bitter European Beer
        ('7A. Vienna Lager',                '7. Amber Bitter European Beer',    1.048,1.055,1.010,1.014,4.7,5.5, 18, 30,20.0,28.0),
        ('7B. Altbier',                     '7. Amber Bitter European Beer',    1.044,1.052,1.008,1.014,4.3,5.5, 25, 50,17.7,33.5),
        ('7C. Kellerbier',                  '7. Amber Bitter European Beer',    1.045,1.054,1.008,1.014,4.7,5.4, 20, 35, 5.9,21.7),
        # 8. Dark European Lager
        ('8A. Munich Dunkel',               '8. Dark European Lager',           1.048,1.056,1.010,1.016,4.5,5.6, 18, 28,28.0,56.0),
        ('8B. Schwarzbier',                 '8. Dark European Lager',           1.046,1.052,1.010,1.016,4.4,5.4, 20, 30,33.5,55.2),
        # 9. Strong European Beer
        ('9A. Doppelbock',                  '9. Strong European Beer',          1.072,1.112,1.016,1.024,7.0,10.0,16, 26,12.0,60.0),
        ('9B. Eisbock',                     '9. Strong European Beer',          1.078,1.120,1.020,1.035,9.0,14.0,25, 35,33.5,59.1),
        ('9C. Baltic Porter',               '9. Strong European Beer',          1.060,1.090,1.016,1.024,6.5, 9.5,20, 40,33.5,59.1),
        # 10. German Wheat Beer
        ('10A. Weissbier',                  '10. German Wheat Beer',            1.044,1.053,1.008,1.014,4.3,5.6,  8, 15, 4.0,16.0),
        ('10B. Dunkles Weissbier',          '10. German Wheat Beer',            1.044,1.057,1.008,1.014,4.3,5.6, 10, 18,27.6,45.3),
        ('10C. Weizenbock',                 '10. German Wheat Beer',            1.064,1.090,1.015,1.022,6.5, 9.0,15, 30,11.8,49.2),
        # 11. British Bitter
        ('11A. Ordinary Bitter',            '11. British Bitter',               1.030,1.039,1.007,1.011,3.2,3.8, 25, 35,15.8,27.5),
        ('11B. Best Bitter',                '11. British Bitter',               1.040,1.048,1.008,1.012,3.8,4.6, 25, 40,15.8,27.6),
        ('11C. Strong Bitter',              '11. British Bitter',               1.048,1.060,1.010,1.016,4.6,6.2, 30, 50,16.0,36.0),
        # 12. Pale Commonwealth Beer
        ('12A. British Golden Ale',         '12. Pale Commonwealth Beer',       1.038,1.053,1.006,1.012,3.8,5.0, 20, 45, 3.9, 9.9),
        ('12B. Australian Sparkling Ale',   '12. Pale Commonwealth Beer',       1.042,1.050,1.006,1.010,4.5,6.0, 20, 35, 5.9,11.8),
        ('12C. English IPA',                '12. Pale Commonwealth Beer',       1.050,1.075,1.010,1.018,5.0,7.5, 40, 60,12.0,28.0),
        # 13. Brown British Beer
        ('13A. Dark Mild',                  '13. Brown British Beer',           1.030,1.038,1.008,1.013,3.0,3.8, 10, 25,27.6,49.2),
        ('13B. British Brown Ale',          '13. Brown British Beer',           1.040,1.052,1.008,1.013,4.2,5.9, 20, 30,23.6,43.3),
        ('13C. English Porter',             '13. Brown British Beer',           1.040,1.052,1.008,1.014,4.0,5.4, 18, 35,40.0,60.0),
        # 14. Scottish Ale
        ('14A. Scottish Light',             '14. Scottish Ale',                 1.030,1.035,1.010,1.013,2.5,3.3, 10, 20,33.5,49.2),
        ('14B. Scottish Heavy',             '14. Scottish Ale',                 1.035,1.040,1.010,1.015,3.3,3.9, 10, 20,23.6,39.4),
        ('14C. Scottish Export',            '14. Scottish Ale',                 1.040,1.060,1.010,1.016,3.9,6.0, 15, 30,23.6,39.4),
        # 15. Irish Beer
        ('15A. Irish Red Ale',              '15. Irish Beer',                   1.036,1.046,1.010,1.014,3.8,5.0, 18, 28,17.7,27.5),
        ('15B. Irish Stout',                '15. Irish Beer',                   1.036,1.044,1.007,1.011,4.0,4.5, 25, 45,50.0,80.0),
        ('15C. Irish Extra Stout',          '15. Irish Beer',                   1.052,1.062,1.010,1.014,5.0,6.5, 35, 50,59.1,78.8),
        # 16. Dark British Beer
        ('16A. Sweet Stout',                '16. Dark British Beer',            1.044,1.060,1.012,1.024,4.0,6.0, 20, 40,59.1,78.8),
        ('16B. Oatmeal Stout',              '16. Dark British Beer',            1.045,1.065,1.010,1.018,4.2,5.9, 25, 40,43.3,78.8),
        ('16C. Tropical Stout',             '16. Dark British Beer',            1.056,1.075,1.010,1.018,5.5,8.0, 30, 50,59.0,79.0),
        ('16D. Foreign Extra Stout',        '16. Dark British Beer',            1.056,1.075,1.010,1.018,5.5,8.0, 30, 50,59.1,78.8),
        # 17. Strong British Ale
        ('17A. British Strong Ale',         '17. Strong British Ale',           1.055,1.080,1.015,1.022,5.5,8.0, 30, 60,15.8,43.3),
        ('17B. Old Ale',                    '17. Strong British Ale',           1.055,1.088,1.015,1.022,5.5,9.0, 30, 60,19.7,43.3),
        ('17C. Wee Heavy',                  '17. Strong British Ale',           1.070,1.130,1.015,1.040,6.5,10.0,17, 35,27.5,49.5),
        ('17D. English Barleywine',         '17. Strong British Ale',           1.080,1.120,1.018,1.030,8.0,12.0,35, 70,15.8,43.3),
        # 18. Pale American Ale
        ('18A. Blonde Ale',                 '18. Pale American Ale',            1.038,1.054,1.008,1.013,3.8,5.5, 15, 28, 6.0,12.0),
        ('18B. American Pale Ale',          '18. Pale American Ale',            1.045,1.060,1.010,1.015,4.5,6.2, 30, 50,10.0,20.0),
        # 19. Amber and Brown American Beer
        ('19A. American Amber Ale',         '19. Amber and Brown American Beer',1.045,1.060,1.010,1.015,4.5,6.2, 25, 40,20.0,34.0),
        ('19B. California Common',          '19. Amber and Brown American Beer',1.048,1.054,1.011,1.014,4.5,5.5, 30, 45,17.7,27.6),
        ('19C. American Brown Ale',         '19. Amber and Brown American Beer',1.045,1.060,1.010,1.016,4.3,6.2, 20, 30,36.0,70.0),
        # 20. American Porter and Stout
        ('20A. American Porter',            '20. American Porter and Stout',    1.050,1.070,1.012,1.018,4.8,6.5, 25, 50,45.0,80.0),
        ('20B. American Stout',             '20. American Porter and Stout',    1.050,1.075,1.010,1.022,5.0,7.0, 35, 75,60.0,120.0),
        ('20C. Imperial Stout',             '20. American Porter and Stout',    1.075,1.115,1.018,1.030,8.0,12.0,50, 90,60.0,120.0),
        # 21. IPA
        ('21A. American IPA',               '21. IPA',                          1.056,1.070,1.010,1.015,5.5,7.5, 40, 70,12.0,28.0),
        ('21B. Specialty IPA: Belgian IPA', '21. IPA',                          1.058,1.080,1.008,1.016,6.2,9.5, 50,100, 9.9,15.8),
        ('21B. Specialty IPA: Black IPA',   '21. IPA',                          1.050,1.085,1.010,1.018,5.5,9.0, 50, 90,49.5,79.0),
        ('21B. Specialty IPA: Brown IPA',   '21. IPA',                          1.056,1.070,1.008,1.016,5.5,7.5, 40, 70,35.5,69.0),
        ('21B. Specialty IPA: Red IPA',     '21. IPA',                          1.056,1.070,1.008,1.016,5.5,7.5, 40, 70,40.0,70.0),
        ('21B. Specialty IPA: Rye IPA',     '21. IPA',                          1.056,1.075,1.008,1.014,5.5,8.0, 50, 75,11.8,27.5),
        ('21B. Specialty IPA: White IPA',   '21. IPA',                          1.056,1.065,1.010,1.016,5.5,7.0, 40, 70, 9.9,11.8),
        ('21B. Specialty IPA: Brut IPA',    '21. IPA',                          1.046,1.057,0.990,1.004,6.0,7.5, 20, 30, 3.9, 7.9),
        ('21C. Hazy IPA',                   '21. IPA',                          1.060,1.085,1.010,1.015,6.0,9.0, 25, 60, 6.0,12.0),
        # 22. Strong American Ale
        ('22A. Double IPA',                 '22. Strong American Ale',          1.065,1.085,1.010,1.020,7.5,10.0,60,120,12.0,30.0),
        ('22B. American Strong Ale',        '22. Strong American Ale',          1.062,1.090,1.014,1.024,6.3,10.0,50,100,13.8,35.5),
        ('22C. American Barleywine',        '22. Strong American Ale',          1.080,1.120,1.016,1.030,8.0,12.0,50,100,20.0,40.0),
        ('22D. Wheatwine',                  '22. Strong American Ale',          1.080,1.120,1.016,1.030,8.0,12.0,30, 60,11.8,27.6),
        # 23. European Sour Ale
        ('23A. Berliner Weisse',            '23. European Sour Ale',            1.028,1.032,1.003,1.006,2.8,3.8,  3,  8, 4.0, 6.0),
        ('23B. Flanders Red Ale',           '23. European Sour Ale',            1.048,1.057,1.002,1.012,4.6,6.5, 10, 25,19.7,33.5),
        ('23C. Oud Bruin',                  '23. European Sour Ale',            1.040,1.074,1.008,1.012,4.0,8.0, 20, 25,33.5,43.3),
        ('23D. Lambic',                     '23. European Sour Ale',            1.040,1.054,1.001,1.010,5.0,6.5,  0, 10, 5.9,11.8),
        ('23E. Gueuze',                     '23. European Sour Ale',            1.040,1.054,1.000,1.006,5.0,8.0,  0,  1, 9.9,11.8),
        ('23F. Fruit Lambic',               '23. European Sour Ale',            1.036,1.056,1.006,1.010,4.2,4.8,  5, 12, 5.9, 7.9),
        ('23G. Gose',                       '23. European Sour Ale',            1.036,1.056,1.006,1.010,4.2,4.8,  5, 12, 6.0, 8.0),
        # 24. Belgian Ale
        ('24A. Witbier',                    '24. Belgian Ale',                  1.044,1.052,1.008,1.012,4.5,5.5,  8, 20, 4.0, 8.0),
        ('24B. Belgian Pale Ale',           '24. Belgian Ale',                  1.048,1.054,1.010,1.014,4.8,5.5, 20, 30,15.8,27.6),
        ('24C. Bière de Garde',             '24. Belgian Ale',                  1.060,1.080,1.008,1.016,6.0,8.5, 18, 28,11.8,37.5),
        # 25. Strong Belgian Ale
        ('25A. Belgian Blond Ale',          '25. Strong Belgian Ale',           1.062,1.075,1.008,1.018,6.0,7.5, 15, 30, 7.9,11.8),
        ('25B. Saison',                     '25. Strong Belgian Ale',           1.048,1.065,1.002,1.008,5.0,7.0, 20, 35,10.0,28.0),
        ('25C. Belgian Golden Strong Ale',  '25. Strong Belgian Ale',           1.070,1.095,1.005,1.016,7.5,10.5,22, 35, 5.9,11.8),
        # 26. Monastic Ale
        ('26A. Belgian Single',             '26. Monastic Ale',                 1.044,1.054,1.004,1.010,4.8,6.0, 25, 45, 5.9, 9.8),
        ('26B. Belgian Dubbel',             '26. Monastic Ale',                 1.062,1.075,1.008,1.018,6.0,7.6, 15, 25,20.0,60.0),
        ('26C. Belgian Tripel',             '26. Monastic Ale',                 1.075,1.085,1.008,1.014,7.5,9.5, 20, 40, 9.0,14.0),
        ('26D. Belgian Dark Strong Ale',    '26. Monastic Ale',                 1.075,1.110,1.010,1.024,8.0,12.0,20, 35,24.0,45.0),
        # 27. Historical Beer
        ('27. Historical Beer: Gose',           '27. Historical Beer',          1.036,1.056,1.006,1.010,4.2,4.8,  5, 12, 6.0, 8.0),
        ('27. Historical Beer: Kentucky Common','27. Historical Beer',          1.044,1.055,1.010,1.018,4.0,5.5, 15, 30,21.5,39.5),
        ('27. Historical Beer: Lichtenhainer',  '27. Historical Beer',          1.032,1.040,1.004,1.008,3.5,4.7,  5, 12, 5.9,11.8),
        ('27. Historical Beer: London Brown Ale','27. Historical Beer',         1.033,1.038,1.012,1.015,2.8,3.6, 15, 20,43.5,69.0),
        ('27. Historical Beer: Piwo Grodziskie','27. Historical Beer',          1.028,1.032,1.006,1.012,2.5,3.3, 20, 35, 5.9,11.8),
        ('27. Historical Beer: Pre-Prohibition Lager','27. Historical Beer',   1.044,1.060,1.010,1.015,4.5,6.0, 25, 40, 5.9,11.8),
        ('27. Historical Beer: Pre-Prohibition Porter','27. Historical Beer',  1.046,1.060,1.010,1.016,4.5,6.0, 20, 30,39.5,59.0),
        ('27. Historical Beer: Roggenbier', '27. Historical Beer',              1.046,1.056,1.010,1.014,4.5,6.0, 10, 20,27.5,37.5),
        ('27. Historical Beer: Sahti',      '27. Historical Beer',              1.076,1.120,1.016,1.038,7.0,11.0, 0, 16, 7.9,43.5),
        # 28. American Wild Ale
        ('28A. Brett Beer',                 '28. American Wild Ale',            1.020,1.090,1.000,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('28B. Mixed-Fermentation Sour Beer','28. American Wild Ale',           1.020,1.090,1.000,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('28C. Wild Specialty Beer',        '28. American Wild Ale',            1.020,1.090,1.000,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        # 29. Fruit Beer
        ('29A. Fruit Beer',                 '29. Fruit Beer',                   1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('29B. Fruit and Spice Beer',       '29. Fruit Beer',                   1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('29C. Specialty Fruit Beer',       '29. Fruit Beer',                   1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        # 30. Spiced Beer
        ('30A. Spice, Herb, or Vegetable Beer','30. Spiced Beer',               1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('30B. Autumn Seasonal Beer',       '30. Spiced Beer',                  1.020,1.090,1.006,1.016,5.0,10.0, 5, 50,13.8,98.5),
        ('30C. Winter Seasonal Beer',       '30. Spiced Beer',                  1.020,1.090,1.006,1.016,5.0,10.0, 5, 50,13.8,98.5),
        # 31. Alternative Fermentables
        ('31A. Alternative Grain Beer',     '31. Alternative Fermentables',     1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('31B. Alternative Sugar Beer',     '31. Alternative Fermentables',     1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        # 32. Smoked Beer
        ('32A. Classic Style Smoked Beer',  '32. Smoked Beer',                  1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('32B. Specialty Smoked Beer',      '32. Smoked Beer',                  1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        # 33. Wood Beer
        ('33A. Wood-Aged Beer',             '33. Wood Beer',                    1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('33B. Specialty Wood-Aged Beer',   '33. Wood Beer',                    1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        # 34. Specialty Beer
        ('34A. Clone Beer',                 '34. Specialty Beer',               1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('34B. Mixed-Style Beer',           '34. Specialty Beer',               1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
        ('34C. Experimental Beer',          '34. Specialty Beer',               1.020,1.090,1.006,1.016,2.0,10.0, 5, 50, 3.9,98.5),
    ]
    conn.executemany(
        '''INSERT OR IGNORE INTO bjcp_styles
           (name,category,og_min,og_max,fg_min,fg_max,abv_min,abv_max,ibu_min,ibu_max,ebc_min,ebc_max)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        styles
    )


# ── BJCP ─────────────────────────────────────────────────────────────────────

@app.route('/api/bjcp')
def get_bjcp():
    q = request.args.get('q', '').strip().lower()
    with get_db() as conn:
        if q:
            rows = conn.execute(
                '''SELECT * FROM bjcp_styles
                   WHERE LOWER(name) LIKE ? OR LOWER(category) LIKE ?
                   ORDER BY id''',
                (f'%{q}%', f'%{q}%')
            ).fetchall()
        else:
            rows = conn.execute('SELECT * FROM bjcp_styles ORDER BY id').fetchall()
    return jsonify([dict(r) for r in rows])


# ── STATS ────────────────────────────────────────────────────────────────────

@app.route('/api/stats')
def get_stats():
    with get_db() as conn:
        def scalar(sql):
            return conn.execute(sql).fetchone()[0]
        return jsonify({
            'inventory_count': scalar('SELECT COUNT(*) FROM inventory_items WHERE archived=0'),
            'recipes_count':   scalar('SELECT COUNT(*) FROM recipes   WHERE archived=0'),
            'brews_count':     scalar('SELECT COUNT(*) FROM brews      WHERE archived=0'),
            'brews_active':    scalar("SELECT COUNT(*) FROM brews WHERE archived=0 AND status IN ('planned','in_progress','fermenting')"),
            'beers_count':     scalar('SELECT COUNT(*) FROM beers      WHERE archived=0'),
            'kegs_count':      scalar('SELECT COUNT(*) FROM soda_kegs  WHERE archived=0'),
            'total_33cl':      scalar('SELECT COALESCE(SUM(stock_33cl),0) FROM beers WHERE archived=0'),
            'total_75cl':      scalar('SELECT COALESCE(SUM(stock_75cl),0) FROM beers WHERE archived=0'),
            'total_liters':    scalar(
                'SELECT COALESCE(SUM(stock_33cl*0.33 + stock_75cl*0.75),0) FROM beers WHERE archived=0'
            ),
        })


# ── VÉRIFICATION DE VERSION ──────────────────────────────────────────────────

_version_cache = {'result': None, 'ts': 0}

def _parse_semver(v):
    v = v.strip().lstrip('v')
    try:
        return tuple(int(x) for x in v.split('.'))
    except Exception:
        return (0,)

@app.route('/api/version/check')
def check_app_version():
    now = time.time()
    if _version_cache['result'] and now - _version_cache['ts'] < 6 * 3600:
        return jsonify(_version_cache['result'])
    try:
        req = urllib.request.Request(
            'https://api.github.com/repos/chatainsim/brewhome/releases/latest',
            headers={'User-Agent': f'BrewHome/{APP_VERSION}', 'Accept': 'application/vnd.github+json'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        latest = data.get('tag_name', '').lstrip('v')
        result = {
            'current': APP_VERSION,
            'latest': latest,
            'update_available': _parse_semver(latest) > _parse_semver(APP_VERSION),
            'release_url': data.get('html_url', 'https://github.com/chatainsim/brewhome/releases'),
        }
    except Exception as e:
        app.logger.debug(f"check_app_version: {e}")
        result = {'current': APP_VERSION, 'latest': None, 'update_available': False, 'error': str(e)}
    _version_cache['result'] = result
    _version_cache['ts'] = now
    return jsonify(result)


# ── TELEGRAM NOTIFICATIONS ───────────────────────────────────────────────────

def _tg_get_settings():
    """Récupère la config Telegram depuis la base de données."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_settings "
                "WHERE key IN ('telegram_token','telegram_chat_id','telegram_notifs','telegram_tz')"
            ).fetchall()
    except Exception as e:
        app.logger.warning(f"_tg_get_settings: DB error: {e}")
        return None, None, {}, 'UTC'
    s = {r['key']: r['value'] for r in rows}
    notifs = {}
    try:
        notifs = json.loads(s.get('telegram_notifs') or '{}')
    except Exception as e:
        app.logger.warning(f"_tg_get_settings: invalid telegram_notifs JSON: {e}")
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
        brews = conn.execute(
            "SELECT id, name, status, og, fg, abv, brew_date FROM brews "
            "WHERE archived=0 AND status NOT IN ('completed') ORDER BY brew_date DESC"
        ).fetchall()
        # Dernière mesure densimètre par brassin (via spindle lié)
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
        'planned':    '📋 Planifié',
        'in_progress': '🔥 En cours',
        'fermenting': '🧪 En fermentation',
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
        if b['brew_date']:
            line += f"\n  Brassé le {b['brew_date']}"
        sr = spindle_data.get(b['id'])
        if sr:
            grav_str = f"{float(sr['gravity']):.3f}" if sr['gravity'] is not None else "—"
            temp_str = f"{float(sr['temperature']):.1f} °C" if sr['temperature'] is not None else "—"
            # Ancienneté de la mesure
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
                app.logger.debug(f"_tg_brews_msg: could not compute reading age: {e}")
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
    # Ordre d'affichage fixe
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
        # Catégories inconnues éventuelles
        messages.append("\n".join(lines))
    # Catégories hors liste fixe
    for cat, cat_items in by_cat.items():
        if cat not in order:
            icon, label = labels.get(cat, ('📦', cat.capitalize()))
            lines = [f"{icon} <b>Inventaire — {label}</b>", ""]
            for it in cat_items:
                lines.append(f"• {it['name']} : {it['quantity']} {it['unit']}")
            messages.append("\n".join(lines))
    return messages


_TG_BUILDERS = {
    'brews':     _tg_build_brews,
    'cave':      _tg_build_cave,
    'inventory': _tg_build_inventory,
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
        app.logger.error(f"Telegram send error ({notif_type}): {e}")


_scheduler = BackgroundScheduler()


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
    def _last_dow(y, m, dow):
        d = date(y, m + 1, 1) - timedelta(days=1)
        while d.weekday() != dow:
            d -= timedelta(days=1)
        return d

    evs = []
    for mo, da, label, emoji in _BREW_EVENTS_FIXED:
        try:
            evs.append((date(year, mo, da), label, emoji))
        except ValueError:
            pass
    evs.append((_nth_dow(year, 8, 3, 1),  "IPA Day",               "🌿"))  # 1er jeudi août
    evs.append((_nth_dow(year, 8, 4, 1),  "International Beer Day","🍺"))  # 1er vendredi août
    evs.append((_nth_dow(year, 7, 5, 1),  "Sour Beer Day",         "🍋"))  # 1er samedi juillet
    evs.append((_nth_dow(year, 11, 3, 3), "Beaujolais Nouveau",    "🍷"))  # 3e jeudi novembre
    # Oktoberfest : dernier samedi avant le 22 sept
    okt = date(year, 9, 22)
    while okt.weekday() != 5:
        okt -= timedelta(days=1)
    evs.append((okt, "Début Oktoberfest", "🥨"))
    return sorted(evs, key=lambda x: x[0])


def _tg_brewing_events_fire():
    """Job quotidien : vérifie si aujourd'hui est un event ou un rappel J-45."""
    token, chat_id, _, _ = _tg_get_settings()
    if not token or not chat_id:
        return
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key='tg_brewing_events'").fetchone()
    if not row:
        return
    try:
        cfg = json.loads(row['value'])
    except Exception as e:
        app.logger.warning(f"_tg_brewing_events_fire: invalid tg_brewing_events JSON: {e}")
        return
    if not cfg.get('enabled'):
        return

    today = date.today()
    remind_days = 45

    for year in (today.year, today.year + 1):
        for ev_date, label, emoji in _calc_brewing_events(year):
            if cfg.get('event_day') and ev_date == today:
                _tg_send(token, chat_id,
                    f'{emoji} <b>{label}</b>\n\n'
                    f'C\'est aujourd\'hui ! 🎉\nSanté et bonne dégustation ! 🍺')
            if cfg.get('remind'):
                remind_date = ev_date - timedelta(days=remind_days)
                if remind_date == today:
                    _tg_send(token, chat_id,
                        f'⏰ <b>Rappel brassage — {label}</b>\n\n'
                        f'{emoji} <b>{label}</b> est dans <b>{remind_days} jours</b> '
                        f'({ev_date.strftime("%d/%m/%Y")}).\n\n'
                        f'C\'est le moment idéal pour brasser une bière spéciale ! 🍺')

    # Événements personnalisés
    with get_db() as conn:
        custom_evs = conn.execute(
            'SELECT * FROM custom_calendar_events WHERE telegram_notify=1'
        ).fetchall()
        # Pré-charger recettes et brouillons pour les associations
        all_recipes = {r['id']: r for r in conn.execute('SELECT id, name, style FROM recipes').fetchall()}
        all_drafts  = {d['id']: d for d in conn.execute('SELECT id, title, style FROM draft_recipes').fetchall()}

    for ev in custom_evs:
        try:
            ev_date = date.fromisoformat(ev['event_date'])
        except Exception as e:
            app.logger.warning(f"_tg_brewing_events_fire: invalid event_date {ev.get('event_date')!r}: {e}")
            continue
        emoji = ev['emoji'] or '📅'
        label = ev['title']

        # Construire le bloc d'association (style / recette / brouillon)
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
            _tg_send(token, chat_id,
                f'{emoji} <b>{label}</b>\n\n'
                f'C\'est aujourd\'hui ! 🎉'
                f'{assoc_block}'
                f'{notes_line}')
        if ev['brew_reminder']:
            remind_date = ev_date - timedelta(days=remind_days)
            if remind_date == today:
                _tg_send(token, chat_id,
                    f'⏰ <b>Rappel brassage — {label}</b>\n\n'
                    f'{emoji} <b>{label}</b> est dans <b>{remind_days} jours</b> '
                    f'({ev_date.strftime("%d/%m/%Y")}).'
                    f'{assoc_block}\n\n'
                    f'C\'est le moment idéal pour brasser une bière spéciale ! 🍺')


def reschedule_telegram():
    """Recharge la config depuis la DB et re-planifie les jobs Telegram."""
    token, chat_id, notifs, tz_str = _tg_get_settings()
    for jid in ('tg_brews', 'tg_cave', 'tg_inventory', 'tg_brew_events'):
        try:
            _scheduler.remove_job(jid)
        except Exception as e:
            pass  # job absent = pas encore planifié
    if not token or not chat_id:
        return
    try:
        from zoneinfo import ZoneInfo   # Python 3.9+
        tz = ZoneInfo(tz_str or 'UTC')
    except Exception as e:
        app.logger.warning(f"reschedule_telegram: invalid timezone {tz_str!r}, falling back to UTC: {e}")
        import datetime as _dt
        tz = _dt.timezone.utc

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

    _add('tg_brews',     'brews',     notifs.get('brews', {}),     monthly=False)
    _add('tg_cave',      'cave',      notifs.get('cave', {}),      monthly=True)
    _add('tg_inventory', 'inventory', notifs.get('inventory', {}), monthly=True)

    # Événements brassicoles
    try:
        with get_db() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key='tg_brewing_events'").fetchone()
        ev_cfg = json.loads(row['value']) if row else {}
    except Exception as e:
        app.logger.warning(f"reschedule_telegram: invalid tg_brewing_events JSON: {e}")
        ev_cfg = {}
    if ev_cfg.get('enabled') and (ev_cfg.get('remind') or ev_cfg.get('event_day')):
        h = int(ev_cfg.get('hour', 8))
        m = int(ev_cfg.get('minute', 0))
        _scheduler.add_job(_tg_brewing_events_fire, CronTrigger(hour=h, minute=m, timezone=tz),
                           id='tg_brew_events', replace_existing=True)


@app.route('/api/telegram/test', methods=['POST'])
def telegram_test():
    d = request.json or {}
    token   = (d.get('token')   or '').strip()
    chat_id = (d.get('chat_id') or '').strip()
    if not token or not chat_id:
        return jsonify({'error': 'Token et Chat ID requis'}), 400
    try:
        _tg_send(token, chat_id, '🍺 <b>BrewHome</b>\n\nConnexion Telegram configurée avec succès !')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/telegram/trigger/<notif_type>', methods=['POST'])
def telegram_trigger(notif_type):
    if notif_type not in _TG_BUILDERS:
        return jsonify({'error': 'Type inconnu'}), 400
    token, chat_id, _, _ = _tg_get_settings()
    if not token or not chat_id:
        return jsonify({'error': 'Telegram non configuré (token ou chat_id manquant)'}), 400
    try:
        result = _TG_BUILDERS[notif_type]()
        messages = result if isinstance(result, list) else [result]
        for msg in messages:
            _tg_send(token, chat_id, msg)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── MISES À JOUR DES LIBRAIRIES STATIQUES ────────────────────────────────────

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

def _read_version_from_file(path):
    """Lit la version dans le commentaire d'entête d'un fichier JS/CSS."""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            head = f.read(512)
        import re
        m = re.search(r'v?(\d+\.\d+\.\d+)', head)
        return m.group(1) if m else None
    except Exception as e:
        app.logger.debug(f"_read_version_from_file({path}): {e}")
        return None

def _npm_latest(package):
    """Récupère la dernière version d'un package npm."""
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

@app.route('/api/static/check-updates')
def static_check_updates():
    result = {}
    # Chart.js
    cjs_path = os.path.join(STATIC_DIR, 'js', 'chart.umd.min.js')
    result['chartjs'] = {'current': _read_version_from_file(cjs_path), 'latest': None, 'error': None}
    try:
        result['chartjs']['latest'] = _npm_latest('chart.js')
    except Exception as e:
        result['chartjs']['error'] = str(e)
    # Font Awesome
    fa_path = os.path.join(STATIC_DIR, 'fonts', 'fa', 'all.min.css')
    result['fontawesome'] = {'current': _read_version_from_file(fa_path), 'latest': None, 'error': None}
    try:
        result['fontawesome']['latest'] = _npm_latest('@fortawesome/fontawesome-free')
    except Exception as e:
        result['fontawesome']['error'] = str(e)
    # Google Fonts (pas de version npm — on retourne juste la taille/date du fichier)
    gf_path = os.path.join(STATIC_DIR, 'fonts', 'google', 'fonts.css')
    try:
        st = os.stat(gf_path)
        result['googlefonts'] = {
            'current': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d'),
            'size': st.st_size,
        }
    except Exception as e:
        app.logger.debug(f"check_static_updates: cannot stat google fonts: {e}")
        result['googlefonts'] = {'current': None, 'size': 0}
    return jsonify(result)


@app.route('/api/static/update/chartjs', methods=['POST'])
def update_chartjs():
    try:
        version = _npm_latest('chart.js')
        url = f'https://cdn.jsdelivr.net/npm/chart.js@{version}/dist/chart.umd.min.js'
        dest = os.path.join(STATIC_DIR, 'js', 'chart.umd.min.js')
        size = _download(url, dest)
        return jsonify({'version': version, 'size': size})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/static/update/fontawesome', methods=['POST'])
def update_fontawesome():
    try:
        version = _npm_latest('@fortawesome/fontawesome-free')
        base = f'https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@{version}'
        fa_dir = os.path.join(STATIC_DIR, 'fonts', 'fa')
        wf_dir = os.path.join(fa_dir, 'webfonts')
        os.makedirs(wf_dir, exist_ok=True)
        # CSS
        _download(f'{base}/css/all.min.css', os.path.join(fa_dir, 'all.min.css'))
        # Webfonts
        for wf in ('fa-brands-400.woff2', 'fa-regular-400.woff2',
                   'fa-solid-900.woff2', 'fa-v4compatibility.woff2'):
            try:
                _download(f'{base}/webfonts/{wf}', os.path.join(wf_dir, wf))
            except Exception as e:
                app.logger.debug(f"update_static_lib: optional webfont {wf} unavailable: {e}")
        return jsonify({'version': version})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── GITHUB BACKUP AUTOMATIQUE ────────────────────────────────────────────────

def _gh_push_file(repo, pat, branch, file_path, content_str, message):
    """Pousse un fichier texte vers GitHub via l'API. Retourne True si modifié, False si inchangé."""
    encoded = base64.b64encode(content_str.encode('utf-8')).decode('ascii')
    base_url = f'https://api.github.com/repos/{repo}/contents/{file_path}'
    headers = {
        'Authorization': f'Bearer {pat}',
        'Accept': 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'User-Agent': 'BrewHome',
    }
    # Récupérer le SHA existant
    sha = None
    try:
        req = urllib.request.Request(f'{base_url}?ref={urllib.parse.quote(branch)}', headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            existing = json.loads(resp.read().decode())
            sha = existing.get('sha')
            existing_b64 = (existing.get('content') or '').replace('\n', '')
            if existing_b64 == encoded:
                return False  # inchangé
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    body = {'message': message, 'content': encoded, 'branch': branch}
    if sha:
        body['sha'] = sha
    req = urllib.request.Request(
        base_url, data=json.dumps(body).encode('utf-8'),
        headers=headers, method='PUT'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()
    return True


def _github_data_backup():
    """Sauvegarde complète des données vers GitHub (appellée par le scheduler)."""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key IN "
                            "('gh_data_repo','gh_data_branch','gh_data_pat')").fetchall()
    cfg = {r['key']: r['value'] for r in rows}
    repo = cfg.get('gh_data_repo', '').strip()
    pat  = cfg.get('gh_data_pat',  '').strip()
    branch = cfg.get('gh_data_branch', 'main').strip() or 'main'
    if not repo or not pat:
        app.logger.warning('GitHub backup: dépôt ou PAT manquant, sauvegarde ignorée')
        return

    date_str = datetime.now().strftime('%Y-%m-%d')
    try:
        # Collecte des données
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
            beers = [dict(r) for r in conn.execute(
                'SELECT * FROM beers ORDER BY name').fetchall()]
            spindles = [dict(r) for r in conn.execute(
                'SELECT * FROM spindles ORDER BY name').fetchall()]
            catalog = [dict(r) for r in conn.execute(
                'SELECT * FROM ingredient_catalog ORDER BY category, name').fetchall()]
            settings_rows = conn.execute('SELECT key, value FROM app_settings').fetchall()
        settings_out = {r['key']: r['value'] for r in settings_rows}
        # Retirer les secrets
        for k in ('gh_data_pat', 'gh_vitrine_pat', 'ai_api_key', 'telegram_token'):
            settings_out.pop(k, None)

        files = [
            ('inventaire.json',  inventory),
            ('recettes.json',    recipes),
            ('brassins.json',    brews),
            ('cave.json',        beers),
            ('densimetres.json', spindles),
            ('catalogue.json',   catalog),
            ('parametres.json',  settings_out),
        ]
        pushed = skipped = 0
        for name, data in files:
            changed = _gh_push_file(repo, pat, branch, f'backup_auto/{name}',
                                    json.dumps(data, ensure_ascii=False, indent=2),
                                    f'backup auto: {name.replace(".json","")} {date_str}')
            if changed:
                pushed += 1
            else:
                skipped += 1

        # Enregistrer la date de dernière sauvegarde
        ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        with get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('gh_data_last_backup',?)", (ts,))
            notify = conn.execute("SELECT value FROM app_settings WHERE key='gh_data_backup_notify'").fetchone()
        app.logger.info(f'GitHub backup: {pushed} fichier(s) mis à jour, {skipped} inchangé(s)')
        # Notification Telegram si activée
        if notify and notify['value'] == 'true':
            try:
                tg_token, tg_chat, _, _ = _tg_get_settings()
                if tg_token and tg_chat:
                    skip_txt = f', {skipped} inchangé(s)' if skipped else ''
                    _tg_send(tg_token, tg_chat,
                             f'☁️ <b>Backup GitHub automatique</b>\n\n'
                             f'✅ {pushed} fichier(s) mis à jour{skip_txt}\n'
                             f'🕐 {ts}\n'
                             f'📁 Dépôt : <code>{repo}</code>')
            except Exception as te:
                app.logger.warning(f'GitHub backup Telegram notify error: {te}')
    except Exception as e:
        app.logger.error(f'GitHub backup error: {e}')


def reschedule_github_backup():
    """Recharge la config depuis la DB et re-planifie le job de backup GitHub."""
    try:
        _scheduler.remove_job('gh_backup')
    except Exception as e:
        pass  # job absent = pas encore planifié
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
    else:  # monthly
        day = max(1, min(28, int(cfg.get('gh_data_backup_day', '1'))))
        trigger = CronTrigger(day=day, hour=hour, minute=minute)
    _scheduler.add_job(_github_data_backup, trigger, id='gh_backup', replace_existing=True)


# ── APP SETTINGS (apparence) ─────────────────────────────────────────────────

# Clés dont la valeur ne doit jamais être renvoyée au frontend
_SECRET_KEYS = frozenset({'ai_api_key'})

@app.route('/api/app-settings', methods=['GET'])
def get_app_settings():
    with get_db() as conn:
        rows = conn.execute('SELECT key, value FROM app_settings').fetchall()
    result = {}
    for r in rows:
        if r['key'] in _SECRET_KEYS:
            # Indique si la clé est définie sans révéler sa valeur
            result[r['key']] = '***' if r['value'] else ''
        else:
            result[r['key']] = r['value']
    return jsonify(result)


@app.route('/api/app-settings', methods=['PUT'])
def save_app_settings():
    data = request.json or {}
    with get_db() as conn:
        for key, value in data.items():
            # Ne jamais écraser une clé secrète avec le placeholder masqué
            if key in _SECRET_KEYS and value == '***':
                continue
            if value is None or value == '':
                conn.execute('DELETE FROM app_settings WHERE key=?', (key,))
            else:
                conn.execute(
                    'INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)',
                    (key, str(value))
                )
    if any(k in data for k in ('telegram_token', 'telegram_chat_id', 'telegram_notifs', 'telegram_tz',
                               'tg_brewing_events')):
        try:
            reschedule_telegram()
        except Exception as e:
            app.logger.warning(f"Telegram reschedule error: {e}")
    if any(k.startswith('gh_data_backup_') for k in data):
        try:
            reschedule_github_backup()
        except Exception as e:
            app.logger.warning(f"GitHub backup reschedule error: {e}")
    return jsonify({'success': True})


# ── CUSTOM CALENDAR EVENTS ───────────────────────────────────────────────────

@app.route('/api/custom_events', methods=['GET'])
def get_custom_events():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM custom_calendar_events ORDER BY event_date').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/custom_events', methods=['POST'])
def create_custom_event():
    data = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO custom_calendar_events
               (title, emoji, event_date, color, notes, brew_reminder, telegram_notify,
                style, recipe_id, draft_id, recurrence, brew_reminder_days)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                data.get('title', 'Événement'),
                data.get('emoji', '📅'),
                data.get('event_date'),
                data.get('color', '#f59e0b'),
                data.get('notes'),
                1 if data.get('brew_reminder') else 0,
                1 if data.get('telegram_notify') else 0,
                data.get('style') or None,
                data.get('recipe_id') or None,
                data.get('draft_id') or None,
                data.get('recurrence') or None,
                int(data['brew_reminder_days']) if data.get('brew_reminder_days') is not None else None,
            )
        )
        row = conn.execute('SELECT * FROM custom_calendar_events WHERE id=?', (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route('/api/custom_events/<int:event_id>', methods=['PUT'])
def update_custom_event(event_id):
    data = request.json or {}
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE custom_calendar_events
               SET title=?, emoji=?, event_date=?, color=?, notes=?, brew_reminder=?, telegram_notify=?,
                   style=?, recipe_id=?, draft_id=?, recurrence=?, brew_reminder_days=?
               WHERE id=?''',
            (
                data.get('title', 'Événement'),
                data.get('emoji', '📅'),
                data.get('event_date'),
                data.get('color', '#f59e0b'),
                data.get('notes'),
                1 if data.get('brew_reminder') else 0,
                1 if data.get('telegram_notify') else 0,
                data.get('style') or None,
                data.get('recipe_id') or None,
                data.get('draft_id') or None,
                data.get('recurrence') or None,
                int(data['brew_reminder_days']) if data.get('brew_reminder_days') is not None else None,
                event_id,
            )
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute('SELECT * FROM custom_calendar_events WHERE id=?', (event_id,)).fetchone()
    return jsonify(dict(row))


@app.route('/api/custom_events/<int:event_id>', methods=['DELETE'])
def delete_custom_event(event_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM custom_calendar_events WHERE id=?', (event_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})


# ── BROUILLONS ───────────────────────────────────────────────────────────────

@app.route('/api/drafts', methods=['GET'])
def get_drafts():
    # Exclut 'image' (base64) pour que la liste reste légère ; charger via GET /api/drafts/<id>
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT id, title, style, volume, ingredients, notes, color,
                      target_date, event_label, sort_order, created_at, updated_at
               FROM draft_recipes ORDER BY sort_order ASC, updated_at DESC'''
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/drafts/<int:draft_id>', methods=['GET'])
def get_draft(draft_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM draft_recipes WHERE id=?', (draft_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        return jsonify(dict(row))


@app.route('/api/drafts/reorder', methods=['PUT'])
def reorder_drafts():
    items = request.json or []
    with get_db() as conn:
        for item in items:
            if item.get('id') is None or item.get('sort_order') is None:
                continue
            conn.execute('UPDATE draft_recipes SET sort_order=? WHERE id=?',
                         (item['sort_order'], item['id']))
    return jsonify({'success': True})


@app.route('/api/drafts', methods=['POST'])
def create_draft():
    data = request.json or {}
    if _image_too_large(data.get('image')):
        shrunk = _shrink_image_b64(data['image'])
        data['image'] = shrunk if not _image_too_large(shrunk) else None
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO draft_recipes (title, style, volume, ingredients, notes, color, target_date, event_label, image)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                data.get('title', 'Nouveau brouillon'),
                data.get('style'),
                data.get('volume'),
                data.get('ingredients'),
                data.get('notes'),
                data.get('color'),
                data.get('target_date'),
                data.get('event_label'),
                data.get('image'),
            )
        )
        row = conn.execute('SELECT * FROM draft_recipes WHERE id=?', (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route('/api/drafts/<int:draft_id>', methods=['PUT'])
def update_draft(draft_id):
    data = request.json or {}
    if _image_too_large(data.get('image')):
        shrunk = _shrink_image_b64(data['image'])
        data['image'] = shrunk if not _image_too_large(shrunk) else None
    with get_db() as conn:
        cur = conn.execute(
            '''UPDATE draft_recipes
               SET title=?, style=?, volume=?, ingredients=?, notes=?, color=?,
                   target_date=?, event_label=?, image=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (
                data.get('title', 'Nouveau brouillon'),
                data.get('style'),
                data.get('volume'),
                data.get('ingredients'),
                data.get('notes'),
                data.get('color'),
                data.get('target_date'),
                data.get('event_label'),
                data.get('image'),
                draft_id,
            )
        )
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
        row = conn.execute('SELECT * FROM draft_recipes WHERE id=?', (draft_id,)).fetchone()
    return jsonify(dict(row))


@app.route('/api/drafts/<int:draft_id>', methods=['DELETE'])
def delete_draft(draft_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM draft_recipes WHERE id=?', (draft_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Not found'}), 404
    return jsonify({'success': True})


# ── AI DRAFT SUGGEST ─────────────────────────────────────────────────────────

@app.route('/api/ai/draft-suggest', methods=['POST'])
def ai_draft_suggest():
    data = request.json or {}
    style       = (data.get('style')       or '').strip()
    event_label = (data.get('event_label') or '').strip()
    event_desc  = (data.get('event_desc')  or '').strip()
    notes       = (data.get('notes')       or '').strip()
    volume      = data.get('volume') or 10

    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key='ai_api_key'").fetchone()
    api_key = row['value'].strip() if row and row['value'] else None
    if not api_key:
        return jsonify({'error': 'Clé API Gemini non configurée (Paramètres → IA)'}), 400

    context_parts = []
    if style:       context_parts.append(f"Style BJCP : {style}")
    if event_label: context_parts.append(f"Objectif de brassage : {event_label}")
    if event_desc:  context_parts.append(f"Description de l'événement : {event_desc}")
    if notes:       context_parts.append(f"Notes du brasseur : {notes}")
    context_str = '\n'.join(context_parts) if context_parts else "Bière de dégustation générique"

    prompt = f"""Tu es un expert en brassage amateur (homebrewing). Génère une recette de bière pour un brassin de {volume} litres.

{context_str}

Retourne UNIQUEMENT un objet JSON valide (sans markdown, sans backticks, sans commentaires) avec cette structure exacte :
{{
  "title": "Nom suggéré pour la bière",
  "ingredients": [
    {{"type": "malt", "name": "Pale Ale Malt", "qty": 2.5, "unit": "kg"}},
    {{"type": "houblon", "name": "Cascade", "qty": 25, "unit": "g"}},
    {{"type": "levure", "name": "Safale US-05", "qty": 1, "unit": "sachet"}}
  ],
  "notes": "OG cible, FG cible, température de fermentation, durée, conseils de brassage..."
}}

Règles :
- Types autorisés pour "type" : "malt", "houblon", "levure", "autre"
- Unités pour malts : "kg" ou "g"
- Unités pour houblons : "g"
- Unités pour levures : "sachet", "g" ou "mL"
- Adapte les quantités pour exactement {volume} litres
- Inclus tous les malts, houblons (palier amertume + arôme), et la levure"""

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }).encode('utf-8')
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json",
                                          "x-goog-api-key": api_key},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        # Gemini peut renvoyer promptFeedback sans candidates (safety/quota)
        if 'candidates' not in result:
            feedback = result.get('promptFeedback', {})
            reason   = feedback.get('blockReason', 'Réponse vide de Gemini')
            app.logger.warning(f"Gemini no candidates: {result}")
            return jsonify({'error': f"Gemini : {reason}"}), 502
        text   = result['candidates'][0]['content']['parts'][0]['text']
        recipe = json.loads(text)
        return jsonify(recipe)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        app.logger.warning(f"Gemini HTTPError {e.code}: {body[:400]}")
        try:
            err_msg = json.loads(body).get('error', {}).get('message', body)
        except Exception as e:
            err_msg = body[:300]
        return jsonify({'error': f"Gemini {e.code} : {err_msg}"}), 502
    except urllib.error.URLError as e:
        app.logger.warning(f"Gemini URLError: {e.reason}")
        return jsonify({'error': f"Réseau : {e.reason}"}), 502
    except Exception as e:
        app.logger.exception("Gemini draft-suggest error")
        return jsonify({'error': str(e)}), 500


# ── EXPORT / IMPORT : BROUILLONS ─────────────────────────────────────────────

@app.route('/api/export/drafts')
def export_drafts():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM draft_recipes ORDER BY sort_order ASC, updated_at DESC').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/import/drafts', methods=['POST'])
def import_drafts():
    data = request.json or []
    if isinstance(data, dict):
        data = [data]
    imported = 0
    with get_db() as conn:
        for d in data:
            if not d.get('title'):
                continue
            try:
                conn.execute(
                    '''INSERT INTO draft_recipes
                       (title, style, volume, ingredients, notes, color,
                        target_date, event_label, sort_order, image)
                       VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (d.get('title', 'Brouillon'), d.get('style'), d.get('volume'),
                     d.get('ingredients'), d.get('notes'), d.get('color', '#ff9500'),
                     d.get('target_date'), d.get('event_label'),
                     d.get('sort_order', 0),
                     _shrink_image_b64(d['image']) if _image_too_large(d.get('image')) else d.get('image'))
                )
                imported += 1
            except Exception as e:
                app.logger.warning(f"import_drafts: skipped draft {d.get('title')!r}: {e}")
    return jsonify({'imported': imported})


# ── EXPORT / IMPORT : CALENDRIER (événements personnalisés) ──────────────────

@app.route('/api/export/calendar')
def export_calendar():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM custom_calendar_events ORDER BY event_date').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/import/calendar', methods=['POST'])
def import_calendar():
    data = request.json or []
    if isinstance(data, dict):
        data = [data]
    imported = 0
    with get_db() as conn:
        for ev in data:
            if not ev.get('title') or not ev.get('event_date'):
                continue
            try:
                conn.execute(
                    '''INSERT INTO custom_calendar_events
                       (title, emoji, event_date, color, notes,
                        brew_reminder, telegram_notify, style, recipe_id, draft_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (ev.get('title'), ev.get('emoji', '📅'), ev['event_date'],
                     ev.get('color', '#f59e0b'), ev.get('notes'),
                     ev.get('brew_reminder', 0), ev.get('telegram_notify', 0),
                     ev.get('style'), ev.get('recipe_id'), ev.get('draft_id'))
                )
                imported += 1
            except Exception as e:
                app.logger.warning(f"import_calendar: skipped event {ev.get('title')!r}: {e}")
    return jsonify({'imported': imported})


# ── GLOBAL ERROR HANDLER ─────────────────────────────────────────────────────

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    app.logger.exception(f"Unhandled exception: {e}")
    return jsonify({'error': 'Internal server error'}), 500


# ── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    init_readings_db()
    migrate_db()
    _scheduler.start()
    try:
        reschedule_telegram()
    except Exception as e:
        app.logger.warning(f"Telegram scheduler init error: {e}")
    try:
        reschedule_github_backup()
    except Exception as e:
        app.logger.warning(f"GitHub backup scheduler init error: {e}")
    app.run(host='0.0.0.0', port=5000, debug=False)

