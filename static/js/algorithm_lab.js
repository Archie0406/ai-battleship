// algorithm_lab.js — drives the AI Lab: 10 algorithm cards + one shared
// detail view that runs the real algorithm via /api/lab/demo and renders
// whichever visualization/metrics fit it. Explanatory text is static
// (written once, accurate to this exact implementation); every number
// and every board state comes from the live API response.
(function () {
  const COLS = "ABCDEFGHIJ";
  const STATE_MAP = { unknown: "empty", miss: "miss", hit: "hit", sunk: "sunk" };
  const SPEED_MS = { slow: 850, normal: 380, fast: 120 };

  const ALGOS = window.ALGO_CONTENT;


  const METRIC_LABELS = {
    nodes_expanded: "Nodes Expanded", backtracks: "Backtracks", ac3_removed: "AC-3 Removed",
    search_time_ms: "Search Time", solution_found: "Solution Found",
    nodes_explored: "Nodes Explored", states_visited: "States Visited", search_depth: "Search Depth",
    target: "Target Selected", g_target: "g(n)", h_target: "h(n)", f_target: "f(n)",
    confidence: "Confidence", rules_applied: "Rules Applied", possible_cells: "Possible Cells",
    impossible_cells: "Impossible Cells", destroyed_ships: "Destroyed Ships",
    state: "Planning State", candidate_count: "Candidates", cluster_size: "Cluster Size",
    nodes_evaluated: "Nodes Evaluated", nodes_pruned: "Nodes Pruned", best_action: "Best Action",
    used_alpha_beta: "Pruning",
  };

  const algoById = Object.fromEntries(ALGOS.map((a) => [a.id, a]));
  let currentAlgo = null;
  let currentResult = null;

  // ------------------------------------------------------------------
  // DOM refs
  // ------------------------------------------------------------------
  const cardGrid = document.getElementById("algoCardGrid");
  const detailView = document.getElementById("detailView");
  const detailIcon = document.getElementById("detailIcon");
  const detailCategory = document.getElementById("detailCategory");
  const detailName = document.getElementById("detailName");
  const detailShortDesc = document.getElementById("detailShortDesc");
  const paneWhatItIs = document.getElementById("paneWhatItIs");
  const paneHowItWorks = document.getElementById("paneHowItWorks");
  const paneUsedInBattleship = document.getElementById("paneUsedInBattleship");
  const paneWhy = document.getElementById("paneWhy");
  const detailTabs = document.querySelectorAll(".detail-tab");
  const detailPanes = document.querySelectorAll(".detail-pane");
  const speedControlGroup = document.getElementById("speedControlGroup");
  const speedSelector = document.getElementById("speedSelector");
  const newScenarioBtn = document.getElementById("newScenarioBtn");
  const runDemoBtn = document.getElementById("runDemoBtn");
  const liveToggle = document.getElementById("liveToggle");
  const liveToggleWrap = document.getElementById("liveToggleWrap");
  const labBoard = document.getElementById("labBoard");
  const labCoordCols = document.getElementById("labCoordCols");
  const labCoordRows = document.getElementById("labCoordRows");
  const labStatusFlag = document.getElementById("labStatusFlag");
  const labLegend = document.getElementById("labLegend");
  const labScenarioMeta = document.getElementById("labScenarioMeta");
  const vizSidePanelTitle = document.getElementById("vizSidePanelTitle");
  const vizSideContent = document.getElementById("vizSideContent");
  const metricsGrid = document.getElementById("metricsGrid");
  const formulaStrip = document.getElementById("formulaStrip");
  const fnG = document.getElementById("fnG");
  const fnH = document.getElementById("fnH");
  const fnF = document.getElementById("fnF");

  let speed = "normal";
  let running = false;

  // ------------------------------------------------------------------
  // Board helpers
  // ------------------------------------------------------------------
  function buildGrid(size) {
    labBoard.innerHTML = "";
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cell = document.createElement("div");
        cell.className = "cell state-empty";
        cell.dataset.row = r;
        cell.dataset.col = c;
        cell.setAttribute("aria-label", `${COLS[c]}${r + 1}`);
        labBoard.appendChild(cell);
      }
    }
  }
  function buildCoordLabels(size) {
    labCoordCols.innerHTML = "";
    labCoordRows.innerHTML = "";
    for (let c = 0; c < size; c++) {
      const span = document.createElement("span");
      span.textContent = COLS[c];
      labCoordCols.appendChild(span);
    }
    for (let r = 0; r < size; r++) {
      const span = document.createElement("span");
      span.textContent = r + 1;
      labCoordRows.appendChild(span);
    }
  }
  function cellAt(r, c) {
    return labBoard.querySelector(`.cell[data-row="${r}"][data-col="${c}"]`);
  }
  function paintBaseGrid(trackingGrid) {
    trackingGrid.forEach((row, r) => {
      row.forEach((val, c) => {
        const cell = cellAt(r, c);
        if (cell) {
          cell.className = `cell state-${STATE_MAP[val] || "empty"}`;
          cell.style.cssText = "";
        }
      });
    });
  }
  function clearOverlay() {
    labBoard.querySelectorAll(".cell").forEach((cell) => {
      cell.classList.remove(
        "search-frontier", "search-current", "search-explored", "search-target",
        "kb-possible", "kb-impossible", "kb-priority", "kb-highest", "kb-target",
        "kb-heat-prob", "kb-heat-candidate"
      );
      cell.style.removeProperty("--kb-heat");
      cell.style.removeProperty("box-shadow");
      cell.style.removeProperty("background");
    });
  }
  function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
  function coord(cell) { return cell ? `${COLS[cell[1]]}${cell[0] + 1}` : "—"; }
  function countFired(trackingGrid) {
    let n = 0;
    trackingGrid.forEach((row) => row.forEach((v) => { if (v !== "unknown") n++; }));
    return n;
  }

  // ------------------------------------------------------------------
  // Card grid
  // ------------------------------------------------------------------
  function renderCards() {
    cardGrid.innerHTML = "";
    ALGOS.forEach((algo) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "card glass-panel algo-lab-card";
      card.dataset.id = algo.id;
      card.innerHTML = `
        <div class="card-icon">${algo.icon}</div>
        <span class="algo-category">${algo.category}</span>
        <h3>${algo.name}</h3>
        <p>${algo.shortDesc}</p>
        <span class="btn btn-ghost">View Demo</span>
      `;
      card.addEventListener("click", () => selectAlgorithm(algo.id));
      cardGrid.appendChild(card);
    });
  }

  function setActiveTab(paneName) {
    detailTabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.pane === paneName));
    detailPanes.forEach((pane) => pane.classList.toggle("active", pane.dataset.pane === paneName));
  }
  detailTabs.forEach((tab) => tab.addEventListener("click", () => setActiveTab(tab.dataset.pane)));

  function selectAlgorithm(id) {
    const algo = algoById[id];
    if (!algo) return;
    currentAlgo = algo;
    currentResult = null;

    cardGrid.querySelectorAll(".algo-lab-card").forEach((c) => c.classList.toggle("selected", c.dataset.id === id));

    detailIcon.textContent = algo.icon;
    detailCategory.textContent = algo.category;
    detailName.textContent = algo.name;
    detailShortDesc.textContent = algo.shortDesc;
    paneWhatItIs.textContent = algo.whatItIs;
    paneHowItWorks.textContent = algo.howItWorks;
    paneUsedInBattleship.textContent = algo.usedInBattleship;
    paneWhy.textContent = algo.why;

    speedControlGroup.style.display = algo.vizType === "search" ? "flex" : "none";
    runDemoBtn.disabled = false;
    metricsGrid.innerHTML = "";
    formulaStrip.style.display = "none";
    vizSideContent.innerHTML = `<p class="placement-hint" style="margin:0;">Click "Run Demo" to execute this algorithm.</p>`;
    vizSidePanelTitle.textContent = "Details";
    buildGrid(10);
    buildCoordLabels(10);
    clearOverlay();
    labScenarioMeta.textContent = "No scenario loaded yet.";
    labLegend.innerHTML = "";
    setActiveTab("whatItIs");

    detailView.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ------------------------------------------------------------------
  // Legends per viz type
  // ------------------------------------------------------------------
  const LEGENDS = {
    search: `
      <span class="legend-item"><span class="legend-swatch sw-unexplored"></span>Unexplored</span>
      <span class="legend-item"><span class="legend-swatch sw-frontier"></span>Frontier</span>
      <span class="legend-item"><span class="legend-swatch sw-current"></span>Exploring</span>
      <span class="legend-item"><span class="legend-swatch sw-explored"></span>Explored</span>
      <span class="legend-item"><span class="legend-swatch sw-target"></span>Selected Target</span>
    `,
    probability: `
      <span class="legend-item"><span class="legend-swatch sw-kb-heat-prob"></span>Probability intensity</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-highest"></span>Highest probability</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-target"></span>Selected target</span>
    `,
    reasoning: `
      <span class="legend-item"><span class="legend-swatch sw-kb-possible"></span>Possible</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-impossible"></span>Impossible</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-priority"></span>Priority</span>
    `,
    planning: `
      <span class="legend-item"><span class="legend-swatch sw-kb-priority"></span>Candidate cell</span>
      <span class="legend-item"><span class="legend-swatch sw-kb-target"></span>Cluster / active hits</span>
    `,
    csp: `
      <span class="legend-item">Ship colors mark the sampled solution's fleet layout.</span>
    `,
    minimax: `
      <span class="legend-item"><span class="legend-swatch sw-kb-target"></span>Best action</span>
    `,
  };

  // ------------------------------------------------------------------
  // Visualization renderers per vizType
  // ------------------------------------------------------------------
  async function renderSearchViz(viz) {
    for (const step of viz.steps) {
      clearOverlay();
      step.explored.forEach(([r, c]) => cellAt(r, c) && cellAt(r, c).classList.add("search-explored"));
      step.frontier.forEach(([r, c]) => cellAt(r, c) && cellAt(r, c).classList.add("search-frontier"));
      const cur = cellAt(step.current[0], step.current[1]);
      if (cur) cur.classList.add("search-current");
      await sleep(SPEED_MS[speed]);
    }
    clearOverlay();
    const t = cellAt(viz.target[0], viz.target[1]);
    if (t) t.classList.add("search-target");
    vizSidePanelTitle.textContent = "Search Result";
    vizSideContent.innerHTML = `<p class="placement-hint" style="margin:0;">Target selected: <strong style="color:var(--ink-100);">${coord(viz.target)}</strong>. See the Metrics tab for full statistics.</p>`;
  }

  function renderProbabilityViz(viz) {
    clearOverlay();
    let maxPct = 0;
    viz.probability_grid.forEach((row) => row.forEach((v) => { if (v > maxPct) maxPct = v; }));
    viz.probability_grid.forEach((row, r) => {
      row.forEach((pct, c) => {
        if (pct <= 0) return;
        const cell = cellAt(r, c);
        if (!cell) return;
        cell.classList.add("kb-heat-prob");
        cell.style.setProperty("--kb-heat", maxPct > 0 ? pct / maxPct : 0);
        cell.title = `${COLS[c]}${r + 1}: ${pct}%`;
        if (pct === maxPct) cell.classList.add("kb-highest");
      });
    });
    const t = cellAt(viz.target[0], viz.target[1]);
    if (t) t.classList.add("kb-target");
    vizSidePanelTitle.textContent = "Density Summary";
    vizSideContent.innerHTML = `<p class="placement-hint" style="margin:0;">Selected target: <strong style="color:var(--ink-100);">${coord(viz.target)}</strong>. Cell color intensity is proportional to its share of total placement coverage.</p>`;
  }

  function renderReasoningViz(viz) {
    clearOverlay();
    const state = viz.state;
    state.possible_cells.forEach(([r, c]) => cellAt(r, c) && cellAt(r, c).classList.add("kb-possible"));
    state.impossible_cells.forEach(([r, c]) => cellAt(r, c) && cellAt(r, c).classList.add("kb-impossible"));
    state.priority_cells.forEach(([r, c]) => cellAt(r, c) && cellAt(r, c).classList.add("kb-priority"));
    if (state.current_target) {
      const [tr, tc] = state.current_target;
      const cell = cellAt(tr, tc);
      if (cell) cell.classList.add("kb-target");
    }
    const rep = viz.report;
    vizSidePanelTitle.textContent = "AI Reasoning";
    vizSideContent.innerHTML = `
      <h4 class="reasoning-col-title">What It Knows</h4>
      <ul style="margin:0 0 1rem; padding-left:1.1rem; color:var(--ink-400); font-size:0.85rem;">${rep.know.map((l) => `<li>${l}</li>`).join("")}</ul>
      <h4 class="reasoning-col-title">What It Infers</h4>
      <ul style="margin:0 0 1rem; padding-left:1.1rem; color:var(--ink-400); font-size:0.85rem;">${rep.infer.map((l) => `<li>${l}</li>`).join("")}</ul>
      <h4 class="reasoning-col-title">What It Will Do</h4>
      <ul style="margin:0; padding-left:1.1rem; color:var(--ink-100); font-size:0.85rem;">${rep.will_do.map((l) => `<li>${l}</li>`).join("")}</ul>
    `;
  }

  function renderPlanningViz(viz) {
    clearOverlay();
    (viz.cluster || []).forEach(([r, c]) => cellAt(r, c) && cellAt(r, c).classList.add("kb-target"));
    (viz.candidates || []).forEach(([r, c]) => cellAt(r, c) && cellAt(r, c).classList.add("kb-priority"));
    vizSidePanelTitle.textContent = "Tactical Plan";
    vizSideContent.innerHTML = `
      <div class="tactical-row"><span class="tactical-label">State</span><span class="tactical-value">${viz.state}</span></div>
      <div class="plan-state-track">
        <span class="plan-node ${viz.state === "SEARCH" ? "active" : ""}" data-state="SEARCH">Search</span>
        <span class="plan-arrow">→</span>
        <span class="plan-node ${viz.state === "TARGET" ? "active" : ""}" data-state="TARGET">Target</span>
        <span class="plan-arrow">→</span>
        <span class="plan-node ${viz.state === "DESTROY" ? "active" : ""}" data-state="DESTROY">Destroy</span>
      </div>
      <div class="tactical-row"><span class="tactical-label">Candidates</span><span class="tactical-value">${(viz.candidates || []).map(coord).join(", ") || "—"}</span></div>
    `;
  }

  const SHIP_PALETTE = ["#C6B98A", "#7A8061", "#A84F32", "#E8E1C8", "#8a3d26"];

  function renderCspViz(viz) {
    clearOverlay();
    if (viz.solution) {
      Object.values(viz.solution).forEach((cells, i) => {
        const color = SHIP_PALETTE[i % SHIP_PALETTE.length];
        cells.forEach(([r, c]) => {
          const cell = cellAt(r, c);
          if (cell) {
            cell.style.boxShadow = `inset 0 0 0 2px ${color}`;
            cell.style.background = `${color}33`;
          }
        });
      });
    }

    vizSidePanelTitle.textContent = "Domains & Search Trace";
    const domainRows = viz.variables.map((v) => `
      <tr>
        <td>${v.name}</td>
        <td>${v.domain_before}</td>
        <td>${v.domain_after}
          <span class="domain-bar-track"><span class="domain-bar-fill" style="width:${v.domain_before ? Math.round(100 * v.domain_after / v.domain_before) : 0}%;"></span></span>
        </td>
      </tr>
    `).join("");

    const traceItems = (viz.trace || []).slice(-40).map((step) => {
      if (step.action === "assign") {
        const coords = (step.cells || []).map(coord).join(",");
        return `<li class="action-assign">ASSIGN ${step.variable} → [${coords}]${step.dead_end ? " (dead end)" : ""}</li>`;
      }
      return `<li class="action-backtrack">BACKTRACK from ${step.variable}</li>`;
    }).join("");

    vizSideContent.innerHTML = `
      <table class="domain-table">
        <thead><tr><th>Ship</th><th>Before AC-3</th><th>After AC-3</th></tr></thead>
        <tbody>${domainRows}</tbody>
      </table>
      <h4 class="reasoning-col-title">Search Trace (last 40 steps)</h4>
      <ul class="trace-log">${traceItems || "<li>No search needed — solved during AC-3 or no candidates.</li>"}</ul>
    `;
  }

  function renderMinimaxViz(viz) {
    clearOverlay();
    const t = cellAt(viz.best_action[0], viz.best_action[1]);
    if (t) t.classList.add("kb-target");

    const values = viz.candidate_actions.map(([, v]) => v);
    const min = Math.min(...values), max = Math.max(...values);
    const range = max - min || 1;

    vizSidePanelTitle.textContent = "Candidate Action Values";
    const rows = viz.candidate_actions.map(([cell, val]) => {
      const isBest = cell[0] === viz.best_action[0] && cell[1] === viz.best_action[1];
      const pct = Math.round(100 * (val - min) / range);
      return `
        <div class="minimax-bar-row ${isBest ? "best" : ""}">
          <span class="mm-cell">${coord(cell)}</span>
          <div class="minimax-bar-track"><div class="minimax-bar-fill" style="width:${Math.max(pct, 4)}%;"></div></div>
          <span class="mm-val">${val}</span>
        </div>
      `;
    }).join("");
    vizSideContent.innerHTML = rows || `<p class="placement-hint" style="margin:0;">No candidate actions returned.</p>`;
  }

  // ------------------------------------------------------------------
  // Metrics rendering
  // ------------------------------------------------------------------
  function formatMetricValue(key, value) {
    if (value === null || value === undefined) return "—";
    if (key === "search_time_ms") return value + " ms";
    if (key === "target" || key === "best_action") return coord(value);
    if (key === "solution_found") return value ? "Yes" : "No";
    if (key === "used_alpha_beta") return value ? "Alpha-Beta" : "Exhaustive";
    if (key === "domains") return null; // rendered separately in the CSP viz panel
    return value;
  }

  function renderMetrics(metrics) {
    metricsGrid.innerHTML = "";
    Object.keys(metrics).forEach((key) => {
      if (key === "domains") return;
      const formatted = formatMetricValue(key, metrics[key]);
      if (formatted === null) return;
      const label = METRIC_LABELS[key] || key;
      const block = document.createElement("div");
      block.className = "metric-block";
      block.innerHTML = `<span class="metric-value">${formatted}</span><span class="metric-label">${label}</span>`;
      metricsGrid.appendChild(block);
    });

    if (metrics.f_target !== undefined) {
      formulaStrip.style.display = "flex";
      fnG.textContent = metrics.g_target;
      fnH.textContent = metrics.h_target;
      fnF.textContent = metrics.f_target;
    } else {
      formulaStrip.style.display = "none";
    }
  }

  // ------------------------------------------------------------------
  // Run demo
  // ------------------------------------------------------------------
  async function checkLiveAvailable() {
    try {
      const res = await fetch("/api/lab/live-available");
      const data = await res.json();
      liveToggle.disabled = !data.available;
      liveToggleWrap.classList.toggle("disabled", !data.available);
      if (!data.available) liveToggle.checked = false;
    } catch (e) {
      liveToggle.disabled = true;
      liveToggleWrap.classList.add("disabled");
    }
  }

  async function runDemo(forceNewRandom) {
    if (!currentAlgo || running) return;
    running = true;
    runDemoBtn.disabled = true;
    newScenarioBtn.disabled = true;
    labStatusFlag.textContent = "Running…";
    labStatusFlag.classList.add("active");
    labLegend.innerHTML = LEGENDS[currentAlgo.vizType] || "";

    const useLive = !forceNewRandom && liveToggle.checked;
    if (forceNewRandom) liveToggle.checked = false;

    try {
      const res = await fetch("/api/lab/demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm: currentAlgo.demoId, use_live_game: useLive }),
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.error || "Demo failed");
      currentResult = result;

      paintBaseGrid(result.tracking_grid);
      const shots = countFired(result.tracking_grid);
      labScenarioMeta.textContent = result.source === "live_game"
        ? `Source: your live Human vs AI grid · ${shots} cells already fired`
        : `Source: freshly generated random scenario · ${shots} cells already fired`;

      if (currentAlgo.vizType === "search") {
        await renderSearchViz(result.visualization);
      } else if (currentAlgo.vizType === "probability") {
        renderProbabilityViz(result.visualization);
      } else if (currentAlgo.vizType === "reasoning") {
        renderReasoningViz(result.visualization);
      } else if (currentAlgo.vizType === "planning") {
        renderPlanningViz(result.visualization);
      } else if (currentAlgo.vizType === "csp") {
        renderCspViz(result.visualization);
      } else if (currentAlgo.vizType === "minimax") {
        renderMinimaxViz(result.visualization);
      }

      renderMetrics(result.metrics);
      labStatusFlag.textContent = "Complete";
    } catch (e) {
      labStatusFlag.textContent = "Failed";
      vizSideContent.innerHTML = `<p class="placement-hint" style="margin:0;">Something went wrong running this demo — check the server console.</p>`;
    } finally {
      labStatusFlag.classList.remove("active");
      running = false;
      runDemoBtn.disabled = false;
      newScenarioBtn.disabled = false;
    }
  }

  speedSelector.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    speed = btn.dataset.speed;
    speedSelector.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
  });
  runDemoBtn.addEventListener("click", () => runDemo(false));
  newScenarioBtn.addEventListener("click", () => runDemo(true));

  renderCards();
  checkLiveAvailable();
})();
