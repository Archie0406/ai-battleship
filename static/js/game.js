// game.js — drives the /play page: manual ship placement + Human vs AI battle
(function () {
  const COLS = "ABCDEFGHIJ";

  // ---- Setup phase elements ----
  const setupPhaseEl = document.getElementById("setupPhase");
  const setupBoardEl = document.getElementById("setupBoard");
  const setupFlag = document.getElementById("setupFlag");
  const fleetPicker = document.getElementById("fleetPicker");
  const rotateBtn = document.getElementById("rotateBtn");
  const randomizeBtn = document.getElementById("randomizeBtn");
  const resetBtn = document.getElementById("resetBtn");
  const confirmBtn = document.getElementById("confirmBtn");
  const strategySelector = document.getElementById("strategySelector");
  const strategyDesc = document.getElementById("strategyDesc");

  // ---- Battle phase elements ----
  const battlePhaseEl = document.getElementById("battlePhase");
  const playerBoardEl = document.getElementById("playerBoard");
  const aiBoardEl = document.getElementById("aiBoard");
  const playerTurnFlag = document.getElementById("playerTurnFlag");
  const aiTurnFlag = document.getElementById("aiTurnFlag");
  const aiFleetList = document.getElementById("aiFleetList");
  const battleLog = document.getElementById("battleLog");
  const newGameBtn = document.getElementById("newGameBtn");

  // ---- HUD ----
  const hudTurn = document.getElementById("hudTurn");
  const hudShots = document.getElementById("hudShots");
  const hudHits = document.getElementById("hudHits");
  const hudAccuracy = document.getElementById("hudAccuracy");
  const hudShipsRemaining = document.getElementById("hudShipsRemaining");
  const hudStatus = document.getElementById("hudStatus");
  const hudStatusItem = document.getElementById("hudStatusItem");

  // ---- Tactical panel ----
  const tiTurn = document.getElementById("tiTurn");
  const tiStrategy = document.getElementById("tiStrategy");
  const tiLastMove = document.getElementById("tiLastMove");
  const tiResult = document.getElementById("tiResult");
  const tiShipsRemaining = document.getElementById("tiShipsRemaining");
  const tiConfidence = document.getElementById("tiConfidence");
  const tiConfidenceBar = document.getElementById("tiConfidenceBar");
  const tiMoves = document.getElementById("tiMoves");
  const searchMetricsBlock = document.getElementById("searchMetricsBlock");
  const smNodes = document.getElementById("smNodes");
  const smTime = document.getElementById("smTime");
  const smStates = document.getElementById("smStates");
  const smDepth = document.getElementById("smDepth");
  const planningBlock = document.getElementById("planningBlock");
  const planState = document.getElementById("planState");
  const planStateTrack = document.getElementById("planStateTrack");
  const planCandidates = document.getElementById("planCandidates");
  const minimaxBlock = document.getElementById("minimaxBlock");
  const mmDepth = document.getElementById("mmDepth");
  const mmNodes = document.getElementById("mmNodes");
  const mmPruned = document.getElementById("mmPruned");
  const mmBestAction = document.getElementById("mmBestAction");
  const mmMode = document.getElementById("mmMode");
  const reasoningPanel = document.getElementById("reasoningPanel");
  const reasonKnow = document.getElementById("reasonKnow");
  const reasonInfer = document.getElementById("reasonInfer");
  const reasonWillDo = document.getElementById("reasonWillDo");
  const vizToolbar = document.getElementById("vizToolbar");
  const vizSelector = document.getElementById("vizSelector");
  const vizLegend = document.getElementById("vizLegend");

  // ---- Victory overlay ----
  const victoryOverlay = document.getElementById("victoryOverlay");
  const victoryCard = document.getElementById("victoryCard");
  const victoryTitle = document.getElementById("victoryTitle");
  const victorySubtitle = document.getElementById("victorySubtitle");
  const victoryShots = document.getElementById("victoryShots");
  const victoryAccuracy = document.getElementById("victoryAccuracy");
  const victoryReplayBtn = document.getElementById("victoryReplayBtn");

  let selectedShip = null;   // ship name currently selected for placement
  let horizontal = true;     // current placement orientation
  let currentState = null;   // last known engine state
  let vizMode = "off";       // knowledge/probability/candidates board overlay, reasoning strategy only

  function playSound(name) {
    if (window.BattleshipSound && name) window.BattleshipSound.play(name);
  }
  function resultSound(result) {
    if (result === "hit") return "hit";
    if (result === "sunk") return "sink";
    if (result === "miss") return "miss";
    return null;
  }

  // ------------------------------------------------------------------
  // Shared board helpers
  // ------------------------------------------------------------------
  function buildGrid(container, size) {
    container.innerHTML = "";
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cell = document.createElement("div");
        cell.className = "cell state-empty";
        cell.dataset.row = r;
        cell.dataset.col = c;
        cell.setAttribute("role", "button");
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

  function cellAt(container, r, c) {
    return container.querySelector(`.cell[data-row="${r}"][data-col="${c}"]`);
  }

  function flashCell(container, r, c, kind) {
    const cell = cellAt(container, r, c);
    if (!cell) return;
    cell.classList.remove("target-lock", "hit-flash", "miss-flash", "sink-pulse");
    // force reflow so the animation re-triggers even if the same class was just used
    void cell.offsetWidth;
    cell.classList.add(kind);
  }

  // ------------------------------------------------------------------
  // Setup phase
  // ------------------------------------------------------------------
  function cellsFor(r, c, length, horiz) {
    const cells = [];
    for (let i = 0; i < length; i++) {
      cells.push(horiz ? [r, c + i] : [r + i, c]);
    }
    return cells;
  }

  function isOccupied(grid, r, c) {
    return r >= 0 && r < grid.length && c >= 0 && c < grid.length && grid[r][c] === "ship";
  }

  function previewValid(grid, r, c, length, horiz) {
    const cells = cellsFor(r, c, length, horiz);
    const size = grid.length;
    for (const [cr, cc] of cells) {
      if (cr < 0 || cr >= size || cc < 0 || cc >= size) return false;
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (isOccupied(grid, cr + dr, cc + dc)) return false;
        }
      }
    }
    return true;
  }

  function clearPreview() {
    setupBoardEl.querySelectorAll(".cell").forEach((cell) => {
      cell.classList.remove("state-preview-valid", "state-preview-invalid");
    });
  }

  function showPreview(r, c) {
    if (!selectedShip || !currentState) return;
    const ship = currentState.fleet_definition.find((s) => s.name === selectedShip);
    if (!ship) return;
    clearPreview();
    const grid = currentState.player_board.grid;
    const valid = previewValid(grid, r, c, ship.length, horizontal);
    const cells = cellsFor(r, c, ship.length, horizontal);
    cells.forEach(([cr, cc]) => {
      const cell = cellAt(setupBoardEl, cr, cc);
      if (cell) cell.classList.add(valid ? "state-preview-valid" : "state-preview-invalid");
    });
  }

  function renderFleetPicker(state) {
    fleetPicker.innerHTML = "";
    const placedShips = state.player_board.fleet;
    state.fleet_definition.forEach((def) => {
      const placedInfo = placedShips.find((s) => s.name === def.name);
      const isPlaced = placedInfo && placedInfo.cells && placedInfo.cells.length === def.length;

      const chip = document.createElement("div");
      chip.className = "ship-chip" + (isPlaced ? " placed" : "") + (selectedShip === def.name && !isPlaced ? " selected" : "");
      chip.dataset.name = def.name;

      const cellsHtml = Array.from({ length: def.length }).map(() => "<span></span>").join("");
      chip.innerHTML = `
        <span class="chip-name">${def.name}</span>
        <span class="chip-cells">${cellsHtml}</span>
        <span class="chip-status">${isPlaced ? "Placed" : def.length + " cells"}</span>
      `;

      chip.addEventListener("click", () => {
        if (isPlaced) {
          removeShip(def.name);
        } else {
          selectedShip = def.name;
          renderFleetPicker(currentState);
        }
      });

      fleetPicker.appendChild(chip);
    });
  }

  const STRATEGY_DESCRIPTIONS = {
    probability: "Scores every cell by how many consistent ship placements still cover it.",
    random: "Fires at any untried cell with no reasoning — the uninformed baseline.",
    bfs: "Explores the grid breadth-first (FIFO queue) from known hits, or the board center, to reach the nearest untried cell.",
    dfs: "Dives depth-first (LIFO stack) along one direction before backtracking to find an untried cell.",
    astar: "Orders candidates by f(n) = g(n) + h(n): real path cost plus distance to the nearest lead.",
    reasoning: "Maintains a real knowledge base and forward-chains every hit/miss/sunk fact into a candidate-placement probability grid.",
    planning: "Classifies its own tactical state every turn — SEARCH, TARGET, or DESTROY — and acts accordingly.",
    minimax: "Depth-limited Minimax with alpha-beta pruning over MAX (my shot) vs MIN (the hidden fleet, worst-case within what's logically consistent).",
  };

  function renderStrategySelector(state) {
    const locked = state.phase !== "placement";
    strategySelector.classList.toggle("disabled", locked);
    strategySelector.querySelectorAll("button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.strategy === state.ai_strategy_id);
    });
    strategyDesc.textContent = STRATEGY_DESCRIPTIONS[state.ai_strategy_id] || "";
  }

  async function setStrategy(strategy) {
    const res = await fetch("/api/game/set-strategy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy }),
    });
    if (!res.ok) return;
    const data = await res.json();
    currentState = data.state;
    renderStrategySelector(data.state);
  }

  strategySelector.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn || strategySelector.classList.contains("disabled")) return;
    setStrategy(btn.dataset.strategy);
  });

  function renderSetup(state) {
    currentState = state;
    paintGrid(setupBoardEl, state.player_board.grid);
    renderFleetPicker(state);
    renderStrategySelector(state);
    confirmBtn.disabled = !state.player_board.fleet.every((s) => s.cells && s.cells.length === s.length);

    // auto-advance selection to the next unplaced ship
    const nextUnplaced = state.fleet_definition.find((def) => {
      const placed = state.player_board.fleet.find((s) => s.name === def.name);
      return !(placed && placed.cells && placed.cells.length === def.length);
    });
    if (selectedShip && !state.fleet_definition.some((d) => d.name === selectedShip)) {
      selectedShip = null;
    }
    const currentlyPlaced = state.player_board.fleet.find((s) => s.name === selectedShip);
    if (!selectedShip || (currentlyPlaced && currentlyPlaced.cells.length)) {
      selectedShip = nextUnplaced ? nextUnplaced.name : null;
      renderFleetPicker(state);
    }
  }

  async function placeShip(r, c) {
    if (!selectedShip) return;
    const res = await fetch("/api/game/place", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: selectedShip, row: r, col: c, horizontal }),
    });
    const data = await res.json();
    if (!res.ok) {
      setupFlag.textContent = data.error || "Invalid placement";
      setupFlag.classList.add("active");
      setTimeout(() => {
        setupFlag.textContent = "Placing ships";
        setupFlag.classList.remove("active");
      }, 1400);
      return;
    }
    renderSetup(data.state);
    clearPreview();
  }

  async function removeShip(name) {
    const res = await fetch("/api/game/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (res.ok) {
      selectedShip = name;
      renderSetup(data.state);
    }
  }

  async function randomizeFleet() {
    const res = await fetch("/api/game/randomize", { method: "POST" });
    const data = await res.json();
    if (res.ok) renderSetup(data.state);
  }

  async function resetFleet() {
    const res = await fetch("/api/game/reset", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      selectedShip = null;
      renderSetup(data.state);
    }
  }

  async function confirmFleet() {
    const res = await fetch("/api/game/confirm", { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      setupFlag.textContent = data.error || "Place every ship first";
      setupFlag.classList.add("active");
      setTimeout(() => {
        setupFlag.textContent = "Placing ships";
        setupFlag.classList.remove("active");
      }, 1600);
      return;
    }
    enterBattlePhase(data.state);
  }

  setupBoardEl.addEventListener("mousemove", (e) => {
    const cell = e.target.closest(".cell");
    if (!cell) return;
    showPreview(Number(cell.dataset.row), Number(cell.dataset.col));
  });
  setupBoardEl.addEventListener("mouseleave", clearPreview);
  setupBoardEl.addEventListener("click", (e) => {
    const cell = e.target.closest(".cell");
    if (!cell) return;
    placeShip(Number(cell.dataset.row), Number(cell.dataset.col));
  });

  rotateBtn.addEventListener("click", () => {
    horizontal = !horizontal;
    rotateBtn.textContent = horizontal ? "Rotate ↻" : "Rotate ↺ (Vertical)";
  });
  document.addEventListener("keydown", (e) => {
    if (e.key.toLowerCase() === "r" && setupPhaseEl.style.display !== "none") {
      horizontal = !horizontal;
      rotateBtn.textContent = horizontal ? "Rotate ↻" : "Rotate ↺ (Vertical)";
    }
  });
  randomizeBtn.addEventListener("click", randomizeFleet);
  resetBtn.addEventListener("click", resetFleet);
  confirmBtn.addEventListener("click", confirmFleet);

  // ------------------------------------------------------------------
  // Battle phase
  // ------------------------------------------------------------------
  function renderFleetStatus(fleet) {
    aiFleetList.innerHTML = "";
    fleet.forEach((ship) => {
      const li = document.createElement("li");
      if (ship.is_sunk) li.classList.add("sunk");
      li.innerHTML = `<span>${ship.name}</span><span>${ship.is_sunk ? "SUNK" : ship.length + " cells"}</span>`;
      aiFleetList.appendChild(li);
    });
  }

  function logLine(entry) {
    const actorClass = entry.actor === "player" ? "log-actor-player" : "log-actor-ai";
    const actorLabel = entry.actor === "player" ? "YOU" : "AI";
    const coord = `${COLS[entry.cell[1]]}${entry.cell[0] + 1}`;
    let resultText = entry.result.toUpperCase();
    if (entry.ship) resultText += ` (${entry.ship})`;
    return `<span class="${actorClass}">${actorLabel}</span> → ${coord} — ${resultText}`;
  }

  function renderLog(log) {
    battleLog.innerHTML = "";
    log.forEach((entry) => {
      const li = document.createElement("li");
      li.innerHTML = logLine(entry);
      battleLog.appendChild(li);
    });
    battleLog.scrollTop = battleLog.scrollHeight;
  }

  function renderTacticalPanel(state) {
    const winner = state.winner;
    tiTurn.textContent = winner ? "Game Over" : (state.turn === "player" ? "Your Move" : "AI Targeting…");
    tiStrategy.textContent = state.ai_strategy;

    if (state.last_move) {
      const coord = `${COLS[state.last_move.cell[1]]}${state.last_move.cell[0] + 1}`;
      const who = state.last_move.actor === "player" ? "You" : "AI";
      tiLastMove.textContent = `${who} → ${coord}`;
      let result = state.last_move.result.toUpperCase();
      tiResult.textContent = result;
      tiResult.className = "tactical-value " + (result === "MISS" ? "" : result === "SUNK" ? "accent-hit" : "accent-cyan");
    } else {
      tiLastMove.textContent = "—";
      tiResult.textContent = "—";
    }

    tiShipsRemaining.textContent = `${state.ships_remaining.ai} / ${state.ai_board.fleet.length}`;

    if (state.ai_confidence === null || state.ai_confidence === undefined) {
      tiConfidence.textContent = "—";
      tiConfidenceBar.style.width = "0%";
    } else {
      tiConfidence.textContent = state.ai_confidence + "%";
      tiConfidenceBar.style.width = state.ai_confidence + "%";
    }

    tiMoves.textContent = state.moves.ai;

    if (state.search_metrics) {
      searchMetricsBlock.style.display = "block";
      smNodes.textContent = state.search_metrics.nodes_explored;
      smTime.textContent = state.search_metrics.search_time_ms + " ms";
      smStates.textContent = state.search_metrics.states_visited;
      smDepth.textContent = state.search_metrics.search_depth;
    } else {
      searchMetricsBlock.style.display = "none";
    }

    if (state.planning) {
      planningBlock.style.display = "block";
      planState.textContent = state.planning.state;
      planStateTrack.querySelectorAll(".plan-node").forEach((node) => {
        node.classList.toggle("active", node.dataset.state === state.planning.state);
      });
      const candidates = state.planning.candidates || [];
      planCandidates.textContent = candidates.length
        ? candidates.map(([r, c]) => `${COLS[c]}${r + 1}`).join(", ")
        : "—";
    } else {
      planningBlock.style.display = "none";
    }

    if (state.minimax) {
      minimaxBlock.style.display = "block";
      mmDepth.textContent = state.minimax.search_depth;
      mmNodes.textContent = state.minimax.nodes_evaluated;
      mmPruned.textContent = state.minimax.nodes_pruned;
      const [br, bc] = state.minimax.best_action;
      mmBestAction.textContent = `${COLS[bc]}${br + 1}`;
      mmMode.textContent = state.minimax.used_alpha_beta ? "Alpha-Beta (pruned)" : "Exhaustive (no pruning)";
    } else {
      minimaxBlock.style.display = "none";
    }
  }

  function listItems(ul, lines) {
    ul.innerHTML = "";
    lines.forEach((line) => {
      const li = document.createElement("li");
      li.textContent = line;
      ul.appendChild(li);
    });
  }

  function renderReasoningPanel(state) {
    if (!state.reasoning) {
      reasoningPanel.style.display = "none";
      vizToolbar.style.display = "none";
      vizLegend.style.display = "none";
      clearVizOverlay();
      return;
    }
    reasoningPanel.style.display = "block";
    vizToolbar.style.display = "block";
    const report = state.reasoning.report;
    listItems(reasonKnow, report.know);
    listItems(reasonInfer, report.infer);
    listItems(reasonWillDo, report.will_do);
    renderVisualization(state);
  }

  const VIZ_LEGENDS = {
    off: "",
    probability: `
      <span class="legend-item"><span class="legend-swatch sw-kb-heat-prob"></span>Probability intensity</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-highest"></span>Highest probability cell</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-target"></span>Current target</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-possible"></span>Candidate region</span>
    `,
    knowledge: `
      <span class="legend-item"><span class="legend-swatch sw-kb-possible"></span>Possible (candidate covers it)</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-impossible"></span>Impossible (no candidate covers it)</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-priority"></span>Priority (adjacent to a hit)</span>
    `,
    candidates: `
      <span class="legend-item"><span class="legend-swatch sw-kb-heat-candidate"></span>Candidate placement density</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-possible"></span>Covered by ≥1 placement</span>
    `,
  };

  function clearVizOverlay() {
    aiBoardEl.querySelectorAll(".cell").forEach((cell) => {
      cell.classList.remove("kb-possible", "kb-impossible", "kb-priority", "kb-highest", "kb-target", "kb-heat-prob", "kb-heat-candidate");
      cell.style.removeProperty("--kb-heat");
    });
  }

  function renderVisualization(state) {
    clearVizOverlay();
    vizSelector.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.viz === vizMode));

    if (vizMode === "off" || !state.reasoning) {
      vizLegend.style.display = "none";
      vizLegend.innerHTML = "";
      return;
    }
    vizLegend.style.display = "flex";
    vizLegend.innerHTML = VIZ_LEGENDS[vizMode] || "";

    const reasoning = state.reasoning;

    if (vizMode === "probability") {
      let maxPct = 0;
      reasoning.probability_grid.forEach((row) => row.forEach((v) => { if (v > maxPct) maxPct = v; }));
      reasoning.possible_cells.forEach(([r, c]) => {
        const cell = cellAt(aiBoardEl, r, c);
        if (cell) cell.classList.add("kb-possible");
      });
      reasoning.probability_grid.forEach((row, r) => {
        row.forEach((pct, c) => {
          if (pct <= 0) return;
          const cell = cellAt(aiBoardEl, r, c);
          if (!cell) return;
          cell.classList.add("kb-heat-prob");
          cell.style.setProperty("--kb-heat", maxPct > 0 ? pct / maxPct : 0);
          cell.title = `${COLS[c]}${r + 1}: ${pct.toFixed(1)}% probability`;
        });
      });
      if (maxPct > 0) {
        reasoning.probability_grid.forEach((row, r) => {
          row.forEach((pct, c) => {
            if (pct === maxPct) {
              const cell = cellAt(aiBoardEl, r, c);
              if (cell) cell.classList.add("kb-highest");
            }
          });
        });
      }
      if (reasoning.current_target) {
        const [tr, tc] = reasoning.current_target;
        const cell = cellAt(aiBoardEl, tr, tc);
        if (cell) cell.classList.add("kb-target");
      }
    } else if (vizMode === "knowledge") {
      reasoning.possible_cells.forEach(([r, c]) => {
        const cell = cellAt(aiBoardEl, r, c);
        if (cell) cell.classList.add("kb-possible");
      });
      reasoning.impossible_cells.forEach(([r, c]) => {
        const cell = cellAt(aiBoardEl, r, c);
        if (cell) cell.classList.add("kb-impossible");
      });
      reasoning.priority_cells.forEach(([r, c]) => {
        const cell = cellAt(aiBoardEl, r, c);
        if (cell) cell.classList.add("kb-priority");
      });
    } else if (vizMode === "candidates") {
      let maxDensity = 0;
      reasoning.candidate_density_grid.forEach((row) => row.forEach((v) => { if (v > maxDensity) maxDensity = v; }));
      reasoning.possible_cells.forEach(([r, c]) => {
        const cell = cellAt(aiBoardEl, r, c);
        if (cell) cell.classList.add("kb-possible");
      });
      reasoning.candidate_density_grid.forEach((row, r) => {
        row.forEach((density, c) => {
          if (density <= 0) return;
          const cell = cellAt(aiBoardEl, r, c);
          if (!cell) return;
          cell.classList.add("kb-heat-candidate");
          cell.style.setProperty("--kb-heat", maxDensity > 0 ? density / maxDensity : 0);
          cell.title = `${COLS[c]}${r + 1}: ${density} candidate placement(s)`;
        });
      });
    }
  }

  vizSelector.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    vizMode = btn.dataset.viz;
    if (currentState) renderVisualization(currentState);
  });

  function renderHud(state) {
    hudTurn.textContent = state.winner ? "—" : (state.turn === "player" ? "You" : "AI");
    hudShots.textContent = state.moves.player;
    hudHits.textContent = state.hits.player;
    hudAccuracy.textContent = state.accuracy.player + "%";
    hudShipsRemaining.textContent = state.ships_remaining.ai;
    hudStatus.textContent = state.status_label;
    hudStatusItem.classList.remove("status-victory", "status-defeat");
    if (state.winner === "player") hudStatusItem.classList.add("status-victory");
    if (state.winner === "ai") hudStatusItem.classList.add("status-defeat");
  }

  function setTurnFlags(state) {
    const turn = state.winner ? null : state.turn;
    playerTurnFlag.textContent = turn === "player" ? "Your turn — fire!" : "Standing by";
    playerTurnFlag.classList.toggle("active", turn === "player");
    aiTurnFlag.textContent = turn === "ai" ? "AI targeting…" : "Standing by";
    aiTurnFlag.classList.toggle("active", turn === "ai");
    aiBoardEl.classList.toggle("targetable", !state.winner && state.turn === "player");
  }

  function showVictory(state) {
    if (!state.winner) {
      victoryOverlay.classList.remove("show");
      return;
    }
    const won = state.winner === "player";
    victoryCard.className = "victory-card glass-panel " + (won ? "win" : "lose");
    victoryTitle.textContent = won ? "VICTORY" : "DEFEAT";
    victorySubtitle.textContent = won
      ? "Enemy fleet destroyed."
      : "Your fleet has been sunk.";
    victoryShots.textContent = state.moves.player;
    victoryAccuracy.textContent = state.accuracy.player + "%";
    victoryOverlay.classList.add("show");
  }

  function applyBattleState(state, animate) {
    currentState = state;
    paintGrid(playerBoardEl, state.player_board.grid);
    paintGrid(aiBoardEl, state.ai_board.grid);
    renderFleetStatus(state.ai_board.fleet);
    renderLog(state.log);
    setTurnFlags(state);
    renderTacticalPanel(state);
    renderHud(state);
    renderReasoningPanel(state);
    showVictory(state);

    if (animate && state.last_move) {
      const [r, c] = state.last_move.cell;
      const board = state.last_move.actor === "player" ? aiBoardEl : playerBoardEl;
      const kind = state.last_move.result === "miss" ? "miss-flash" : state.last_move.result === "sunk" ? "sink-pulse" : "hit-flash";
      flashCell(board, r, c, kind);
    }
  }

  function enterBattlePhase(state) {
    buildGrid(playerBoardEl, state.player_board.size);
    buildGrid(aiBoardEl, state.ai_board.size);
    buildCoordLabels(document.getElementById("playerCoordCols"), document.getElementById("playerCoordRows"), state.player_board.size);
    buildCoordLabels(document.getElementById("aiCoordCols"), document.getElementById("aiCoordRows"), state.ai_board.size);
    setupPhaseEl.style.display = "none";
    battlePhaseEl.style.display = "block";
    applyBattleState(state, false);
  }

  async function fire(row, col) {
    if (!currentState || currentState.turn !== "player" || currentState.winner) return;
    playSound("select");
    flashCell(aiBoardEl, row, col, "target-lock");
    const res = await fetch("/api/game/fire", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ row, col }),
    });
    if (!res.ok) return;
    const data = await res.json();

    // paint the player's own shot immediately
    playSound(resultSound(data.player_shot.result));
    const state1 = { ...data.state };
    applyBattleState(state1, true);

    // then, if the AI took a chain of shots, briefly reveal each one
    if (data.ai_shots && data.ai_shots.length) {
      for (const shot of data.ai_shots) {
        await new Promise((resolve) => setTimeout(resolve, 260));
        const kind = shot.result === "miss" ? "miss-flash" : shot.result === "sunk" ? "sink-pulse" : "hit-flash";
        flashCell(playerBoardEl, shot.cell[0], shot.cell[1], kind);
        playSound(resultSound(shot.result));
      }
    }
    applyBattleState(data.state, false);
    if (data.state.winner) {
      playSound(data.state.winner === "player" ? "victory" : "defeat");
    }
  }

  aiBoardEl.addEventListener("click", (e) => {
    const cell = e.target.closest(".cell.state-empty");
    if (!cell || !aiBoardEl.classList.contains("targetable")) return;
    fire(Number(cell.dataset.row), Number(cell.dataset.col));
  });

  // ------------------------------------------------------------------
  // New game / restart
  // ------------------------------------------------------------------
  async function newGame() {
    victoryOverlay.classList.remove("show");
    battlePhaseEl.style.display = "none";
    setupPhaseEl.style.display = "block";
    selectedShip = null;
    horizontal = true;
    rotateBtn.textContent = "Rotate ↻";
    vizMode = "off";
    vizSelector.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.viz === "off"));

    const res = await fetch("/api/game/new", { method: "POST" });
    const state = await res.json();
    buildGrid(setupBoardEl, state.player_board.size);
    buildCoordLabels(document.getElementById("setupCoordCols"), document.getElementById("setupCoordRows"), state.player_board.size);
    renderSetup(state);
  }

  newGameBtn.addEventListener("click", newGame);
  victoryReplayBtn.addEventListener("click", newGame);

  newGame();
})();
