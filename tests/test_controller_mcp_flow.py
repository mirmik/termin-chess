from __future__ import annotations

import sys
import threading
import types
from pathlib import Path

import chess

from conftest import SCRIPTS_DIR, load_script_module


def load_controller_module():
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    scripts_pkg = types.ModuleType("Scripts")
    scripts_pkg.__path__ = [str(SCRIPTS_DIR)]
    sys.modules["Scripts"] = scripts_pkg

    tcbase = types.ModuleType("tcbase")
    tcbase.Action = types.SimpleNamespace(PRESS="press")
    tcbase.MouseButton = types.SimpleNamespace(LEFT="left")
    sys.modules["tcbase"] = tcbase

    termin_pkg = types.ModuleType("termin")
    termin_pkg.__path__ = []
    sys.modules["termin"] = termin_pkg

    geombase = types.ModuleType("termin.geombase")

    class Vec3:
        def __init__(self, x: float, y: float, z: float) -> None:
            self.x = x
            self.y = y
            self.z = z

    geombase.Vec3 = Vec3
    sys.modules["termin.geombase"] = geombase

    input_module = types.ModuleType("termin.input")

    class InputComponent:
        def __init__(self, *, enabled: bool = True, active_in_editor: bool = False) -> None:
            self.enabled = enabled
            self.active_in_editor = active_in_editor

        def start(self) -> None:
            return None

    input_module.InputComponent = InputComponent
    sys.modules["termin.input"] = input_module

    collision_module = types.ModuleType("termin.collision")
    collision_module.CollisionWorld = object
    sys.modules["termin.collision"] = collision_module

    materials_module = types.ModuleType("termin.materials")

    class TcMaterial:
        @staticmethod
        def from_name(name: str) -> object:
            return object()

    materials_module.TcMaterial = TcMaterial
    sys.modules["termin.materials"] = materials_module

    return load_script_module("chess_game_controller_under_test", "ChessGameController.py")


controller_module = load_controller_module()
session_module = sys.modules["Scripts.ChessGameSession"]

ChessGameController = controller_module.ChessGameController
STATE_GAME_OVER = controller_module.STATE_GAME_OVER
STATE_IDLE = controller_module.STATE_IDLE
GameMode = session_module.GameMode
MoveActor = session_module.MoveActor


class RecordingMcpServer:
    def __init__(self) -> None:
        self.reset_count = 0

    def reset_session_state(self) -> None:
        self.reset_count += 1


def make_headless_controller() -> object:
    controller = ChessGameController.__new__(ChessGameController)
    controller._board = chess.Board()
    controller._state = STATE_IDLE
    controller._selected_square = None
    controller._game_started = True
    controller._start_menu_visible = False
    controller._bot_enabled = False
    controller._bot_color = chess.BLACK
    controller._mcp_state_lock = threading.RLock()
    controller._mcp_condition = threading.Condition()
    controller._mcp_events = []
    controller._mcp_next_event_id = 1
    controller._mcp_max_events = 200
    controller._mcp_server = None
    controller._session = session_module.ChessGameSession()
    controller._session.configure_agent_vs_agent()
    return controller


def test_wait_for_mcp_event_returns_user_move_and_updated_waiting_side() -> None:
    controller = make_headless_controller()
    move = chess.Move.from_uci("e2e4")
    san = controller._board.san(move)
    controller._board.push(move)
    controller._record_mcp_event(
        {
            "type": "move",
            "actor": MoveActor.human().event_label(),
            "uci": move.uci(),
            "san": san,
            "from": "e2",
            "to": "e4",
            "promotion": None,
        }
    )

    payload = controller.wait_for_mcp_event(
        after_event_id=None,
        after_ply=0,
        timeout=0,
        caller_side=chess.BLACK,
    )

    assert payload["ok"] is True
    assert payload["event"]["type"] == "move"
    assert payload["event"]["actor"] == "human"
    assert payload["event"]["uci"] == "e2e4"
    assert payload["event"]["ply"] == 1
    assert payload["waiting_for"]["actor"] == "agent:black"
    assert payload["state"]["caller_side"] == "black"
    assert payload["state"]["caller_can_move"] is True


def test_mcp_move_after_game_over_returns_structured_error() -> None:
    controller = make_headless_controller()
    controller._board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    controller._state = STATE_GAME_OVER

    payload = controller._apply_mcp_move("e7e5", side=chess.BLACK)

    assert payload["ok"] is False
    assert payload["error"] == "game is over"
    assert payload["state"]["status"] == "checkmate:black"
    assert payload["state"]["game_over"] is True
    assert payload["state"]["caller_side"] == "black"
    assert payload["state"]["caller_can_move"] is False
    assert payload["state"]["caller_error"] == "game is over"


def test_controller_reset_hook_clears_mcp_session_state() -> None:
    controller = make_headless_controller()
    server = RecordingMcpServer()
    controller._mcp_server = server

    controller._reset_mcp_session_state()

    assert server.reset_count == 1


def test_local_sandbox_controller_mode_disables_mcp_and_allows_human_board_input() -> None:
    controller = make_headless_controller()

    controller._configure_requested_game_mode(GameMode.LOCAL_SANDBOX)
    state = controller.get_mcp_state()
    connection_info = controller.get_connection_panel_info()
    human_authorization = controller._session.can_make_move(
        actor=MoveActor.human(),
        board=controller._board,
        game_state=controller._state,
        move=chess.Move.from_uci("e2e4"),
    )

    assert controller.current_mode() == "local_sandbox"
    assert controller._game_mcp_enabled is False
    assert controller._bot_enabled is False
    assert state["side_owners"] == {"white": "human", "black": "human"}
    assert state["human_sides"] == ["white", "black"]
    assert state["active_mcp_sides"] == []
    assert state["board_input_enabled"] is True
    assert state["board_input_error"] is None
    assert connection_info["ok"] is False
    assert connection_info["error"] == "MCP server is not running"
    assert human_authorization.ok is True
