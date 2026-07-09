"""Steam library detection: locates Steam installs and parses its VDF/ACF files.

Valve's KeyValues format (VDF) is used both by ``libraryfolders.vdf`` and by
``appmanifest_*.acf`` files. This module implements a small, dependency-free
parser for that format plus the filesystem heuristics needed to find a local
Steam installation and enumerate installed games.
"""

import glob
import os
import platform


# ---------------------------------------------------------------------------
# Generic VDF (KeyValues) parser
# ---------------------------------------------------------------------------

def _tokenize(text):
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            tokens.append("".join(buf))
            i = j + 1
            continue
        if c in "{}":
            tokens.append(c)
            i += 1
            continue
        # Unquoted token (uncommon in VDF, but tolerate it).
        j = i
        while j < n and text[j] not in " \t\r\n{}\"":
            j += 1
        tokens.append(text[i:j])
        i = j
    return tokens


def loads(text):
    """Parse a VDF/KeyValues document into a nested dict."""
    tokens = _tokenize(text)
    pos = 0

    def parse_object():
        nonlocal pos
        obj = {}
        while pos < len(tokens):
            tok = tokens[pos]
            if tok == "}":
                pos += 1
                return obj
            key = tok
            pos += 1
            if pos >= len(tokens):
                obj[key] = ""
                break
            nxt = tokens[pos]
            if nxt == "{":
                pos += 1
                obj[key] = parse_object()
            else:
                obj[key] = nxt
                pos += 1
        return obj

    result = {}
    while pos < len(tokens):
        key = tokens[pos]
        pos += 1
        if pos < len(tokens) and tokens[pos] == "{":
            pos += 1
            result[key] = parse_object()
        elif pos < len(tokens):
            result[key] = tokens[pos]
            pos += 1
    return result


# ---------------------------------------------------------------------------
# appmanifest_*.acf / libraryfolders.vdf
# ---------------------------------------------------------------------------

def parse_acf_text(text):
    """Extract {appid, name} from an appmanifest .acf file's contents."""
    data = loads(text)
    app_state = data.get("AppState") or data.get("appstate")
    if not isinstance(app_state, dict):
        return None
    appid = app_state.get("appid")
    name = app_state.get("name")
    if not appid or not name:
        return None
    return {"appid": str(appid), "name": name}


def parse_acf_file(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return parse_acf_text(f.read())


def parse_library_folders_text(text):
    """Extract the list of library root paths from libraryfolders.vdf."""
    data = loads(text)
    root = data.get("libraryfolders") or data.get("LibraryFolders")
    paths = []
    if not isinstance(root, dict):
        return paths
    for key, val in root.items():
        if isinstance(val, dict):
            p = val.get("path")
            if p:
                paths.append(p)
        elif isinstance(val, str) and key.isdigit():
            # Very old library format: "0" "C:\path"
            paths.append(val)
    return paths


def parse_library_folders_file(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return parse_library_folders_text(f.read())


# ---------------------------------------------------------------------------
# Steam install / library discovery
# ---------------------------------------------------------------------------

def get_candidate_steam_paths():
    """Return likely Steam install roots for the current OS that actually exist."""
    system = platform.system()
    candidates = []
    home = os.path.expanduser("~")

    if system == "Windows":
        candidates += [
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
        ]
        try:
            import winreg

            registry_keys = [
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ]
            for hive, subkey in registry_keys:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        value, _ = winreg.QueryValueEx(key, "InstallPath")
                        if value:
                            candidates.insert(0, value)
                except OSError:
                    pass
        except ImportError:
            pass
    elif system == "Darwin":
        candidates.append(os.path.join(home, "Library/Application Support/Steam"))
    else:
        candidates += [
            os.path.join(home, ".steam/steam"),
            os.path.join(home, ".steam/root"),
            os.path.join(home, ".local/share/Steam"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/data/Steam"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam"),
        ]

    seen = set()
    result = []
    for c in candidates:
        if os.path.isdir(c) and c not in seen:
            seen.add(c)
            result.append(c)
    return result


def resolve_steamapps_dir(steam_root):
    steamapps = os.path.join(steam_root, "steamapps")
    if os.path.isdir(steamapps):
        return steamapps
    return None


def get_library_steamapps_dirs(manual_path=None):
    """Return every steamapps/ directory (main + extra libraries) we can find."""
    dirs = []

    if manual_path:
        base = os.path.abspath(os.path.expanduser(manual_path)).rstrip(os.sep)
        if os.path.isdir(base) and os.path.basename(base).lower() == "steamapps":
            dirs.append(base)
        else:
            sa = resolve_steamapps_dir(base)
            if sa:
                dirs.append(sa)
            elif os.path.isdir(base) and glob.glob(os.path.join(base, "appmanifest_*.acf")):
                dirs.append(base)
    else:
        for root in get_candidate_steam_paths():
            sa = resolve_steamapps_dir(root)
            if sa:
                dirs.append(sa)

    all_dirs = list(dirs)
    for sa in dirs:
        lf = os.path.join(sa, "libraryfolders.vdf")
        if os.path.isfile(lf):
            try:
                extra_paths = parse_library_folders_file(lf)
            except Exception:
                extra_paths = []
            for p in extra_paths:
                extra_sa = resolve_steamapps_dir(p)
                if extra_sa and extra_sa not in all_dirs:
                    all_dirs.append(extra_sa)

    seen = set()
    result = []
    for d in all_dirs:
        if d not in seen:
            seen.add(d)
            result.append(d)
    return result


def get_installed_games(manual_path=None):
    """Return (games, steamapps_dirs). games = [{"appid": str, "name": str}, ...]."""
    steamapps_dirs = get_library_steamapps_dirs(manual_path)
    games = {}
    for sa in steamapps_dirs:
        for acf_path in glob.glob(os.path.join(sa, "appmanifest_*.acf")):
            try:
                info = parse_acf_file(acf_path)
            except Exception:
                info = None
            if info:
                games[info["appid"]] = info["name"]

    result = [{"appid": appid, "name": name} for appid, name in games.items()]
    result.sort(key=lambda g: g["name"].lower())
    return result, steamapps_dirs


def find_userdata_ids(steam_root):
    """Return the steamid3 folder names found under <steam_root>/userdata, if any."""
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.isdir(userdata):
        return []
    return sorted(entry for entry in os.listdir(userdata) if entry.isdigit())
