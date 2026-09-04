"""
ai/minimax.py
=============
A genuine Minimax search, with and without alpha-beta pruning, for
choosing the AI's next shot.

==========================================================================
HOW HIDDEN INFORMATION IS HANDLED (read this before anything else)
==========================================================================
Battleship is NOT a perfect-information game: neither player can see the
other's fleet. Classic Minimax assumes both players see the exact game
state, so it cannot be applied to the raw board -- doing that honestly
would just be lying about what the AI "sees".

Instead, this module treats the *unknown fleet layout itself* as the
adversary's hidden choice, and searches an explicit MAX/MIN tree where:

    MAX ply (the AI choosing a shot)
        Legal actions are a short list of candidate cells -- the
        highest-probability UNKNOWN cells according to the same
        density-map reasoning ai/probability.py already uses (imported
        directly, not reimplemented). Restricting the branching factor
        to these top-K cells is a standard move-ordering/pruning choice
        (exactly what real engines do to keep search tractable), not a
        rule of the game -- documented here so it's clear in a viva.

    MIN ply ("the hidden fleet", played adversarially)
        For the cell MAX just fired at, MIN chooses the outcome --
        HIT or MISS -- from whichever outcomes are actually still
        CONSISTENT with everything observed so far. A cell already
        proven impossible to contain a ship (e.g. it's surrounded by
        misses/sunk cells such that no remaining ship of any length
        could legally cover it) only offers MISS as a legal choice.
        Otherwise MIN can pick either outcome, and being adversarial,
        picks whichever is worse for MAX. This is a standard, honest way
        to make worst-case decisions under hidden information: instead
        of guessing the true layout, plan for the worst layout that is
        still LOGICALLY CONSISTENT with what has actually been observed.
        No cheating: this code never reads the opponent's real fleet.

Because fully simulating every ship's exact shape at every depth is
expensive, the search does not track ship geometry beyond hit/miss counts
past the root; it uses a depth-limited heuristic evaluation (net hits
minus misses accumulated along the simulated line) instead of searching
to a true terminal (all-ships-sunk) state -- exactly the same reason
chess engines use a heuristic evaluation function instead of searching to
checkmate.

==========================================================================
STATE REPRESENTATION
==========================================================================
A _MMState is a small, immutable-by-convention snapshot:
    tracking            -- 2D UNKNOWN/MISS/HIT/SUNK grid for this branch
    remaining_lengths    -- lengths of ships not yet known-sunk in this branch
    hits, misses          -- net shots landed/wasted so far in this branch
    maximizing           -- whose ply this node is

==========================================================================
ALGORITHMS
==========================================================================
minimax(state, depth)      -- exhaustive, no pruning
alpha_beta(state, depth)   -- identical tree and identical decision,
                                 fewer nodes visited
Both return SearchStats (nodes_evaluated, nodes_pruned, search_depth,
best_action) so the two can be compared on IDENTICAL trees.
"""

import time
from dataclasses import dataclass, field

from ai.probability import ProbabilityAI, UNKNOWN, MISS, HIT

TOP_K_ACTIONS = 5     # branching factor at MAX nodes (move-ordering cutoff)
DEFAULT_DEPTH = 3     # number of plies searched (MAX, MIN, MAX by default)


def _cell_could_be_hit(tracking, remaining_lengths, cell, size):
    """
    True iff at least one remaining ship length has SOME legal
    orientation/position, consistent with `tracking`, that covers `cell`.
    Cheap: only checks placements that actually pass through this one
    cell, not the whole board.
    """
    r0, c0 = cell

    def placement_ok(cells):
        for (r, c) in cells:
            if not (0 <= r < size and 0 <= c < size):
                return False
            if tracking[r][c] in (MISS, "sunk"):
                return False
        return True

    for length in remaining_lengths:
        # horizontal placements through (r0, c0)
        for start in range(max(0, c0 - length + 1), min(c0, size - length) + 1):
            cells = [(r0, start + i) for i in range(length)]
            if placement_ok(cells):
                return True
        # vertical placements through (r0, c0)
        for start in range(max(0, r0 - length + 1), min(r0, size - length) + 1):
            cells = [(start + i, c0) for i in range(length)]
            if placement_ok(cells):
                return True
    return False


@dataclass
class _MMState:
    tracking: list
    remaining_lengths: list
    hits: int = 0
    misses: int = 0
    maximizing: bool = True


@dataclass
class SearchStats:
    nodes_evaluated: int = 0
    nodes_pruned: int = 0
    search_depth: int = 0
    best_action: tuple = None
    best_value: float = None
    search_time_ms: float = 0.0
    used_alpha_beta: bool = False
    candidate_actions: list = field(default_factory=list)  # [(cell, value), ...] at the root


def _legal_actions(state, board_size, prob_engine, k=TOP_K_ACTIONS):
    """MAX's legal actions: the top-K highest-density UNKNOWN cells."""
    density = prob_engine.compute_density_map(state.tracking, state.remaining_lengths)
    scored = [
        (density[r][c], (r, c))
        for r in range(board_size)
        for c in range(board_size)
        if state.tracking[r][c] == UNKNOWN
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [cell for _score, cell in scored[:k]]


def _apply_action(state, cell, outcome, board_size):
    """Returns a NEW child state after firing at `cell` with the given
    (hypothesized) outcome -- never mutates the parent."""
    r, c = cell
    new_tracking = [row[:] for row in state.tracking]
    new_tracking[r][c] = HIT if outcome == "hit" else MISS
    return _MMState(
        tracking=new_tracking,
        remaining_lengths=list(state.remaining_lengths),
        hits=state.hits + (1 if outcome == "hit" else 0),
        misses=state.misses + (0 if outcome == "hit" else 1),
        maximizing=not state.maximizing,
    )


def _evaluate(state):
    """Depth-limit / terminal heuristic: net damage dealt so far in this
    simulated line. MAX wants this high, MIN (adversarial hidden info)
    wants it low."""
    return state.hits - state.misses


def minimax(state, depth, board_size, prob_engine, stats):
    """Exhaustive minimax, no pruning. Mutates `stats` in place."""
    stats.nodes_evaluated += 1

    if depth == 0:
        return _evaluate(state)

    if state.maximizing:
        actions = _legal_actions(state, board_size, prob_engine)
        if not actions:
            return _evaluate(state)
        best = float("-inf")
        for cell in actions:
            child_hit = _apply_action(state, cell, "hit", board_size)
            child_miss = _apply_action(state, cell, "miss", board_size)
            # MIN chooses whichever outcome is worse for MAX, among LEGAL outcomes
            outcome_values = []
            if _cell_could_be_hit(state.tracking, state.remaining_lengths, cell, board_size):
                outcome_values.append(minimax(child_hit, depth - 1, board_size, prob_engine, stats))
            outcome_values.append(minimax(child_miss, depth - 1, board_size, prob_engine, stats))
            value = min(outcome_values)
            best = max(best, value)
        return best
    else:
        # A MIN node here represents "having just observed the outcome";
        # by construction (see maximizing branch) MIN's choice is already
        # folded into the min() above, so a bare MIN node just continues
        # the line as MAX again at the next ply. This keeps the tree
        # exactly two conceptual actors (shooter, hidden fleet) while
        # still alternating plies for depth bookkeeping.
        return minimax(_MMState(state.tracking, state.remaining_lengths, state.hits, state.misses, True),
                        depth, board_size, prob_engine, stats)


def alpha_beta(state, depth, alpha, beta, board_size, prob_engine, stats):
    """Minimax with alpha-beta pruning over the IDENTICAL tree as minimax()."""
    stats.nodes_evaluated += 1

    if depth == 0:
        return _evaluate(state)

    if state.maximizing:
        actions = _legal_actions(state, board_size, prob_engine)
        if not actions:
            return _evaluate(state)
        best = float("-inf")
        for i, cell in enumerate(actions):
            child_hit = _apply_action(state, cell, "hit", board_size)
            child_miss = _apply_action(state, cell, "miss", board_size)

            # MIN's turn for this action: evaluate its legal outcomes,
            # pruning between them with the same alpha/beta window.
            min_best = float("inf")
            min_alpha, min_beta = alpha, beta
            legal_outcomes = []
            if _cell_could_be_hit(state.tracking, state.remaining_lengths, cell, board_size):
                legal_outcomes.append(child_hit)
            legal_outcomes.append(child_miss)

            for j, child in enumerate(legal_outcomes):
                v = alpha_beta(child, depth - 1, min_alpha, min_beta, board_size, prob_engine, stats)
                min_best = min(min_best, v)
                min_beta = min(min_beta, min_best)
                if min_beta <= min_alpha:
                    remaining = len(legal_outcomes) - (j + 1)
                    stats.nodes_pruned += remaining
                    break

            best = max(best, min_best)
            alpha = max(alpha, best)
            if beta <= alpha:
                remaining_actions = len(actions) - (i + 1)
                stats.nodes_pruned += remaining_actions
                break
        return best
    else:
        return alpha_beta(_MMState(state.tracking, state.remaining_lengths, state.hits, state.misses, True),
                           depth, alpha, beta, board_size, prob_engine, stats)


def select_best_action(tracking, remaining_lengths, board_size=10, depth=DEFAULT_DEPTH,
                        use_alpha_beta=True, top_k=TOP_K_ACTIONS):
    """
    Main public entry point. Runs a depth-limited minimax (optionally
    alpha-beta pruned) rooted at the current tracking grid, and returns
    (best_cell, SearchStats). This is what ai.agent.MinimaxAgent calls,
    and what the Minimax vs Minimax+Alpha-Beta comparison calls twice
    (once with each flag) on the identical root state.
    """
    prob_engine = ProbabilityAI(board_size)
    root = _MMState(tracking=tracking, remaining_lengths=list(remaining_lengths), maximizing=True)
    actions = _legal_actions(root, board_size, prob_engine, k=top_k)

    stats = SearchStats(search_depth=depth, used_alpha_beta=use_alpha_beta)
    start = time.perf_counter()

    if not actions:
        stats.search_time_ms = round((time.perf_counter() - start) * 1000, 4)
        return None, stats

    best_cell, best_value = None, float("-inf")
    candidate_values = []

    for cell in actions:
        child_hit = _apply_action(root, cell, "hit", board_size)
        child_miss = _apply_action(root, cell, "miss", board_size)
        legal = []
        if _cell_could_be_hit(root.tracking, root.remaining_lengths, cell, board_size):
            legal.append(child_hit)
        legal.append(child_miss)

        if use_alpha_beta:
            alpha, beta = float("-inf"), float("inf")
            min_best = float("inf")
            for j, child in enumerate(legal):
                v = alpha_beta(child, depth - 1, alpha, beta, board_size, prob_engine, stats)
                min_best = min(min_best, v)
                beta = min(beta, min_best)
                if beta <= alpha:
                    stats.nodes_pruned += len(legal) - (j + 1)
                    break
        else:
            min_best = min(minimax(child, depth - 1, board_size, prob_engine, stats) for child in legal)

        candidate_values.append((cell, min_best))
        if min_best > best_value:
            best_value = min_best
            best_cell = cell

    stats.search_time_ms = round((time.perf_counter() - start) * 1000, 4)
    stats.best_action = best_cell
    stats.best_value = best_value
    stats.candidate_actions = candidate_values
    return best_cell, stats
