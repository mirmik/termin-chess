from __future__ import annotations

import json
from pathlib import Path

import chess

from conftest import load_script_module


mcp_module = load_script_module("chess_mcp_server_under_test", "ChessMcpServer.py")

ChessGameMcpServer = mcp_module.ChessGameMcpServer
ChessMcpConfig = mcp_module.ChessMcpConfig


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool | None]] = []
        self.shutdown_notifications = 0

    def get_mcp_state(self, *, caller_side: bool | None = None) -> dict[str, object]:
        self.calls.append(("get_mcp_state", caller_side))
        caller_name = None
        caller_can_move = None
        caller_error = None
        if caller_side == chess.WHITE:
            caller_name = "white"
            caller_can_move = True
        elif caller_side == chess.BLACK:
            caller_name = "black"
            caller_can_move = False
            caller_error = "white is controlled by agent"

        return {
            "ok": True,
            "fen": chess.STARTING_FEN,
            "board_ascii": str(chess.Board()),
            "turn": "white",
            "turn_owner": {
                "side": "white",
                "owner": "agent",
                "label": "White agent",
                "actor": "agent:white",
            },
            "fullmove_number": 1,
            "ply": 0,
            "legal_moves": [{"uci": "e2e4", "san": "e4", "from": "e2", "to": "e4"}],
            "last_move": None,
            "status": "playing",
            "check": False,
            "checkmate": False,
            "stalemate": False,
            "game_over": False,
            "game_started": True,
            "start_menu_visible": False,
            "board_input_enabled": False,
            "board_input_error": "white is controlled by agent",
            "selected_square": None,
            "mode": "agent_vs_agent",
            "side_owners": {"white": "agent", "black": "agent"},
            "human_sides": [],
            "agent_sides": ["white", "black"],
            "local_bot_sides": [],
            "seats": [
                {"side": "white", "owner": "agent", "label": "White agent"},
                {"side": "black", "owner": "agent", "label": "Black agent"},
            ],
            "mcp_seats": [
                {"side": "white", "active": True, "display_name": "White agent", "token_name": "white"},
                {"side": "black", "active": True, "display_name": "Black agent", "token_name": "black"},
            ],
            "active_mcp_sides": ["white", "black"],
            "mcp_side": None,
            "caller_side": caller_name,
            "caller_can_move": caller_can_move,
            "caller_error": caller_error,
            "bot_enabled": False,
            "bot_color": "black",
            "next_event_id": 1,
        }

    def request_mcp_move(self, move_text: str, *, side: bool, timeout: float) -> dict[str, object]:
        return {"ok": True, "move": move_text, "side": "white" if side == chess.WHITE else "black", "timeout": timeout}

    def wait_for_mcp_event(
        self,
        *,
        timeout: float,
        caller_side: bool | None = None,
    ) -> dict[str, object]:
        return {
            "ok": False,
            "timeout": True,
            "caller_side": "white" if caller_side == chess.WHITE else "black",
        }

    def get_mcp_pgn(self) -> str:
        return ""

    def get_mcp_events(self) -> dict[str, object]:
        return {"ok": True, "events": [], "next_event_id": 1}

    def notify_mcp_server_stopping(self) -> None:
        self.shutdown_notifications += 1


class FakeHttpServer:
    def __init__(self) -> None:
        self.shutdown_called = False
        self.server_close_called = False

    def shutdown(self) -> None:
        self.shutdown_called = True

    def server_close(self) -> None:
        self.server_close_called = True


class FakeThread:
    def __init__(self) -> None:
        self.join_timeout: float | None = None

    def join(self, timeout: float | None = None) -> None:
        self.join_timeout = timeout

    def is_alive(self) -> bool:
        return False


def make_server(session_file: Path) -> ChessGameMcpServer:
    controller = FakeController()
    config = ChessMcpConfig(
        host="127.0.0.1",
        port=8790,
        white_token="white-token",
        black_token="black-token",
        session_file=session_file,
    )
    return ChessGameMcpServer(controller, config)


def test_stop_closes_http_server_joins_thread_and_removes_session_file(tmp_path: Path) -> None:
    controller = FakeController()
    config = ChessMcpConfig(
        host="127.0.0.1",
        port=8790,
        white_token="white-token",
        black_token="black-token",
        session_file=tmp_path / "session.json",
    )
    server = ChessGameMcpServer(controller, config)
    httpd = FakeHttpServer()
    thread = FakeThread()
    config.session_file.write_text("{}", encoding="utf-8")
    server._httpd = httpd
    server._thread = thread

    server.stop()
    server.stop()

    assert controller.shutdown_notifications == 1
    assert httpd.shutdown_called is True
    assert httpd.server_close_called is True
    assert thread.join_timeout == 2.0
    assert not config.session_file.exists()


def test_session_file_contains_two_agent_handoff(tmp_path: Path) -> None:
    session_file = tmp_path / "session.json"
    server = make_server(session_file)

    server._write_session_file()

    payload = json.loads(session_file.read_text(encoding="utf-8"))
    mode = session_file.stat().st_mode & 0o777

    assert mode == 0o600
    assert payload["mode"] == "agent_vs_agent"
    assert payload["legacy_default_side"] == "black"
    assert payload["turn_owner"]["actor"] == "agent:white"
    assert payload["status"] == "playing"
    assert payload["ply"] == 0
    assert payload["board_input_enabled"] is False
    assert payload["board_input_error"] == "white is controlled by agent"
    assert payload["active_mcp_sides"] == ["white", "black"]
    assert payload["tokens"] == {"white": "white-token", "black": "black-token"}
    assert payload["agents"]["white"] == {
        "active": True,
        "token": "white-token",
        "authorization": "Bearer white-token",
    }
    assert payload["agents"]["black"] == {
        "active": True,
        "token": "black-token",
        "authorization": "Bearer black-token",
    }
    assert "make_move" in payload["tools"]
    assert "chess://game/connection" in payload["resources"]


def test_connection_payload_is_caller_scoped(tmp_path: Path) -> None:
    server = make_server(tmp_path / "session.json")
    server._mark_seat_seen(chess.BLACK, method="tools/call")

    payload = server._connection_payload(chess.BLACK)

    assert payload["mode"] == "agent_vs_agent"
    assert payload["turn_owner"]["actor"] == "agent:white"
    assert payload["board_input_enabled"] is False
    assert payload["board_input_error"] == "white is controlled by agent"
    assert payload["caller"]["side"] == "black"
    assert payload["caller"]["can_move"] is False
    assert payload["caller"]["error"] == "white is controlled by agent"
    assert payload["caller"]["token"] == "black-token"
    assert payload["caller"]["authorization"] == "Bearer black-token"
    assert payload["hints"]["two_agent_mode_uses_one_endpoint"] is True

    white_seat = payload["seats"][0]
    black_seat = payload["seats"][1]
    assert white_seat["side"] == "white"
    assert white_seat["caller"] is False
    assert white_seat["token"] is None
    assert white_seat["authorization"] is None
    assert black_seat["side"] == "black"
    assert black_seat["caller"] is True
    assert black_seat["token"] == "black-token"
    assert black_seat["connected"] is True
    assert black_seat["request_count"] == 1
    assert black_seat["last_method"] == "tools/call"


def test_reset_session_state_clears_live_seat_status_and_rewrites_session_file(tmp_path: Path) -> None:
    session_file = tmp_path / "session.json"
    server = make_server(session_file)
    original_session_id = server._session_id
    server._mark_seat_seen(chess.WHITE, method="tools/call")
    server._mark_seat_seen(chess.BLACK, method="resources/read")

    connected_payload = server.ui_connection_payload()
    assert [seat["connected"] for seat in connected_payload["seats"]] == [True, True]

    server.reset_session_state()

    reset_payload = server.ui_connection_payload()
    file_payload = json.loads(session_file.read_text(encoding="utf-8"))
    assert reset_payload["session_id"] != original_session_id
    assert file_payload["session_id"] == reset_payload["session_id"]
    assert [seat["connected"] for seat in reset_payload["seats"]] == [False, False]
    assert [seat["request_count"] for seat in reset_payload["seats"]] == [0, 0]
    assert [seat["last_method"] for seat in reset_payload["seats"]] == [None, None]


def test_side_seat_tools_are_caller_aware(tmp_path: Path) -> None:
    server = make_server(tmp_path / "session.json")

    response = server._handle_tool_call(
        1,
        {"name": "legal_moves", "arguments": {}},
        mcp_side=chess.BLACK,
    )
    restricted = server._handle_tool_call(
        2,
        {"name": "new_game", "arguments": {}},
        mcp_side=chess.WHITE,
    )

    payload = response["result"]["structuredContent"]
    restricted_payload = restricted["result"]["structuredContent"]
    assert response["result"]["isError"] is False
    assert payload["turn"] == "white"
    assert payload["turn_owner"]["actor"] == "agent:white"
    assert payload["caller_side"] == "black"
    assert payload["caller_can_move"] is False
    assert payload["caller_error"] == "white is controlled by agent"
    assert restricted["result"]["isError"] is True
    assert restricted_payload["ok"] is False
    assert restricted_payload["caller_side"] == "white"
    assert "new_game is reserved" in restricted_payload["error"]


def test_invalid_timeout_argument_returns_invalid_params(tmp_path: Path) -> None:
    server = make_server(tmp_path / "session.json")

    response = server._handle_tool_call(
        1,
        {"name": "make_move", "arguments": {"move": "e2e4", "timeout": "soon"}},
        mcp_side=chess.WHITE,
    )

    assert response["error"]["code"] == -32602
    assert response["error"]["message"] == "timeout must be a non-negative finite number"
