"""
ai/agent.py
===========
A common interface every AI targeting strategy implements, so the game
engine (and the AI-vs-AI engine) can drive any of them interchangeably
without knowing which algorithm is underneath.

    agent.choose_target(tracking_grid, remaining_lengths)
        -> ((row, col), confidence)

`tracking_grid` is what this agent currently knows about the *opponent's*
board (UNKNOWN/MISS/HIT/SUNK per cell, see ai/probability.py).
`confidence` is a 0-100 int, or None if the strategy doesn't have a
meaningful notion of confidence (e.g. pure random search).

Two agents ship today:
    RandomAgent        -- uninformed baseline, fires at any untried cell
    ProbabilityAgent    -- wraps ai/probability.py's density-map reasoning

Future phases add CSPAgent, SearchAgent, MinimaxAgent, GeneticAgent, etc.
by implementing this same interface -- nothing else in the game needs to
change to plug a new one in.
"""

import random

from ai.probability import ProbabilityAI, UNKNOWN, HIT


class BaseAgent:
    name = "Base Agent"
    description = ""

    def __init__(self, board_size=10):
        self.board_size = board_size

    def choose_target(self, tracking_grid, remaining_lengths):
        raise NotImplementedError

    def observe_result(self, r, c, result, ship_name=None, ship_cells=None):
        """
        Optional hook: called by the engine right after a shot this agent
        took is resolved, so stateful agents can record what happened.
        Stateless agents (Random, Probability, Search) recompute fresh
        from the tracking grid every turn and don't need history, so the
        default is a no-op.
        """
        pass

    def to_dict(self):
        return {"name": self.name, "description": self.description}


class RandomAgent(BaseAgent):
    """Uninformed baseline: fires at a uniformly random untried cell."""

    name = "Random Targeting"
    description = "Fires at any untried cell with no reasoning."

    def choose_target(self, tracking_grid, remaining_lengths):
        n = self.board_size
        candidates = [
            (r, c)
            for r in range(n)
            for c in range(n)
            if tracking_grid[r][c] == UNKNOWN
        ]
        if not candidates:
            candidates = [(0, 0)]
        return random.choice(candidates), None


class ProbabilityAgent(BaseAgent):
    """Wraps the live probability-density reasoning engine."""

    name = "Probability Density"
    description = "Scores every cell by how many consistent ship placements still cover it."

    def __init__(self, board_size=10):
        super().__init__(board_size)
        self.engine = ProbabilityAI(board_size)

    def choose_target(self, tracking_grid, remaining_lengths):
        return self.engine.choose_target_with_confidence(tracking_grid, remaining_lengths)


_SEARCH_LABELS = {
    "bfs": "BFS Search",
    "dfs": "DFS Search",
    "astar": "A* Search",
}
_SEARCH_DESCRIPTIONS = {
    "bfs": "Explores the grid breadth-first (FIFO queue) from known hits, or the board center, to reach the nearest untried cell.",
    "dfs": "Dives depth-first (LIFO stack) along one direction before backtracking to find an untried cell.",
    "astar": "Orders candidates by f(n) = g(n) + h(n): real path cost plus distance to the nearest lead, reaching a close, promising cell efficiently.",
}


class SearchAgent(BaseAgent):
    """
    Wraps ai/search.py's real BFS, DFS, or A* implementation. Whichever
    algorithm is selected genuinely executes and decides the target --
    this class does not fake or relabel anything.
    """

    def __init__(self, algorithm="bfs", board_size=10):
        super().__init__(board_size)
        self.algorithm = algorithm
        self.name = _SEARCH_LABELS.get(algorithm, "Search Agent")
        self.description = _SEARCH_DESCRIPTIONS.get(algorithm, "")
        self.last_result = None  # most recent full search trace + metrics

    def choose_target(self, tracking_grid, remaining_lengths):
        # imported lazily to avoid any import-order surprises at module load
        from ai.search import run_search

        result = run_search(self.algorithm, tracking_grid, self.board_size)
        self.last_result = result

        r, c = result["target"]
        # Confidence: derived directly from the real search output --
        # h_target for A* (distance to the nearest lead), or search_depth
        # as a stand-in for BFS/DFS which don't compute a heuristic.
        h_val = result.get("h_target", result.get("search_depth", 0))
        confidence = max(5, min(99, round(100 / (1 + h_val))))
        return (r, c), confidence


class ReasoningAgent(BaseAgent):
    """
    Wraps ai/reasoning.py's real knowledge base + forward-chaining engine.
    Unlike the stateless agents above, this one keeps a persistent
    KnowledgeBase across the whole match: every resolved shot is recorded
    via observe_result() (hit/miss/sunk, with the real ship name), which
    runs forward chaining and incrementally prunes the candidate-placement
    domain for every remaining ship. choose_target() then targets the
    single highest-probability cell in that domain -- the same
    computation the AI Reasoning panel displays, not a separate one.
    """

    name = "Knowledge & Reasoning"
    description = "Maintains a real knowledge base and forward-chains hit/miss/sunk facts into a candidate-placement probability grid."

    def __init__(self, board_size=10):
        super().__init__(board_size)
        # Lazy imports: keeps ai/reasoning.py and game/ships.py decoupled
        # from the rest of ai/ until a ReasoningAgent is actually built.
        from ai.reasoning import KnowledgeBase, ShipInfo
        from game.ships import FLEET

        ships = [ShipInfo(name=n, length=length) for n, length in FLEET]
        self.kb = KnowledgeBase(board_size=board_size, ships=ships)
        self.last_reasoning = None  # {"report": {...}, "state": {...}}, refreshed after every shot
        self._pending_target = None
        self._pending_confidence = None
        self._pending_explanation = None

    def choose_target(self, tracking_grid, remaining_lengths):
        # Defensive re-sync: harmless no-op if observe_result() already
        # kept the knowledge base's tracking grid in lockstep (the normal
        # path), but keeps this agent correct even if used somewhere that
        # never calls observe_result (e.g. a future AI-vs-AI matchup).
        self.kb.sync_from_tracking_grid(tracking_grid, self.kb.destroyed_ships)
        target, confidence, explanation = self.kb.choose_target()
        self._pending_target = target
        self._pending_confidence = confidence
        self._pending_explanation = explanation
        self.last_reasoning = {
            "report": self.kb.reasoning_report(target, confidence, explanation),
            "state": self.kb.to_state_dict(),
        }
        return target, confidence

    def observe_result(self, r, c, result, ship_name=None, ship_cells=None):
        self.kb.record_shot(r, c, result, ship_name=ship_name, ship_cells=ship_cells)
        # Refresh the snapshot now that the outcome is known, so "WHAT I
        # KNOW" reflects this shot's result while "WHAT I WILL DO" still
        # describes (accurately, in hindsight) the decision that led to it.
        self.last_reasoning = {
            "report": self.kb.reasoning_report(
                self._pending_target, self._pending_confidence, self._pending_explanation
            ),
            "state": self.kb.to_state_dict(),
        }


class PlanningAgent(BaseAgent):
    """
    Wraps ai/planning.py's real SEARCH -> TARGET -> DESTROY state machine.
    The tactical state is never stored as a flag that could drift out of
    sync -- compute_tactical_state() (inside plan_candidates()) derives it
    fresh from the tracking grid every single turn. In TARGET/DESTROY the
    planner's own priority-ordered candidates are used directly; in SEARCH
    (no lead to follow) broad scanning is delegated to the same
    probability-density engine ai.agent.ProbabilityAgent uses, since the
    planner intentionally doesn't duplicate that logic (see planning.py's
    docstring on plan_candidates()).
    """

    name = "Tactical Planner"
    description = "Classifies its own state every turn -- SEARCH, TARGET, or DESTROY -- and acts accordingly."

    def __init__(self, board_size=10):
        super().__init__(board_size)
        self.prob_engine = ProbabilityAI(board_size)
        self.last_plan = None  # {"state", "cluster", "candidates"}

    def choose_target(self, tracking_grid, remaining_lengths):
        from ai.planning import plan_candidates, SEARCH, DESTROY

        state, cluster, candidates = plan_candidates(tracking_grid, self.board_size)
        self.last_plan = {
            "state": state,
            "cluster": [list(c) for c in cluster] if cluster else [],
            "candidates": [list(c) for c in candidates],
        }

        if state != SEARCH and candidates:
            target = candidates[0]
            confidence = 90 if state == DESTROY else 65
            return target, confidence

        # SEARCH: no lead to follow -- broad-scan with probability density.
        target, confidence = self.prob_engine.choose_target_with_confidence(
            tracking_grid, remaining_lengths
        )
        return target, confidence


class MinimaxAgent(BaseAgent):
    """
    Wraps ai/minimax.py's real depth-limited Minimax search (optionally
    alpha-beta pruned) over an explicit MAX (the AI's shot) / MIN (the
    hidden fleet, played adversarially within what's logically consistent
    with observations) game tree. See ai/minimax.py's module docstring for
    the full, honest treatment of hidden information -- this class only
    wires that search into the common agent interface and records its
    real statistics for the Minimax Engine panel.
    """

    def __init__(self, board_size=10, use_alpha_beta=True, depth=3):
        super().__init__(board_size)
        self.use_alpha_beta = use_alpha_beta
        self.depth = depth
        self.name = "Minimax + Alpha-Beta" if use_alpha_beta else "Minimax (no pruning)"
        self.description = (
            "Depth-limited Minimax over MAX (my shot) vs MIN (the hidden fleet, worst-case "
            "within what's still logically consistent), " +
            ("pruned with alpha-beta." if use_alpha_beta else "exhaustive, no pruning.")
        )
        self.last_minimax = None  # real SearchStats, as a JSON-safe dict

    def choose_target(self, tracking_grid, remaining_lengths):
        from ai.minimax import select_best_action

        best_cell, stats = select_best_action(
            tracking_grid,
            remaining_lengths,
            board_size=self.board_size,
            depth=self.depth,
            use_alpha_beta=self.use_alpha_beta,
        )

        if best_cell is None:
            # No legal actions scored (board effectively full) -- fall back
            # to any untried cell so the agent never stalls.
            n = self.board_size
            fallback = [
                (r, c) for r in range(n) for c in range(n) if tracking_grid[r][c] == UNKNOWN
            ]
            best_cell = fallback[0] if fallback else (0, 0)

        values = [v for _cell, v in stats.candidate_actions]
        if len(values) >= 2 and (max(values) - min(values)) > 0:
            spread = max(values) - min(values)
            avg = sum(values) / len(values)
            confidence = round(50 + 45 * (stats.best_value - avg) / spread)
            confidence = max(5, min(99, confidence))
        else:
            confidence = 50

        self.last_minimax = {
            "nodes_evaluated": stats.nodes_evaluated,
            "nodes_pruned": stats.nodes_pruned,
            "search_depth": stats.search_depth,
            "best_action": list(stats.best_action) if stats.best_action else list(best_cell),
            "best_value": stats.best_value,
            "search_time_ms": stats.search_time_ms,
            "used_alpha_beta": stats.used_alpha_beta,
            "candidate_actions": [[list(c), v] for c, v in stats.candidate_actions],
        }
        return best_cell, confidence


class HybridSearchCommander(BaseAgent):
    """
    "AI Commander 01": probability-density broad scanning, switching to
    real A* search the instant there's a lead (any active HIT cell) to
    home in on. Both halves are the genuine agents already implemented
    elsewhere -- this class only decides, each turn, which one gets to
    act, and is honest about which mode produced the shot.
    """

    name = "Commander 01 — Probability + Search"
    description = "Hunts broadly with probability density; switches to A* search the moment it has a lead."

    def __init__(self, board_size=10):
        super().__init__(board_size)
        self.prob_agent = ProbabilityAgent(board_size)
        self.search_agent = SearchAgent("astar", board_size)
        self.last_mode = None       # "probability" | "search"
        self.last_result = None     # mirrors SearchAgent.last_result while in search mode

    def choose_target(self, tracking_grid, remaining_lengths):
        has_lead = any(HIT in row for row in tracking_grid)
        if has_lead:
            self.last_mode = "search"
            target, confidence = self.search_agent.choose_target(tracking_grid, remaining_lengths)
            self.last_result = self.search_agent.last_result
            return target, confidence
        self.last_mode = "probability"
        self.last_result = None
        return self.prob_agent.choose_target(tracking_grid, remaining_lengths)


class HybridMinimaxCommander(BaseAgent):
    """
    "AI Commander 02": formally classifies its tactical state every turn
    via ai/planning.py's real SEARCH/TARGET/DESTROY machine. In TARGET or
    DESTROY it follows the planner's own prioritized candidates directly.
    In SEARCH -- no lead yet -- it hunts using genuine depth-limited
    Minimax with alpha-beta pruning rather than plain probability density,
    so its broad-scan decisions are adversarially worst-case reasoned.
    """

    name = "Commander 02 — Minimax + Planning"
    description = "Classifies SEARCH/TARGET/DESTROY every turn; hunts broadly with Minimax + Alpha-Beta, follows the planner once it has a lead."

    def __init__(self, board_size=10):
        super().__init__(board_size)
        self.minimax_agent = MinimaxAgent(board_size, use_alpha_beta=True)
        self.last_plan = None
        self.last_minimax = None

    def choose_target(self, tracking_grid, remaining_lengths):
        from ai.planning import plan_candidates, SEARCH, DESTROY

        state, cluster, candidates = plan_candidates(tracking_grid, self.board_size)
        self.last_plan = {
            "state": state,
            "cluster": [list(c) for c in cluster] if cluster else [],
            "candidates": [list(c) for c in candidates],
        }

        if state != SEARCH and candidates:
            self.last_minimax = None
            target = candidates[0]
            confidence = 90 if state == DESTROY else 65
            return target, confidence

        target, confidence = self.minimax_agent.choose_target(tracking_grid, remaining_lengths)
        self.last_minimax = self.minimax_agent.last_minimax
        return target, confidence


class CSPAgent(BaseAgent):
    """
    Wraps ai/csp.py's real Constraint Satisfaction formulation, solved by
    ai/backtracking.py's MRV/LCV/forward-checking search. Each turn,
    several complete consistent fleet assignments are sampled (see
    ai.csp.sample_target's docstring for why this is a genuinely
    different -- and stronger -- notion of "probability" than per-ship
    independent counting), and the AI fires at whichever UNKNOWN cell
    was covered by the most sampled solutions.
    """

    name = "CSP + Backtracking"
    description = "Solves fleet placement as a real Constraint Satisfaction Problem (AC-3 + MRV/LCV backtracking) and targets the cell most sampled solutions agree on."

    def __init__(self, board_size=10, samples=6):
        super().__init__(board_size)
        self.samples = samples
        self.last_csp = None  # {"result": <solve_fleet_csp() dict>, "samples": int}

    def choose_target(self, tracking_grid, remaining_lengths):
        from ai.csp import sample_target
        from ai.scenario import remaining_ships_from_tracking

        # remaining_lengths (ints) doesn't carry ship names, which the CSP
        # needs for its per-ship variables -- reconstruct them the same
        # honest, best-effort way the Lab's demo endpoints do.
        remaining_ships = remaining_ships_from_tracking(tracking_grid, self.board_size)
        # Defend against any length mismatch (shouldn't happen in normal
        # play, since remaining_lengths always comes from the same board).
        if sorted(l for _n, l in remaining_ships) != sorted(remaining_lengths):
            from game.ships import FLEET
            pool = list(FLEET)
            remaining_ships = []
            for length in remaining_lengths:
                for i, (name, plen) in enumerate(pool):
                    if plen == length:
                        remaining_ships.append((name, plen))
                        pool.pop(i)
                        break

        target, confidence, last_result = sample_target(
            tracking_grid, remaining_ships, board_size=self.board_size, samples=self.samples
        )
        self.last_csp = {"result": last_result, "samples": self.samples}
        return target, confidence


def make_agent(kind, board_size=10):
    """Factory so callers can select an agent by short string id."""
    if kind in ("bfs", "dfs", "astar"):
        return SearchAgent(kind, board_size)
    registry = {
        "random": RandomAgent,
        "probability": ProbabilityAgent,
        "reasoning": ReasoningAgent,
        "planning": PlanningAgent,
        "minimax": MinimaxAgent,
        "csp": CSPAgent,
        "commander1": HybridSearchCommander,
        "commander2": HybridMinimaxCommander,
    }
    cls = registry.get(kind, ProbabilityAgent)
    return cls(board_size)
