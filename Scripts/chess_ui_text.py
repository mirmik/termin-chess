"""Pure text formatting helpers for the chess UI."""

from __future__ import annotations


def seat_payloads(info: dict[str, object]) -> list[dict[str, object]]:
    seats = info["seats"]
    if not isinstance(seats, list):
        return []
    return [seat for seat in seats if isinstance(seat, dict) and bool(seat["active"])]


def seat_status_text(seat: dict[str, object]) -> str:
    side = str(seat["side"]).title()
    state = "connected" if bool(seat["connected"]) else "waiting"
    requests = int(seat["request_count"])
    method = seat["last_method"]
    method_text = str(method) if method is not None else "no calls"
    return f"{side}: {state}, {requests} req, {method_text}"


def agent_memo_button_label(seat: dict[str, object], active_seats: list[dict[str, object]]) -> str:
    side = str(seat["side"]).title()
    if len(active_seats) <= 1:
        return "Copy & Paste to Your Agent"
    return f"Copy & Paste to {side} Agent"


def agent_memo_text(info: dict[str, object], seat: dict[str, object]) -> str:
    side = str(seat["side"])
    url = str(info["url"])
    token = str(seat["token"])
    authorization = str(seat.get("authorization", f"Bearer {token}"))
    mode = str(info["mode"])
    session_file = str(info["session_file"])
    active_sides = info.get("active_mcp_sides")
    if isinstance(active_sides, list):
        active_text = ", ".join(str(active_side) for active_side in active_sides)
    else:
        active_text = side

    return "\n".join(
        [
            "You are playing chess as an MCP-connected agent.",
            "",
            "Connection:",
            f"- Endpoint URL: {url}",
            f"- Authorization header: {authorization}",
            f"- Token: {token}",
            f"- Your side: {side}",
            f"- Game mode: {mode}",
            f"- Active MCP sides: {active_text}",
            f"- Local session file, if accessible: {session_file}",
            "",
            "Expected conduct:",
            "- Play your own chess moves. Do not ask the user/operator to choose moves for you.",
            "- Do not use external tools, chess engines, web search, opening books, or tablebases unless the user explicitly allows it.",
            "- Use only the chess MCP connection above for game state and moves.",
            "- If it is not your turn, call `wait_for_move` with a reasonable timeout instead of polling or asking the user for updates.",
            "- On your turn, call `get_state` or `legal_moves`, choose one legal move, then call `make_move`.",
            "- Side-seat agents must not try to call `new_game` or `set_bot_enabled`; those controls are reserved for the in-game UI.",
            "",
            "Useful MCP tools:",
            "- `get_connection_info`: verify your seat, mode, endpoint and policy.",
            "- `get_state`: inspect FEN, legal moves, turn owner, game status and last move.",
            "- `legal_moves`: list legal UCI/SAN moves for the current position.",
            "- `make_move`: play your selected legal UCI or SAN move.",
            "- `wait_for_move`: wait until your side can move or the game ends.",
        ]
    )


def last_event_text(info: dict[str, object]) -> str:
    event = info["last_event"]
    return event_text(event, prefix="Last event")


def last_move_text(info: dict[str, object]) -> str:
    event = info["last_move"]
    return event_text(event, prefix="Last move")


def event_text(event: object, *, prefix: str) -> str:
    if not isinstance(event, dict):
        return f"{prefix}: none"
    event_type = str(event["type"])
    san = event.get("san")
    actor = event.get("actor")
    if san is None:
        return f"{prefix}: {event_type}"
    return f"{prefix}: {san} by {actor}"


def owners_text(info: dict[str, object]) -> str:
    owners = info["side_owners"]
    if not isinstance(owners, dict):
        return "White: unknown | Black: unknown"
    white = str(owners["white"]).replace("_", " ")
    black = str(owners["black"]).replace("_", " ")
    return f"White: {white} | Black: {black}"


def captures_text(info: dict[str, object]) -> str:
    captured = info.get("captured")
    if not isinstance(captured, dict):
        return "Captured: none"
    by_white = captured_side_text(captured.get("by_white"))
    by_black = captured_side_text(captured.get("by_black"))
    if by_white == "-" and by_black == "-":
        return "Captured: none"
    return f"Captured W: {by_white} | B: {by_black}"


def captured_side_text(items: object) -> str:
    if not isinstance(items, list) or not items:
        return "-"
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        symbol = str(item["symbol"])
        count = int(item["count"])
        parts.append(symbol if count == 1 else f"{symbol}x{count}")
    return " ".join(parts) if parts else "-"


def board_view(info: dict[str, object]) -> str:
    human_sides = info.get("human_sides")
    if not isinstance(human_sides, list):
        return "white"
    sides = {str(side) for side in human_sides}
    if sides == {"black"}:
        return "black"
    return "white"


def board_hint_text(info: dict[str, object]) -> str:
    human_sides = info.get("human_sides")
    if not isinstance(human_sides, list):
        return "Board: white view"
    sides = {str(side) for side in human_sides}
    if sides == {"white", "black"}:
        return "Board: sandbox white view"
    if not sides:
        return "Board: default white view"
    view = board_view(info)
    return f"Board: {view} view"


def files_text(info: dict[str, object]) -> str:
    files = list("abcdefgh")
    if board_view(info) == "black":
        files.reverse()
    return f"Files: {' '.join(files)}"


def ranks_text(info: dict[str, object]) -> str:
    ranks = [str(rank) for rank in range(1, 9)]
    if board_view(info) == "black":
        ranks.reverse()
    return f"Ranks: {' '.join(ranks)}"


def turn_text(info: dict[str, object]) -> str:
    turn = str(info["turn"]).title()
    turn_owner = info["turn_owner"]
    actor = "unknown"
    if isinstance(turn_owner, dict):
        actor = str(turn_owner["actor"])
    return f"{turn} to move ({actor})"


def status_text(info: dict[str, object]) -> str:
    status = str(info["status"])
    if status.startswith("checkmate:"):
        winner = status.split(":", 1)[1].title()
        return f"Checkmate! {winner} wins!"
    if status == "stalemate":
        return "Stalemate! Draw."
    if status.startswith("draw:"):
        reason = status.split(":", 1)[1].replace("_", " ")
        return f"Draw: {reason}"
    if status == "check":
        return "Check!"
    promotion = info.get("pending_promotion")
    if isinstance(promotion, dict) and bool(promotion["pending"]):
        return promotion_title(promotion)
    if bool(info["game_over"]):
        return "Game over"
    hint = info.get("selection_hint")
    if hint is not None:
        return str(hint)
    return ""


def short_path(path: str) -> str:
    if len(path) <= 34:
        return path
    return f"...{path[-31:]}"


def promotion_title(info: dict[str, object]) -> str:
    from_sq = str(info["from"])
    to_sq = str(info["to"])
    return f"Promote {from_sq}-{to_sq}"


def promotion_choices(info: dict[str, object]) -> list[dict[str, object]]:
    choices = info["choices"]
    if not isinstance(choices, list):
        return []
    return [choice for choice in choices if isinstance(choice, dict)]
