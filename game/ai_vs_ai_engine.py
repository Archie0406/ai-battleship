"""
game/ai_vs_ai_engine.py
========================
Infrastructure for two AI agents to play a full Battleship match against
each other with no human input. Built around the same ai.agent.BaseAgent
interface the Human vs AI engine uses (choose_target + optional
observe_result), so ANY registered agent -- including future ones -- can
be dropped onto either side without touching this file.

By default this pits two named "AI Commanders" against each other, per
the project brief's example pairing:

    AI Commander 01 -- Probability + Search
        Broad-scans with probability-density reasoning; the instant it
        has a lead (an active hit), it switches to real A* search to
        home in on the ship (ai.agent.HybridSearchCommander).

    AI Commander 02 -- Minimax + Planning
        Classifies its own tactical state every turn via the real
        SEARCH/TARGET/DESTROY planner; in SEARCH it hunts using genuine
        depth-limited Minimax with alpha-beta pruning, and in TARGET/
        DESTROY it follows the planner's own prioritized candidates
        (ai.agent.HybridMinimaxCommander).

Either side can be swapped for any other registered strategy (see
ai.agent.make_agent) -- e.g. pure Minimax vs pure Probability -- via the
agent_a_id / agent_b_id constructor arguments, so spectators can set up
whatever matchup they want to watch.
"""

import uuid

from game.board import Board, SIZE
from ai.agent import make_agent
from ai.probability import UNKNOWN, MISS, HIT, SUNK

DEFAULT_AGENT_A = "commander1"
DEFAULT_AGENT_B = "commander2"


class AIVsAIEngine:
    def __init__(self, board_size=10, agent_a_id=None, agent_b_id=None):
        self.id = str(uuid.uuid4())
        self.board_size = board_size

        self.board_a = Board(board_size)
        self.board_b = Board(board_size)
        self.board_a.random_placement()
        self.board_b.random_placement()

        self.agent_a_id = agent_a_id or DEFAULT_AGENT_A
        self.agent_b_id = agent_b_id or DEFAULT_AGENT_B
        # agent_a fires at board_b; agent_b fires at board_a
        self.agent_a = make_agent(self.agent_a_id, board_size)
        self.agent_b = make_agent(self.agent_b_id, board_size)

        self.tracking_a = [[UNKNOWN] * board_size for _ in range(board_size)]  # what A knows about B
        self.tracking_b = [[UNKNOWN] * board_size for _ in range(board_size)]  # what B knows about A

        self.turn = "a"
        self.winner = None
        self.log = []
        self.moves = {"a": 0, "b": 0}
        self.hits = {"a": 0, "b": 0}
        self.last_move = None

        # Per-side telemetry, mirroring GameEngine's pattern exactly so the
        # same frontend rendering logic can drive either page.
        self.telemetry = {"a": {}, "b": {}}

    def _remaining_lengths(self, board):
        return [ship.length for ship in board.fleet if not ship.is_sunk]

    def _apply_result(self, tracking, r, c, outcome, target_board):
        result = outcome["result"]
        if result == "sunk":
            tracking[r][c] = SUNK
            for ship in target_board.fleet:
                if ship.name == outcome["ship"]:
                    for sr, sc in ship.cells:
                        tracking[sr][sc] = SUNK
        elif result == "hit":
            tracking[r][c] = HIT
        elif result == "miss":
            tracking[r][c] = MISS

    def _check_winner(self):
        if self.board_b.all_sunk:
            self.winner = "a"
        elif self.board_a.all_sunk:
            self.winner = "b"
        return self.winner

    def _capture_telemetry(self, side, agent):
        self.telemetry[side] = {
            "search": getattr(agent, "last_result", None),
            "reasoning": getattr(agent, "last_reasoning", None),
            "planning": getattr(agent, "last_plan", None),
            "minimax": getattr(agent, "last_minimax", None),
        }

    def step(self):
        """Execute exactly one shot for whichever agent's turn it is."""
        if self.winner is not None:
            return None

        if self.turn == "a":
            attacker, agent = "a", self.agent_a
            tracking, target_board = self.tracking_a, self.board_b
        else:
            attacker, agent = "b", self.agent_b
            tracking, target_board = self.tracking_b, self.board_a

        remaining = self._remaining_lengths(target_board)
        (r, c), confidence = agent.choose_target(tracking, remaining)
        outcome = target_board.receive_shot(r, c)
        result = outcome["result"]

        sunk_ship_cells = None
        if result == "sunk":
            for ship in target_board.fleet:
                if ship.name == outcome["ship"]:
                    sunk_ship_cells = list(ship.cells)
                    break

        self._apply_result(tracking, r, c, outcome, target_board)
        agent.observe_result(r, c, result, outcome["ship"], sunk_ship_cells)
        self._capture_telemetry(attacker, agent)

        self.moves[attacker] += 1
        if result in ("hit", "sunk"):
            self.hits[attacker] += 1

        entry = {
            "actor": attacker,
            "agent": agent.name,
            "cell": [r, c],
            "result": result,
            "ship": outcome["ship"],
            "confidence": confidence,
        }
        self.log.append(entry)
        self.last_move = entry

        self._check_winner()
        if result == "miss" or self.winner is not None:
            self.turn = "b" if attacker == "a" else "a"

        return entry

    def state(self):
        return {
            "id": self.id,
            "turn": self.turn,
            "winner": self.winner,
            "agent_a": {**self.agent_a.to_dict(), "id": self.agent_a_id},
            "agent_b": {**self.agent_b.to_dict(), "id": self.agent_b_id},
            "board_a": self.board_a.to_dict(reveal_ships=True),
            "board_b": self.board_b.to_dict(reveal_ships=True),
            "log": self.log[-20:],
            "last_move": self.last_move,
            "moves": self.moves,
            "hits": self.hits,
            "telemetry_a": self.telemetry["a"],
            "telemetry_b": self.telemetry["b"],
        }
