# AI Battleship — CSP & Backtracking

An academic AI project rebuilding Battleship as a live testbed for classic
AI algorithms: CSP, backtracking, search (BFS/DFS/A*), knowledge
representation, planning, minimax with alpha-beta pruning, and an optional
genetic algorithm layer.

**This phase completes the AI Lab and Algorithm Comparison** — the
academic centerpiece of the project. All ten algorithms (CSP,
Backtracking, BFS, DFS, A*, Probability, Forward Chaining, Planning,
Minimax, Alpha-Beta) are now genuinely wired end to end: selectable as a
Human vs AI strategy, runnable as a standalone live demo with real
visualization and metrics, comparable side by side on a shared scenario,
and benchmarkable over multiple automated games.

## What's implemented right now

- **Three game modes**: Human vs AI (9 real strategies including the new
  CSP + Backtracking), AI vs AI (any two of 11 registered strategies,
  fully configurable), and the AI Lab.
- **CSP + Backtracking, for real** (`ai/csp.py` + `ai/backtracking.py` via
  `ai.agent.CSPAgent`): each remaining ship is a CSP variable; its domain
  is every legal placement consistent with known misses/sunk cells; AC-3
  arc-consistency prunes domains before search even starts; MRV/LCV-
  ordered backtracking with forward checking finds complete, mutually
  consistent fleet assignments. The AI samples several such assignments
  and targets whichever cell the most of them agree on — a genuinely
  different, jointly-consistent notion of probability from the
  independent per-ship density approach. *(This phase also fixed a real
  bug found while wiring it up: `ai/csp.py` was missing `import random`,
  which would have crashed the moment the strategy was selected.)*
- **AI Lab — ten real, interactive algorithm cards**: CSP, Backtracking,
  BFS, DFS, A*, Probability, Forward Chaining, Planning, Minimax, and
  Alpha-Beta, each with an icon, category, and short description. Clicking
  "View Demo" opens a shared **Algorithm Detail View** with:
  - **What It Is / How It Works / Used In Battleship** — accurate,
    exam-ready explanations specific to this exact implementation.
  - **Live Visualization** — a real scenario board that actually renders
    that algorithm's real output: animated frontier/explored/target for
    the search family, a probability heatmap for Probability, a
    knowledge-map overlay + live "What I Know / Infer / Will Do" report
    for Forward Chaining, the SEARCH→TARGET→DESTROY state track for
    Planning, ship-colored solution highlighting + a domain-shrink table
    + a scrolling assign/backtrack trace log for CSP/Backtracking, and a
    ranked candidate-action bar list for Minimax/Alpha-Beta.
  - **Metrics** — only the fields that genuinely apply to that algorithm
    (nodes expanded, backtracks, AC-3 removed, nodes explored/evaluated/
    pruned, states visited, search depth, confidence, g/h/f, etc.), all
    real numbers from the run that just executed.
  - **Why This Algorithm?** — a short, simple explanation of where each
    algorithm is actually useful in Battleship specifically.
  - A live/random scenario toggle and (for the search family) an
    animation speed control, matching the Human vs AI experience.
- **Algorithm Comparison — three dashboards**:
  - **BFS vs DFS vs A\*** and **Minimax vs Minimax+Alpha-Beta** (from the
    previous phase) — both run on one identical scenario/root state.
  - **Multi-Algorithm Dashboard** (new) — pick any combination of the ten
    algorithms, run them all against one shared fresh scenario via one
    unified endpoint, and see a table with only the metrics that apply to
    each selected algorithm — no fabricated "—" dressed up as a real
    number, genuinely omitted columns instead.
  - **Simulation Runner** (new) — pick a strategy and a number of games
    (3/5/10/20, lower-capped for CSP/Minimax-driven strategies since each
    decision is a genuine exhaustive search), and run that many complete
    automated matches against a random-targeting baseline via the real
    `AIVsAIEngine`. Reports GAME 1, GAME 2, ... rows (result, shots, hits,
    accuracy) plus an aggregate summary (win rate, avg/min/max shots,
    avg accuracy) — all real outcomes, nothing precomputed.
- **`ai/lab_demo.py`** — the single dispatch module all three of the
  above features share: one function, `run_demo(algorithm, tracking_grid,
  ...)`, that actually runs the named algorithm and returns a normalized
  `{metrics, visualization}` envelope. The Forward Chaining demo notably
  *replays* the scenario's real hits/misses/sunk cells through genuine
  `record_shot()` calls before generating its report, so its rules fire
  against real data every time, not a canned example.
- **Eight real AI targeting strategies** in Human vs AI (now nine with
  CSP), selectable before battle starts, each genuinely deciding the AI's
  shots — not just relabeling the display.
- **Two named "AI Commander" hybrid strategies** for AI vs AI:
  Commander 01 (Probability + Search) and Commander 02 (Minimax +
  Planning), with either side of any match reassignable to any of the 11
  registered strategies.
- **Knowledge base + forward chaining**, **Tactical Planner**, **Minimax +
  Alpha-Beta**, **BFS/DFS/A\***, and **Probability Density** all remain
  fully wired from previous phases — see the AI Lab for the same
  explanations now presented as live, interactive demonstrations.
- **A pluggable AI agent architecture** (`ai/agent.py`): a common
  `choose_target(tracking_grid, remaining_lengths) -> (cell, confidence)`
  interface plus an optional `observe_result(...)` hook, implemented by
  ten agent classes today (`RandomAgent`, `ProbabilityAgent`,
  `SearchAgent`, `ReasoningAgent`, `PlanningAgent`, `MinimaxAgent`,
  `CSPAgent`, `HybridSearchCommander`, `HybridMinimaxCommander`) — usable
  interchangeably in Human vs AI, AI vs AI, and the Lab's simulation
  runner without any special-casing.
- **A five-page premium UI** — Landing, Play, AI vs AI, AI Lab, Compare,
  How It Works — dark tactical/naval command-center aesthetic throughout.
- Documented architectural scaffolds for genetic algorithms — ready to be
  filled in and plugged into the agent architecture above.

## Project structure

```
ai-battleship/
├── app.py                     Flask app: pages + /api/game/* + /api/aivai/* + /api/lab/*
├── requirements.txt
├── ai/
│   ├── agent.py                ✅ pluggable interface: 9 real agent classes
│   ├── probability.py          ✅ density-map reasoning + confidence scoring
│   ├── search.py                ✅ real BFS / DFS / A* with full step traces + metrics
│   ├── reasoning.py             ✅ knowledge base + 4-rule forward chaining + probability grid
│   ├── planning.py              ✅ real SEARCH/TARGET/DESTROY tactical state machine
│   ├── minimax.py               ✅ real Minimax + Alpha-Beta over an honest hidden-info tree
│   ├── csp.py                   ✅ real CSP: variables, domains, constraints, AC-3
│   ├── backtracking.py          ✅ real MRV/LCV backtracking + forward checking
│   ├── lab_demo.py              ✅ unified dispatcher: runs any of the 10 algorithms, normalized output
│   ├── scenario.py              generates scenario boards + remaining-fleet reconstruction helpers
│   └── genetic.py               scaffold — optional genetic algorithm
├── game/
│   ├── ships.py, fleet.py, board.py, player.py    core game model
│   ├── game_engine.py             Human vs AI: placement, strategy selection, battle loop, all telemetry
│   └── ai_vs_ai_engine.py         AI vs AI: any two pluggable agents, per-side telemetry
├── templates/
│   ├── base.html, index.html      shared shell + landing page
│   ├── game.html                  Human vs AI: placement + strategy selector + all telemetry panels
│   ├── ai_vs_ai.html              AI vs AI: commander selection + per-side telemetry
│   ├── ai_lab.html                AI Lab: 10-card grid + shared Algorithm Detail View
│   ├── comparison.html            search + minimax benchmarks, multi-algorithm dashboard, simulation runner
│   └── how_it_works.html          pipeline explanation page
└── static/
    ├── css/                       tokens, base, nav, components, landing, game, lab
    └── js/                        main, landing, game, ai_vs_ai, lab, comparison, minimax_compare,
                                    algorithm_lab, multi_compare, simulation_runner
```

## Running it locally

```bash
cd ai-battleship
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## Pages

| Route              | Page                                       |
|---------------------|----------------------------------------------|
| `/`                 | Landing page                                  |
| `/play`             | Human vs AI (placement + 9-strategy selector + battle) |
| `/play/ai-vs-ai`    | AI vs AI (configurable commanders + spectator UI) |
| `/ai-lab`           | AI Lab — 10 algorithm cards + live Detail View |
| `/compare`          | Algorithm Comparison — 4 live dashboards      |
| `/how-it-works`     | How the current AI reasons, step by step      |

## API

**Human vs AI** (`/api/game/*`) — new/state/place/remove/randomize/reset/
`set-strategy` (now accepts `csp` too)/confirm/fire.

**AI vs AI** (`/api/aivai/*`) — new (`{agent_a, agent_b}`)/state/step.

**Algorithm Lab / Comparison** (`/api/lab/*`)

| Method | Endpoint             | Description                                                    |
|--------|-----------------------|--------------------------------------------------------------|
| POST   | `/run`                | Real BFS/DFS/A* search (legacy single-purpose endpoint, still used by the Search Explorer pattern) |
| GET    | `/live-available`     | Whether the session has a live Human vs AI grid to demo against |
| POST   | `/compare`            | BFS, DFS, A* on one shared fresh scenario                    |
| POST   | `/minimax-compare`    | `{use_live_game, depth}` — Minimax vs Minimax+Alpha-Beta on the identical root state |
| POST   | `/demo`               | `{algorithm, use_live_game}` — run any of the 10 algorithms, normalized `{metrics, visualization}` |
| POST   | `/simulate`           | `{strategy, games}` — N full automated games vs. a random baseline, real per-game + summary results |

## Next phases (not yet built)

1. Optional: implement `ai/genetic.py` as an advanced extra, and a
   `GeneticAgent` wrapping it, addable to every dashboard above the same
   way CSP was added this phase.
2. Extend the Comparison page's long-term roadmap table with full
   shots-to-win benchmarks once a genetic strategy exists to compare.
