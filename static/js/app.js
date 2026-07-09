(function () {
  "use strict";

  const API_KEY_STORAGE = "sgdb_api_key";
  const AUTHORS_STORAGE = "sgdb_preferred_authors";

  const state = {
    apiKey: localStorage.getItem(API_KEY_STORAGE) || "",
    authors: safeParseAuthors(localStorage.getItem(AUTHORS_STORAGE)),
    games: [],
    polling: null,
    dragSrcIndex: null,
  };

  function safeParseAuthors(raw) {
    try {
      const parsed = JSON.parse(raw || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      return [];
    }
  }

  const el = (id) => document.getElementById(id);

  function init() {
    el("api-key").value = state.apiKey;
    renderAuthors();
    bindEvents();
    refreshOutputInfo();
    updateStartButtonState();
  }

  function bindEvents() {
    el("api-key").addEventListener("input", onApiKeyInput);
    el("validate-key-btn").addEventListener("click", onValidateKey);
    el("detect-btn").addEventListener("click", onDetectLibrary);
    el("add-author-btn").addEventListener("click", onAddAuthor);
    el("author-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onAddAuthor();
      }
    });
    el("start-btn").addEventListener("click", onStartDownload);
    el("cancel-btn").addEventListener("click", onCancelDownload);
  }

  // --- API key -------------------------------------------------------

  function onApiKeyInput() {
    state.apiKey = el("api-key").value.trim();
    localStorage.setItem(API_KEY_STORAGE, state.apiKey);
    setStatus("key-status", "", "");
    updateStartButtonState();
  }

  function setStatus(id, text, cls) {
    const node = el(id);
    node.textContent = text;
    node.className = "status " + (cls || "");
  }

  async function onValidateKey() {
    if (!state.apiKey) {
      setStatus("key-status", "Introduce una API key primero.", "error");
      return;
    }
    setStatus("key-status", "Validando…", "");
    try {
      const res = await fetch("/api/validate-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: state.apiKey }),
      });
      const data = await res.json();
      if (data.valid) {
        setStatus("key-status", "✓ API key válida.", "ok");
      } else {
        setStatus("key-status", data.error || "API key inválida.", "error");
      }
    } catch (e) {
      setStatus("key-status", "No se pudo contactar con el servidor local.", "error");
    }
  }

  // --- Preferred authors ----------------------------------------------

  function renderAuthors() {
    const list = el("author-list");
    list.innerHTML = "";

    if (state.authors.length === 0) {
      const empty = document.createElement("li");
      empty.className = "author-empty";
      empty.textContent = "Sin autores preferidos todavía. Se usará siempre el asset con mejor puntuación.";
      list.appendChild(empty);
      return;
    }

    state.authors.forEach((author, idx) => {
      const li = document.createElement("li");
      li.className = "author-item";
      li.draggable = true;
      li.dataset.index = String(idx);

      const rank = document.createElement("span");
      rank.className = "author-rank";
      rank.textContent = String(idx + 1);

      const name = document.createElement("span");
      name.className = "author-name";
      name.textContent = author;

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "author-remove";
      removeBtn.textContent = "✕";
      removeBtn.title = "Quitar autor";
      removeBtn.addEventListener("click", () => removeAuthor(idx));

      li.appendChild(rank);
      li.appendChild(name);
      li.appendChild(removeBtn);

      li.addEventListener("dragstart", onDragStart);
      li.addEventListener("dragover", onDragOver);
      li.addEventListener("drop", onDrop);
      li.addEventListener("dragend", onDragEnd);

      list.appendChild(li);
    });
  }

  function persistAuthors() {
    localStorage.setItem(AUTHORS_STORAGE, JSON.stringify(state.authors));
  }

  function onAddAuthor() {
    const input = el("author-input");
    const name = input.value.trim();
    if (!name) return;
    if (state.authors.some((a) => a.toLowerCase() === name.toLowerCase())) {
      input.value = "";
      return;
    }
    state.authors.push(name);
    persistAuthors();
    renderAuthors();
    input.value = "";
    input.focus();
  }

  function removeAuthor(idx) {
    state.authors.splice(idx, 1);
    persistAuthors();
    renderAuthors();
  }

  function onDragStart(e) {
    state.dragSrcIndex = Number(e.currentTarget.dataset.index);
    e.currentTarget.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(state.dragSrcIndex));
  }

  function onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }

  function onDrop(e) {
    e.preventDefault();
    const targetIndex = Number(e.currentTarget.dataset.index);
    if (state.dragSrcIndex === null || state.dragSrcIndex === targetIndex) return;
    const [moved] = state.authors.splice(state.dragSrcIndex, 1);
    state.authors.splice(targetIndex, 0, moved);
    persistAuthors();
    renderAuthors();
  }

  function onDragEnd(e) {
    e.currentTarget.classList.remove("dragging");
    state.dragSrcIndex = null;
  }

  // --- Library detection ----------------------------------------------

  async function onDetectLibrary() {
    const manualPath = el("manual-path").value.trim();
    setStatus("detect-status", "Buscando biblioteca de Steam…", "");
    el("detect-btn").disabled = true;
    try {
      const res = await fetch("/api/detect-library", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manual_path: manualPath }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus("detect-status", data.error || "Error al detectar la biblioteca.", "error");
        return;
      }
      state.games = data.games || [];
      if (state.games.length === 0) {
        setStatus("detect-status", data.error || "No se encontraron juegos.", "error");
      } else {
        setStatus(
          "detect-status",
          `✓ ${data.count} juego(s) detectado(s) en ${data.library_paths.length} biblioteca(s).`,
          "ok"
        );
      }
      renderGamesPreview();
      updateStartButtonState();
    } catch (e) {
      setStatus("detect-status", "No se pudo contactar con el servidor local.", "error");
    } finally {
      el("detect-btn").disabled = false;
    }
  }

  function renderGamesPreview() {
    const box = el("games-preview");
    if (!state.games.length) {
      box.textContent = "";
      return;
    }
    const names = state.games.slice(0, 8).map((g) => g.name);
    let text = names.join(", ");
    if (state.games.length > 8) text += `, … (+${state.games.length - 8} más)`;
    box.textContent = text;
  }

  function updateStartButtonState() {
    el("start-btn").disabled = state.games.length === 0 || state.polling !== null;
  }

  // --- Download ---------------------------------------------------------

  function getSelectedAssetTypes() {
    return Array.from(document.querySelectorAll(".asset-type:checked")).map((c) => c.value);
  }

  async function onStartDownload() {
    if (!state.apiKey) {
      alert("Introduce tu API key de SteamGridDB antes de continuar.");
      return;
    }
    if (!state.games.length) {
      alert("Detecta primero tu biblioteca de Steam.");
      return;
    }
    const assetTypes = getSelectedAssetTypes();
    if (!assetTypes.length) {
      alert("Selecciona al menos un tipo de arte para descargar.");
      return;
    }

    const style = el("style-select").value;
    const skipExisting = el("skip-existing").checked;

    el("start-btn").disabled = true;
    resetProgressUI();

    try {
      const res = await fetch("/api/download/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: state.apiKey,
          games: state.games,
          preferred_authors: state.authors,
          asset_types: assetTypes,
          style: style || null,
          skip_existing: skipExisting,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.error || "No se pudo iniciar la descarga.");
        el("start-btn").disabled = false;
        return;
      }
      el("output-path").textContent = data.output_dir;
      startPolling();
    } catch (e) {
      alert("No se pudo contactar con el servidor local.");
      el("start-btn").disabled = false;
    }
  }

  async function onCancelDownload() {
    el("cancel-btn").disabled = true;
    try {
      await fetch("/api/download/cancel", { method: "POST" });
    } finally {
      el("cancel-btn").disabled = false;
    }
  }

  function resetProgressUI() {
    el("progress-section").hidden = false;
    el("progress-bar-fill").style.width = "0%";
    el("progress-text").textContent = "Iniciando…";
    el("current-game").textContent = "";
    el("log-list").innerHTML = "";
    el("summary-box").hidden = true;
    el("cancel-btn").hidden = false;
  }

  function startPolling() {
    if (state.polling) clearInterval(state.polling);
    state.polling = setInterval(pollStatus, 1500);
    pollStatus();
  }

  async function pollStatus() {
    try {
      const res = await fetch("/api/download/status");
      const data = await res.json();
      renderStatus(data);
      if (!data.running) {
        clearInterval(state.polling);
        state.polling = null;
        el("cancel-btn").hidden = true;
        updateStartButtonState();
        if (data.summary) renderSummary(data.summary);
        if (data.error) {
          el("progress-text").textContent = "Error: " + data.error;
        }
      }
    } catch (e) {
      // Transient network hiccup: keep polling.
    }
  }

  function renderStatus(data) {
    const pct = data.total ? Math.round((data.processed / data.total) * 100) : 0;
    el("progress-bar-fill").style.width = pct + "%";
    el("progress-text").textContent = `${data.processed} / ${data.total} juegos procesados`;
    if (data.current_game) {
      el("current-game").textContent = "Procesando: " + data.current_game.name;
    }
    renderLog(data.log || []);
  }

  const STATUS_LABELS = {
    preferred: "autor preferido",
    fallback: "fallback (mejor puntuación)",
    no_asset: "sin asset disponible",
    no_match: "juego no encontrado en SteamGridDB",
    skipped_existing: "ya existía, omitido",
    error: "error al descargar",
  };

  function renderLog(log) {
    const list = el("log-list");
    list.innerHTML = "";
    const entries = log.slice().reverse();
    for (const entry of entries) {
      const li = document.createElement("li");
      li.className = "log-entry log-" + entry.status;
      let text = entry.game;
      if (entry.asset) text += ` — ${entry.asset}`;
      text += `: ${STATUS_LABELS[entry.status] || entry.status}`;
      if (entry.author) text += ` (${entry.author})`;
      li.textContent = text;
      list.appendChild(li);
    }
  }

  function renderSummary(summary) {
    const box = el("summary-box");
    box.hidden = false;
    box.innerHTML = "";

    const heading = document.createElement("h3");
    heading.textContent = "Resumen";
    box.appendChild(heading);

    const items = [
      ["Juegos procesados", summary.processed],
      ["Assets de autores preferidos", summary.preferred],
      ["Assets de fallback (mejor puntuación)", summary.fallback],
      ["Ya existentes (omitidos)", summary.skipped_existing],
      ["Juegos sin coincidencia en SteamGridDB", summary.skipped_no_match],
      ["Errores de descarga", summary.errors],
    ];

    const ul = document.createElement("ul");
    for (const [label, value] of items) {
      const li = document.createElement("li");
      const strong = document.createElement("strong");
      strong.textContent = String(value);
      li.appendChild(document.createTextNode(label + ": "));
      li.appendChild(strong);
      ul.appendChild(li);
    }
    box.appendChild(ul);
  }

  async function refreshOutputInfo() {
    try {
      const res = await fetch("/api/output-info");
      const data = await res.json();
      el("output-path").textContent = data.output_dir;
    } catch (e) {
      // Ignore: informational only.
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
