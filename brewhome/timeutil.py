"""Horodatages des relevés : stockés en UTC (« AAAA-MM-JJ HH:MM:SS »), comme ceux des
densimètres et des sondes et comme datetime('now') de SQLite. Une heure saisie sans fuseau
(formulaire datetime-local, anciennes versions de l'appli) est lue dans le fuseau de l'appli."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def app_timezone(conn):
    """Fuseau réglé dans l'appli (paramètre telegram_tz), UTC à défaut ou s'il est invalide."""
    row = conn.execute("SELECT value FROM app_settings WHERE key='telegram_tz'").fetchone()
    try:
        return ZoneInfo(row[0]) if row and row[0] else timezone.utc
    except Exception:
        return timezone.utc


def to_utc_timestamp(value, tz):
    """'2026-10-13T18:14' (heure locale de tz), '…+02:00' ou '…Z' → '2026-10-13 16:14:00' ; None si illisible."""
    s = str(value or '').strip().replace(' ', 'T')
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=tz)
    return d.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
