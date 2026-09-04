"""
game/ships.py
=============
Defines the Ship entity used on a Battleship board.

A Ship owns its own set of grid coordinates and tracks which of those
coordinates have been hit. This keeps "is this ship sunk?" logic local
to the ship itself instead of scattered through the board/game engine.
"""

from dataclasses import dataclass, field

# Standard Battleship fleet: (name, length)
FLEET = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]


@dataclass
class Ship:
    name: str
    length: int
    cells: list = field(default_factory=list)   # (row, col) tuples occupied
    hits: set = field(default_factory=set)       # subset of cells that were hit

    def place(self, cells):
        """Assign the board cells this ship occupies."""
        cells = list(cells)
        if len(cells) != self.length:
            raise ValueError(
                f"{self.name} requires {self.length} cells, got {len(cells)}"
            )
        self.cells = cells

    def register_hit(self, cell):
        """Mark `cell` as hit if it belongs to this ship. Returns True if it did."""
        if cell in self.cells:
            self.hits.add(cell)
            return True
        return False

    @property
    def is_sunk(self):
        return self.length > 0 and len(self.hits) == self.length

    def to_dict(self, reveal=True):
        data = {
            "name": self.name,
            "length": self.length,
            "is_sunk": self.is_sunk,
        }
        if reveal or self.is_sunk:
            data["cells"] = self.cells
            data["hits"] = list(self.hits)
        return data


def build_fleet():
    """Factory that returns a fresh, unplaced fleet of Ship objects."""
    return [Ship(name=name, length=length) for name, length in FLEET]
