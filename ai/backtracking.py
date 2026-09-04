"""
ai/backtracking.py
===================
Real backtracking search over the CSP defined in ai/csp.py: finds ONE
complete assignment of every remaining ship to a placement, consistent
with every constraint, using the standard textbook heuristics:

    Variable ordering: Minimum Remaining Values (MRV) -- assign the
    ship with the fewest legal placements left first, since it fails
    fastest if the board is inconsistent (and is most constrained, so
    getting it right early prunes the most).

    Value ordering: Least Constraining Value (LCV) -- among a ship's
    remaining placements, try the one that eliminates the fewest
    placements from the OTHER still-unassigned ships' domains first,
    to keep as many future options open as possible.

    Forward checking: after tentatively assigning a placement, remove
    now-incompatible placements from every other unassigned variable's
    domain. If any domain becomes empty, this branch cannot lead to a
    solution -- backtrack immediately instead of continuing deeper.

Every node visited (nodes_expanded) and every backtrack (a variable ran
out of domain values to try) is counted, and a step-by-step trace is
recorded, so the AI Lab's CSP detail view can animate exactly what the
solver did, not a fabricated summary of it.
"""

import random

from ai.csp import NoOverlapConstraint


class BacktrackingSolver:
    def __init__(self, csp_solver, rng=None, max_nodes=40000):
        self.csp = csp_solver
        self.nodes_expanded = 0
        self.backtracks = 0
        self.trace = []  # [{"action": "assign"|"backtrack", "variable", "cells"?, "domain_remaining"?}, ...]
        self.rng = rng or random.Random()
        self.max_nodes = max_nodes
        self.budget_exceeded = False

    def select_unassigned_variable(self, domains, assigned):
        """MRV: the unassigned variable with the smallest remaining domain."""
        candidates = [v for v in self.csp.variables if v.name not in assigned]
        return min(candidates, key=lambda v: len(domains[v.name]))

    def order_domain_values(self, variable, domains, assigned):
        """
        LCV: order this variable's remaining candidate placements by how
        few placements they eliminate from every OTHER unassigned
        variable's domain -- try the least-constraining option first.
        """
        others = [v for v in self.csp.variables if v.name != variable.name and v.name not in assigned]

        def eliminated_count(placement):
            total = 0
            for other in others:
                for other_placement in domains[other.name]:
                    if not NoOverlapConstraint.compatible(placement, other_placement):
                        total += 1
            return total

        return sorted(domains[variable.name], key=eliminated_count)

    def forward_check(self, variable, placement, domains, assigned):
        """
        Prune every OTHER unassigned variable's domain to only values
        compatible with this tentative placement. Returns a dict of the
        domains actually changed (name -> original domain), so the
        caller can restore them exactly on backtrack, and None if any
        domain became empty (this branch is dead).
        """
        pruned_backup = {}
        for other in self.csp.variables:
            if other.name == variable.name or other.name in assigned:
                continue
            new_domain = [
                p for p in domains[other.name]
                if NoOverlapConstraint.compatible(placement, p)
            ]
            if len(new_domain) != len(domains[other.name]):
                pruned_backup[other.name] = domains[other.name]
                domains[other.name] = new_domain
            if not new_domain:
                return None  # dead end -- some other ship now has zero legal placements
        return pruned_backup

    def _remaining_hits_coverable(self, domains, assignment):
        """
        Extends forward checking to the global ConsistentWithShotsConstraint:
        every active hit not yet covered by an assigned ship must still be
        coverable by SOME unassigned ship's remaining domain. If any hit
        cell is covered by nobody's domain, this branch is dead -- no
        point exploring it to full depth just to fail at the very end.
        """
        covered = set()
        for cells in assignment.values():
            covered.update(cells)
        remaining_hits = [h for h in self.csp.active_hits if h not in covered]
        if not remaining_hits:
            return True

        unassigned_domains = [
            domains[v.name] for v in self.csp.variables if v.name not in assignment
        ]
        for hit in remaining_hits:
            if not any(hit in placement for domain in unassigned_domains for placement in domain):
                return False
        return True

    def search(self):
        """
        Recursive backtracking entry point. Returns a complete assignment
        {ship_name: cells} on success, or None if the CSP is genuinely
        unsatisfiable (shouldn't happen with real Battleship data, but
        handled honestly rather than assumed away).
        """
        domains = {v.name: list(v.domain) for v in self.csp.variables}
        assignment = {}
        result = self._backtrack(domains, assignment)
        return result

    def _backtrack(self, domains, assignment):
        if self.nodes_expanded >= self.max_nodes:
            self.budget_exceeded = True
            return None

        if len(assignment) == len(self.csp.variables):
            # Complete assignment: NoOverlapConstraint is already guaranteed
            # by forward checking (every placement was drawn from a domain
            # already pruned to be compatible with every earlier
            # assignment) -- but ConsistentWithShotsConstraint (every known
            # active hit must be explained) can only be checked now that
            # every ship has been placed, not on a partial assignment.
            if self.csp.is_consistent(assignment):
                return dict(assignment)
            return None

        variable = self.select_unassigned_variable(domains, assignment)
        ordered_values = self.order_domain_values(variable, domains, assignment)

        for placement in ordered_values:
            self.nodes_expanded += 1
            assignment[variable.name] = placement

            pruned_backup = self.forward_check(variable, placement, domains, assignment)
            self.trace.append({
                "action": "assign",
                "variable": variable.name,
                "cells": [list(c) for c in placement],
                "dead_end": pruned_backup is None,
            })

            if pruned_backup is not None and self._remaining_hits_coverable(domains, assignment):
                result = self._backtrack(domains, assignment)
                if result is not None:
                    return result

            # undo: restore any domains this placement pruned, then
            # un-assign and try the next candidate value
            if pruned_backup is not None:
                for name, original in pruned_backup.items():
                    domains[name] = original
            del assignment[variable.name]
            self.backtracks += 1
            self.trace.append({"action": "backtrack", "variable": variable.name})

        return None
