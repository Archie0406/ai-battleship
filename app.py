"""
app.py
======
Flask entry point for AI Battleship.

Routes are split into three groups:
  - Page routes    -> render templates (landing, game modes, AI lab,
                       comparison, how-it-works)
  - Game API        -> /api/game/*   Human vs AI: placement + battle
  - AI-vs-AI API     -> /api/aivai/*  autoplay match between two agents

Games are held server-side in memory, keyed by a UUID stored in the
browser's session cookie. This is intentionally simple (no database)
since the brief calls for a foundation, not production persistence.
"""

from flask import Flask, render_template, request, jsonify, session

from game.game_engine import GameEngine
from game.ai_vs_ai_engine import AIVsAIEngine
from game.board import SIZE
from ai.search import run_search
from ai.scenario import generate_scenario, remaining_lengths_from_tracking, remaining_ships_from_tracking
from ai.minimax import select_best_action
from ai.lab_demo import run_demo

app = Flask(__name__)
app.secret_key = "ai-battleship-dev-secret"  # fine for a local academic project

# In-memory game stores: {game_id: engine}
GAMES = {}
AIVAI_GAMES = {}


def get_or_create_game(new=False):
    game_id = session.get("game_id")
    if new or game_id not in GAMES:
        engine = GameEngine()
        GAMES[engine.id] = engine
        session["game_id"] = engine.id
        return engine
    return GAMES[game_id]


def get_or_create_aivai_game(new=False, agent_a_id=None, agent_b_id=None):
    game_id = session.get("aivai_game_id")
    if new or game_id not in AIVAI_GAMES:
        engine = AIVsAIEngine(agent_a_id=agent_a_id, agent_b_id=agent_b_id)
        AIVAI_GAMES[engine.id] = engine
        session["aivai_game_id"] = engine.id
        return engine
    return AIVAI_GAMES[game_id]


# ----------------------------------------------------------------------
# Page routes
# ----------------------------------------------------------------------
@app.route("/")
def landing():
    return render_template("index.html")


@app.route("/play")
def play():
    return render_template("game.html")


@app.route("/play/ai-vs-ai")
def play_ai_vs_ai():
    return render_template("ai_vs_ai.html")


@app.route("/ai-lab")
def ai_lab():
    return render_template("ai_lab.html")


@app.route("/compare")
def compare():
    return render_template("comparison.html")


@app.route("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")


# ----------------------------------------------------------------------
# Human vs AI game API
# ----------------------------------------------------------------------
@app.route("/api/game/new", methods=["POST"])
def api_new_game():
    engine = get_or_create_game(new=True)
    return jsonify(engine.state())


@app.route("/api/game/state", methods=["GET"])
def api_state():
    engine = get_or_create_game()
    return jsonify(engine.state())


@app.route("/api/game/place", methods=["POST"])
def api_place():
    engine = get_or_create_game()
    data = request.get_json(force=True) or {}
    name = data.get("name")
    r, c = data.get("row"), data.get("col")
    horizontal = bool(data.get("horizontal", True))
    if name is None or r is None or c is None:
        return jsonify({"error": "name, row and col are required"}), 400

    result = engine.place_ship(name, int(r), int(c), horizontal)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "state": engine.state()})


@app.route("/api/game/remove", methods=["POST"])
def api_remove():
    engine = get_or_create_game()
    data = request.get_json(force=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400
    result = engine.remove_ship(name)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "state": engine.state()})


@app.route("/api/game/randomize", methods=["POST"])
def api_randomize():
    engine = get_or_create_game()
    result = engine.randomize_player_fleet()
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "state": engine.state()})


@app.route("/api/game/reset", methods=["POST"])
def api_reset_placement():
    engine = get_or_create_game()
    result = engine.reset_player_fleet()
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "state": engine.state()})


@app.route("/api/game/confirm", methods=["POST"])
def api_confirm():
    engine = get_or_create_game()
    result = engine.confirm_fleet()
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "state": engine.state()})


@app.route("/api/game/set-strategy", methods=["POST"])
def api_set_strategy():
    engine = get_or_create_game()
    data = request.get_json(force=True) or {}
    strategy = data.get("strategy", "probability")
    result = engine.set_ai_strategy(strategy)
    if "error" in result:
        return jsonify(result), 400
    return jsonify({"ok": True, "state": engine.state()})


@app.route("/api/game/fire", methods=["POST"])
def api_fire():
    engine = get_or_create_game()
    data = request.get_json(force=True) or {}
    r, c = data.get("row"), data.get("col")
    if r is None or c is None:
        return jsonify({"error": "row and col are required"}), 400

    result = engine.fire_player_shot(int(r), int(c))
    if "error" in result:
        return jsonify(result), 400

    ai_shots = []
    if engine.turn == "ai" and engine.winner is None:
        ai_shots = engine.run_ai_turn()

    return jsonify(
        {
            "player_shot": result,
            "ai_shots": ai_shots,
            "state": engine.state(),
        }
    )


# ----------------------------------------------------------------------
# AI vs AI API
# ----------------------------------------------------------------------
@app.route("/api/aivai/new", methods=["POST"])
def api_aivai_new():
    data = request.get_json(force=True, silent=True) or {}
    agent_a_id = data.get("agent_a")
    agent_b_id = data.get("agent_b")
    engine = get_or_create_aivai_game(new=True, agent_a_id=agent_a_id, agent_b_id=agent_b_id)
    return jsonify(engine.state())


@app.route("/api/aivai/state", methods=["GET"])
def api_aivai_state():
    engine = get_or_create_aivai_game()
    return jsonify(engine.state())


@app.route("/api/aivai/step", methods=["POST"])
def api_aivai_step():
    engine = get_or_create_aivai_game()
    event = engine.step()
    return jsonify({"event": event, "state": engine.state()})


# ----------------------------------------------------------------------
# Algorithm Lab / Comparison API
#
# These run the real BFS/DFS/A* implementations in ai/search.py against
# either the live Human vs AI game's current tracking grid (if one
# exists this session) or a freshly generated random scenario -- never
# fabricated numbers.
# ----------------------------------------------------------------------
@app.route("/api/lab/run", methods=["POST"])
def api_lab_run():
    data = request.get_json(force=True) or {}
    algorithm = data.get("algorithm", "bfs")
    use_live = bool(data.get("use_live_game", False))

    game_id = session.get("game_id")
    if use_live and game_id in GAMES and GAMES[game_id].phase != "placement":
        engine = GAMES[game_id]
        tracking_grid = engine.ai_tracking
        source = "live_game"
    else:
        tracking_grid = generate_scenario()
        source = "random_scenario"

    result = run_search(algorithm, tracking_grid, SIZE)
    result["source"] = source
    result["tracking_grid"] = tracking_grid
    return jsonify(result)


@app.route("/api/lab/live-available", methods=["GET"])
def api_lab_live_available():
    game_id = session.get("game_id")
    available = bool(game_id in GAMES and GAMES[game_id].phase != "placement")
    return jsonify({"available": available})


@app.route("/api/lab/compare", methods=["POST"])
def api_lab_compare():
    """Run BFS, DFS, and A* on the exact same freshly generated scenario."""
    tracking_grid = generate_scenario()
    results = {}
    for algo in ("bfs", "dfs", "astar"):
        results[algo] = run_search(algo, tracking_grid, SIZE)
    return jsonify({"tracking_grid": tracking_grid, "results": results})


@app.route("/api/lab/minimax-compare", methods=["POST"])
def api_lab_minimax_compare():
    """
    Run plain Minimax and Minimax + Alpha-Beta on the IDENTICAL root
    state (same tracking grid, same remaining ship lengths, same depth),
    so nodes evaluated / nodes pruned / execution time / decision are a
    genuine apples-to-apples comparison -- both real executions of
    ai/minimax.py, never invented numbers.
    """
    data = request.get_json(force=True) or {}
    use_live = bool(data.get("use_live_game", False))
    depth = int(data.get("depth", 3))
    depth = max(1, min(depth, 4))  # deeper trees get expensive fast; keep this interactive

    game_id = session.get("game_id")
    if use_live and game_id in GAMES and GAMES[game_id].phase != "placement":
        engine = GAMES[game_id]
        tracking_grid = [row[:] for row in engine.ai_tracking]
        remaining_lengths = engine.remaining_ai_target_lengths()
        source = "live_game"
    else:
        tracking_grid = generate_scenario()
        remaining_lengths = remaining_lengths_from_tracking(tracking_grid, SIZE)
        source = "random_scenario"

    results = {}
    for label, use_ab in (("minimax", False), ("minimax_ab", True)):
        best_cell, stats = select_best_action(
            tracking_grid, remaining_lengths, board_size=SIZE, depth=depth, use_alpha_beta=use_ab
        )
        results[label] = {
            "best_action": list(best_cell) if best_cell else None,
            "best_value": stats.best_value,
            "nodes_evaluated": stats.nodes_evaluated,
            "nodes_pruned": stats.nodes_pruned,
            "search_depth": stats.search_depth,
            "search_time_ms": stats.search_time_ms,
            "used_alpha_beta": stats.used_alpha_beta,
        }

    return jsonify(
        {
            "tracking_grid": tracking_grid,
            "remaining_lengths": remaining_lengths,
            "depth": depth,
            "source": source,
            "results": results,
        }
    )


@app.route("/api/lab/demo", methods=["POST"])
def api_lab_demo():
    """
    Single entry point the AI Lab's algorithm detail view (and the
    Comparison dashboard) uses: runs ONE real algorithm against a
    scenario and returns metrics + a visualization payload. See
    ai/lab_demo.py for exactly what each algorithm returns and why.
    """
    data = request.get_json(force=True) or {}
    algorithm = data.get("algorithm", "bfs")
    use_live = bool(data.get("use_live_game", False))
    depth = int(data.get("depth", 3))
    depth = max(1, min(depth, 4))

    game_id = session.get("game_id")
    if use_live and game_id in GAMES and GAMES[game_id].phase != "placement":
        engine = GAMES[game_id]
        tracking_grid = [row[:] for row in engine.ai_tracking]
        remaining_lengths = engine.remaining_ai_target_lengths()
        remaining_ships = [
            (s.name, s.length) for s in engine.player_board.fleet if not s.is_sunk
        ]
        source = "live_game"
    else:
        tracking_grid = generate_scenario()
        remaining_lengths = remaining_lengths_from_tracking(tracking_grid, SIZE)
        remaining_ships = remaining_ships_from_tracking(tracking_grid, SIZE)
        source = "random_scenario"

    try:
        result = run_demo(
            algorithm, tracking_grid, remaining_lengths,
            board_size=SIZE, remaining_ships=remaining_ships, depth=depth,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    result["source"] = source
    result["tracking_grid"] = tracking_grid
    return jsonify(result)


@app.route("/api/lab/simulate", methods=["POST"])
def api_lab_simulate():
    """
    Runs `games` full automated matches of the chosen strategy against a
    random-targeting baseline (via the real AIVsAIEngine, same engine AI
    vs AI uses), and reports real per-game and aggregate results --
    shots taken, hits, accuracy, and win/loss. Capped so a runaway
    request can't hang the server.
    """
    data = request.get_json(force=True) or {}
    strategy = data.get("strategy", "probability")
    games = int(data.get("games", 5))
    # CSP (repeated AC-3 + backtracking) and anything Minimax-driven cost
    # far more per shot than the others; cap those lower so a request
    # can't take minutes to answer.
    expensive = {"csp", "minimax", "commander2"}
    max_games = 4 if strategy in expensive else 25
    games = max(1, min(games, max_games))

    per_game = []
    wins = 0
    for i in range(games):
        engine = AIVsAIEngine(agent_a_id=strategy, agent_b_id="random")
        steps = 0
        while engine.winner is None and steps < 500:
            engine.step()
            steps += 1
        won = engine.winner == "a"
        wins += int(won)
        shots = engine.moves["a"]
        hits = engine.hits["a"]
        per_game.append(
            {
                "game": i + 1,
                "result": "win" if won else "loss",
                "shots": shots,
                "hits": hits,
                "accuracy": round(100 * hits / shots) if shots else 0,
                "opponent_shots": engine.moves["b"],
            }
        )

    shots_list = [g["shots"] for g in per_game]
    summary = {
        "games": games,
        "wins": wins,
        "losses": games - wins,
        "win_rate": round(100 * wins / games),
        "avg_shots": round(sum(shots_list) / games, 1),
        "min_shots": min(shots_list),
        "max_shots": max(shots_list),
        "avg_accuracy": round(sum(g["accuracy"] for g in per_game) / games, 1),
    }

    return jsonify({"strategy": strategy, "per_game": per_game, "summary": summary})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
