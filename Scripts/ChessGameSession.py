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
class PlayerSeat:
    side: bool
    owner: SideOwner
    label: str

    def payload(self) -> dict[str, object]:
        return {
            "side": side_name(self.side),
            "owner": self.owner.value,
            "label": self.label,
        }


@dataclass(frozen=True)
class McpSeat:
    side: bool
    active: bool
    display_name: str

    def payload(self) -> dict[str, object]:
        return {
            "side": side_name(self.side),
            "active": self.active,
            "display_name": self.display_name,
            "token_name": side_name(self.side),
        }


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
        self._player_seats: dict[bool, PlayerSeat] = {}
        self._mcp_seats: dict[bool, McpSeat] = {}
        self._mcp_side: bool | None = None
        self.configure_human_vs_bot(bot_color=chess.BLACK)

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
        self._configure_mode(
            mode=GameMode.LOCAL_SANDBOX,
            white_owner=SideOwner.HUMAN,
            black_owner=SideOwner.HUMAN,
            active_mcp_sides=(),
            default_mcp_side=None,
        )

    def configure_human_vs_agent(self, *, agent_side: bool) -> None:
        self._configure_mode(
            mode=GameMode.HUMAN_VS_AGENT,
            white_owner=SideOwner.AGENT if agent_side == chess.WHITE else SideOwner.HUMAN,
            black_owner=SideOwner.AGENT if agent_side == chess.BLACK else SideOwner.HUMAN,
            active_mcp_sides=(agent_side,),
            default_mcp_side=agent_side,
        )

    def configure_agent_vs_agent(self) -> None:
        self._configure_mode(
            mode=GameMode.AGENT_VS_AGENT,
            white_owner=SideOwner.AGENT,
            black_owner=SideOwner.AGENT,
            active_mcp_sides=(chess.WHITE, chess.BLACK),
            default_mcp_side=None,
        )

    def configure_human_vs_bot(self, *, bot_color: bool) -> None:
        self._configure_mode(
            mode=GameMode.HUMAN_VS_BOT,
            white_owner=SideOwner.LOCAL_BOT if bot_color == chess.WHITE else SideOwner.HUMAN,
            black_owner=SideOwner.LOCAL_BOT if bot_color == chess.BLACK else SideOwner.HUMAN,
            active_mcp_sides=(),
            default_mcp_side=None,
        )

    def owner_for_side(self, side: bool) -> SideOwner:
        return self._player_seats[side].owner

    def side_owners_payload(self) -> dict[str, str]:
        return {
            side_name(chess.WHITE): self.owner_for_side(chess.WHITE).value,
            side_name(chess.BLACK): self.owner_for_side(chess.BLACK).value,
        }

    def player_seats_payload(self) -> list[dict[str, object]]:
        return [
            self._player_seats[chess.WHITE].payload(),
            self._player_seats[chess.BLACK].payload(),
        ]

    def mcp_seats_payload(self) -> list[dict[str, object]]:
        return [
            self._mcp_seats[chess.WHITE].payload(),
            self._mcp_seats[chess.BLACK].payload(),
        ]

    def active_mcp_sides_payload(self) -> list[str]:
        return [
            side_name(side)
            for side in (chess.WHITE, chess.BLACK)
            if self._mcp_seats[side].active
        ]

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

    def _configure_mode(
        self,
        *,
        mode: GameMode,
        white_owner: SideOwner,
        black_owner: SideOwner,
        active_mcp_sides: tuple[bool, ...],
        default_mcp_side: bool | None,
    ) -> None:
        self._mode = mode
        self._player_seats = {
            chess.WHITE: PlayerSeat(
                side=chess.WHITE,
                owner=white_owner,
                label=self._player_label(chess.WHITE, white_owner),
            ),
            chess.BLACK: PlayerSeat(
                side=chess.BLACK,
                owner=black_owner,
                label=self._player_label(chess.BLACK, black_owner),
            ),
        }
        active_mcp_side_set = set(active_mcp_sides)
        self._mcp_seats = {
            chess.WHITE: McpSeat(
                side=chess.WHITE,
                active=chess.WHITE in active_mcp_side_set,
                display_name="White agent",
            ),
            chess.BLACK: McpSeat(
                side=chess.BLACK,
                active=chess.BLACK in active_mcp_side_set,
                display_name="Black agent",
            ),
        }
        self._mcp_side = default_mcp_side

    @staticmethod
    def _player_label(side: bool, owner: SideOwner) -> str:
        side_label = "White" if side == chess.WHITE else "Black"
        if owner == SideOwner.HUMAN:
            return f"{side_label} human"
        if owner == SideOwner.AGENT:
            return f"{side_label} agent"
        if owner == SideOwner.LOCAL_BOT:
            return f"{side_label} local bot"
        return f"{side_label} unassigned"
