"""Game mode and move authorization model for Chess."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import chess


class GameMode(str, Enum):
    LOCAL_SANDBOX = "local_sandbox"
    HUMAN_VS_AGENT = "human_vs_agent"
    AGENT_VS_AGENT = "agent_vs_agent"
    HUMAN_VS_BOT = "human_vs_bot"


class SideOwner(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    LOCAL_BOT = "local_bot"
    NONE = "none"


class MoveActorKind(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    BOT = "bot"
    SYSTEM = "system"


@dataclass(frozen=True)
class MoveActor:
    kind: MoveActorKind
    side: bool | None = None

    @staticmethod
    def human() -> "MoveActor":
        return MoveActor(MoveActorKind.HUMAN)

    @staticmethod
    def agent(side: bool | None = None) -> "MoveActor":
        return MoveActor(MoveActorKind.AGENT, side)

    @staticmethod
    def bot() -> "MoveActor":
        return MoveActor(MoveActorKind.BOT)

    @staticmethod
    def system() -> "MoveActor":
        return MoveActor(MoveActorKind.SYSTEM)

    def event_label(self) -> str:
        if self.kind == MoveActorKind.AGENT and self.side is not None:
            return f"agent:{side_name(self.side)}"
        return self.kind.value


@dataclass(frozen=True)
class MoveAuthorization:
    ok: bool
    actor: MoveActor
    turn: bool
    owner: SideOwner
    error: str = ""


def side_name(side: bool) -> str:
    return "white" if side == chess.WHITE else "black"


class ChessGameSession:
    def __init__(self) -> None:
        self._mode = GameMode.HUMAN_VS_BOT
        self._side_owners: dict[bool, SideOwner] = {
            chess.WHITE: SideOwner.HUMAN,
            chess.BLACK: SideOwner.LOCAL_BOT,
        }
        self._mcp_side: bool | None = None

    @property
    def mode(self) -> GameMode:
        return self._mode

    @property
    def mcp_side(self) -> bool | None:
        return self._mcp_side

    def configure_runtime(
        self,
        *,
        mcp_enabled: bool,
        bot_enabled: bool,
        bot_color: bool,
    ) -> None:
        if mcp_enabled:
            self.configure_human_vs_agent(agent_side=chess.BLACK)
            return
        if bot_enabled:
            self.configure_human_vs_bot(bot_color=bot_color)
            return
        self.configure_local_sandbox()

    def configure_local_sandbox(self) -> None:
        self._mode = GameMode.LOCAL_SANDBOX
        self._side_owners = {
            chess.WHITE: SideOwner.HUMAN,
            chess.BLACK: SideOwner.HUMAN,
        }
        self._mcp_side = None

    def configure_human_vs_agent(self, *, agent_side: bool) -> None:
        self._mode = GameMode.HUMAN_VS_AGENT
        self._side_owners = {
            chess.WHITE: SideOwner.AGENT if agent_side == chess.WHITE else SideOwner.HUMAN,
            chess.BLACK: SideOwner.AGENT if agent_side == chess.BLACK else SideOwner.HUMAN,
        }
        self._mcp_side = agent_side

    def configure_agent_vs_agent(self) -> None:
        self._mode = GameMode.AGENT_VS_AGENT
        self._side_owners = {
            chess.WHITE: SideOwner.AGENT,
            chess.BLACK: SideOwner.AGENT,
        }
        self._mcp_side = None

    def configure_human_vs_bot(self, *, bot_color: bool) -> None:
        self._mode = GameMode.HUMAN_VS_BOT
        self._side_owners = {
            chess.WHITE: SideOwner.LOCAL_BOT if bot_color == chess.WHITE else SideOwner.HUMAN,
            chess.BLACK: SideOwner.LOCAL_BOT if bot_color == chess.BLACK else SideOwner.HUMAN,
        }
        self._mcp_side = None

    def owner_for_side(self, side: bool) -> SideOwner:
        return self._side_owners[side]

    def side_owners_payload(self) -> dict[str, str]:
        return {
            side_name(chess.WHITE): self.owner_for_side(chess.WHITE).value,
            side_name(chess.BLACK): self.owner_for_side(chess.BLACK).value,
        }

    def actor_for_mcp_request(self) -> MoveActor:
        if self._mode == GameMode.AGENT_VS_AGENT:
            return MoveActor.agent()
        return MoveActor.agent(self._mcp_side)

    def can_move_now(
        self,
        *,
        actor: MoveActor,
        board: chess.Board,
        game_state: str,
    ) -> MoveAuthorization:
        if game_state == "game_over" or board.is_game_over():
            return self._reject(actor, board.turn, "game is over")
        return self._authorize_actor_for_turn(actor, board.turn)

    def can_make_move(
        self,
        *,
        actor: MoveActor,
        board: chess.Board,
        game_state: str,
        move: chess.Move,
    ) -> MoveAuthorization:
        base = self.can_move_now(actor=actor, board=board, game_state=game_state)
        if not base.ok:
            return base

        moving_piece = board.piece_at(move.from_square)
        if moving_piece is None:
            return self._reject(actor, board.turn, "move has no source piece")
        if moving_piece.color != board.turn:
            return self._reject(actor, board.turn, "move source does not match the side to move")
        if move not in board.legal_moves:
            return self._reject(actor, board.turn, "move is not legal")
        return base

    def _authorize_actor_for_turn(self, actor: MoveActor, turn: bool) -> MoveAuthorization:
        owner = self.owner_for_side(turn)
        if owner == SideOwner.HUMAN:
            if actor.kind == MoveActorKind.HUMAN:
                return MoveAuthorization(True, actor, turn, owner)
            return self._reject(actor, turn, f"{side_name(turn)} is controlled by human")
        if owner == SideOwner.AGENT:
            if actor.kind == MoveActorKind.AGENT and (actor.side is None or actor.side == turn):
                return MoveAuthorization(True, actor, turn, owner)
            return self._reject(actor, turn, f"{side_name(turn)} is controlled by agent")
        if owner == SideOwner.LOCAL_BOT:
            if actor.kind == MoveActorKind.BOT:
                return MoveAuthorization(True, actor, turn, owner)
            return self._reject(actor, turn, f"{side_name(turn)} is controlled by local bot")
        return self._reject(actor, turn, f"{side_name(turn)} is not assigned to a player")

    def _reject(self, actor: MoveActor, turn: bool, error: str) -> MoveAuthorization:
        return MoveAuthorization(False, actor, turn, self.owner_for_side(turn), error)
