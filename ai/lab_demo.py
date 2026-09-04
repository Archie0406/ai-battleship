"""
ai/lab_demo.py
===============
Single dispatch point that runs any one of the ten AI Lab algorithms
against a given tracking grid and returns a normalized envelope:

    {
        "algorithm": "csp",
        "metrics": {...only fields that make sense for this algorithm...},
        "visualization": {...structure the detail view renders...},
    }

This is deliberately separate from app.py so it can be unit-tested
without Flask, and separate from ai/agent.py so a single demo run
doesn't need to construct a full stateful agent. Every number returned
here comes from actually running the real algorithm in ai/csp.py,
ai/backtracking.py, ai/search.py, ai/probability.py, ai/reasoning.py,
ai/planning.py, or ai/minimax.py against the tracking grid passed in --
nothing is precomputed or invented.

CSP and Backtracking share one underlying solve (ai.csp.solve_fleet_csp
IS the backtracking search over the CSP's domains -- they are the same
computation, viewed through two different pedagogical lenses: "what is
the model" vs "what is the algorithm that solves it"), so both algorithm
ids dispatch to the same handler.
"""

import random

from ai.probability import ProbabilityAI, UNKNOWN, HIT
from ai.search import run_search
from ai.scenario import remaining_ships_from_tracking


def _csp_demo(tracking_grid, remaining_ships, board_size):
    from ai.csp import solve_fleet_csp

    result = solve_fleet_csp(tracking_grid, remaining_ships, board_size=board_size)
    metrics = {
        "nodes_expanded": result["nodes_expanded"],
        "backtracks": result["backtracks"],
        "ac3_removed": result["ac3_removed"],
        "search_time_ms": result["search_time_ms"],
        "solution_found": result["solution"] is not None,
        "domains": [
            {"name": v["name"], "before": v["domain_before"], "after": v["domain_after"]}
            for v in result["variables"]
        ],
    }
    visualization = {
        "variables": result["variables"],
        "solution": result["solution"],
        "trace": result["trace"],
        "ac3_consistent": result["ac3_consistent"],
        "budget_exceeded": result["budget_exceeded"],
    }
    return metrics, visualization


def _search_demo(algorithm, tracking_grid, board_size):
    result = run_search(algorithm, tracking_grid, board_size)
    metrics = {
        "nodes_explored": result["nodes_explored"],
        "states_visited": result["states_visited"],
        "search_time_ms": result["search_time_ms"],
        "search_depth": result["search_depth"],
        "target": result["target"],
    }
    if algorithm == "astar":
        metrics["g_target"] = result.get("g_target")
        metrics["h_target"] = result.get("h_target")
        metrics["f_target"] = result.get("f_target")
    visualization = {"steps": result["steps"], "target": result["target"]}
    return metrics, visualization


def _probability_demo(tracking_grid, remaining_lengths, board_size):
    engine = ProbabilityAI(board_size)
    target, confidence = engine.choose_target_with_confidence(tracking_grid, remaining_lengths)
    density = engine.compute_density_map(tracking_grid, remaining_lengths)
    total = sum(v for row in density for v in row) or 1
    percentages = [[round(100 * v / total, 2) for v in row] for row in density]
    metrics = {"confidence": confidence, "target": list(target)}
    visualization = {"probability_grid": percentages, "target": list(target)}
    return metrics, visualization


def _reasoning_demo(tracking_grid, remaining_ships, board_size):
    """
    Real forward chaining, replayed: build a fresh KnowledgeBase for the
    given fleet, then feed it every fact already present in the tracking
    grid via the exact same record_shot() calls the live game makes, so
    every rule genuinely fires against real data before the final report
    and target are generated.
    """
    from ai.reasoning import KnowledgeBase, ShipInfo

    ships = [ShipInfo(name=n, length=length) for n, length in remaining_ships]
    kb = KnowledgeBase(board_size=board_size, ships=ships)

    size = board_size
    seen = set()
    for r in range(size):
        for c in range(size):
            if tracking_grid[r][c] == "miss" and (r, c) not in seen:
                kb.record_shot(r, c, "miss")
                seen.add((r, c))
            elif tracking_grid[r][c] == HIT and (r, c) not in seen:
                kb.record_shot(r, c, "hit")
                seen.add((r, c))

    # Replay sunk clusters as a hit-then-sunk sequence, so Rule 3 (destroy)
    # actually fires the same way it would in a live game.
    for r in range(size):
        for c in range(size):
            if tracking_grid[r][c] == "sunk" and (r, c) not in seen:
                stack = [(r, c)]
                seen.add((r, c))
                cluster = []
                while stack:
                    cr, cc = stack.pop()
                    cluster.append((cr, cc))
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nr, nc = cr + dr, cc + dc
                        if (
                            0 <= nr < size
                            and 0 <= nc < size
                            and (nr, nc) not in seen
                            and tracking_grid[nr][nc] == "sunk"
                        ):
                            seen.add((nr, nc))
                            stack.append((nr, nc))
                ship_name = None
                for ship in kb.ships:
                    if ship.length == len(cluster) and ship.name not in kb.destroyed_ships:
                        ship_name = ship.name
                        break
                for i, (cr, cc) in enumerate(cluster):
                    is_last = i == len(cluster) - 1
                    kb.record_shot(
                        cr, cc, "sunk" if is_last else "hit",
                        ship_name=ship_name if is_last else None,
                        ship_cells=cluster if is_last else None,
                    )

    target, confidence, explanation = kb.choose_target()
    report = kb.reasoning_report(target, confidence, explanation)
    state = kb.to_state_dict()

    metrics = {
        "confidence": confidence,
        "target": list(target) if target else None,
        "rules_applied": len(report["infer"]),
        "possible_cells": len(state["possible_cells"]),
        "impossible_cells": len(state["impossible_cells"]),
        "destroyed_ships": len(state["destroyed_ships"]),
    }
    visualization = {"report": report, "state": state}
    return metrics, visualization


def _planning_demo(tracking_grid, board_size):
    from ai.planning import plan_candidates

    state, cluster, candidates = plan_candidates(tracking_grid, board_size)
    metrics = {
        "state": state,
        "candidate_count": len(candidates),
        "cluster_size": len(cluster) if cluster else 0,
    }
    visualization = {
        "state": state,
        "cluster": [list(c) for c in cluster] if cluster else [],
        "candidates": [list(c) for c in candidates],
    }
    return metrics, visualization


def _minimax_demo(tracking_grid, remaining_lengths, board_size, use_alpha_beta, depth=3):
    from ai.minimax import select_best_action

    best_cell, stats = select_best_action(
        tracking_grid, remaining_lengths, board_size=board_size, depth=depth, use_alpha_beta=use_alpha_beta
    )
    metrics = {
        "nodes_evaluated": stats.nodes_evaluated,
        "nodes_pruned": stats.nodes_pruned,
        "search_depth": stats.search_depth,
        "search_time_ms": stats.search_time_ms,
        "best_action": list(best_cell) if best_cell else None,
        "used_alpha_beta": stats.used_alpha_beta,
    }
    visualization = {
        "candidate_actions": [[list(c), v] for c, v in stats.candidate_actions],
        "best_action": list(best_cell) if best_cell else None,
    }
    return metrics, visualization


def run_demo(algorithm, tracking_grid, remaining_lengths, board_size=10, remaining_ships=None, depth=3):
    """
    algorithm: one of "csp", "backtracking", "bfs", "dfs", "astar",
               "probability", "reasoning", "planning", "minimax", "alphabeta"
    remaining_lengths: list[int], required for probability/minimax/alphabeta
    remaining_ships: list[(name, length)], required for csp/backtracking/reasoning
                      (derived from tracking_grid if not supplied)
    """
    if remaining_ships is None:
        remaining_ships = remaining_ships_from_tracking(tracking_grid, board_size)

    if algorithm in ("csp", "backtracking"):
        metrics, visualization = _csp_demo(tracking_grid, remaining_ships, board_size)
    elif algorithm in ("bfs", "dfs", "astar"):
        metrics, visualization = _search_demo(algorithm, tracking_grid, board_size)
    elif algorithm == "probability":
        metrics, visualization = _probability_demo(tracking_grid, remaining_lengths, board_size)
    elif algorithm == "reasoning":
        metrics, visualization = _reasoning_demo(tracking_grid, remaining_ships, board_size)
    elif algorithm == "planning":
        metrics, visualization = _planning_demo(tracking_grid, board_size)
    elif algorithm == "minimax":
        metrics, visualization = _minimax_demo(tracking_grid, remaining_lengths, board_size, use_alpha_beta=False, depth=depth)
    elif algorithm == "alphabeta":
        metrics, visualization = _minimax_demo(tracking_grid, remaining_lengths, board_size, use_alpha_beta=True, depth=depth)
    else:
        raise ValueError(f"Unknown algorithm '{algorithm}'")

    return {
        "algorithm": algorithm,
        "metrics": metrics,
        "visualization": visualization,
    }
