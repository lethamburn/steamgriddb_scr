"""Flask app: local web UI for the SteamGridDB Homogenizer.

The SteamGridDB API key is supplied by the browser on every request and is
used in-memory only for the duration of that request/background job. It is
never written to disk, never logged, and never stored server-side.
"""

import os
import threading
import time

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

import downloader
from sgdb_client import validate_key
from steam_library import get_installed_games

app = Flask(__name__)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid_output")

MAX_LOG_ENTRIES = 500
LOG_ENTRIES_RETURNED = 150


class ProgressTracker:
    """Thread-safe state shared between the background worker and the API."""

    def __init__(self):
        self.lock = threading.Lock()
        self._reset()

    def _reset(self):
        self.running = False
        self.total = 0
        self.processed = 0
        self.current_game = None
        self.log = []
        self.summary = None
        self.error = None
        self.cancelled = False

    def start(self, total):
        with self.lock:
            self._reset()
            self.running = True
            self.total = total

    def set_total(self, total):
        with self.lock:
            self.total = total

    def set_current_game(self, appid, name):
        with self.lock:
            self.current_game = {"appid": appid, "name": name}

    def log_event(self, game_name, asset_label, status, author, appid=None, image=None):
        with self.lock:
            self.log.append({
                "game": game_name,
                "asset": asset_label,
                "status": status,
                "author": author,
                "appid": appid,
                "image": image,
                "ts": time.time(),
            })
            if len(self.log) > MAX_LOG_ENTRIES:
                self.log = self.log[-MAX_LOG_ENTRIES:]

    def increment_processed(self):
        with self.lock:
            self.processed += 1

    def is_cancelled(self):
        with self.lock:
            return self.cancelled

    def cancel(self):
        with self.lock:
            self.cancelled = True

    def finish(self, summary):
        with self.lock:
            self.running = False
            self.summary = summary

    def fail(self, message):
        with self.lock:
            self.running = False
            self.error = message

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "total": self.total,
                "processed": self.processed,
                "current_game": self.current_game,
                "log": list(self.log[-LOG_ENTRIES_RETURNED:]),
                "summary": self.summary,
                "error": self.error,
            }


progress = ProgressTracker()
download_lock = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/detect-library", methods=["POST"])
def api_detect_library():
    data = request.get_json(silent=True) or {}
    manual_path = (data.get("manual_path") or "").strip() or None
    try:
        games, steamapps_dirs = get_installed_games(manual_path)
    except Exception as exc:
        return jsonify({"error": f"Error al detectar la biblioteca: {exc}"}), 400

    if not games:
        return jsonify({
            "games": [],
            "count": 0,
            "library_paths": steamapps_dirs,
            "error": "No se encontraron juegos. Indica la ruta de tu carpeta steamapps manualmente.",
        }), 200

    return jsonify({"games": games, "count": len(games), "library_paths": steamapps_dirs})


@app.route("/api/validate-key", methods=["POST"])
def api_validate_key():
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "")
    if not api_key:
        return jsonify({"valid": False, "error": "Falta la API key."}), 400
    valid, error = validate_key(api_key)
    return jsonify({"valid": valid, "error": error})


@app.route("/api/download/start", methods=["POST"])
def api_download_start():
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "")
    games = data.get("games") or []
    preferred_authors = data.get("preferred_authors") or []
    asset_types = [t for t in (data.get("asset_types") or []) if t in downloader.ASSET_TYPES]
    style = data.get("style") or None
    skip_existing = bool(data.get("skip_existing", True))

    if not api_key:
        return jsonify({"error": "Falta la API key."}), 400
    if not games:
        return jsonify({"error": "No hay juegos para procesar. Detecta la biblioteca primero."}), 400
    if not asset_types:
        return jsonify({"error": "Selecciona al menos un tipo de arte."}), 400

    acquired = download_lock.acquire(blocking=False)
    if not acquired:
        return jsonify({"error": "Ya hay una descarga en curso."}), 409

    progress.start(len(games))

    def worker():
        try:
            downloader.run_download(
                games=games,
                api_key=api_key,
                preferred_authors=preferred_authors,
                asset_type_keys=asset_types,
                style=style,
                skip_existing=skip_existing,
                output_dir=OUTPUT_DIR,
                progress=progress,
            )
        except Exception as exc:
            progress.fail(f"Error inesperado durante la descarga: {exc}")
        finally:
            download_lock.release()

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"started": True, "output_dir": OUTPUT_DIR})


@app.route("/api/download/status")
def api_download_status():
    return jsonify(progress.snapshot())


@app.route("/api/download/cancel", methods=["POST"])
def api_download_cancel():
    progress.cancel()
    return jsonify({"cancelled": True})


@app.route("/api/output-info")
def api_output_info():
    return jsonify({"output_dir": OUTPUT_DIR})


@app.route("/media/<path:filename>")
def media(filename):
    # send_from_directory rejects path traversal / absolute paths on its own,
    # scoping every response to files that actually live inside OUTPUT_DIR.
    if not os.path.isdir(OUTPUT_DIR):
        abort(404)
    return send_from_directory(OUTPUT_DIR, filename)


@app.route("/api/gallery")
def api_gallery():
    if not os.path.isdir(OUTPUT_DIR):
        return jsonify({"images": []})
    images = []
    for filename in sorted(os.listdir(OUTPUT_DIR)):
        if not os.path.isfile(os.path.join(OUTPUT_DIR, filename)):
            continue
        info = downloader.classify_filename(filename)
        if info:
            images.append({"filename": filename, **info})
    return jsonify({"images": images})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
