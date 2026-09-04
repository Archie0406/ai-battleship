"""
game/fleet.py
=============
A Fleet is the collection of Ship objects that belong to one board. It
existed implicitly as a plain list before; pulling it into its own class
gives Board (and anything else that needs fleet-level answers -- "is
everything placed?", "is everything sunk?", "what lengths are still
afloat?") one place to ask instead of re-writing the same list
comprehension everywhere.

Fleet is iterable and sized like a list (`for ship in fleet`,
`len(fleet)`), so it drops into existing code that expected a plain
list of ships without any call-site changes.
"""

from game.ships import build_fleet


class Fleet:
    def __init__(self, ships=None):
        self.ships = ships if ships is not None else build_fleet()

    def __iter__(self):
        return iter(self.ships)

    def __len__(self):
        return len(self.ships)

    def __getitem__(self, index):
        return self.ships[index]

    def find(self, name):
        for ship in self.ships:
            if ship.name == name:
                return ship
        return None

    def reset(self):
        """Rebuild every ship fresh (unplaced, unhit)."""
        self.ships = build_fleet()

    @property
    def all_sunk(self):
        return all(ship.is_sunk for ship in self.ships)

    @property
    def is_fully_placed(self):
        return all(len(ship.cells) == ship.length for ship in self.ships)

    def remaining_lengths(self):
        """Lengths of every ship not yet sunk -- what an AI still has to find."""
        return [ship.length for ship in self.ships if not ship.is_sunk]

    def remaining_count(self):
        return sum(1 for ship in self.ships if not ship.is_sunk)

    def to_dict(self, reveal=True):
        return [ship.to_dict(reveal=reveal) for ship in self.ships]
