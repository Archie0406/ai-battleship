"""
game/game_engine.py
====================
Orchestrates a single Human vs AI Battleship match: owns both boards,
runs a manual/random ship-placement phase, manages whose turn it is
once battle starts, resolves shots, and delegates AI targeting to an
injected agent (see ai/agent.py for the pluggable agent interface).

A GameEngine instance is meant to be kept server-side per session (see
app.py) and mutated via the placement methods, then fire_player_shot()
/ run_ai_turn() once the battle phase begins.
"""

import uuid

from game.board import Board, SIZE
from ai.agent import ProbabilityAgent, RandomAgent, SearchAgent, ReasoningAgent, PlanningAgent, MinimaxAgent, CSPAgent
from ai.probability import UNKNOWN, MISS, HIT, SUNK

PHASE_PLACEMENT = "placement"
PHASE_BATTLE = "battle"
PHASE_OVER = "over"

# String ids the frontend's algorithm selector sends -> factory functions.
# Kept here (rather than only in ai/agent.make_agent) so GameEngine can
# validate the id and reject anything unrecognized with a clean error.
STRATEGIES = {
    "probability": lambda size: ProbabilityAgent(size),
    "random": lambda size: RandomAgent(size),
    "bfs": lambda size: SearchAgent("bfs", size),
    "dfs": lambda size: SearchAgent("dfs", size),
    "astar": lambda size: SearchAgent("astar", size),
    "reasoning": lambda size: ReasoningAgent(size),
    "planning": lambda size: PlanningAgent(size),
    "minimax": lambda size: MinimaxAgent(size, use_alpha_beta=True),
    "csp": lambda size: CSPAgent(size),
}


class GameEngine:
    def __init__(self, board_size=SIZE):
        self.id = str(uuid.uuid4())
        self.board_size = board_size

        # Player fleet starts empty -- filled via manual placement or
        # randomize_player_fleet() during the placement phase.
        self.player_board = Board(board_size)
        # The AI's own fleet can be placed immediately since it stays hidden.
        self.ai_board = Board(board_size)
        self.ai_board.random_placement()

        self.ai_tracking = [
            [UNKNOWN for _ in range(board_size)] for _ in range(board_size)
        ]

        self.ai_agent = ProbabilityAgent(board_size)
        self.ai_confidence = None
        self.ai_strategy_id = "probability"
        self.last_search = None  # most recent search trace/metrics, when using a SearchAgent
        self.reasoning_state = None  # knowledge base + inference report, when using ReasoningAgent
        self.planning_state = None  # {"state","cluster","candidates"}, when using a planner
        self.minimax_state = None  # real SearchStats dict, when using a minimax-driven agent
        self.csp_state = None  # solve_fleet_csp() result, when using CSPAgent

        self.phase = PHASE_PLACEMENT
        self.turn = "player"
        self.winner = None
        self.log = []

        self.last_move = None
        self.player_shots = 0
        self.player_hits = 0
        self.ai_shots = 0
        self.ai_hits = 0

    # ------------------------------------------------------------------
    # Placement phase
    # ------------------------------------------------------------------
    def place_ship(self, name, r, c, horizontal):
        if self.phase != PHASE_PLACEMENT:
            return {"error": "Fleet is already locked in"}
        try:
            self.player_board.place_named_ship(name, r, c, horizontal)
        except ValueError as e:
            return {"error": str(e)}
        return {"ok": True}

    def remove_ship(self, name):
        if self.phase != PHASE_PLACEMENT:
            return {"error": "Fleet is already locked in"}
        self.player_board.remove_ship(name)
        return {"ok": True}

    def randomize_player_fleet(self):
        if self.phase != PHASE_PLACEMENT:
            return {"error": "Fleet is already locked in"}
        self.player_board.random_placement()
        return {"ok": True}

    def reset_player_fleet(self):
        if self.phase != PHASE_PLACEMENT:
            return {"error": "Fleet is already locked in"}
        self.player_board.reset_fleet()
        return {"ok": True}

    def confirm_fleet(self):
        if self.phase != PHASE_PLACEMENT:
            return {"error": "Fleet is already locked in"}
        if not self.player_board.is_fully_placed:
            return {"error": "Place every ship before confirming"}
        self.phase = PHASE_BATTLE
        self.turn = "player"
        return {"ok": True}

    def set_ai_strategy(self, strategy):
        """
        Swap the AI's targeting brain before battle starts. This is not
        cosmetic: run_ai_turn() calls self.ai_agent.choose_target() every
        turn, so whichever strategy is selected here genuinely decides
        the AI's shots for the rest of the match.
        """
        if self.phase != PHASE_PLACEMENT:
            return {"error": "Strategy can only be changed before battle starts"}
        factory = STRATEGIES.get(strategy)
        if factory is None:
            return {"error": f"Unknown strategy '{strategy}'"}
        self.ai_agent = factory(self.board_size)
        self.ai_strategy_id = strategy
        self.ai_confidence = None
        self.last_search = None
        self.reasoning_state = None
        self.planning_state = None
        self.minimax_state = None
        self.csp_state = None
        return {"ok": True}

    # ------------------------------------------------------------------
    # Battle phase
    # ------------------------------------------------------------------
    def _remaining_lengths(self, board):
        return [ship.length for ship in board.fleet if not ship.is_sunk]

    def remaining_ai_target_lengths(self):
        """Public accessor: lengths of the player's ships not yet sunk --
        i.e. what the AI is still hunting for. Used by the Algorithm Lab's
        live-game Minimax comparison so it reasons about the exact same
        remaining fleet the real AI turn would."""
        return self._remaining_lengths(self.player_board)

    def _record(self, actor, cell, outcome):
        entry = {
            "actor": actor,
            "cell": list(cell),
            "result": outcome["result"],
            "ship": outcome["ship"],
        }
        self.log.append(entry)
        self.last_move = entry

    def _check_winner(self):
        if self.ai_board.all_sunk:
            self.winner = "player"
            self.phase = PHASE_OVER
        elif self.player_board.all_sunk:
            self.winner = "ai"
            self.phase = PHASE_OVER
        return self.winner

    def fire_player_shot(self, r, c):
        if self.phase != PHASE_BATTLE:
            return {"error": "Game is not in the battle phase"}
        if self.turn != "player":
            return {"error": "Not player's turn"}

        outcome = self.ai_board.receive_shot(r, c)
        if outcome["result"] == "repeat":
            return {"error": "Cell already fired upon"}

        self.player_shots += 1
        if outcome["result"] in ("hit", "sunk"):
            self.player_hits += 1

        self._record("player", (r, c), outcome)
        self._check_winner()

        if self.winner is None and outcome["result"] == "miss":
            self.turn = "ai"

        return {
            "result": outcome["result"],
            "ship": outcome["ship"],
            "winner": self.winner,
            "turn": self.turn,
        }

    def run_ai_turn(self):
        """
        Executes AI shots until the AI misses, the game ends, or turn
        control returns to the player. Returns the list of shots taken.
        """
        if self.phase != PHASE_BATTLE or self.turn != "ai":
            return []

        shots_taken = []
        while self.turn == "ai" and self.winner is None:
            remaining = self._remaining_lengths(self.player_board)
            (r, c), confidence = self.ai_agent.choose_target(self.ai_tracking, remaining)
            self.ai_confidence = confidence
            self.last_search = getattr(self.ai_agent, "last_result", None)

            outcome = self.player_board.receive_shot(r, c)
            result = outcome["result"]

            sunk_ship_cells = None
            if result == "sunk":
                self.ai_tracking[r][c] = SUNK
                for ship in self.player_board.fleet:
                    if ship.name == outcome["ship"]:
                        sunk_ship_cells = list(ship.cells)
                        for sr, sc in ship.cells:
                            self.ai_tracking[sr][sc] = SUNK
            elif result == "hit":
                self.ai_tracking[r][c] = HIT
            elif result == "miss":
                self.ai_tracking[r][c] = MISS

            self.ai_agent.observe_result(r, c, result, outcome["ship"], sunk_ship_cells)
            self.reasoning_state = getattr(self.ai_agent, "last_reasoning", None)
            self.planning_state = getattr(self.ai_agent, "last_plan", None)
            self.minimax_state = getattr(self.ai_agent, "last_minimax", None)
            self.csp_state = getattr(self.ai_agent, "last_csp", None)

            self.ai_shots += 1
            if result in ("hit", "sunk"):
                self.ai_hits += 1

            self._record("ai", (r, c), outcome)
            shots_taken.append({"cell": [r, c], "result": result, "ship": outcome["ship"]})
            self._check_winner()

            if result == "miss" or self.winner is not None:
                self.turn = "player"

        return shots_taken

    # ------------------------------------------------------------------
    def _accuracy(self, hits, shots):
        return round((hits / shots) * 100) if shots else 0

    def _status_label(self):
        if self.phase == PHASE_PLACEMENT:
            return "Setup"
        if self.winner == "player":
            return "Victory"
        if self.winner == "ai":
            return "Defeat"
        return "In Progress"

    def state(self):
        search_metrics = None
        search_trace = None
        if self.last_search is not None:
            search_metrics = {
                "algorithm": self.last_search["algorithm"],
                "nodes_explored": self.last_search["nodes_explored"],
                "states_visited": self.last_search["states_visited"],
                "search_time_ms": self.last_search["search_time_ms"],
                "search_depth": self.last_search["search_depth"],
                "target_selected": self.last_search["target"],
                "g_target": self.last_search.get("g_target"),
                "h_target": self.last_search.get("h_target"),
                "f_target": self.last_search.get("f_target"),
            }
            search_trace = self.last_search["steps"]

        reasoning = None
        if self.reasoning_state is not None:
            reasoning = {
                "report": self.reasoning_state["report"],
                "probability_grid": self.reasoning_state["state"]["probability_grid"],
                "candidate_density_grid": self.reasoning_state["state"]["candidate_density_grid"],
                "possible_cells": self.reasoning_state["state"]["possible_cells"],
                "impossible_cells": self.reasoning_state["state"]["impossible_cells"],
                "priority_cells": self.reasoning_state["state"]["priority_cells"],
                "current_target": self.reasoning_state["state"]["current_target"],
                "destroyed_ships": self.reasoning_state["state"]["destroyed_ships"],
                "candidate_counts": self.reasoning_state["state"]["candidate_counts"],
            }

        return {
            "id": self.id,
            "phase": self.phase,
            "turn": self.turn,
            "winner": self.winner,
            "status_label": self._status_label(),
            "player_board": self.player_board.to_dict(reveal_ships=True),
            "ai_board": self.ai_board.to_dict(reveal_ships=False),
            "log": self.log[-20:],
            "last_move": self.last_move,
            "ai_strategy": self.ai_agent.name,
            "ai_strategy_id": self.ai_strategy_id,
            "ai_confidence": self.ai_confidence,
            "search_metrics": search_metrics,
            "search_trace": search_trace,
            "reasoning": reasoning,
            "planning": self.planning_state,
            "minimax": self.minimax_state,
            "csp": self.csp_state,
            "moves": {"player": self.player_shots, "ai": self.ai_shots},
            "hits": {"player": self.player_hits, "ai": self.ai_hits},
            "accuracy": {
                "player": self._accuracy(self.player_hits, self.player_shots),
                "ai": self._accuracy(self.ai_hits, self.ai_shots),
            },
            "ships_remaining": {
                "player": sum(1 for s in self.player_board.fleet if not s.is_sunk),
                "ai": sum(1 for s in self.ai_board.fleet if not s.is_sunk),
            },
            "fleet_definition": [
                {"name": s.name, "length": s.length} for s in self.player_board.fleet
            ],
        }
