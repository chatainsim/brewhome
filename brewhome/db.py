import sqlite3
import os
import json
import logging as _logging
from flask import g, has_request_context, current_app

_db_logger = _logging.getLogger(__name__)

DB_PATH          = os.path.join(os.path.dirname(__file__), 'brewhome.db')
READINGS_DB_PATH = os.path.join(os.path.dirname(__file__), 'brewhome_readings.db')
PHOTOS_DIR       = os.path.join(os.path.dirname(__file__), 'data', 'brew_photos')


def _ensure_readings_db_exists():
    """Ensure the readings DB file exists with its tables before attaching it."""
    if not os.path.exists(READINGS_DB_PATH):
        try:
            init_readings_db()
        except Exception as exc:
            _db_logger.warning('_ensure_readings_db_exists: could not initialize readings DB: %s', exc)


def _open_main_db():
    """Ouvre et configure une connexion SQLite principale."""
    _ensure_readings_db_exists()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("ATTACH DATABASE ? AS rdb", (READINGS_DB_PATH,))
    return conn


def _open_readings_db():
    """Ouvre et configure une connexion SQLite mesures densimètre."""
    conn = sqlite3.connect(READINGS_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_db():
    """Connexion principale — réutilisée pendant toute la durée de la requête."""
    if has_request_context():
        if 'db' not in g:
            g.db = _open_main_db()
        return g.db
    return _open_main_db()


def get_readings_db():
    """Connexion mesures densimètre — réutilisée pendant toute la durée de la requête."""
    if has_request_context():
        if 'readings_db' not in g:
            g.readings_db = _open_readings_db()
        return g.readings_db
    return _open_readings_db()


def close_db(e=None):
    """Ferme les connexions en fin de requête."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
    rdb = g.pop('readings_db', None)
    if rdb is not None:
        rdb.close()


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
        except Exception:
            pass  # colonne déjà existante
        _seed_catalog(conn)
        _seed_catalog_extras(conn)
        _seed_bjcp(conn)


# ── Migrations versionnées ────────────────────────────────────────────────────
# Règles :
#   • Ne jamais modifier ni supprimer une entrée existante.
#   • Toujours ajouter les nouvelles migrations À LA FIN de la liste.
#   • La version stockée dans schema_version correspond au dernier index appliqué.
#     Une migration n'est donc jamais appliquée deux fois.

_MIGRATIONS = [
    # 01
    "ALTER TABLE inventory_items ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
    # 02
    "ALTER TABLE recipes ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
    # 03
    "ALTER TABLE brews ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
    # 04
    "ALTER TABLE brews ADD COLUMN ferm_time INTEGER",
    # 05
    "ALTER TABLE beers ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
    # 06
    "ALTER TABLE beers ADD COLUMN initial_33cl INTEGER NOT NULL DEFAULT 0",
    # 07
    "ALTER TABLE beers ADD COLUMN initial_75cl INTEGER NOT NULL DEFAULT 0",
    # 08
    "ALTER TABLE recipes ADD COLUMN ferm_temp REAL",
    # 09
    "ALTER TABLE recipes ADD COLUMN ferm_time INTEGER",
    # 10
    "ALTER TABLE recipe_ingredients ADD COLUMN other_type TEXT",
    # 11
    "ALTER TABLE recipe_ingredients ADD COLUMN other_time REAL",
    # 12
    "ALTER TABLE beers ADD COLUMN brew_date DATE",
    # 13
    "ALTER TABLE beers ADD COLUMN bottling_date DATE",
    # 14
    "ALTER TABLE ingredient_catalog ADD COLUMN temp_min REAL",
    # 15
    "ALTER TABLE ingredient_catalog ADD COLUMN temp_max REAL",
    # 16
    "ALTER TABLE ingredient_catalog ADD COLUMN dosage_per_liter REAL",
    # 17
    "ALTER TABLE ingredient_catalog ADD COLUMN attenuation_min REAL",
    # 18
    "ALTER TABLE ingredient_catalog ADD COLUMN attenuation_max REAL",
    # 19
    "ALTER TABLE ingredient_catalog ADD COLUMN alcohol_tolerance REAL",
    # 20
    "ALTER TABLE ingredient_catalog ADD COLUMN max_usage_pct REAL",
    # 21
    "ALTER TABLE ingredient_catalog ADD COLUMN aroma_spec TEXT",
    # 22
    "ALTER TABLE inventory_items ADD COLUMN price_per_unit REAL",
    # 23
    "ALTER TABLE recipes ADD COLUMN rating INTEGER",
    # 24
    "ALTER TABLE spindles ADD COLUMN sort_order INTEGER DEFAULT 0",
    # 25
    "ALTER TABLE recipes ADD COLUMN sort_order INTEGER DEFAULT 0",
    # 26
    "ALTER TABLE recipes ADD COLUMN draft_id INTEGER REFERENCES draft_recipes(id) ON DELETE SET NULL",
    # 27
    "ALTER TABLE brews ADD COLUMN sort_order INTEGER DEFAULT 0",
    # 28
    "ALTER TABLE beers ADD COLUMN sort_order INTEGER DEFAULT 0",
    # 29
    "ALTER TABLE inventory_items ADD COLUMN sort_order INTEGER DEFAULT 0",
    # 30
    "ALTER TABLE spindles ADD COLUMN device_type TEXT NOT NULL DEFAULT 'ispindel'",
    # 31
    "ALTER TABLE spindles ADD COLUMN stable_notif_at TEXT",
    # 32
    "ALTER TABLE temperature_sensors ADD COLUMN sensor_type TEXT NOT NULL DEFAULT 'sensor'",
    # 33
    "ALTER TABLE temperature_sensors ADD COLUMN ha_entity TEXT",
    # 34
    "ALTER TABLE temperature_sensors ADD COLUMN ha_entity_hum TEXT",
    # 35
    "ALTER TABLE temperature_sensors ADD COLUMN brew_id INTEGER REFERENCES brews(id) ON DELETE SET NULL",
    # 36
    "ALTER TABLE beers ADD COLUMN keg_liters REAL",
    # 37
    "ALTER TABLE beers ADD COLUMN keg_initial_liters REAL",
    # 38
    "ALTER TABLE beers ADD COLUMN taste_appearance TEXT",
    # 39
    "ALTER TABLE beers ADD COLUMN taste_aroma TEXT",
    # 40
    "ALTER TABLE beers ADD COLUMN taste_flavor TEXT",
    # 41
    "ALTER TABLE beers ADD COLUMN taste_bitterness TEXT",
    # 42
    "ALTER TABLE beers ADD COLUMN taste_mouthfeel TEXT",
    # 43
    "ALTER TABLE beers ADD COLUMN taste_overall TEXT",
    # 44
    "ALTER TABLE beers ADD COLUMN taste_finish TEXT",
    # 45
    "ALTER TABLE beers ADD COLUMN taste_rating INTEGER",
    # 46
    "ALTER TABLE beers ADD COLUMN taste_date TEXT",
    # 47
    "ALTER TABLE beers ADD COLUMN taste_score_appearance INTEGER",
    # 48
    "ALTER TABLE beers ADD COLUMN taste_score_aroma INTEGER",
    # 49
    "ALTER TABLE beers ADD COLUMN taste_score_flavor INTEGER",
    # 50
    "ALTER TABLE beers ADD COLUMN taste_score_bitterness INTEGER",
    # 51
    "ALTER TABLE beers ADD COLUMN taste_score_mouthfeel INTEGER",
    # 52
    "ALTER TABLE beers ADD COLUMN taste_score_finish INTEGER",
    # 53
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
    # 54 — no-op sur installations neuves (colonne déjà dans le CREATE TABLE #53)
    "ALTER TABLE draft_recipes ADD COLUMN target_date TEXT",
    # 55 — idem
    "ALTER TABLE draft_recipes ADD COLUMN event_label TEXT",
    # 56
    "ALTER TABLE draft_recipes ADD COLUMN sort_order INTEGER DEFAULT 0",
    # 57
    "ALTER TABLE draft_recipes ADD COLUMN image TEXT",
    # 58
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
    # 59
    "ALTER TABLE custom_calendar_events ADD COLUMN style TEXT",
    # 60
    "ALTER TABLE custom_calendar_events ADD COLUMN recipe_id INTEGER",
    # 61
    "ALTER TABLE custom_calendar_events ADD COLUMN draft_id INTEGER",
    # 62
    "ALTER TABLE custom_calendar_events ADD COLUMN recurrence TEXT",
    # 63
    "ALTER TABLE custom_calendar_events ADD COLUMN brew_reminder_days INTEGER",
    # 64
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
    # 65
    "ALTER TABLE soda_kegs ADD COLUMN manufacturer TEXT",
    # 66
    "ALTER TABLE soda_kegs ADD COLUMN next_revision_date TEXT",
    # 67
    "ALTER TABLE soda_kegs ADD COLUMN last_revision_date TEXT",
    # 68
    "ALTER TABLE soda_kegs ADD COLUMN revision_interval_months INTEGER DEFAULT 12",
    # 69
    """CREATE TABLE IF NOT EXISTS activity_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        ts         DATETIME DEFAULT CURRENT_TIMESTAMP,
        category   TEXT NOT NULL,
        action     TEXT NOT NULL,
        label      TEXT NOT NULL,
        entity_id  INTEGER
    )""",
    # 70
    """CREATE TABLE IF NOT EXISTS brew_photos (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        brew_id    INTEGER NOT NULL,
        step       TEXT,
        caption    TEXT,
        photo      TEXT NOT NULL,
        thumb      TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (brew_id) REFERENCES brews(id) ON DELETE CASCADE
    )""",
    # 71
    "CREATE INDEX IF NOT EXISTS idx_bp_brew ON brew_photos(brew_id)",
    # 72
    """CREATE TABLE IF NOT EXISTS consumption_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        beer_id    INTEGER,
        beer_name  TEXT NOT NULL,
        ts         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d', 'now')),
        qty_33cl   INTEGER NOT NULL DEFAULT 0,
        qty_75cl   INTEGER NOT NULL DEFAULT 0,
        keg_liters REAL NOT NULL DEFAULT 0,
        FOREIGN KEY (beer_id) REFERENCES beers(id) ON DELETE SET NULL
    )""",
    # 73
    "CREATE INDEX IF NOT EXISTS idx_clog_ts ON consumption_log(ts)",
    # 74
    "ALTER TABLE inventory_items ADD COLUMN min_stock REAL",
    # 75
    "ALTER TABLE inventory_items ADD COLUMN expiry_date TEXT",
    # 76
    "ALTER TABLE inventory_items ADD COLUMN yeast_type TEXT",
    # 77
    "ALTER TABLE inventory_items ADD COLUMN yeast_mfg_date TEXT",
    # 78
    "ALTER TABLE inventory_items ADD COLUMN yeast_open_date TEXT",
    # 79
    "ALTER TABLE inventory_items ADD COLUMN yeast_generation INTEGER DEFAULT 1",
    # 80
    "ALTER TABLE recipes ADD COLUMN deleted_at TIMESTAMP",
    # 81
    "ALTER TABLE inventory_items ADD COLUMN deleted_at TIMESTAMP",
    # 82
    "ALTER TABLE brews ADD COLUMN deleted_at TIMESTAMP",
    # 83
    "ALTER TABLE brews ADD COLUMN batch_number INTEGER",
    # 84
    "ALTER TABLE beers ADD COLUMN deleted_at TIMESTAMP",
    # 85
    "ALTER TABLE beers ADD COLUMN refermentation INTEGER NOT NULL DEFAULT 0",
    # 86
    "ALTER TABLE beers ADD COLUMN refermentation_days INTEGER",
    # 87
    """CREATE TABLE IF NOT EXISTS checklist_templates (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        description TEXT,
        items       TEXT NOT NULL DEFAULT '[]',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    # 88
    "CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity_log(ts DESC)",
    # 89
    """CREATE TABLE IF NOT EXISTS recipe_history (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        saved_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        snapshot  TEXT NOT NULL,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
    )""",
    # 90
    "CREATE INDEX IF NOT EXISTS idx_rh_recipe ON recipe_history(recipe_id, saved_at DESC)",
    # 91
    """CREATE TABLE IF NOT EXISTS brew_checklists (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        brew_id       INTEGER NOT NULL,
        template_id   INTEGER,
        checked_items TEXT NOT NULL DEFAULT '[]',
        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(brew_id),
        FOREIGN KEY (brew_id)     REFERENCES brews(id) ON DELETE CASCADE,
        FOREIGN KEY (template_id) REFERENCES checklist_templates(id) ON DELETE SET NULL
    )""",
    # 92
    "ALTER TABLE brew_fermentation_readings ADD COLUMN source TEXT NOT NULL DEFAULT 'spindle'",
    # 93
    "ALTER TABLE brew_fermentation_readings ADD COLUMN notes TEXT",
    # 94
    "ALTER TABLE recipes ADD COLUMN ferm_profile TEXT",
    # 95
    """CREATE TABLE IF NOT EXISTS brew_log (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        brew_id INTEGER NOT NULL,
        ts      TIMESTAMP NOT NULL,
        step    TEXT,
        note    TEXT NOT NULL,
        FOREIGN KEY (brew_id) REFERENCES brews(id) ON DELETE CASCADE
    )""",
    # 96
    "CREATE INDEX IF NOT EXISTS idx_recipes_deleted   ON recipes(deleted_at)",
    # 97
    "CREATE INDEX IF NOT EXISTS idx_inventory_deleted ON inventory_items(deleted_at)",
    # 98
    "CREATE INDEX IF NOT EXISTS idx_brews_archived    ON brews(archived)",
    # 99
    "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('default_brew_reminder_days', '45')",
    # 100
    "CREATE INDEX IF NOT EXISTS idx_brews_deleted     ON brews(deleted_at)",
    # 101
    "CREATE INDEX IF NOT EXISTS idx_beers_deleted     ON beers(deleted_at)",
    # 102
    "CREATE INDEX IF NOT EXISTS idx_beers_archived    ON beers(archived)",
    # 103
    "CREATE INDEX IF NOT EXISTS idx_inventory_archived ON inventory_items(archived)",
    # 104
    "CREATE INDEX IF NOT EXISTS idx_recipes_archived  ON recipes(archived)",
    # 105
    "CREATE INDEX IF NOT EXISTS idx_soda_kegs_archived ON soda_kegs(archived)",
    # 106 — recréer brew_photos : photo/thumb nullable, + colonnes photo_file/thumb_file
    """CREATE TABLE IF NOT EXISTS brew_photos_new (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        brew_id    INTEGER NOT NULL,
        step       TEXT,
        caption    TEXT,
        photo      TEXT,
        thumb      TEXT,
        photo_file TEXT,
        thumb_file TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (brew_id) REFERENCES brews(id) ON DELETE CASCADE
    )""",
    # 107
    "INSERT OR IGNORE INTO brew_photos_new SELECT id, brew_id, step, caption, photo, thumb, NULL, NULL, created_at FROM brew_photos",
    # 108
    "DROP TABLE IF EXISTS brew_photos",
    # 109
    "ALTER TABLE brew_photos_new RENAME TO brew_photos",
    # 110
    "CREATE INDEX IF NOT EXISTS idx_bp_brew ON brew_photos(brew_id)",
    # 111
    "ALTER TABLE brews ADD COLUMN fermenting_since TIMESTAMP",
    # 112
    "ALTER TABLE brews ADD COLUMN photos_url TEXT",
    # 113
    "CREATE INDEX IF NOT EXISTS idx_bfr_brew  ON brew_fermentation_readings(brew_id)",
    # 114
    "CREATE INDEX IF NOT EXISTS idx_blog_brew ON brew_log(brew_id)",
    # 115
    "CREATE INDEX IF NOT EXISTS idx_beers_brew ON beers(brew_id)",
    # 116
    "CREATE INDEX IF NOT EXISTS idx_clog_beer ON consumption_log(beer_id)",
    # 117
    "ALTER TABLE brews ADD COLUMN actual_efficiency REAL",
    # 118
    "ALTER TABLE brews ADD COLUMN cost_snapshot REAL",
    # 119
    "ALTER TABLE brews ADD COLUMN cost_per_liter_snapshot REAL",
    # 120
    "ALTER TABLE brews ADD COLUMN dryhop_done_dates TEXT",
    # 121
    """CREATE TABLE IF NOT EXISTS inventory_log (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        inventory_item_id INTEGER NOT NULL,
        ts                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        delta             REAL NOT NULL,
        old_qty           REAL,
        new_qty           REAL,
        reason            TEXT,
        entity_type       TEXT,
        entity_id         INTEGER,
        entity_label      TEXT
    )""",
    # 122
    "CREATE INDEX IF NOT EXISTS idx_invlog_item ON inventory_log(inventory_item_id, ts DESC)",
    # ── Ajouter les nouvelles migrations ci-dessous ───────────────────────────
]

_READINGS_MIGRATIONS = [
    # 01
    "ALTER TABLE temperature_readings ADD COLUMN target_temp REAL",
    # 02
    "ALTER TABLE temperature_readings ADD COLUMN hvac_mode TEXT",
    # 03 — index couvrant pour le CTE stability (recorded_at range + GROUP BY spindle_id + gravity)
    "CREATE INDEX IF NOT EXISTS idx_sr_stability ON spindle_readings(recorded_at, spindle_id, gravity)",
    # ── Ajouter les nouvelles migrations ci-dessous ───────────────────────────
]


def _apply_versioned_migrations(conn, migrations, label='main'):
    """Crée schema_version si absent, puis applique chaque migration dont
    le numéro est supérieur à la version courante. La version est mise à
    jour après chaque migration (succès ou échec), garantissant qu'aucune
    migration n'est exécutée deux fois."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS schema_version (
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL DEFAULT 0
        )
    ''')
    conn.execute('INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, 0)')
    current = conn.execute('SELECT version FROM schema_version').fetchone()['version']
    for i, sql in enumerate(migrations, start=1):
        if i <= current:
            continue
        try:
            conn.execute(sql)
        except Exception as e:
            current_app.logger.debug(f"migration [{label}] #{i:03d}: {e}")
        conn.execute('UPDATE schema_version SET version=? WHERE id=1', (i,))
    total = len(migrations)
    if current < total:
        current_app.logger.info(
            f"DB [{label}] migrée de v{current} → v{total}"
        )


def migrate_db():
    with get_db() as conn:
        _apply_versioned_migrations(conn, _MIGRATIONS, label='main')
        # Backfill idempotent : initial counts pour les bières existantes
        conn.execute('UPDATE beers SET initial_33cl=stock_33cl WHERE initial_33cl=0 AND stock_33cl>0')
        conn.execute('UPDATE beers SET initial_75cl=stock_75cl WHERE initial_75cl=0 AND stock_75cl>0')
        # Migration données : déplacer spindle_readings → brewhome_readings.db
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
        except sqlite3.OperationalError:
            pass  # table absente = déjà migrée ou installation neuve
    with get_readings_db() as rconn:
        _apply_versioned_migrations(rconn, _READINGS_MIGRATIONS, label='readings')


def _log(category, action, label, entity_id=None, conn=None):
    """Insert an activity log entry. Fails silently — never blocks business logic."""
    try:
        sql  = 'INSERT INTO activity_log (category, action, label, entity_id) VALUES (?,?,?,?)'
        args = (category, action, label, entity_id)
        if conn is not None:
            conn.execute(sql, args)
        else:
            with get_db() as c:
                c.execute(sql, args)
    except Exception as e:
        _db_logger.warning(f'activity_log error: {e}')


def _log_inv(item_id, delta, old_qty, new_qty, reason,
             entity_type=None, entity_id=None, entity_label=None, conn=None):
    """Insert an inventory movement log entry. Fails silently — never blocks business logic."""
    try:
        sql = '''INSERT INTO inventory_log
                    (inventory_item_id, delta, old_qty, new_qty, reason, entity_type, entity_id, entity_label)
                 VALUES (?,?,?,?,?,?,?,?)'''
        args = (item_id, delta, old_qty, new_qty, reason, entity_type, entity_id, entity_label)
        if conn is not None:
            conn.execute(sql, args)
        else:
            with get_db() as c:
                c.execute(sql, args)
    except Exception as e:
        _db_logger.warning('inventory_log error: %s', e)


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
