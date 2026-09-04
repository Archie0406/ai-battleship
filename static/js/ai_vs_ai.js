// ai_vs_ai.js — drives /play/ai-vs-ai: configurable autoplay match between
// two AI Commanders, with live per-side telemetry (search / reasoning /
// planning / minimax), whichever applies to that commander's strategy.
(function () {
  const COLS = "ABCDEFGHIJ";

  const boardA = document.getElementById("boardA");
  const boardB = document.getElementById("boardB");
  const turnFlagA = document.getElementById("turnFlagA");
  const turnFlagB = document.getElementById("turnFlagB");
  const agentATag = document.getElementById("agentATag");
  const agentBTag = document.getElementById("agentBTag");
  const aivaiLog = document.getElementById("aivaiLog");
  const telemetryA = document.getElementById("telemetryA");
  const telemetryB = document.getElementById("telemetryB");

  const agentASelect = document.getElementById("agentASelect");
  const agentBSelect = document.getElementById("agentBSelect");

  const hudTurnAgent = document.getElementById("hudTurnAgent");
  const hudMovesA = document.getElementById("hudMovesA");
  const hudMovesB = document.getElementById("hudMovesB");
  const hudHitsA = document.getElementById("hudHitsA");
  const hudHitsB = document.getElementById("hudHitsB");
  const hudMatchStatus = document.getElementById("hudMatchStatus");
  const hudMatchStatusItem = document.getElementById("hudMatchStatusItem");

  const startBtn = document.getElementById("startBtn");
  const pauseBtn = document.getElementById("pauseBtn");
  const stepBtn = document.getElementById("stepBtn");
  const newMatchBtn = document.getElementById("newMatchBtn");
  const speedSlider = document.getElementById("speedSlider");

  const matchOverlay = document.getElementById("matchOverlay");
  const matchCard = document.getElementById("matchCard");
  const matchTitle = document.getElementById("matchTitle");
  const matchSubtitle = document.getElementById("matchSubtitle");
  const matchMovesA = document.getElementById("matchMovesA");
  const matchMovesB = document.getElementById("matchMovesB");
  const matchReplayBtn = document.getElementById("matchReplayBtn");

  let timer = null;
  let running = false;

  function buildGrid(container, size) {
    container.innerHTML = "";
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cell = document.createElement("div");
        cell.className = "cell state-empty";
        cell.dataset.row = r;
        cell.dataset.col = c;
        cell.setAttribute("aria-label", `${COLS[c]}${r + 1}`);
        container.appendChild(cell);
      }
    }
  }

  function buildCoordLabels(colsEl, rowsEl, size) {
    colsEl.innerHTML = "";
    rowsEl.innerHTML = "";
    for (let c = 0; c < size; c++) {
      const span = document.createElement("span");
      span.textContent = COLS[c];
      colsEl.appendChild(span);
    }
    for (let r = 0; r < size; r++) {
      const span = document.createElement("span");
      span.textContent = r + 1;
      rowsEl.appendChild(span);
    }
  }

  function paintGrid(container, grid) {
    grid.forEach((row, r) => {
      row.forEach((state, c) => {
        const cell = container.querySelector(`.cell[data-row="${r}"][data-col="${c}"]`);
        if (cell) cell.className = `cell state-${state}`;
      });
    });
  }

  function flashCell(container, r, c, kind) {
    const cell = container.querySelector(`.cell[data-row="${r}"][data-col="${c}"]`);
    if (!cell) return;
    cell.classList.remove("target-lock", "hit-flash", "miss-flash", "sink-pulse");
    void cell.offsetWidth;
    cell.classList.add(kind);
  }

  function logLine(entry) {
    const actorClass = entry.actor === "a" ? "log-actor-player" : "log-actor-ai";
    const actorLabel = entry.actor === "a" ? "COMMANDER 01" : "COMMANDER 02";
    const coord = `${COLS[entry.cell[1]]}${entry.cell[0] + 1}`;
    let resultText = entry.result.toUpperCase();
    if (entry.ship) resultText += ` (${entry.ship})`;
    return `<span class="${actorClass}">${actorLabel}</span> → ${coord} — ${resultText}`;
  }

  function renderLog(log) {
    aivaiLog.innerHTML = "";
    log.forEach((entry) => {
      const li = document.createElement("li");
      li.innerHTML = logLine(entry);
      aivaiLog.appendChild(li);
    });
    aivaiLog.scrollTop = aivaiLog.scrollHeight;
  }

  function renderHud(state) {
    hudTurnAgent.textContent = state.winner ? "—" : (state.turn === "a" ? "Commander 01" : "Commander 02");
    hudMovesA.textContent = state.moves.a;
    hudMovesB.textContent = state.moves.b;
    hudHitsA.textContent = state.hits.a;
    hudHitsB.textContent = state.hits.b;
    hudMatchStatus.textContent = state.winner ? (state.winner === "a" ? "Commander 01 Wins" : "Commander 02 Wins") : "In Progress";
    hudMatchStatusItem.classList.remove("status-victory", "status-defeat");
    if (state.winner === "b") hudMatchStatusItem.classList.add("status-victory");
    if (state.winner === "a") hudMatchStatusItem.classList.add("status-defeat");

    turnFlagA.textContent = !state.winner && state.turn === "a" ? "Targeting…" : "Standing by";
    turnFlagA.classList.toggle("active", !state.winner && state.turn === "a");
    turnFlagB.textContent = !state.winner && state.turn === "b" ? "Targeting…" : "Standing by";
    turnFlagB.classList.toggle("active", !state.winner && state.turn === "b");
  }

  function showMatchOver(state) {
    if (!state.winner) {
      matchOverlay.classList.remove("show");
      return;
    }
    const bWon = state.winner === "b";
    matchCard.className = "victory-card glass-panel " + (bWon ? "win" : "lose");
    matchTitle.textContent = state.winner === "a" ? "COMMANDER 01 WINS" : "COMMANDER 02 WINS";
    matchSubtitle.textContent = `${state.winner === "a" ? state.agent_a.name : state.agent_b.name} sank the opposing fleet.`;
    matchMovesA.textContent = state.moves.a;
    matchMovesB.textContent = state.moves.b;
    matchOverlay.classList.add("show");
    stopAutoplay();
  }

  // ------------------------------------------------------------------
  // Telemetry rendering: whichever of search/reasoning/planning/minimax
  // this commander's current agent exposes, rendered generically so any
  // future agent type "just works" the moment it sets the matching
  // attribute (see ai/agent.py + game/ai_vs_ai_engine.py's telemetry dict).
  // ------------------------------------------------------------------
  function coord(cell) {
    return `${COLS[cell[1]]}${cell[0] + 1}`;
  }

  function lastOrDash(arr) {
    return arr && arr.length ? arr[arr.length - 1] : "—";
  }

  function renderTelemetryHTML(telemetry) {
    if (!telemetry) {
      return `<p class="placement-hint" style="margin:0;">Awaiting this commander's first move…</p>`;
    }
    const parts = [];

    if (telemetry.search) {
      const s = telemetry.search;
      parts.push(`
        <h4 class="reasoning-col-title" style="margin-bottom:0.6rem;">Search Metrics</h4>
        <div class="tactical-row"><span class="tactical-label">Algorithm</span><span class="tactical-value">${s.algorithm}</span></div>
        <div class="tactical-row"><span class="tactical-label">Nodes Explored</span><span class="tactical-value">${s.nodes_explored}</span></div>
        <div class="tactical-row"><span class="tactical-label">Search Time</span><span class="tactical-value">${s.search_time_ms} ms</span></div>
        <div class="tactical-row"><span class="tactical-label">Search Depth</span><span class="tactical-value">${s.search_depth}</span></div>
        <div class="tactical-row"><span class="tactical-label">Target Selected</span><span class="tactical-value">${coord(s.target)}</span></div>
      `);
    }

    if (telemetry.planning) {
      const p = telemetry.planning;
      const candTxt = (p.candidates || []).map(coord).join(", ") || "—";
      parts.push(`
        <h4 class="reasoning-col-title" style="margin: ${parts.length ? "1rem" : "0"} 0 0.6rem;">Tactical Plan</h4>
        <div class="tactical-row"><span class="tactical-label">Planning State</span><span class="tactical-value">${p.state}</span></div>
        <div class="plan-state-track">
          <span class="plan-node ${p.state === "SEARCH" ? "active" : ""}" data-state="SEARCH">Search</span>
          <span class="plan-arrow">→</span>
          <span class="plan-node ${p.state === "TARGET" ? "active" : ""}" data-state="TARGET">Target</span>
          <span class="plan-arrow">→</span>
          <span class="plan-node ${p.state === "DESTROY" ? "active" : ""}" data-state="DESTROY">Destroy</span>
        </div>
        <div class="tactical-row"><span class="tactical-label">Candidates</span><span class="tactical-value">${candTxt}</span></div>
      `);
    }

    if (telemetry.minimax) {
      const m = telemetry.minimax;
      parts.push(`
        <h4 class="reasoning-col-title" style="margin: ${parts.length ? "1rem" : "0"} 0 0.6rem;">Minimax Engine</h4>
        <div class="tactical-row"><span class="tactical-label">Search Depth</span><span class="tactical-value">${m.search_depth}</span></div>
        <div class="tactical-row"><span class="tactical-label">Nodes Evaluated</span><span class="tactical-value">${m.nodes_evaluated}</span></div>
        <div class="tactical-row"><span class="tactical-label">Nodes Pruned</span><span class="tactical-value accent-cyan">${m.nodes_pruned}</span></div>
        <div class="tactical-row"><span class="tactical-label">Best Action</span><span class="tactical-value">${coord(m.best_action)}</span></div>
        <div class="tactical-row"><span class="tactical-label">Pruning</span><span class="tactical-value">${m.used_alpha_beta ? "Alpha-Beta" : "Exhaustive"}</span></div>
      `);
    }

    if (telemetry.reasoning) {
      const rep = telemetry.reasoning.report;
      parts.push(`
        <h4 class="reasoning-col-title" style="margin: ${parts.length ? "1rem" : "0"} 0 0.6rem;">Knowledge &amp; Reasoning</h4>
        <div class="tactical-row"><span class="tactical-label">Knows</span><span class="tactical-value">${lastOrDash(rep.know)}</span></div>
        <div class="tactical-row"><span class="tactical-label">Infers</span><span class="tactical-value">${lastOrDash(rep.infer)}</span></div>
        <div class="tactical-row"><span class="tactical-label">Will Do</span><span class="tactical-value">${lastOrDash(rep.will_do)}</span></div>
      `);
    }

    if (!parts.length) {
      return `<p class="placement-hint" style="margin:0;">This commander uses direct targeting with no extra telemetry to display.</p>`;
    }
    return parts.join("");
  }

  function applyState(state, animate) {
    paintGrid(boardA, state.board_a.grid);
    paintGrid(boardB, state.board_b.grid);
    agentATag.textContent = state.agent_a.name;
    agentBTag.textContent = state.agent_b.name;
    renderLog(state.log);
    renderHud(state);
    telemetryA.innerHTML = renderTelemetryHTML(state.telemetry_a);
    telemetryB.innerHTML = renderTelemetryHTML(state.telemetry_b);
    showMatchOver(state);

    if (animate && state.last_move) {
      const [r, c] = state.last_move.cell;
      const board = state.last_move.actor === "a" ? boardB : boardA;
      const kind = state.last_move.result === "miss" ? "miss-flash" : state.last_move.result === "sunk" ? "sink-pulse" : "hit-flash";
      flashCell(board, r, c, kind);
    }
  }

  async function newMatch() {
    stopAutoplay();
    matchOverlay.classList.remove("show");
    const res = await fetch("/api/aivai/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_a: agentASelect.value, agent_b: agentBSelect.value }),
    });
    const state = await res.json();
    buildGrid(boardA, state.board_a.size);
    buildGrid(boardB, state.board_b.size);
    buildCoordLabels(document.getElementById("coordColsA"), document.getElementById("coordRowsA"), state.board_a.size);
    buildCoordLabels(document.getElementById("coordColsB"), document.getElementById("coordRowsB"), state.board_b.size);
    applyState(state, false);
  }

  async function stepOnce() {
    const res = await fetch("/api/aivai/step", { method: "POST" });
    const data = await res.json();
    applyState(data.state, true);
    if (data.state.winner) stopAutoplay();
    return data.state;
  }

  function startAutoplay() {
    if (running) return;
    running = true;
    startBtn.disabled = true;
    pauseBtn.disabled = false;
    agentASelect.disabled = true;
    agentBSelect.disabled = true;
    const tick = async () => {
      if (!running) return;
      const state = await stepOnce();
      if (!running || state.winner) return;
      timer = setTimeout(tick, Number(speedSlider.value));
    };
    tick();
  }

  function stopAutoplay() {
    running = false;
    startBtn.disabled = false;
    pauseBtn.disabled = true;
    agentASelect.disabled = false;
    agentBSelect.disabled = false;
    if (timer) clearTimeout(timer);
    timer = null;
  }

  startBtn.addEventListener("click", startAutoplay);
  pauseBtn.addEventListener("click", stopAutoplay);
  stepBtn.addEventListener("click", () => { stopAutoplay(); stepOnce(); });
  newMatchBtn.addEventListener("click", newMatch);
  matchReplayBtn.addEventListener("click", newMatch);

  newMatch();
})();
