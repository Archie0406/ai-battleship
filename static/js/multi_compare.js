// multi_compare.js — drives the Multi-Algorithm Dashboard on /compare:
// lets the user pick any combination of the 10 real algorithms and runs
// each once against the exact same freshly generated scenario via
// /api/lab/demo, then renders a table showing only the metrics that
// genuinely apply to each one.
(function () {
  const COLS = "ABCDEFGHIJ";
  const picker = document.getElementById("multiAlgoPicker");
  const runBtn = document.getElementById("runMultiCompareBtn");
  const statusWrap = document.getElementById("multiCompareStatusWrap");
  const statusEl = document.getElementById("multiCompareStatus");
  const resultsEl = document.getElementById("multiCompareResults");

  if (!picker) return;

  const ALGOS = [
    { id: "csp", label: "CSP" },
    { id: "backtracking", label: "Backtracking" },
    { id: "bfs", label: "BFS" },
    { id: "dfs", label: "DFS" },
    { id: "astar", label: "A*" },
    { id: "probability", label: "Probability" },
    { id: "reasoning", label: "Forward Chaining" },
    { id: "planning", label: "Planning" },
    { id: "minimax", label: "Minimax" },
    { id: "alphabeta", label: "Alpha-Beta" },
  ];

  const METRIC_ORDER = [
    "nodes_expanded", "nodes_explored", "nodes_evaluated",
    "search_time_ms", "backtracks", "nodes_pruned", "states_visited",
    "ac3_removed", "search_depth", "confidence", "candidate_count",
  ];
  const METRIC_LABELS = {
    nodes_expanded: "Nodes Expanded", nodes_explored: "Nodes Explored", nodes_evaluated: "Nodes Evaluated",
    search_time_ms: "Search Time (ms)", backtracks: "Backtracks", nodes_pruned: "Nodes Pruned",
    states_visited: "States Visited", ac3_removed: "AC-3 Removed", search_depth: "Search Depth",
    confidence: "Confidence (%)", candidate_count: "Candidates",
  };
  const ALGO_LABELS = Object.fromEntries(ALGOS.map((a) => [a.id, a.label]));

  const selected = new Set(["bfs", "dfs", "astar"]);

  function coord(cell) {
    return cell ? `${COLS[cell[1]]}${cell[0] + 1}` : "—";
  }

  function renderPicker() {
    picker.innerHTML = "";
    ALGOS.forEach((algo) => {
      const chip = document.createElement("div");
      chip.className = "ship-chip" + (selected.has(algo.id) ? " selected" : "");
      chip.style.cursor = "pointer";
      chip.innerHTML = `<span class="chip-name">${algo.label}</span>`;
      chip.addEventListener("click", () => {
        if (selected.has(algo.id)) selected.delete(algo.id);
        else selected.add(algo.id);
        renderPicker();
      });
      picker.appendChild(chip);
    });
  }

  async function runComparison() {
    if (selected.size === 0) {
      resultsEl.innerHTML = `<p class="placement-hint" style="margin:0;">Select at least one algorithm first.</p>`;
      return;
    }
    runBtn.disabled = true;
    statusWrap.style.display = "flex";
    statusEl.textContent = "Running…";

    const results = {};
    try {
      for (const id of selected) {
        const res = await fetch("/api/lab/demo", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ algorithm: id, use_live_game: false }),
        });
        const data = await res.json();
        if (res.ok) results[id] = data;
      }

      const presentMetrics = METRIC_ORDER.filter((m) => Object.values(results).some((r) => r.metrics[m] !== undefined));

      const headerCells = presentMetrics.map((m) => `<th>${METRIC_LABELS[m]}</th>`).join("");
      const rows = Object.keys(results).map((id) => {
        const r = results[id];
        const cells = presentMetrics.map((m) => {
          const v = r.metrics[m];
          if (v === undefined) return "<td>—</td>";
          if (m === "search_time_ms") return `<td>${v.toFixed(3)}</td>`;
          if (m === "confidence") return `<td>${v}</td>`;
          return `<td>${v}</td>`;
        }).join("");
        const target = r.metrics.target || r.metrics.best_action || (r.visualization && r.visualization.state && r.visualization.state.current_target);
        return `<tr><td class="metric-name">${ALGO_LABELS[id] || id}</td>${cells}<td>${target ? coord(target) : "—"}</td></tr>`;
      }).join("");

      resultsEl.innerHTML = `
        <table class="compare-table">
          <thead><tr><th>Algorithm</th>${headerCells}<th>Target Selected</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="scenario-meta" style="margin-top: var(--sp-3);">All ${Object.keys(results).length} algorithm(s) ran against the exact same freshly generated scenario board.</p>
      `;
      statusEl.textContent = "Complete";
    } catch (e) {
      resultsEl.innerHTML = `<p class="placement-hint" style="margin:0;">Comparison failed — check the server console.</p>`;
      statusEl.textContent = "Failed";
    } finally {
      runBtn.disabled = false;
      setTimeout(() => { statusWrap.style.display = "none"; }, 1200);
    }
  }

  runBtn.addEventListener("click", runComparison);
  renderPicker();
})();
