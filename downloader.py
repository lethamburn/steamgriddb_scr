"""Background download orchestrator: picks the best asset per game and author
priority list, then saves it to grid_output/ using Steam's expected naming.
"""

import glob
import os
import time

import requests

from sgdb_client import SGDB_BASE, auth_headers

REQUEST_DELAY = 0.2  # seconds between SteamGridDB API calls
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0

# Asset type key -> SteamGridDB endpoint config + Steam filename suffix.
ASSET_TYPES = {
    "grid_vertical": {
        "label": "Grid vertical",
        "endpoint": "grids",
        "dimensions": "600x900",
        "suffix": "p",
        "style_param": True,
    },
    "grid_horizontal": {
        "label": "Grid horizontal",
        "endpoint": "grids",
        "dimensions": "460x215",
        "suffix": "",
        "style_param": True,
    },
    "hero": {
        "label": "Hero",
        "endpoint": "heroes",
        "dimensions": None,
        "suffix": "_hero",
        "style_param": False,
    },
    "logo": {
        "label": "Logo",
        "endpoint": "logos",
        "dimensions": None,
        "suffix": "_logo",
        "style_param": False,
    },
    "icon": {
        "label": "Icono",
        "endpoint": "icons",
        "dimensions": None,
        "suffix": "_icon",
        "style_param": False,
    },
}

ASSET_ORDER = ["grid_vertical", "grid_horizontal", "hero", "logo", "icon"]


def _api_get(session, url, api_key, params=None):
    """GET with a small delay and exponential backoff on HTTP 429."""
    backoff = INITIAL_BACKOFF
    resp = None
    for _ in range(MAX_RETRIES):
        resp = session.get(url, headers=auth_headers(api_key), params=params, timeout=15)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else backoff
            time.sleep(wait)
            backoff = min(backoff * 2, MAX_BACKOFF)
            continue
        break
    time.sleep(REQUEST_DELAY)
    return resp


def find_sgdb_game_id(session, api_key, steam_appid):
    """Look up a game's SteamGridDB id from its Steam appid. None if not found."""
    url = f"{SGDB_BASE}/games/steam/{steam_appid}"
    resp = _api_get(session, url, api_key)
    if resp is None or resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    if not data.get("success"):
        return None
    d = data.get("data")
    if isinstance(d, list):
        return d[0]["id"] if d else None
    if isinstance(d, dict):
        return d.get("id")
    return None


def fetch_assets(session, api_key, game_id, asset_key, style=None):
    cfg = ASSET_TYPES[asset_key]
    url = f"{SGDB_BASE}/{cfg['endpoint']}/game/{game_id}"
    params = {}
    if cfg["dimensions"]:
        params["dimensions"] = cfg["dimensions"]
    if cfg["style_param"] and style:
        params["styles"] = style
    resp = _api_get(session, url, api_key, params)
    if resp is None or resp.status_code != 200:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    if not data.get("success"):
        return []
    return data.get("data") or []


def select_best(assets, preferred_authors_lower):
    """Pick the best-scoring asset, preferring the first matching author.

    Returns (asset_or_None, source) where source is "preferred" or "fallback".
    """
    if not assets:
        return None, "none"
    for author in preferred_authors_lower:
        matches = [
            a for a in assets
            if (a.get("author") or {}).get("name", "").strip().lower() == author
        ]
        if matches:
            return max(matches, key=lambda a: a.get("score", 0)), "preferred"
    return max(assets, key=lambda a: a.get("score", 0)), "fallback"


def _find_existing(output_dir, appid, suffix):
    pattern = os.path.join(output_dir, f"{appid}{suffix}.*")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def _download_binary(session, url, dest_path):
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    tmp_path = dest_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(resp.content)
    os.replace(tmp_path, dest_path)


def run_download(games, api_key, preferred_authors, asset_type_keys, style,
                  skip_existing, output_dir, progress):
    """Process every game and write chosen assets into output_dir.

    `progress` must implement: set_total, set_current_game, log_event,
    increment_processed, is_cancelled, finish.
    """
    os.makedirs(output_dir, exist_ok=True)
    session = requests.Session()
    preferred_lower = [a.strip().lower() for a in preferred_authors if a.strip()]
    asset_keys = [k for k in ASSET_ORDER if k in asset_type_keys]

    stats = {
        "processed": 0,
        "preferred": 0,
        "fallback": 0,
        "skipped_existing": 0,
        "skipped_no_match": 0,
        "errors": 0,
    }
    progress.set_total(len(games))

    for game in games:
        if progress.is_cancelled():
            break

        appid = game["appid"]
        name = game["name"]
        progress.set_current_game(appid, name)

        game_id = find_sgdb_game_id(session, api_key, appid)
        if not game_id:
            progress.log_event(name, None, "no_match", None)
            stats["skipped_no_match"] += 1
            stats["processed"] += 1
            progress.increment_processed()
            continue

        for asset_key in asset_keys:
            if progress.is_cancelled():
                break
            cfg = ASSET_TYPES[asset_key]

            if skip_existing and _find_existing(output_dir, appid, cfg["suffix"]):
                progress.log_event(name, cfg["label"], "skipped_existing", None)
                stats["skipped_existing"] += 1
                continue

            assets = fetch_assets(session, api_key, game_id, asset_key, style)
            chosen, source = select_best(assets, preferred_lower)
            if not chosen:
                progress.log_event(name, cfg["label"], "no_asset", None)
                continue

            url = chosen.get("url")
            if not url:
                progress.log_event(name, cfg["label"], "no_asset", None)
                continue

            ext = os.path.splitext(url.split("?")[0])[1] or ".png"
            dest_path = os.path.join(output_dir, f"{appid}{cfg['suffix']}{ext}")
            try:
                _download_binary(session, url, dest_path)
            except Exception:
                progress.log_event(name, cfg["label"], "error", None)
                stats["errors"] += 1
                continue

            author_name = (chosen.get("author") or {}).get("name")
            progress.log_event(name, cfg["label"], source, author_name)
            if source == "preferred":
                stats["preferred"] += 1
            else:
                stats["fallback"] += 1

        stats["processed"] += 1
        progress.increment_processed()

    progress.finish(stats)
    return stats
