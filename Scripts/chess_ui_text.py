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
    from pathlib import Path
    import sys

    side = str(seat["side"])
    cli = str(Path(__file__).with_name("chess_agent_cli.py").resolve())
    session = str(seat.get("session_file", info["session_file"]))
    python = "python" if sys.platform.startswith("win") else "python3"
    command = f'{python} "<client>" --session "<session>"'
    return "\n".join([
        f"Play chess with me. Your side: {side}.",
        "Play your own moves. Do not ask the user/operator to choose moves for you.",
        "Do not use chess engines, web search, opening books or tablebases",
        "unless I explicitly allow them. The game connection utility is allowed.",
        "",
        "Use this Python 3 utility on the same computer as the game:",
        f"Client: {cli}",
        f"Session: {session}",
        "Replace <client> and <session> below with these paths:",
        f"{command} status",
        f"{command} wait --timeout 60",
        f"{command} move <UCI-or-SAN>",
        f"{command} pgn",
        "Add --json before the subcommand for machine-readable output.",
        "",
        "Loop: wait for your turn, read the returned position and legal moves,",
        "choose a move, then send it. Wait again on timeout; stop at game over.",
        "If the game changes, stop and request a fresh invitation.",
        "Do not reset the game or change the players. I control new games in the UI.",
        "The move command checks the game and position you last read.",
        "",
        "Optional MCP / HTTP connection (use only your seat):",
        f"Endpoint URL: {info['url']}",
        f"Authorization header: {seat.get('authorization', 'Bearer ' + str(seat['token']))}",
        "Tools: get_state, wait_for_move, make_move, get_pgn.",
        "Pass game_id and expected_fen from get_state when calling make_move.",
        "Do not call new_game or set_bot_enabled.",
        "",
        "My preferences: briefly explain the idea behind each move.",
    ])


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
    if info.get("board_view") in ("white", "black"):
        return str(info["board_view"])
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


def side_label(side: str) -> str:
    return "Белые" if side == "white" else "Чёрные"


def game_status_ru(info: dict[str, object]) -> str:
    status = str(info["status"])
    if status.startswith("checkmate:"):
        return f"Мат. Победили {side_label(status.split(':')[1]).lower()}."
    if status == "stalemate":
        return "Пат. Ничья."
    if status.startswith("draw:"):
        reasons = {"insufficient_material": "недостаточно фигур", "seventyfive_moves": "75 ходов",
                   "fivefold_repetition": "повторение позиции"}
        reason = status.split(":", 1)[1]
        return "Ничья: " + reasons.get(reason, reason.replace("_", " "))
    if info.get("pending_promotion", {}).get("pending"):
        return "Выберите фигуру для превращения"
    if status == "check":
        return "Шах!"
    actor = info.get("turn_owner", {}).get("owner")
    return "Ожидаем ход агента" if actor == "agent" else "Выберите фигуру и поле"
