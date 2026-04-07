import base64
import time
import threading
from flask import current_app, jsonify
from db import get_db


def api_error(code: str, status: int, **extra):
    """Consistent JSON error response.

    Always produces: {"error": "<snake_case_code>", ...extra}

    Use `detail=` for a human-readable explanation (shown in the UI).
    Use named kwargs for structured payloads (fields=, items=, ...).
    Never pass raw exception strings as the code — use 'internal_error'.

    Examples:
        api_error('not_found', 404)
        api_error('validation', 400, fields={'name': 'too long'})
        api_error('missing_field', 400, detail='name is required')
        api_error('internal_error', 500)
    """
    return jsonify({'error': code, **extra}), status

# ── Limite taille image base64 ────────────────────────────────────────────────
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
        current_app.logger.warning(f"_shrink_image_b64 failed: {e}")
        return data_url


# ── Rate limiter capteurs ──────────────────────────────────────────────────────
# Sliding-window par token : 1 requête toutes les SENSOR_RL_MIN_INTERVAL secondes.
SENSOR_RL_MIN_INTERVAL = 30  # secondes
_rl_lock  = threading.Lock()
_rl_cache: dict[str, float] = {}  # token → timestamp dernière requête acceptée
_RL_TTL = 3600  # purge les entrées inactives depuis plus d'1 heure


def _sensor_rate_limit(token: str) -> bool:
    """Retourne True si la requête est autorisée, False si elle doit être rejetée."""
    now = time.monotonic()
    with _rl_lock:
        if len(_rl_cache) > 100:
            expired = [t for t, ts in _rl_cache.items() if now - ts > _RL_TTL]
            for t in expired:
                del _rl_cache[t]
        last = _rl_cache.get(token, 0.0)
        if now - last < SENSOR_RL_MIN_INTERVAL:
            return False
        _rl_cache[token] = now
        return True


# ── Conversion unités ─────────────────────────────────────────────────────────

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


def _to_kg(qty, unit):
    """Convert a solid ingredient quantity to kilograms (BeerXML standard)."""
    q = float(qty or 0)
    u = (unit or '').lower()
    if u == 'kg': return q
    if u == 'mg': return q / 1_000_000
    return q / 1000  # g or fallback


# ── Validation d'entrée ───────────────────────────────────────────────────────

def validate(data: dict, schema: dict) -> dict:
    """Valide les valeurs présentes dans *data* selon *schema*.

    Chaque clé du schéma peut avoir :
        type     — type Python attendu (ex. str, int, (int, float))
        max_len  — longueur maximale pour les chaînes
        min_val  — borne inférieure pour les nombres
        max_val  — borne supérieure pour les nombres

    Retourne un dict {champ: message} pour chaque champ invalide.
    Un dict vide signifie que toutes les valeurs présentes sont valides.
    Les champs absents (None) sont ignorés — la présence est vérifiée
    par les checks `if not d.get(...)` existants dans les routes.
    """
    errors: dict = {}
    for field, rules in schema.items():
        val = data.get(field)
        if val is None:
            continue

        # ── Type ──────────────────────────────────────────────────────────────
        expected = rules.get('type')
        if expected is not None:
            # bool est une sous-classe de int — on l'exclut
            if isinstance(val, bool) or not isinstance(val, expected):
                type_name = (
                    ' ou '.join(t.__name__ for t in expected)
                    if isinstance(expected, tuple)
                    else expected.__name__
                )
                errors[field] = f'doit être de type {type_name}'
                continue

        # ── Longueur (chaînes) ────────────────────────────────────────────────
        if isinstance(val, str):
            max_len = rules.get('max_len')
            if max_len is not None and len(val) > max_len:
                errors[field] = f'max {max_len} caractères'
                continue

        # ── Plage (nombres) ───────────────────────────────────────────────────
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            min_val = rules.get('min_val')
            max_val = rules.get('max_val')
            if min_val is not None and val < min_val:
                errors[field] = f'doit être ≥ {min_val}'
            elif max_val is not None and val > max_val:
                errors[field] = f'doit être ≤ {max_val}'

    return errors


# ── Image filesystem helpers ──────────────────────────────────────────────────

def _b64_to_jpeg_file(data_url: str, path: str, quality: int = 85) -> None:
    """Decode a base64 data URL and save as JPEG file."""
    try:
        from PIL import Image
        import io as _io
        _, b64data = data_url.split(',', 1) if ',' in data_url else ('', data_url)
        img = Image.open(_io.BytesIO(base64.b64decode(b64data))).convert('RGB')
        img.save(path, 'JPEG', quality=quality, optimize=True)
    except Exception as e:
        from flask import current_app
        current_app.logger.warning(f"_b64_to_jpeg_file failed: {e}")
        raise


def _make_thumb_file(data_url: str, path: str, max_px: int = 200) -> None:
    """Create a thumbnail and save as JPEG file."""
    try:
        from PIL import Image
        import io as _io
        _, b64data = data_url.split(',', 1) if ',' in data_url else ('', data_url)
        img = Image.open(_io.BytesIO(base64.b64decode(b64data))).convert('RGB')
        img.thumbnail((max_px, max_px), Image.LANCZOS)
        img.save(path, 'JPEG', quality=55, optimize=True)
    except Exception as e:
        from flask import current_app
        current_app.logger.warning(f"_make_thumb_file failed: {e}")
        raise


# ── Image thumbnail (base64) ──────────────────────────────────────────────────

def _make_thumb(data_url: str, max_px: int = 200) -> str:
    """Returns a small JPEG data URL (longest side ≤ max_px)."""
    try:
        from PIL import Image
        import io as _io
        header, b64data = data_url.split(',', 1) if ',' in data_url else ('data:image/jpeg;base64', data_url)
        img = Image.open(_io.BytesIO(base64.b64decode(b64data))).convert('RGB')
        img.thumbnail((max_px, max_px), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format='JPEG', quality=55, optimize=True)
        return f'data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}'
    except Exception:
        return data_url
