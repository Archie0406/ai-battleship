"""
game/player.py
===============
A Player pairs a Board with an identity (human or AI) and, for
AI-controlled players, the targeting agent that plays for them. It
doesn't implement any game rules itself -- it's what the engines pass
around so "whose board is this" and "who decides the next move" travel
together as one object instead of as parallel `player_board` /
`ai_agent` attributes.

Both GameEngine (Human vs AI) and AIVsAIEngine (AI vs AI) build their
matches out of two Players, which is what lets the same Board / Fleet /
Ship / Agent classes serve either mode unchanged.
"""


class Player:
    def __init__(self, name, board, is_ai=False, agent=None):
        self.name = name
        self.board = board
        self.is_ai = is_ai
        self.agent = agent  # an ai.agent.BaseAgent subclass, only set when is_ai

    @property
    def fleet(self):
        return self.board.fleet

    @property
    def ships_remaining(self):
        return self.board.fleet.remaining_count()

    @property
    def all_sunk(self):
        return self.board.fleet.all_sunk

    def choose_target(self, tracking_grid, remaining_lengths):
        """Delegates to this player's AI agent. Only valid when is_ai."""
        if not self.agent:
            raise ValueError(f"Player '{self.name}' has no AI agent to choose a target")
        return self.agent.choose_target(tracking_grid, remaining_lengths)

    def to_dict(self, reveal_ships=False):
        return self.board.to_dict(reveal_ships=reveal_ships)
