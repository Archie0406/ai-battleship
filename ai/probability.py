"""
ai/probability.py
==================
Reasoning-under-uncertainty module.

This is the ONE AI module that is fully functional in this phase, so the
game is actually playable end-to-end. It implements the classic
"probability density" targeting strategy:

    For every remaining enemy ship, and every legal orientation/position
    on the board, check whether that placement is still consistent with
    everything we've observed (misses and sunk ships block a placement;
    unresolved hits are cells a placement should explain). Every cell
    covered by a still-consistent placement gets +1 (or a bonus if the
    placement explains an active hit). The cell with the highest total
    is statistically the best next shot.

This is deliberately simple probabilistic reasoning, NOT the CSP/
backtracking engine described in the project brief -- ai/csp.py and
ai/backtracking.py are reserved for that more formal treatment in a
later phase. Once those exist, GameEngine can be pointed at them
instead of this module without changing anything else.
"""

import random

UNKNOWN = "unknown"
MISS = "miss"
HIT = "hit"
SUNK = "sunk"

HIT_BONUS = 6  # extra weight for placements that would explain an active hit


class ProbabilityAI:
    def __init__(self, board_size=10):
        self.size = board_size

    def _placements(self, length):
        """Yield every (cells) placement of a ship of `length` on the board."""
        n = self.size
        for r in range(n):
            for c in range(n - length + 1):
                yield [(r, c + i) for i in range(length)]
        for r in range(n - length + 1):
            for c in range(n):
                yield [(r + i, c) for i in range(length)]

    def compute_density_map(self, tracking_grid, remaining_lengths):
        """
        tracking_grid: 2D list of UNKNOWN/MISS/HIT/SUNK describing what the
                        AI currently knows about the opponent's board.
        remaining_lengths: list[int] lengths of enemy ships not yet sunk.
        Returns a 2D list of ints (density score per cell).
        """
        n = self.size
        density = [[0 for _ in range(n)] for _ in range(n)]
        active_hits = {
            (r, c)
            for r in range(n)
            for c in range(n)
            if tracking_grid[r][c] == HIT
        }

        for length in remaining_lengths:
            for cells in self._placements(length):
                if any(tracking_grid[r][c] in (MISS, SUNK) for r, c in cells):
                    continue  # placement contradicts known information
                covers_hit = any((r, c) in active_hits for r, c in cells)
                weight = 1 + (HIT_BONUS if covers_hit else 0)
                for r, c in cells:
                    if tracking_grid[r][c] == UNKNOWN:
                        density[r][c] += weight
                    elif tracking_grid[r][c] == HIT:
                        # can't fire here again, but keep it in the score
                        # space for debugging/visualization purposes
                        density[r][c] += weight

        return density

    def choose_target(self, tracking_grid, remaining_lengths):
        """Pick the best untried cell to fire at."""
        cell, _confidence = self.choose_target_with_confidence(tracking_grid, remaining_lengths)
        return cell

    def choose_target_with_confidence(self, tracking_grid, remaining_lengths):
        """
        Same targeting decision as choose_target(), but also reports a
        0-100 "confidence" score: how dominant the winning cell's density
        is relative to the average of every candidate cell. A single
        overwhelmingly-likely cell (e.g. hunting a wounded ship) scores
        high; a flat, wide-open board scores low.
        """
        n = self.size
        density = self.compute_density_map(tracking_grid, remaining_lengths)

        candidates = []
        best_score = -1
        scored_cells = []
        for r in range(n):
            for c in range(n):
                if tracking_grid[r][c] != UNKNOWN:
                    continue
                score = density[r][c]
                scored_cells.append(score)
                if score > best_score:
                    best_score = score
                    candidates = [(r, c)]
                elif score == best_score:
                    candidates.append((r, c))

        if not candidates:
            candidates = [
                (r, c)
                for r in range(n)
                for c in range(n)
                if tracking_grid[r][c] == UNKNOWN
            ] or [(0, 0)]
            return random.choice(candidates), 0

        avg_score = (sum(scored_cells) / len(scored_cells)) if scored_cells else 0
        if best_score <= 0:
            confidence = 0
        elif avg_score <= 0:
            confidence = 50
        else:
            ratio = best_score / avg_score
            # squash the ratio into a readable 0-100 confidence reading
            confidence = round(min(99, 30 + (ratio - 1) * 18))
            confidence = max(confidence, 5)

        return random.choice(candidates), int(confidence)
