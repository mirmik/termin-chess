"""Typed payload helpers for the chess MCP contract."""

from __future__ import annotations

from typing import TypedDict

import chess


LegalMovePayload = TypedDict(
    "LegalMovePayload",
    {
        "uci": str,
        "san": str,
        "from": str,
        "to": str,
        "promotion": str | None,
        "capture": bool,
        "check": bool,
    },
)

MoveEventPayload = TypedDict(
    "MoveEventPayload",
    {
        "type": str,
        "actor": str,
        "uci": str,
        "san": str,
        "from": str,
        "to": str,
        "promotion": str | None,
    },
    total=False,
)

McpEventPayload = TypedDict(
    "McpEventPayload",
    {
        "type": str,
        "actor": str,
        "uci": str,
        "san": str,
        "from": str,
        "to": str,
        "promotion": str | None,
        "id": int,
        "fen": str,
        "turn": str,
        "ply": int,
        "status": str,
    },
    total=False,
)

CapturedPiecePayload = TypedDict(
    "CapturedPiecePayload",
    {
        "piece": str,
        "symbol": str,
        "count": int,
    },
)

CapturedSummaryPayload = TypedDict(
    "CapturedSummaryPayload",
    {
        "by_white": list[CapturedPiecePayload],
        "by_black": list[CapturedPiecePayload],
    },
)

SeatPayload = TypedDict("SeatPayload", {"side": str, "owner": str, "label": str}, total=False)

ConnectionPayload = TypedDict(
    "ConnectionPayload",
    {
        "ok": bool,
        "server": dict[str, object],
        "session": dict[str, object],
        "endpoint": dict[str, object],
        "session_file": str,
        "mode": str,
        "turn": str,
        "turn_owner": dict[str, object],
        "status": str,
        "side_owners": dict[str, str],
        "game_seats": list[SeatPayload],
        "mcp_seats": list[dict[str, object]],
        "active_mcp_sides": list[str],
        "board_input_enabled": bool,
        "board_input_error": str | None,
        "caller": dict[str, object],
        "seats": list[dict[str, object]],
        "hints": dict[str, object],
        "tool_policy": dict[str, object],
        "tools": list[str],
        "resources": list[str],
    },
)

UiConnectionPayload = TypedDict(
    "UiConnectionPayload",
    {
        "ok": bool,
        "url": str,
        "health_url": str,
        "session_file": str,
        "session_id": str,
        "mode": str,
        "turn": str,
        "turn_owner": dict[str, object],
        "status": str,
        "last_event": McpEventPayload | None,
        "active_mcp_sides": list[str],
        "seats": list[dict[str, object]],
    },
)

McpStatePayload = TypedDict(
    "McpStatePayload",
    {
        "ok": bool,
        "fen": str,
        "board_ascii": str,
        "turn": str,
        "turn_owner": dict[str, object],
        "fullmove_number": int,
        "ply": int,
        "legal_moves": list[LegalMovePayload],
        "selected_legal_moves": list[LegalMovePayload],
        "selection_hint": str | None,
        "pending_promotion": dict[str, object],
        "last_move": McpEventPayload | None,
        "last_move_squares": list[str],
        "check_square": str | None,
        "captured": CapturedSummaryPayload,
        "status": str,
        "check": bool,
        "checkmate": bool,
        "stalemate": bool,
        "game_over": bool,
        "game_started": bool,
        "start_menu_visible": bool,
        "board_input_enabled": bool,
        "board_input_error": str | None,
        "selected_square": str | None,
        "mode": str,
        "side_owners": dict[str, str],
        "human_sides": list[str],
        "agent_sides": list[str],
        "local_bot_sides": list[str],
        "seats": list[SeatPayload],
        "mcp_seats": list[dict[str, object]],
        "active_mcp_sides": list[str],
        "mcp_side": str | None,
        "caller_side": str | None,
        "caller_can_move": bool | None,
        "caller_error": str | None,
        "bot_enabled": bool,
        "bot_color": str,
        "next_event_id": int,
    },
)


def legal_move_payload(board: chess.Board, move: chess.Move) -> LegalMovePayload:
    return {
        "uci": move.uci(),
        "san": board.san(move),
        "from": chess.square_name(move.from_square),
        "to": chess.square_name(move.to_square),
        "promotion": chess.piece_name(move.promotion) if move.promotion else None,
        "capture": board.is_capture(move),
        "check": board.gives_check(move),
    }
