// lab.js — drives the Algorithm Lab's Search Explorer: runs real BFS/DFS/A*
// against a scenario board and replays the algorithm's own step trace.
(function () {
  const COLS = "ABCDEFGHIJ";
  const STATE_MAP = { unknown: "empty", miss: "miss", hit: "hit", sunk: "sunk" };
  const SPEED_MS = { slow: 850, normal: 380, fast: 120 };

  const board = document.getElementById("labBoard");
  const coordCols = document.getElementById("labCoordCols");
  const coordRows = document.getElementById("labCoordRows");
  const statusFlag = document.getElementById("labStatusFlag");
  const scenarioMeta = document.getElementById("labScenarioMeta");

  const algoSelector = document.getElementById("algoSelector");
  const speedSelector = document.getElementById("speedSelector");
  const newScenarioBtn = document.getElementById("newScenarioBtn");
  const runSearchBtn = document.getElementById("runSearchBtn");
  const liveToggle = document.getElementById("liveToggle");
  const liveToggleWrap = document.getElementById("liveToggleWrap");

  const labNodes = document.getElementById("labNodes");
  const labTime = document.getElementById("labTime");
  const labStates = document.getElementById("labStates");
  const labTarget = document.getElementById("labTarget");
  const labDepth = document.getElementById("labDepth");
  const formulaStrip = document.getElementById("formulaStrip");
  const fnG = document.getElementById("fnG");
  const fnH = document.getElementById("fnH");
  const fnF = document.getElementById("fnF");
  const algoExplainer = document.getElementById("algoExplainer");

  const EXPLAINERS = {
    bfs: "BFS explores the grid level by level from every known hit (or the board center), guaranteeing the closest untried cell is found first.",
    dfs: "DFS dives along one fixed direction as far as it can before backtracking, using an explicit stack — it often reaches a farther cell before a closer one.",
    astar: "A* orders every candidate by f(n) = g(n) + h(n) — real steps taken plus Manhattan distance to the nearest lead — reaching a close, promising cell efficiently.",
  };

  let algorithm = "bfs";
  let speed = "normal";
  let running = false;

  function buildGrid(size) {
    board.innerHTML = "";
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const cell = document.createElement("div");
        cell.className = "cell state-empty";
        cell.dataset.row = r;
        cell.dataset.col = c;
        cell.setAttribute("aria-label", `${COLS[c]}${r + 1}`);
        board.appendChild(cell);
      }
    }
  }

  function buildCoordLabels(size) {
    coordCols.innerHTML = "";
    coordRows.innerHTML = "";
    for (let c = 0; c < size; c++) {
      const span = document.createElement("span");
      span.textContent = COLS[c];
      coordCols.appendChild(span);
    }
    for (let r = 0; r < size; r++) {
      const span = document.createElement("span");
      span.textContent = r + 1;
      coordRows.appendChild(span);
    }
  }

  function cellAt(r, c) {
    return board.querySelector(`.cell[data-row="${r}"][data-col="${c}"]`);
  }

  function paintBaseGrid(trackingGrid) {
    trackingGrid.forEach((row, r) => {
      row.forEach((val, c) => {
        const cell = cellAt(r, c);
        if (cell) cell.className = `cell state-${STATE_MAP[val] || "empty"}`;
      });
    });
  }

  function clearSearchOverlay() {
    board.querySelectorAll(".cell").forEach((cell) => {
      cell.classList.remove("search-frontier", "search-current", "search-explored", "search-target");
    });
  }

  function countFired(trackingGrid) {
    let n = 0;
    trackingGrid.forEach((row) => row.forEach((v) => { if (v !== "unknown") n++; }));
    return n;
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function animateSteps(steps, target) {
    for (const step of steps) {
      clearSearchOverlay();
      step.explored.forEach(([r, c]) => {
        const cell = cellAt(r, c);
        if (cell) cell.classList.add("search-explored");
      });
      step.frontier.forEach(([r, c]) => {
        const cell = cellAt(r, c);
        if (cell) cell.classList.add("search-frontier");
      });
      const cur = cellAt(step.current[0], step.current[1]);
      if (cur) cur.classList.add("search-current");
      await sleep(SPEED_MS[speed]);
    }
    clearSearchOverlay();
    const targetCell = cellAt(target[0], target[1]);
    if (targetCell) targetCell.classList.add("search-target");
  }

  function updateMetrics(result) {
    labNodes.textContent = result.nodes_explored;
    labTime.textContent = result.search_time_ms + " ms";
    labStates.textContent = result.states_visited;
    labTarget.textContent = `${COLS[result.target[1]]}${result.target[0] + 1}`;
    labDepth.textContent = result.search_depth;

    if (result.algorithm === "A*") {
      formulaStrip.style.display = "flex";
      fnG.textContent = result.g_target;
      fnH.textContent = result.h_target;
      fnF.textContent = result.f_target;
    } else {
      formulaStrip.style.display = "none";
    }
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
      liveToggleWrap.classList.toggle("disabled", true);
    }
  }

  async function runSearch(forceNewRandom) {
    if (running) return;
    running = true;
    runSearchBtn.disabled = true;
    newScenarioBtn.disabled = true;
    statusFlag.textContent = "Searching…";
    statusFlag.classList.add("active");
    algoExplainer.textContent = EXPLAINERS[algorithm];

    const useLive = !forceNewRandom && liveToggle.checked;
    if (forceNewRandom) liveToggle.checked = false;

    try {
      const res = await fetch("/api/lab/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm, use_live_game: useLive }),
      });
      const result = await res.json();

      paintBaseGrid(result.tracking_grid);
      const shots = countFired(result.tracking_grid);
      scenarioMeta.textContent = result.source === "live_game"
        ? `Source: your live Human vs AI grid · ${shots} cells already fired`
        : `Source: freshly generated random scenario · ${shots} cells already fired`;

      await animateSteps(result.steps, result.target);
      updateMetrics(result);
      statusFlag.textContent = "Search complete";
    } catch (e) {
      statusFlag.textContent = "Search failed";
    } finally {
      statusFlag.classList.remove("active");
      running = false;
      runSearchBtn.disabled = false;
      newScenarioBtn.disabled = false;
    }
  }

  algoSelector.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn || running) return;
    algorithm = btn.dataset.algo;
    algoSelector.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
    algoExplainer.textContent = EXPLAINERS[algorithm];
  });

  speedSelector.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    speed = btn.dataset.speed;
    speedSelector.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
  });

  runSearchBtn.addEventListener("click", () => runSearch(false));
  newScenarioBtn.addEventListener("click", () => runSearch(true));

  buildGrid(10);
  buildCoordLabels(10);
  checkLiveAvailable();
})();
