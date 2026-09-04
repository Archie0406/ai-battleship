// comparison.js — drives /compare: runs real BFS/DFS/A* on one shared
// scenario and renders the actual results as bar charts. No numbers here
// are invented; everything comes straight from /api/lab/compare.
(function () {
  const COLS = "ABCDEFGHIJ";
  const runBtn = document.getElementById("runCompareBtn");
  const statusWrap = document.getElementById("compareStatusWrap");
  const statusEl = document.getElementById("compareStatus");
  const resultsEl = document.getElementById("compareResults");

  const ALGO_LABELS = { bfs: "BFS", dfs: "DFS", astar: "A*" };
  const ALGO_BAR_CLASS = { bfs: "", dfs: "bar-dfs", astar: "bar-astar" };

  function barChart(title, results, key, formatter, unit) {
    const values = Object.keys(results).map((k) => results[k][key]);
    const max = Math.max(...values, 1);
    const rows = Object.keys(results).map((algo) => {
      const val = results[algo][key];
      const pct = max > 0 ? Math.round((val / max) * 100) : 0;
      return `
        <div class="bar-row">
          <span class="bar-label">${ALGO_LABELS[algo]}</span>
          <div class="bar-track"><div class="bar-fill ${ALGO_BAR_CLASS[algo]}" style="width:${pct}%;"></div></div>
          <span class="bar-value">${formatter ? formatter(val) : val}${unit || ""}</span>
        </div>
      `;
    }).join("");
    return `<div class="compare-section-title">${title}</div><div class="bar-chart">${rows}</div>`;
  }

  function targetTable(results) {
    const rows = Object.keys(results).map((algo) => {
      const r = results[algo];
      const coord = `${COLS[r.target[1]]}${r.target[0] + 1}`;
      const extra = r.algorithm === "A*" ? ` · g=${r.g_target} h=${r.h_target} f=${r.f_target}` : "";
      return `<div class="tactical-row"><span class="tactical-label">${ALGO_LABELS[algo]} Target</span><span class="tactical-value">${coord}${extra}</span></div>`;
    }).join("");
    return `<div class="compare-section-title" style="margin-top: var(--sp-4);">Selected Targets</div>${rows}`;
  }

  async function runComparison() {
    runBtn.disabled = true;
    statusWrap.style.display = "flex";
    statusEl.textContent = "Running…";

    try {
      const res = await fetch("/api/lab/compare", { method: "POST" });
      const data = await res.json();
      const results = data.results;

      resultsEl.innerHTML = `
        ${barChart("Nodes Explored", results, "nodes_explored")}
        ${barChart("Search Time", results, "search_time_ms", (v) => v.toFixed(3), " ms")}
        ${barChart("Search Depth", results, "search_depth")}
        ${targetTable(results)}
        <p class="scenario-meta" style="margin-top: var(--sp-4);">All three algorithms ran against the identical freshly generated scenario board, so nodes explored and depth are directly comparable.</p>
      `;
      statusEl.textContent = "Complete";
    } catch (e) {
      resultsEl.innerHTML = `<p class="placement-hint" style="margin:0;">Comparison failed — check the server console.</p>`;
      statusEl.textContent = "Failed";
    } finally {
      runBtn.disabled = false;
      setTimeout(() => { statusWrap.style.display = "none"; }, 1500);
    }
  }

  runBtn.addEventListener("click", runComparison);
})();
