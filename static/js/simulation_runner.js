// simulation_runner.js — drives the Simulation Runner on /compare: runs
// N full automated games of the chosen strategy against a random
// baseline via /api/lab/simulate (the real AIVsAIEngine), and renders
// real per-game results plus an aggregate summary.
(function () {
  const strategySelect = document.getElementById("simStrategySelect");
  const gamesSelector = document.getElementById("simGamesSelector");
  const runBtn = document.getElementById("runSimBtn");
  const statusWrap = document.getElementById("simStatusWrap");
  const statusEl = document.getElementById("simStatus");
  const gameList = document.getElementById("simGameList");
  const summaryEl = document.getElementById("simSummary");

  if (!runBtn) return;

  let games = 5;

  gamesSelector.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    games = Number(btn.dataset.games);
    gamesSelector.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
  });

  function renderPerGame(perGame) {
    gameList.innerHTML = "";
    perGame.forEach((g) => {
      const row = document.createElement("div");
      row.className = "sim-game-row";
      row.innerHTML = `
        <span>GAME ${g.game}</span>
        <span class="sim-result ${g.result}">${g.result}</span>
        <span class="sim-shots">${g.shots} shots · ${g.hits} hits</span>
        <span class="sim-acc">${g.accuracy}%</span>
      `;
      gameList.appendChild(row);
    });
  }

  function renderSummary(summary, strategyLabel) {
    summaryEl.innerHTML = `
      <div class="tactical-row"><span class="tactical-label">Strategy</span><span class="tactical-value">${strategyLabel}</span></div>
      <div class="tactical-row"><span class="tactical-label">Games Played</span><span class="tactical-value">${summary.games}</span></div>
      <div class="tactical-row"><span class="tactical-label">Wins / Losses</span><span class="tactical-value accent-cyan">${summary.wins} / ${summary.losses}</span></div>
      <div class="tactical-row"><span class="tactical-label">Win Rate</span><span class="tactical-value">${summary.win_rate}%</span></div>
      <div class="tactical-row"><span class="tactical-label">Avg. Shots to Win</span><span class="tactical-value">${summary.avg_shots}</span></div>
      <div class="tactical-row"><span class="tactical-label">Shots Range</span><span class="tactical-value">${summary.min_shots} – ${summary.max_shots}</span></div>
      <div class="tactical-row"><span class="tactical-label">Avg. Accuracy</span><span class="tactical-value">${summary.avg_accuracy}%</span></div>
    `;
  }

  async function runSimulation() {
    runBtn.disabled = true;
    statusWrap.style.display = "flex";
    statusEl.textContent = "Running…";
    gameList.innerHTML = `<p class="placement-hint" style="margin:0;">Running ${games} game(s)…</p>`;
    summaryEl.innerHTML = "";

    try {
      const res = await fetch("/api/lab/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: strategySelect.value, games }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Simulation failed");

      renderPerGame(data.per_game);
      renderSummary(data.summary, strategySelect.options[strategySelect.selectedIndex].text);
      statusEl.textContent = "Complete";
      if (data.summary.games < games) {
        statusEl.textContent = `Complete (capped at ${data.summary.games} for this strategy)`;
      }
    } catch (e) {
      gameList.innerHTML = `<p class="placement-hint" style="margin:0;">Simulation failed — check the server console.</p>`;
      statusEl.textContent = "Failed";
    } finally {
      runBtn.disabled = false;
      setTimeout(() => { statusWrap.style.display = "none"; }, 1500);
    }
  }

  runBtn.addEventListener("click", runSimulation);
})();
