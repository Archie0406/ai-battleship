"""
game/board.py
=============
A single 10x10 Battleship board: grid state, ship placement rules,
and shot resolution. Two Board instances make up a game (player + AI).

Cell states exposed to the frontend:
    "empty"  -> never fired upon
    "miss"   -> fired upon, no ship
    "hit"    -> fired upon, ship present, not yet sunk
    "sunk"   -> fired upon, ship present, ship fully sunk
    "ship"   -> ship present, unfired (only revealed for the human's own board)
"""

import random

from game.ships import build_fleet

SIZE = 10


class Board:
    def __init__(self, size=SIZE):
        self.size = size
        self.fleet = build_fleet()
        # occupancy[r][c] = Ship or None
        self.occupancy = [[None for _ in range(size)] for _ in range(size)]
        # shots[r][c] = True if that cell has been fired upon
        self.shots = [[False for _ in range(size)] for _ in range(size)]

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------
    def in_bounds(self, r, c):
        return 0 <= r < self.size and 0 <= c < self.size

    def _cells_for(self, r, c, length, horizontal):
        if horizontal:
            cells = [(r, c + i) for i in range(length)]
        else:
            cells = [(r + i, c) for i in range(length)]
        return cells

    def can_place(self, r, c, length, horizontal):
        cells = self._cells_for(r, c, length, horizontal)
        for cr, cc in cells:
            if not self.in_bounds(cr, cc):
                return False
            # no overlap, and no ship touching another (adjacent cells clear)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    nr, nc = cr + dr, cc + dc
                    if self.in_bounds(nr, nc) and self.occupancy[nr][nc] is not None:
                        return False
        return True

    def place_ship(self, ship, r, c, horizontal):
        if not self.can_place(r, c, ship.length, horizontal):
            raise ValueError(f"Cannot place {ship.name} at ({r},{c})")
        cells = self._cells_for(r, c, ship.length, horizontal)
        ship.place(cells)
        for cr, cc in cells:
            self.occupancy[cr][cc] = ship

    def find_ship(self, name):
        for ship in self.fleet:
            if ship.name == name:
                return ship
        return None

    def place_named_ship(self, name, r, c, horizontal):
        """Place a specific fleet ship by name (used for manual player setup)."""
        ship = self.find_ship(name)
        if ship is None:
            raise ValueError(f"Unknown ship '{name}'")
        if ship.cells:
            raise ValueError(f"{name} is already placed — remove it first")
        self.place_ship(ship, r, c, horizontal)
        return ship

    def remove_ship(self, name):
        """Un-place a ship so it can be repositioned during manual setup."""
        ship = self.find_ship(name)
        if ship is None or not ship.cells:
            return
        for cr, cc in ship.cells:
            self.occupancy[cr][cc] = None
        ship.cells = []
        ship.hits = set()

    def reset_fleet(self):
        """Clear every placement, ready for a fresh manual/random setup."""
        self.fleet = build_fleet()
        self.occupancy = [[None for _ in range(self.size)] for _ in range(self.size)]

    @property
    def is_fully_placed(self):
        return all(len(ship.cells) == ship.length for ship in self.fleet)

    def random_placement(self):
        """Place the whole fleet randomly using rejection sampling."""
        self.reset_fleet()
        for ship in self.fleet:
            placed = False
            attempts = 0
            while not placed and attempts < 500:
                attempts += 1
                horizontal = random.choice([True, False])
                r = random.randint(0, self.size - 1)
                c = random.randint(0, self.size - 1)
                if self.can_place(r, c, ship.length, horizontal):
                    self.place_ship(ship, r, c, horizontal)
                    placed = True
            if not placed:
                # extremely unlikely with a 10x10 board; retry whole fleet
                return self.random_placement()
        return self.fleet

    # ------------------------------------------------------------------
    # Shooting
    # ------------------------------------------------------------------
    def receive_shot(self, r, c):
        """
        Fire at (r, c). Returns a dict describing the outcome:
        {result: "hit"|"miss"|"sunk"|"repeat", ship: str|None}
        """
        if not self.in_bounds(r, c):
            raise ValueError("Shot out of bounds")
        if self.shots[r][c]:
            return {"result": "repeat", "ship": None}

        self.shots[r][c] = True
        ship = self.occupancy[r][c]
        if ship is None:
            return {"result": "miss", "ship": None}

        ship.register_hit((r, c))
        if ship.is_sunk:
            return {"result": "sunk", "ship": ship.name}
        return {"result": "hit", "ship": ship.name}

    @property
    def all_sunk(self):
        return all(ship.is_sunk for ship in self.fleet)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def cell_state(self, r, c, reveal_ships):
        fired = self.shots[r][c]
        ship = self.occupancy[r][c]
        if fired and ship is not None:
            return "sunk" if ship.is_sunk else "hit"
        if fired:
            return "miss"
        if ship is not None and reveal_ships:
            return "ship"
        return "empty"

    def grid_state(self, reveal_ships=False):
        return [
            [self.cell_state(r, c, reveal_ships) for c in range(self.size)]
            for r in range(self.size)
        ]

    def to_dict(self, reveal_ships=False):
        return {
            "size": self.size,
            "grid": self.grid_state(reveal_ships),
            "fleet": [s.to_dict(reveal=reveal_ships) for s in self.fleet],
            "all_sunk": self.all_sunk,
        }
