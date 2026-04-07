import os
import sqlite3
import secrets
import json
import urllib.request
from datetime import datetime
from flask import Blueprint, jsonify, request
from db import get_db, get_readings_db, READINGS_DB_PATH
from helpers import _sensor_rate_limit, api_error
from constants import KegStatus

bp = Blueprint('spindles', __name__)

_SODA_KEGS_SELECT = '''
    SELECT k.*,
           b.name AS beer_name,
           br.name AS brew_name
    FROM soda_kegs k
    LEFT JOIN beers b ON k.beer_id = b.id
    LEFT JOIN brews br ON k.brew_id = br.id
'''

_SPINDLE_PATCH_FIELDS: frozenset[str] = frozenset({'name', 'brew_id', 'notes', 'device_type'})

_SPINDLE_SELECT = '''
    SELECT s.*,
           b.name as brew_name,
           lr.gravity        AS last_gravity,
           lr.temperature    AS last_temperature,
           lr.battery        AS last_battery,
           lr.recorded_at    AS last_reading_at,
           (SELECT COUNT(*) FROM rdb.spindle_readings WHERE spindle_id=s.id) AS reading_count
    FROM spindles s
    LEFT JOIN brews b ON s.brew_id=b.id
    LEFT JOIN rdb.spindle_readings lr
        ON lr.id = (SELECT id FROM rdb.spindle_readings WHERE spindle_id=s.id ORDER BY recorded_at DESC LIMIT 1)
'''

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
    ),
    stability AS (
        SELECT spindle_id,
               CASE WHEN COUNT(*) >= 3 AND (MAX(gravity) - MIN(gravity)) <= 0.003 THEN 1 ELSE 0 END AS gravity_stable,
               AVG(gravity) AS stable_gravity_avg
        FROM rdb.spindle_readings
        WHERE recorded_at >= datetime('now', '-3 days')
          AND gravity IS NOT NULL
        GROUP BY spindle_id
    )
    SELECT s.*,
           b.name AS brew_name,
           lr.gravity        AS last_gravity,
           lr.temperature    AS last_temperature,
           lr.battery        AS last_battery,
           lr.recorded_at    AS last_reading_at,
           COALESCE(rc.reading_count, 0) AS reading_count,
           CASE WHEN b.fermenting_since IS NOT NULL
                     AND b.fermenting_since >= datetime('now', '-3 days')
                THEN 0
                ELSE COALESCE(st.gravity_stable, 0)
           END AS gravity_stable,
           st.stable_gravity_avg
    FROM spindles s
    LEFT JOIN brews b ON s.brew_id = b.id
    LEFT JOIN lr ON lr.spindle_id = s.id AND lr.rn = 1
    LEFT JOIN rc ON rc.spindle_id = s.id
    LEFT JOIN stability st ON st.spindle_id = s.id
'''

_TEMP_PATCH_FIELDS: frozenset[str] = frozenset({'name', 'notes', 'temp_min', 'temp_max', 'sensor_type', 'ha_entity', 'ha_entity_hum', 'brew_id'})

_TEMP_SELECT = '''
    SELECT ts.*,
           b.name as brew_name,
           lr.temperature  AS last_temperature,
           lr.humidity     AS last_humidity,
           lr.target_temp  AS last_target_temp,
           lr.hvac_mode    AS last_hvac_mode,
           lr.recorded_at  AS last_reading_at,
           (SELECT COUNT(*) FROM rdb.temperature_readings WHERE sensor_id=ts.id) AS reading_count
    FROM temperature_sensors ts
    LEFT JOIN brews b ON ts.brew_id=b.id
    LEFT JOIN rdb.temperature_readings lr
        ON lr.id = (SELECT id FROM rdb.temperature_readings WHERE sensor_id=ts.id ORDER BY recorded_at DESC LIMIT 1)
'''

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


# ── SODA KEGS ────────────────────────────────────────────────────────────────

@bp.route('/api/soda-kegs', methods=['GET'])
def get_soda_kegs():
    with get_db() as conn:
        rows = conn.execute(
            _SODA_KEGS_SELECT +
            ' ORDER BY COALESCE(k.sort_order, 9999) ASC, k.created_at DESC'
        ).fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/soda-kegs/revisions-due', methods=['GET'])
def kegs_revisions_due():
    """Retourne les kegs non-archivés dont la révision est dépassée ou due dans <= days jours (défaut 30)."""
    from datetime import date, timedelta
    days = max(0, min(365, int(request.args.get('days', 30))))
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            '''SELECT id, name, keg_type, next_revision_date,
                      julianday(next_revision_date) - julianday('now') AS days_remaining
               FROM soda_kegs
               WHERE archived = 0
                 AND next_revision_date IS NOT NULL
                 AND next_revision_date <= ?
               ORDER BY next_revision_date ASC''',
            (cutoff,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/soda-kegs/reorder', methods=['PUT'])
def reorder_soda_kegs():
    items = request.json or []
    if any(not isinstance(it.get('sort_order'), int) or isinstance(it.get('sort_order'), bool) or it.get('sort_order') < 0
           for it in items if it.get('id') is not None):
        return api_error('validation', 400, detail='sort_order must be a non-negative integer')
    valid = [(it['sort_order'], it['id']) for it in items
             if it.get('id') is not None and it.get('sort_order') is not None]
    with get_db() as conn:
        conn.executemany('UPDATE soda_kegs SET sort_order=? WHERE id=?', valid)
    return jsonify({'success': True})


@bp.route('/api/soda-kegs', methods=['POST'])
def create_soda_keg():
    d = request.json or {}
    if not (d.get('name') or '').strip():
        return api_error('missing_field', 400, detail='name required')
    with get_db() as conn:
        cur = conn.execute(
            '''INSERT INTO soda_kegs
               (name, keg_type, manufacturer, volume_total, volume_ferment, weight_empty,
                status, current_liters, beer_id, brew_id, notes, color, photo,
                last_revision_date, revision_interval_months, next_revision_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (d.get('name').strip(), d.get('keg_type'), d.get('manufacturer'),
             d.get('volume_total'), d.get('volume_ferment'), d.get('weight_empty'),
             d.get('status', KegStatus.EMPTY), d.get('current_liters'),
             d.get('beer_id'), d.get('brew_id'),
             d.get('notes'), d.get('color', '#f59e0b'), d.get('photo'),
             d.get('last_revision_date') or None,
             d.get('revision_interval_months') or 12,
             d.get('next_revision_date') or None)
        )
        row = conn.execute(
            _SODA_KEGS_SELECT + ' WHERE k.id=?', (cur.lastrowid,)
        ).fetchone()
        if not row:
            return api_error('not_found', 500, detail='keg created but not retrievable')
        return jsonify(dict(row)), 201


@bp.route('/api/soda-kegs/<int:keg_id>', methods=['PUT'])
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
             d.get('status', KegStatus.EMPTY), d.get('current_liters'),
             d.get('beer_id'), d.get('brew_id'),
             d.get('notes'), d.get('color', '#f59e0b'), d.get('photo'),
             d.get('last_revision_date') or None,
             d.get('revision_interval_months') or 12,
             d.get('next_revision_date') or None,
             keg_id)
        )
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        row = conn.execute(
            _SODA_KEGS_SELECT + ' WHERE k.id=?', (keg_id,)
        ).fetchone()
        return jsonify(dict(row))


@bp.route('/api/soda-kegs/<int:keg_id>', methods=['DELETE'])
def delete_soda_keg(keg_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM soda_kegs WHERE id=?', (keg_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
        return jsonify({'success': True})


# ── SPINDLES ─────────────────────────────────────────────────────────────────

@bp.route('/api/spindles', methods=['GET'])
def get_spindles():
    with get_db() as conn:
        rows = conn.execute(_SPINDLE_SELECT_LIST + ' ORDER BY COALESCE(s.sort_order, 9999) ASC, s.created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/spindles', methods=['POST'])
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


@bp.route('/api/spindles/<int:spindle_id>', methods=['PATCH'])
def patch_spindle(spindle_id):
    d = request.json or {}
    updates = {col: d[col] for col in _SPINDLE_PATCH_FIELDS if col in d}
    with get_db() as conn:
        # When (re-)assigning a brew, backfill spindle_readings from brew_fermentation_readings
        # so the spindle chart shows the full history even after a COMPLETED migration.
        if 'brew_id' in updates and updates['brew_id']:
            new_brew_id = updates['brew_id']
            ferm_rows = conn.execute(
                '''SELECT recorded_at, gravity, temperature, battery, angle
                   FROM brew_fermentation_readings
                   WHERE brew_id=? AND gravity IS NOT NULL
                   ORDER BY recorded_at''',
                (new_brew_id,)
            ).fetchall()
            conn.execute('DELETE FROM rdb.spindle_readings WHERE spindle_id=?', (spindle_id,))
            if ferm_rows:
                conn.executemany(
                    'INSERT INTO rdb.spindle_readings (spindle_id, recorded_at, gravity, temperature, battery, angle) VALUES (?,?,?,?,?,?)',
                    [(spindle_id, r['recorded_at'], r['gravity'], r['temperature'],
                      r['battery'], r['angle']) for r in ferm_rows]
                )
        if updates:
            sql = 'UPDATE spindles SET ' + ', '.join(f'{col}=?' for col in updates) + ' WHERE id=?'
            conn.execute(sql, [*updates.values(), spindle_id])
        row = conn.execute(_SPINDLE_SELECT + ' WHERE s.id=?', (spindle_id,)).fetchone()
        if not row:
            return api_error('not_found', 404)
        return jsonify(dict(row))


@bp.route('/api/spindles/<int:spindle_id>', methods=['DELETE'])
def delete_spindle(spindle_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM spindles WHERE id=?', (spindle_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
    with get_readings_db() as rconn:
        rconn.execute('DELETE FROM spindle_readings WHERE spindle_id=?', (spindle_id,))
    return jsonify({'success': True})


@bp.route('/api/spindles/reorder', methods=['PUT'])
def reorder_spindles():
    items = request.json or []
    if any(not isinstance(it.get('sort_order'), int) or isinstance(it.get('sort_order'), bool) or it.get('sort_order') < 0
           for it in items if it.get('id') is not None):
        return api_error('validation', 400, detail='sort_order must be a non-negative integer')
    valid = [(it['sort_order'], it['id']) for it in items
             if it.get('id') is not None and it.get('sort_order') is not None]
    with get_db() as conn:
        conn.executemany('UPDATE spindles SET sort_order=? WHERE id=?', valid)
    return jsonify({'success': True})


_READINGS_MAX_LIMIT = 10_000

@bp.route('/api/spindles/<int:spindle_id>/readings', methods=['GET'])
def get_spindle_readings(spindle_id):
    limit   = max(1, min(request.args.get('limit', 2000, type=int) or 2000, _READINGS_MAX_LIMIT))
    hours   = request.args.get('hours',  type=int)
    from_ts = request.args.get('from')
    to_ts   = request.args.get('to')
    # Hard cap on rows fetched from DB to avoid loading millions of rows into memory
    db_limit = _READINGS_MAX_LIMIT
    with get_readings_db() as conn:
        if hours:
            rows = conn.execute(
                "SELECT * FROM spindle_readings WHERE spindle_id=? AND recorded_at >= datetime('now',?) ORDER BY recorded_at ASC LIMIT ?",
                (spindle_id, f'-{hours} hours', db_limit)
            ).fetchall()
        elif from_ts and to_ts:
            rows = conn.execute(
                'SELECT * FROM spindle_readings WHERE spindle_id=? AND recorded_at >= ? AND recorded_at <= ? ORDER BY recorded_at ASC LIMIT ?',
                (spindle_id, from_ts, to_ts, db_limit)
            ).fetchall()
        elif from_ts:
            rows = conn.execute(
                'SELECT * FROM spindle_readings WHERE spindle_id=? AND recorded_at >= ? ORDER BY recorded_at ASC LIMIT ?',
                (spindle_id, from_ts, db_limit)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM spindle_readings WHERE spindle_id=? ORDER BY recorded_at ASC LIMIT ?',
                (spindle_id, db_limit)
            ).fetchall()
        # Decimate uniformly if too many points — preserves curve shape across full range
        if len(rows) > limit:
            step = max(1, len(rows) // limit)
            rows = rows[::step]
        return jsonify([dict(r) for r in rows])


@bp.route('/api/spindle/data', methods=['POST', 'GET'])
def receive_spindle_data():
    d = request.json or {}
    token = request.args.get('token') or d.get('token') or d.get('Token') or ''
    if not token:
        return api_error('missing_token', 401)
    if not _sensor_rate_limit(f's:{token}'):
        return api_error('rate_limited', 429)

    with get_db() as conn:
        spindle = conn.execute(
            'SELECT id, brew_id, device_type FROM spindles WHERE token=?', (token,)
        ).fetchone()
        if not spindle:
            return api_error('invalid_token', 401)
        sid        = spindle['id']
        brew_id    = spindle['brew_id']
        device_type = spindle['device_type'] or 'ispindel'

    import math

    def _f(v):
        try:
            x = float(v) if v is not None else None
            return x if (x is not None and math.isfinite(x)) else None
        except (ValueError, TypeError):
            return None

    def _frange(v, lo, hi):
        x = _f(v)
        return x if (x is not None and lo <= x <= hi) else None

    gravity = _frange(
        d.get('gravity') or d.get('Gravity') or d.get('SG') or
        d.get('specific_gravity') or d.get('og'),
        0.900, 1.200,
    )

    if device_type == 'tilt':
        temp_raw = _frange(d.get('Temp') or d.get('temp'), 32.0, 212.0)  # °F plausible range
        temp_c = round((temp_raw - 32) * 5 / 9, 2) if temp_raw is not None else None
    else:
        temp_c = _frange(
            d.get('temperature') or d.get('Temperature') or d.get('temp') or d.get('celsius'),
            -20.0, 100.0,
        )
        if temp_c is None:
            temp_f = _frange(d.get('temp_f') or d.get('Fahrenheit') or d.get('fahrenheit'), -4.0, 212.0)
            if temp_f is not None:
                temp_c = round((temp_f - 32) * 5 / 9, 2)

    battery = _frange(
        d.get('battery') or d.get('Battery') or
        d.get('battery_level') or d.get('voltage') or d.get('Voltage'),
        0.0, 100.0,
    )
    angle = _frange(d.get('angle') or d.get('Angle') or d.get('tilt'), -90.0, 90.0)

    rssi_raw = d.get('RSSI') or d.get('rssi') or d.get('signal') or d.get('Signal')
    try:
        rssi_int = int(rssi_raw)
        rssi = rssi_int if -150 <= rssi_int <= 0 else None
    except (ValueError, TypeError):
        rssi = None

    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with get_readings_db() as rconn:
        if not brew_id:
            rconn.execute('DELETE FROM spindle_readings WHERE spindle_id=?', (sid,))
        rconn.execute(
            'INSERT INTO spindle_readings (spindle_id,gravity,temperature,battery,angle,rssi,recorded_at) VALUES (?,?,?,?,?,?,?)',
            (sid, gravity, temp_c, battery, angle, rssi, now)
        )
    return jsonify({'ok': True}), 201


@bp.route('/api/spindle/readings/stats')
def spindle_readings_stats():
    with get_readings_db() as conn:
        total  = conn.execute('SELECT COUNT(*) FROM spindle_readings').fetchone()[0]
        oldest = conn.execute('SELECT MIN(recorded_at) FROM spindle_readings').fetchone()[0]
        newest = conn.execute('SELECT MAX(recorded_at) FROM spindle_readings').fetchone()[0]
    size = os.path.getsize(READINGS_DB_PATH) if os.path.exists(READINGS_DB_PATH) else 0
    return jsonify({'total': total, 'oldest': oldest, 'newest': newest, 'db_size': size})


@bp.route('/api/spindle/readings/purge', methods=['DELETE'])
def purge_spindle_readings():
    days = request.args.get('days', 30, type=int)
    with get_readings_db() as conn:
        cur = conn.execute(
            "DELETE FROM spindle_readings WHERE recorded_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        deleted = cur.rowcount
        remaining = conn.execute('SELECT COUNT(*) FROM spindle_readings').fetchone()[0]
    vac = sqlite3.connect(READINGS_DB_PATH)
    try:
        vac.isolation_level = None
        vac.execute('VACUUM')
    finally:
        vac.close()
    return jsonify({'deleted': deleted, 'remaining': remaining})


# ── TEMPERATURE SENSORS ───────────────────────────────────────────────────────

@bp.route('/api/temperature', methods=['GET'])
def get_temp_sensors():
    with get_db() as conn:
        rows = conn.execute(_TEMP_SELECT_LIST + ' ORDER BY COALESCE(ts.sort_order,9999) ASC, ts.created_at DESC').fetchall()
        return jsonify([dict(r) for r in rows])


@bp.route('/api/temperature', methods=['POST'])
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


@bp.route('/api/temperature/<int:sensor_id>', methods=['PATCH'])
def patch_temp_sensor(sensor_id):
    d = request.json or {}
    updates = {col: d[col] for col in _TEMP_PATCH_FIELDS if col in d}
    with get_db() as conn:
        # Si on retire l'association d'un brassin, migrer les lectures vers brew_fermentation_readings
        if 'brew_id' in updates and not updates['brew_id']:
            current = conn.execute(
                'SELECT brew_id FROM temperature_sensors WHERE id=?', (sensor_id,)
            ).fetchone()
            if current and current['brew_id']:
                old_brew_id = current['brew_id']
                tr = conn.execute(
                    '''SELECT recorded_at, temperature
                       FROM rdb.temperature_readings WHERE sensor_id=? ORDER BY recorded_at''',
                    (sensor_id,)
                ).fetchall()
                if tr:
                    conn.executemany(
                        '''INSERT INTO brew_fermentation_readings
                           (brew_id, recorded_at, temperature, source)
                           VALUES (?,?,?,'temp_sensor')''',
                        [(old_brew_id, r['recorded_at'], r['temperature']) for r in tr]
                    )
                conn.execute('DELETE FROM rdb.temperature_readings WHERE sensor_id=?', (sensor_id,))
        if updates:
            sql = 'UPDATE temperature_sensors SET ' + ', '.join(f'{col}=?' for col in updates) + ' WHERE id=?'
            conn.execute(sql, [*updates.values(), sensor_id])
        row = conn.execute(_TEMP_SELECT + ' WHERE ts.id=?', (sensor_id,)).fetchone()
        if not row:
            return api_error('not_found', 404)
        return jsonify(dict(row))


@bp.route('/api/temperature/<int:sensor_id>', methods=['DELETE'])
def delete_temp_sensor(sensor_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM temperature_sensors WHERE id=?', (sensor_id,))
        if cur.rowcount == 0:
            return api_error('not_found', 404)
    with get_readings_db() as rconn:
        rconn.execute('DELETE FROM temperature_readings WHERE sensor_id=?', (sensor_id,))
    return jsonify({'success': True})


@bp.route('/api/temperature/reorder', methods=['PUT'])
def reorder_temp_sensors():
    items = request.json or []
    if any(not isinstance(it.get('sort_order'), int) or isinstance(it.get('sort_order'), bool) or it.get('sort_order') < 0
           for it in items if it.get('id') is not None):
        return api_error('validation', 400, detail='sort_order must be a non-negative integer')
    valid = [(it['sort_order'], it['id']) for it in items
             if it.get('id') is not None and it.get('sort_order') is not None]
    with get_db() as conn:
        conn.executemany('UPDATE temperature_sensors SET sort_order=? WHERE id=?', valid)
    return jsonify({'success': True})


@bp.route('/api/temperature/data', methods=['POST', 'GET'])
def receive_temp_data():
    d = request.json or {}
    token = request.args.get('token') or d.get('token') or d.get('Token') or ''
    if not token:
        return api_error('missing_token', 401)
    if not _sensor_rate_limit(f't:{token}'):
        return api_error('rate_limited', 429)

    with get_db() as conn:
        sensor = conn.execute('SELECT id, brew_id FROM temperature_sensors WHERE token=?', (token,)).fetchone()
        if not sensor:
            return api_error('invalid_token', 401)
        sid     = sensor['id']
        brew_id = sensor['brew_id']

    def _f(v):
        try: return float(v) if v is not None else None
        except (ValueError, TypeError): return None

    temperature = _f(d.get('temperature') or d.get('Temperature') or
                     d.get('temp') or d.get('value'))
    if temperature is None:
        temp_f = _f(d.get('temp_f') or d.get('fahrenheit') or d.get('Fahrenheit'))
        if temp_f is not None:
            temperature = round((temp_f - 32) * 5 / 9, 2)
    humidity    = _f(d.get('humidity') or d.get('Humidity') or d.get('hum'))
    target_temp = _f(d.get('target_temp') or d.get('target_temperature') or d.get('setpoint'))
    hvac_mode   = d.get('hvac_mode') or d.get('mode') or None
    if hvac_mode:
        hvac_mode = str(hvac_mode)[:32]

    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with get_readings_db() as rconn:
        if not brew_id:
            rconn.execute('DELETE FROM temperature_readings WHERE sensor_id=?', (sid,))
        rconn.execute(
            'INSERT INTO temperature_readings (sensor_id,temperature,humidity,target_temp,hvac_mode,recorded_at) VALUES (?,?,?,?,?,?)',
            (sid, temperature, humidity, target_temp, hvac_mode, now)
        )
    return jsonify({'ok': True}), 201


@bp.route('/api/temperature/<int:sensor_id>/readings', methods=['GET'])
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


@bp.route('/api/temperature/readings/stats')
def temp_readings_stats():
    with get_readings_db() as conn:
        total  = conn.execute('SELECT COUNT(*) FROM temperature_readings').fetchone()[0]
        oldest = conn.execute('SELECT MIN(recorded_at) FROM temperature_readings').fetchone()[0]
        newest = conn.execute('SELECT MAX(recorded_at) FROM temperature_readings').fetchone()[0]
    size = os.path.getsize(READINGS_DB_PATH) if os.path.exists(READINGS_DB_PATH) else 0
    return jsonify({'total': total, 'oldest': oldest, 'newest': newest, 'db_size': size})


@bp.route('/api/temperature/readings/purge', methods=['DELETE'])
def purge_temp_readings():
    if request.args.get('unassigned'):
        with get_db() as main_conn:
            unassigned_ids = [
                r[0] for r in main_conn.execute(
                    'SELECT id FROM temperature_sensors WHERE brew_id IS NULL'
                ).fetchall()
            ]
        if not unassigned_ids:
            return jsonify({'deleted': 0, 'remaining': 0})
        placeholders = ','.join('?' * len(unassigned_ids))
        with get_readings_db() as conn:
            cur = conn.execute(
                f'''DELETE FROM temperature_readings
                    WHERE sensor_id IN ({placeholders})
                      AND id NOT IN (
                          SELECT id FROM temperature_readings
                          WHERE sensor_id IN ({placeholders})
                          GROUP BY sensor_id
                          HAVING id = MAX(id)
                      )''',
                unassigned_ids * 2
            )
            deleted   = cur.rowcount
            remaining = conn.execute('SELECT COUNT(*) FROM temperature_readings').fetchone()[0]
        return jsonify({'deleted': deleted, 'remaining': remaining})
    days = request.args.get('days', 30, type=int)
    with get_readings_db() as conn:
        cur = conn.execute(
            "DELETE FROM temperature_readings WHERE recorded_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        deleted   = cur.rowcount
        remaining = conn.execute('SELECT COUNT(*) FROM temperature_readings').fetchone()[0]
    return jsonify({'deleted': deleted, 'remaining': remaining})
