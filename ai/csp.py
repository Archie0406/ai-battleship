"""
ai/csp.py
=========
A genuine Constraint Satisfaction Problem formulation of "where could the
remaining enemy ships be, given everything observed so far?" -- with real
AC-3 arc-consistency domain pruning. ai/backtracking.py then performs the
actual backtracking search over these pruned domains.

==========================================================================
FORMULATION
==========================================================================
Variables    One per remaining (not-yet-sunk) enemy ship: Carrier,
             Battleship, Cruiser, Submarine, Destroyer -- whichever are
             still alive in the current game.

Domains      For each ship variable, every legal (row, col, horizontal)
             placement of that ship's length on the board that is
             consistent with the tracking grid on its own:
               - stays in bounds
               - doesn't cover a MISS or SUNK cell
             (SUNK cells belonging to THIS ship, if any of its cells are
             already known hit, are handled by the CSP's constraints
             below rather than the domain -- a ship whose own hits are
             known must have a placement that covers them.)

Constraints  - NoOverlapConstraint: two assigned ships' placements may
               not share a cell, and (Battleship's no-touch rule) may
               not even be orthogonally/diagonally adjacent.
             - ConsistentWithShotsConstraint: every active (unsunk) HIT
               cell on the board must be covered by SOME ship's
               placement in a complete assignment -- an assignment that
               leaves a known hit unexplained is not a real solution.

AC-3         Standard arc-consistency: for every ordered pair of
             variables (Vi, Vj), remove any value from Vi's domain that
             has no COMPATIBLE value left in Vj's domain (compatible =
             doesn't violate NoOverlapConstraint). Repeat until no
             domain changes on a full pass. This is real arc-consistency
             pruning, not a cosmetic filter -- it can and does shrink
             domains before backtracking search even starts, exactly the
             textbook AC-3 speed-up.
"""

import random
import time
from dataclasses import dataclass, field
from functools import lru_cache


@lru_cache(maxsize=None)
def _footprint(cells):
    """
    Every cell a placement occupies OR touches (its 3x3 neighborhood),
    as a frozenset -- this IS the no-touch rule. Cached per unique
    placement (cells is a hashable tuple-of-tuples) since the same
    placements get compatibility-checked repeatedly across AC-3 arcs,
    LCV ordering, and every backtracking node -- recomputing this from
    scratch every time was the dominant cost before caching it.
    """
    occ = set()
    for (r, c) in cells:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                occ.add((r + dr, c + dc))
    return frozenset(occ)


@dataclass
class Variable:
    """A single unplaced ship, treated as a CSP variable."""
    name: str
    length: int
    domain: list = field(default_factory=list)  # list of tuple-of-cells placements


class Constraint:
    """Base class for a constraint over a complete assignment."""

    def is_satisfied(self, assignment):
        raise NotImplementedError


class NoOverlapConstraint(Constraint):
    """No two assigned ships may share or touch a cell (no-touch rule)."""

    @staticmethod
    def compatible(cells_a, cells_b):
        return _footprint(cells_a).isdisjoint(cells_b)

    def is_satisfied(self, assignment):
        names = list(assignment.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if not self.compatible(assignment[names[i]], assignment[names[j]]):
                    return False
        return True


class ConsistentWithShotsConstraint(Constraint):
    """Every active (unsunk) HIT cell must be covered by some ship."""

    def __init__(self, active_hit_cells):
        self.active_hit_cells = set(active_hit_cells)

    def is_satisfied(self, assignment):
        covered = set()
        for cells in assignment.values():
            covered.update(cells)
        return self.active_hit_cells.issubset(covered)


def _cells_for(r, c, length, horizontal):
    if horizontal:
        return tuple((r, c + i) for i in range(length))
    return tuple((r + i, c) for i in range(length))


def _domain_consistent_with_tracking(cells, tracking, size):
    for (r, c) in cells:
        if not (0 <= r < size and 0 <= c < size):
            return False
        if tracking[r][c] in ("miss", "sunk"):
            return False
    return True


def build_domain(length, tracking, size):
    """Every legal placement of a ship of `length`, consistent with the
    tracking grid on its own (bounds + no miss/sunk cells)."""
    domain = []
    for r in range(size):
        for c in range(size - length + 1):
            cells = _cells_for(r, c, length, True)
            if _domain_consistent_with_tracking(cells, tracking, size):
                domain.append(cells)
    for r in range(size - length + 1):
        for c in range(size):
            cells = _cells_for(r, c, length, False)
            if _domain_consistent_with_tracking(cells, tracking, size):
                domain.append(cells)
    return domain


class CSPSolver:
    """
    Orchestrates variables + constraints, runs AC-3 arc-consistency to
    prune each ship's domain, and hands the pruned domains to
    ai/backtracking.py's BacktrackingSolver for the actual search.
    """

    def __init__(self, board_size=10):
        self.board_size = board_size
        self.variables = []           # list[Variable]
        self.constraints = []         # list[Constraint]
        self.domain_sizes_before = {}
        self.domain_sizes_after = {}
        self.ac3_removed = 0

    def build_variables(self, remaining_ships, tracking):
        """remaining_ships: list of (name, length). Builds one Variable
        per ship with its full (pre-AC3) domain."""
        self.variables = []
        for name, length in remaining_ships:
            domain = build_domain(length, tracking, self.board_size)
            self.variables.append(Variable(name=name, length=length, domain=domain))
            self.domain_sizes_before[name] = len(domain)

        active_hits = [
            (r, c)
            for r in range(self.board_size)
            for c in range(self.board_size)
            if tracking[r][c] == "hit"
        ]
        self.active_hits = active_hits
        self.constraints = [
            NoOverlapConstraint(),
            ConsistentWithShotsConstraint(active_hits),
        ]
        return self.variables

    def ac3(self):
        """
        Real AC-3: maintain a queue of ordered variable pairs (arcs);
        for each arc (Vi, Vj), remove any value from Vi's domain that has
        no compatible value in Vj's domain. Whenever Vi's domain shrinks,
        re-enqueue every arc (Vk, Vi) for k != i, since Vk's domain may
        now need re-checking against Vi's smaller domain. Converges when
        the queue empties.
        """
        queue = [
            (vi, vj)
            for vi in self.variables
            for vj in self.variables
            if vi is not vj
        ]
        removed_total = 0

        def revise(vi, vj):
            revised = False
            new_domain = []
            for value in vi.domain:
                if any(NoOverlapConstraint.compatible(value, other) for other in vj.domain):
                    new_domain.append(value)
                else:
                    revised = True
            if revised:
                vi.domain = new_domain
            return revised

        while queue:
            vi, vj = queue.pop(0)
            before = len(vi.domain)
            if revise(vi, vj):
                removed_total += before - len(vi.domain)
                if not vi.domain:
                    self.ac3_removed = removed_total
                    for v in self.variables:
                        self.domain_sizes_after[v.name] = len(v.domain)
                    return False  # inconsistent -- some ship has no legal placement left
                for vk in self.variables:
                    if vk is not vi and vk is not vj:
                        queue.append((vk, vi))

        self.ac3_removed = removed_total
        for v in self.variables:
            self.domain_sizes_after[v.name] = len(v.domain)
        return True

    def is_consistent(self, assignment):
        return all(c.is_satisfied(assignment) for c in self.constraints)


def solve_fleet_csp(tracking, remaining_ships, board_size=10, rng=None):
    """
    Main public entry point: build variables, run AC-3, then run
    backtracking search (ai/backtracking.py) for ONE complete consistent
    fleet assignment. Returns a plain dict describing every step, for
    both the CSP detail view's live visualization and for CSPAgent's
    targeting decision.
    """
    from ai.backtracking import BacktrackingSolver

    start = time.perf_counter()
    solver = CSPSolver(board_size)
    solver.build_variables(remaining_ships, tracking)
    ac3_ok = solver.ac3()

    result = {
        "variables": [
            {
                "name": v.name,
                "length": v.length,
                "domain_before": solver.domain_sizes_before[v.name],
                "domain_after": solver.domain_sizes_after.get(v.name, len(v.domain)),
            }
            for v in solver.variables
        ],
        "ac3_removed": solver.ac3_removed,
        "ac3_consistent": ac3_ok,
        "solution": None,
        "nodes_expanded": 0,
        "backtracks": 0,
        "trace": [],
        "budget_exceeded": False,
        "search_time_ms": 0.0,
    }

    if not ac3_ok:
        result["search_time_ms"] = round((time.perf_counter() - start) * 1000, 4)
        return result

    backtracker = BacktrackingSolver(solver, rng=rng)
    solution = backtracker.search()
    result["solution"] = (
        {name: [list(c) for c in cells] for name, cells in solution.items()}
        if solution
        else None
    )
    result["nodes_expanded"] = backtracker.nodes_expanded
    result["backtracks"] = backtracker.backtracks
    result["trace"] = backtracker.trace
    result["budget_exceeded"] = backtracker.budget_exceeded
    result["search_time_ms"] = round((time.perf_counter() - start) * 1000, 4)
    return result


def sample_target(tracking, remaining_ships, board_size=10, samples=6, rng=None):
    """
    Runs solve_fleet_csp() several times with randomized MRV/LCV
    tie-breaking, collecting one complete consistent fleet solution per
    run, and tallies how often each UNKNOWN cell is covered across those
    solutions. This is a genuinely different (and more correct) notion
    of "probability" than ai/probability.py's per-ship independent
    counting: every sample here is a JOINTLY consistent complete fleet,
    respecting all ships' constraints simultaneously, not just one ship
    at a time.

    Returns (target_cell, confidence, last_solve_result) -- the last
    solve's full stats/trace are kept for the CSP detail view / telemetry
    panel, since showing all `samples` traces at once isn't useful.
    """
    rng = rng or random.Random()
    size = board_size
    coverage = [[0 for _ in range(size)] for _ in range(size)]
    last_result = None
    successful = 0

    for _ in range(samples):
        result = solve_fleet_csp(tracking, remaining_ships, board_size=size, rng=rng)
        last_result = result
        if result["solution"]:
            successful += 1
            for cells in result["solution"].values():
                for (r, c) in cells:
                    if tracking[r][c] == "unknown":
                        coverage[r][c] += 1

    best_cell = None
    best_count = -1
    for r in range(size):
        for c in range(size):
            if tracking[r][c] != "unknown":
                continue
            if coverage[r][c] > best_count:
                best_count = coverage[r][c]
                best_cell = (r, c)

    if best_cell is None or successful == 0:
        # Every sample failed (shouldn't happen with valid Battleship
        # data, but handled honestly) -- fall back to any untried cell.
        candidates = [
            (r, c) for r in range(size) for c in range(size) if tracking[r][c] == "unknown"
        ]
        best_cell = rng.choice(candidates) if candidates else (0, 0)
        confidence = 0
    else:
        confidence = round(100 * best_count / successful)

    return best_cell, confidence, last_result
