"""
ai/scenario.py
==============
Generates a realistic, randomized "tracking grid" -- the same
UNKNOWN/MISS/HIT/SUNK representation ai/search.py and ai/probability.py
operate on -- for the Algorithm Lab and Algorithm Comparison pages to
run real searches against without needing a live Human vs AI game in
progress.

This never touches session/game state; it builds a throwaway Board,
fires a batch of random shots at it to simulate a partially-played
match, and returns just the resulting tracking grid. Kept in its own
module (rather than ai/search.py) so the search algorithms themselves
have zero dependency on game/board.py and can be unit-tested in
isolation.
"""

import random

from game.board import Board, SIZE
from ai.probability import UNKNOWN, MISS, HIT, SUNK


def generate_scenario(board_size=SIZE, num_shots=24, seed=None):
    """
    Build a fresh random fleet, fire `num_shots` random shots at it, and
    return the resulting tracking grid (what an AI would know so far).
    """
    rng = random.Random(seed)
    board = Board(board_size)
    board.random_placement()

    tracking = [[UNKNOWN for _ in range(board_size)] for _ in range(board_size)]
    all_cells = [(r, c) for r in range(board_size) for c in range(board_size)]
    rng.shuffle(all_cells)

    for (r, c) in all_cells[:num_shots]:
        outcome = board.receive_shot(r, c)
        result = outcome["result"]
        if result == "sunk":
            tracking[r][c] = SUNK
            for ship in board.fleet:
                if ship.name == outcome["ship"]:
                    for sr, sc in ship.cells:
                        tracking[sr][sc] = SUNK
        elif result == "hit":
            tracking[r][c] = HIT
        elif result == "miss":
            tracking[r][c] = MISS

    return tracking


def remaining_lengths_from_tracking(tracking_grid, board_size=SIZE):
    """
    Derive which ship lengths are still unsunk purely from a tracking
    grid: flood-fill every contiguous SUNK region (one per destroyed
    ship, since Battleship's no-touch rule means two ships never touch),
    then remove one matching length per sunk cluster from the standard
    fleet. Used by the Algorithm Lab / Comparison pages, which only have
    a tracking grid to work with -- never fabricated.
    """
    from game.ships import FLEET

    size = board_size
    seen = set()
    sunk_lengths = []
    for r in range(size):
        for c in range(size):
            if tracking_grid[r][c] == SUNK and (r, c) not in seen:
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
                            and tracking_grid[nr][nc] == SUNK
                        ):
                            seen.add((nr, nc))
                            stack.append((nr, nc))
                sunk_lengths.append(len(cluster))

    remaining = [length for _name, length in FLEET]
    for length in sunk_lengths:
        if length in remaining:
            remaining.remove(length)
    return remaining


def remaining_ships_from_tracking(tracking_grid, board_size=SIZE):
    """
    Same derivation as remaining_lengths_from_tracking(), but keeps each
    surviving ship's name too -- list[(name, length)] -- since ai/csp.py's
    variables are per-named-ship. For a synthetic scenario there's no
    real ship identity to recover, so names are assigned in standard
    fleet order after removing one entry per detected sunk length; for a
    live game, callers should prefer GameEngine's own fleet records
    instead of this best-effort reconstruction.
    """
    from game.ships import FLEET

    lengths_left = remaining_lengths_from_tracking(tracking_grid, board_size)
    remaining_ships = []
    pool = list(FLEET)
    for length in lengths_left:
        for i, (name, plen) in enumerate(pool):
            if plen == length:
                remaining_ships.append((name, plen))
                pool.pop(i)
                break
    return remaining_ships
