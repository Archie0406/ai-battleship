// minimax_compare.js — drives the Minimax vs Minimax+Alpha-Beta section on
// /compare: runs both variants on one identical root state via
// /api/lab/minimax-compare and renders the real results.
(function () {
  const COLS = "ABCDEFGHIJ";
  const depthSelector = document.getElementById("mmDepthSelector");
  const liveToggle = document.getElementById("mmLiveToggle");
  const liveToggleWrap = document.getElementById("mmLiveToggleWrap");
  const runBtn = document.getElementById("runMinimaxCompareBtn");
  const statusWrap = document.getElementById("mmCompareStatusWrap");
  const statusEl = document.getElementById("mmCompareStatus");
  const resultsEl = document.getElementById("mmCompareResults");

  if (!runBtn) return; // section not present on this page

  let depth = 3;

  const LABELS = { minimax: "Minimax (no pruning)", minimax_ab: "Minimax + Alpha-Beta" };
  const BAR_CLASS = { minimax: "", minimax_ab: "bar-minimax-ab" };

  function coord(cell) {
    return cell ? `${COLS[cell[1]]}${cell[0] + 1}` : "—";
  }

  function barChart(title, results, key, formatter, unit) {
    const values = Object.keys(results).map((k) => results[k][key]);
    const max = Math.max(...values, 1);
    const rows = Object.keys(results).map((variant) => {
      const val = results[variant][key];
      const pct = max > 0 ? Math.round((val / max) * 100) : 0;
      return `
        <div class="bar-row">
          <span class="bar-label">${LABELS[variant]}</span>
          <div class="bar-track"><div class="bar-fill ${BAR_CLASS[variant]}" style="width:${pct}%;"></div></div>
          <span class="bar-value">${formatter ? formatter(val) : val}${unit || ""}</span>
        </div>
      `;
    }).join("");
    return `<div class="compare-section-title">${title}</div><div class="bar-chart">${rows}</div>`;
  }

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

  depthSelector.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    depth = Number(btn.dataset.depth);
    depthSelector.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
  });

  async function runComparison() {
    runBtn.disabled = true;
    statusWrap.style.display = "flex";
    statusEl.textContent = "Running…";

    try {
      const res = await fetch("/api/lab/minimax-compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ use_live_game: liveToggle.checked, depth }),
      });
      const data = await res.json();
      const results = data.results;

      const sameDecision = results.minimax.best_action && results.minimax_ab.best_action &&
        results.minimax.best_action[0] === results.minimax_ab.best_action[0] &&
        results.minimax.best_action[1] === results.minimax_ab.best_action[1];

      resultsEl.innerHTML = `
        ${barChart("Nodes Evaluated", results, "nodes_evaluated")}
        ${barChart("Nodes Pruned", results, "nodes_pruned")}
        ${barChart("Execution Time", results, "search_time_ms", (v) => v.toFixed(3), " ms")}
        <div class="compare-section-title" style="margin-top: var(--sp-4);">Decisions</div>
        <div class="tactical-row"><span class="tactical-label">Minimax (no pruning) chose</span><span class="tactical-value">${coord(results.minimax.best_action)}</span></div>
        <div class="tactical-row"><span class="tactical-label">Minimax + Alpha-Beta chose</span><span class="tactical-value">${coord(results.minimax_ab.best_action)}</span></div>
        <div class="tactical-row"><span class="tactical-label">Same decision reached</span><span class="tactical-value ${sameDecision ? "accent-cyan" : "accent-hit"}">${sameDecision ? "Yes — pruning changed nothing about the outcome" : "No — check the tree"}</span></div>
        <p class="scenario-meta" style="margin-top: var(--sp-4);">Source: ${data.source === "live_game" ? "your live Human vs AI grid" : "a freshly generated random scenario"} · depth ${data.depth} · remaining fleet ${data.remaining_lengths.join(", ")}.</p>
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
  checkLiveAvailable();
})();
