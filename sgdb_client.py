"""Thin client for the public SteamGridDB API (v2).

The API key is only ever placed in the Authorization header of outgoing
requests here; it is never written to a file, logged, or echoed back in an
error message. Callers are responsible for keeping it out of logs too.
"""

import requests

SGDB_BASE = "https://www.steamgriddb.com/api/v2"


def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


def validate_key(api_key, session=None, timeout=10):
    """Check whether an API key is accepted by SteamGridDB.

    Returns (valid: bool, error_message: str | None). The error message
    never includes the key itself.
    """
    session = session or requests.Session()
    try:
        resp = session.get(
            f"{SGDB_BASE}/search/autocomplete/portal",
            headers=auth_headers(api_key),
            timeout=timeout,
        )
    except requests.RequestException:
        return False, "No se pudo conectar con SteamGridDB. Comprueba tu conexión a internet."

    if resp.status_code == 200:
        return True, None
    if resp.status_code in (401, 403):
        return False, "La API key fue rechazada por SteamGridDB (no autorizada)."
    return False, f"SteamGridDB devolvió un error inesperado (HTTP {resp.status_code})."
