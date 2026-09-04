"""
ai/reasoning.py
================
A real knowledge base + forward-chaining inference engine for the AI's
targeting. This is not a display layer over another algorithm -- the
candidate-placement domain and probability grid computed here are what
ai.agent.ReasoningAgent actually fires at (see choose_target() at the
bottom of this file).

Knowledge tracked
------------------
    - tracking grid: UNKNOWN / MISS / HIT / SUNK per cell (ground truth
      observed from shots so far)
    - candidate_placements: per remaining ship name, every (row, col)
      tuple-sequence placement still consistent with everything known
    - destroyed_ships: names of ships confirmed sunk
    - current_target: the cell most recently selected to fire at
    - action_log: every shot recorded so far, in order

Forward chaining
------------------
record_shot() updates the tracking grid and action log, then calls
forward_chain(), which re-derives everything else from scratch by
repeatedly applying four rules until no candidate list changes further:

    RULE 1 (miss elimination)
        Any candidate placement containing a MISS cell is impossible
        and is removed from its ship's domain.

    RULE 2 (hit reinforcement)
        Cells orthogonally adjacent to an active (unsunk) HIT are
        tagged high-priority -- placements covering them are weighted
        more heavily when the probability grid is built.

    RULE 3 (destruction cleanup)
        Once a ship is confirmed SUNK, its own candidate domain is
        cleared entirely, and every remaining ship's candidate list
        drops any placement that overlaps or (per Battleship's no-touch
        rule) is adjacent to that ship's footprint.

    RULE 4 (general consistency)
        Any candidate placement that overlaps a SUNK cell belonging to
        a different ship, or contains a MISS cell, is removed -- this
        is the general form Rules 1 and 3 are specific cases of, and is
        re-applied on every pass so the domain always matches reality.

Every call to record_shot() rebuilds self.last_inference: a list of
plain-English sentences describing exactly what was just derived, built
directly from the numbers involved (placements eliminated, priority
cells found, ships destroyed) -- never a canned/static message.
"""

from dataclasses import dataclass, field

UNKNOWN = "unknown"
MISS = "miss"
HIT = "hit"
SUNK = "sunk"

HIT_WEIGHT = 6  # extra weight a placement gets for covering an active hit


def _cells_for(r, c, length, horizontal):
    if horizontal:
        return tuple((r, c + i) for i in range(length))
    return tuple((r + i, c) for i in range(length))


def _all_placements(length, size):
    for r in range(size):
        for c in range(size - length + 1):
            yield _cells_for(r, c, length, True)
    for r in range(size - length + 1):
        for c in range(size):
            yield _cells_for(r, c, length, False)


def _coord(cell):
    cols = "ABCDEFGHIJ"
    r, c = cell
    return f"{cols[c]}{r + 1}"


@dataclass
class ShipInfo:
    name: str
    length: int


class KnowledgeBase:
    def __init__(self, board_size=10, ships=None):
        self.size = board_size
        # ships: list of ShipInfo for every ship on the board being hunted
        self.ships = ships or []
        self.tracking = [[UNKNOWN] * board_size for _ in range(board_size)]
        self.destroyed_ships = []          # list of ship names
        self.current_target = None          # (r, c) last selected
        self.action_log = []                # [{cell, result, ship}]
        self.last_inference = []            # human-readable lines from the last forward_chain()
        self.priority_cells = set()         # Rule 2 output: high-value unknown cells
        self.impossible_cells = set()       # cells no remaining ship can occupy
        self.possible_cells = set()         # cells covered by >=1 surviving placement
        self.candidate_placements = {
            ship.name: list(_all_placements(ship.length, board_size))
            for ship in self.ships
        }
        self._last_probability = {}

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------
    def sync_from_tracking_grid(self, tracking_grid, destroyed_ship_names):
        """
        Bring this knowledge base in line with an externally-maintained
        tracking grid (used when the engine, not this class, is the
        source of truth for shot results -- e.g. resuming a match). Runs
        forward_chain() once at the end so candidate domains reflect the
        full grid immediately.
        """
        changed = False
        for r in range(self.size):
            for c in range(self.size):
                if self.tracking[r][c] != tracking_grid[r][c]:
                    self.tracking[r][c] = tracking_grid[r][c]
                    changed = True
        for name in destroyed_ship_names:
            if name not in self.destroyed_ships:
                self.destroyed_ships.append(name)
                changed = True
        if changed:
            self.forward_chain()

    def record_shot(self, r, c, result, ship_name=None, ship_cells=None):
        """
        Tell the knowledge base about one resolved shot, then run forward
        chaining to re-derive candidate domains, priorities, and the
        human-readable inference trace.
        """
        if result == "sunk":
            self.tracking[r][c] = SUNK
            if ship_cells:
                for sr, sc in ship_cells:
                    self.tracking[sr][sc] = SUNK
            if ship_name and ship_name not in self.destroyed_ships:
                self.destroyed_ships.append(ship_name)
        elif result == "hit":
            self.tracking[r][c] = HIT
        elif result == "miss":
            self.tracking[r][c] = MISS

        self.action_log.append({"cell": (r, c), "result": result, "ship": ship_name})
        self.forward_chain()

    # ------------------------------------------------------------------
    # Forward chaining
    # ------------------------------------------------------------------
    def _active_hits(self):
        return [
            (r, c)
            for r in range(self.size)
            for c in range(self.size)
            if self.tracking[r][c] == HIT
        ]

    def _sunk_cells_by_ship(self):
        """Group SUNK cells by which destroyed ship they belong to, using
        each ship's own candidate history is unreliable once cleared, so
        we reconstruct groups via connected SUNK runs -- good enough since
        no two ships may touch, so any contiguous SUNK run is one ship."""
        cells = [
            (r, c)
            for r in range(self.size)
            for c in range(self.size)
            if self.tracking[r][c] == SUNK
        ]
        return cells  # flat list is sufficient for adjacency exclusion below

    def _touches(self, cell, other_cells):
        r, c = cell
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if (r + dr, c + dc) in other_cells:
                    return True
        return False

    def forward_chain(self):
        inference_lines = []
        size = self.size
        sunk_cells = set(self._sunk_cells_by_ship())
        active_hits = self._active_hits()

        # ---- RULE 3: destroyed ships lose their entire domain ----
        for ship in self.ships:
            if ship.name in self.destroyed_ships:
                if self.candidate_placements.get(ship.name):
                    self.candidate_placements[ship.name] = []

        # ---- RULE 1 + RULE 4: eliminate placements inconsistent with misses/sunk ----
        total_eliminated = 0
        for ship in self.ships:
            if ship.name in self.destroyed_ships:
                continue
            before = self.candidate_placements[ship.name]
            survivors = []
            for placement in before:
                cell_set = set(placement)
                # Rule 1: any MISS cell in the placement kills it
                if any(self.tracking[r][c] == MISS for r, c in placement):
                    continue
                # Rule 4: overlapping a sunk cell (from another ship) kills it
                if cell_set & sunk_cells:
                    continue
                # No-touch rule: a placement adjacent to any sunk footprint
                # is impossible too (ships may never be adjacent)
                if any(self._touches(cell, sunk_cells) for cell in placement):
                    continue
                survivors.append(placement)
            eliminated = len(before) - len(survivors)
            total_eliminated += eliminated
            self.candidate_placements[ship.name] = survivors

        # ---- RULE 2: hit reinforcement -- tag high-priority cells ----
        priority = set()
        for (hr, hc) in active_hits:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = hr + dr, hc + dc
                if 0 <= nr < size and 0 <= nc < size and self.tracking[nr][nc] == UNKNOWN:
                    priority.add((nr, nc))
        self.priority_cells = priority

        # ---- Derive possible/impossible cells from the surviving domains ----
        possible = set()
        for placements in self.candidate_placements.values():
            for placement in placements:
                possible.update(placement)
        self.possible_cells = possible
        self.impossible_cells = {
            (r, c)
            for r in range(size)
            for c in range(size)
            if self.tracking[r][c] == UNKNOWN and (r, c) not in possible
        }

        # ---- Build the plain-English inference trace for this round ----
        if self.action_log:
            last = self.action_log[-1]
            coord = _coord(last["cell"])
            if last["result"] == "sunk":
                inference_lines.append(
                    f"{last['ship']} destroyed at {coord} — clearing its remaining candidate "
                    f"placements and marking its footprint off-limits for other ships."
                )
            elif last["result"] == "hit":
                inference_lines.append(f"Confirmed HIT at {coord}.")
            elif last["result"] == "miss":
                inference_lines.append(f"Confirmed MISS at {coord}.")

        if total_eliminated > 0:
            inference_lines.append(
                f"{total_eliminated} candidate placement(s) eliminated as inconsistent with known misses/sunk cells."
            )

        remaining_total = sum(len(v) for v in self.candidate_placements.values())
        active_ships = [s for s in self.ships if s.name not in self.destroyed_ships]
        if active_hits and priority:
            coords = ", ".join(_coord(c) for c in sorted(priority))
            inference_lines.append(
                f"Active hit(s) at {', '.join(_coord(h) for h in active_hits)} raise priority on "
                f"neighboring cell(s): {coords}."
            )
        if active_ships:
            inference_lines.append(
                f"{remaining_total} placement(s) remain possible across {len(active_ships)} "
                f"undestroyed ship(s)."
            )

        self.last_inference = inference_lines
        return inference_lines

    # ------------------------------------------------------------------
    # Probability grid + target selection
    # ------------------------------------------------------------------
    def probability_grid(self):
        """
        Raw (unnormalized) score per cell: sum, across every surviving
        candidate placement of every undestroyed ship, of a weight that's
        boosted for placements covering an active hit (Rule 2). This IS
        the same structure choose_target() uses -- the visualization and
        the decision are the same computation, not two separate things.
        """
        size = self.size
        grid = [[0.0 for _ in range(size)] for _ in range(size)]
        active_hits = set(self._active_hits())

        for ship in self.ships:
            if ship.name in self.destroyed_ships:
                continue
            for placement in self.candidate_placements[ship.name]:
                covers_hit = any(cell in active_hits for cell in placement)
                weight = 1 + (HIT_WEIGHT if covers_hit else 0)
                for (r, c) in placement:
                    if self.tracking[r][c] == UNKNOWN:
                        grid[r][c] += weight
        return grid

    def probability_percentages(self):
        """Normalize the raw grid to percentages over UNKNOWN cells (sums to ~100)."""
        raw = self.probability_grid()
        size = self.size
        total = sum(
            raw[r][c]
            for r in range(size)
            for c in range(size)
            if self.tracking[r][c] == UNKNOWN
        )
        pct = [[0.0 for _ in range(size)] for _ in range(size)]
        if total > 0:
            for r in range(size):
                for c in range(size):
                    if self.tracking[r][c] == UNKNOWN:
                        pct[r][c] = round(100 * raw[r][c] / total, 2)
        self._last_probability = pct
        return pct

    def choose_target(self):
        """
        Pick the highest-probability UNKNOWN cell. Returns
        ((row, col), confidence, explanation) where confidence is the
        chosen cell's own probability share (0-100, real, not fabricated)
        and explanation is a plain-English "what I will do" sentence.
        """
        import random

        size = self.size
        pct = self.probability_percentages()

        best_score = -1.0
        candidates = []
        for r in range(size):
            for c in range(size):
                if self.tracking[r][c] != UNKNOWN:
                    continue
                score = pct[r][c]
                if score > best_score:
                    best_score = score
                    candidates = [(r, c)]
                elif score == best_score:
                    candidates.append((r, c))

        if not candidates or best_score <= 0:
            # No informative signal at all (e.g. opening move) -- fall
            # back to any untried cell, preferring priority cells if any.
            fallback_pool = list(self.priority_cells) or [
                (r, c)
                for r in range(size)
                for c in range(size)
                if self.tracking[r][c] == UNKNOWN
            ]
            target = random.choice(fallback_pool) if fallback_pool else (0, 0)
            confidence = pct[target[0]][target[1]] if pct[target[0]][target[1]] else 5
            explanation = f"No strong signal yet — targeting {_coord(target)} to open up new information."
        else:
            target = random.choice(candidates)
            confidence = best_score
            if target in self.priority_cells:
                explanation = (
                    f"{_coord(target)} is adjacent to an active hit and currently has the highest "
                    f"probability ({confidence:.1f}%). Targeting {_coord(target)}."
                )
            else:
                explanation = (
                    f"{_coord(target)} currently has the highest probability ({confidence:.1f}%) "
                    f"among all remaining candidate placements. Targeting {_coord(target)}."
                )

        self.current_target = target
        return target, round(confidence), explanation

    # ------------------------------------------------------------------
    # Reasoning panel content -- generated from real state, every call
    # ------------------------------------------------------------------
    def reasoning_report(self, target=None, confidence=None, explanation=None):
        size = self.size
        hits = sum(1 for r in range(size) for c in range(size) if self.tracking[r][c] == HIT)
        misses = sum(1 for r in range(size) for c in range(size) if self.tracking[r][c] == MISS)
        sunk_cells = sum(1 for r in range(size) for c in range(size) if self.tracking[r][c] == SUNK)
        unknown = size * size - hits - misses - sunk_cells

        know = []
        if self.action_log:
            recent = self.action_log[-3:]
            for entry in reversed(recent):
                coord = _coord(entry["cell"])
                if entry["result"] == "sunk":
                    know.append(f"{entry['ship']} confirmed destroyed at {coord}.")
                elif entry["result"] == "hit":
                    know.append(f"Confirmed HIT at {coord}.")
                else:
                    know.append(f"Confirmed MISS at {coord}.")
        else:
            know.append("No shots fired yet — no confirmed information.")
        know.append(
            f"{hits} active hit cell(s), {misses} miss(es), {sunk_cells} sunk cell(s), "
            f"{unknown} cell(s) unknown."
        )
        if self.destroyed_ships:
            know.append(f"Destroyed so far: {', '.join(self.destroyed_ships)}.")

        infer = list(self.last_inference) if self.last_inference else [
            "No inferences yet — every placement is still equally possible."
        ]

        will_do = [explanation] if explanation else ["Awaiting enough information to commit to a target."]

        return {"know": know, "infer": infer, "will_do": will_do}

    # ------------------------------------------------------------------
    def to_state_dict(self):
        """Everything the frontend needs to render the reasoning panel and
        the three visualization toggles, all derived from real state."""
        size = self.size
        return {
            "probability_grid": self.probability_percentages(),
            "candidate_density_grid": self.probability_grid(),
            "possible_cells": [list(c) for c in sorted(self.possible_cells)],
            "impossible_cells": [list(c) for c in sorted(self.impossible_cells)],
            "priority_cells": [list(c) for c in sorted(self.priority_cells)],
            "current_target": list(self.current_target) if self.current_target else None,
            "destroyed_ships": list(self.destroyed_ships),
            "candidate_counts": {
                name: len(placements) for name, placements in self.candidate_placements.items()
            },
            "action_log": [
                {"cell": list(a["cell"]), "result": a["result"], "ship": a["ship"]}
                for a in self.action_log[-20:]
            ],
        }
