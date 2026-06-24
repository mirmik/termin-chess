from __future__ import annotations

import sys
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


class FakeMeshRenderer:
    def __init__(self, material: object) -> None:
        self.material = material

    def get_field(self, name: str) -> object:
        assert name == "material"
        return self.material

    def set_field(self, name: str, value: object) -> None:
        assert name == "material"
        self.material = value


class FakeTile:
    def __init__(self, material: object) -> None:
        self.renderer = FakeMeshRenderer(material)

    def get_tc_component(self, name: str) -> FakeMeshRenderer | None:
        if name == "MeshRenderer":
            return self.renderer
        return None


def make_headless_controller() -> object:
    controller = ChessGameController()
    controller._highlight_selected = "selected"
    controller._highlight_valid = "valid"
    controller._highlight_last_move = "last"
    controller._highlight_check = "check"
    controller._game_started = True
    controller._start_menu_visible = False
    controller._bot_enabled = False
    controller._ui_component = None
    controller._session.configure_agent_vs_agent()
    controller._mark_state_dirty()
    return controller


def test_wait_for_mcp_event_returns_ready_after_opponent_move() -> None:
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
        timeout=0,
        caller_side=chess.BLACK,
    )

    assert payload["ok"] is True
    assert payload["ready"] is True
    assert payload["event"] is None
    assert payload["waiting_for"]["actor"] == "agent:black"
    assert payload["state"]["caller_side"] == "black"
    assert payload["state"]["caller_can_move"] is True
    assert payload["state"]["last_move"]["uci"] == "e2e4"


def test_wait_for_mcp_event_returns_ready_immediately_on_caller_turn() -> None:
    controller = make_headless_controller()

    payload = controller.wait_for_mcp_event(
        timeout=0,
        caller_side=chess.WHITE,
    )

    assert payload["ok"] is True
    assert payload["ready"] is True
    assert payload["event"] is None
    assert payload["waiting_for"]["actor"] == "agent:white"
    assert payload["state"]["caller_side"] == "white"
    assert payload["state"]["caller_can_move"] is True


def test_get_mcp_state_caches_shared_snapshot_but_scopes_caller_fields() -> None:
    controller = make_headless_controller()
    original_build = controller._build_mcp_state
    build_count = 0

    def counting_build() -> dict[str, object]:
        nonlocal build_count
        build_count += 1
        return original_build()

    controller._build_mcp_state = counting_build

    white_state = controller.get_mcp_state(caller_side=chess.WHITE)
    black_state = controller.get_mcp_state(caller_side=chess.BLACK)

    assert build_count == 1
    assert white_state["caller_side"] == "white"
    assert white_state["caller_can_move"] is True
    assert black_state["caller_side"] == "black"
    assert black_state["caller_can_move"] is False

    controller._mark_state_dirty()
    controller.get_mcp_state(caller_side=chess.WHITE)

    assert build_count == 2


def test_timed_out_mcp_move_is_not_applied_later() -> None:
    controller = make_headless_controller()

    payload = controller._submit_mcp_command(
        {"kind": "move", "move": "e2e4", "side": chess.WHITE},
        timeout=0,
    )
    controller._process_mcp_commands()

    assert payload["ok"] is False
    assert payload["timeout"] is True
    assert controller._board.fen() == chess.STARTING_FEN
    assert controller.get_mcp_events()["events"] == []


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


def test_board_highlight_layers_keep_last_move_check_selection_and_valid_moves() -> None:
    controller = make_headless_controller()
    squares = ("e2", "e4", "e8", "a1")
    controller._tiles = {square: FakeTile(f"base-{square}") for square in squares}
    controller._original_materials = {square: f"base-{square}" for square in squares}
    controller._last_move_squares = ("e2", "e4")
    controller._check_square = "e8"
    controller._selected_square = "e2"
    controller._valid_moves = [chess.Move.from_uci("e2e4")]

    controller._refresh_board_highlights()

    assert controller._tiles["e2"].renderer.material == "selected"
    assert controller._tiles["e4"].renderer.material == "valid"
    assert controller._tiles["e8"].renderer.material == "check"
    assert controller._tiles["a1"].renderer.material == "base-a1"


def test_selected_promotion_state_reports_piece_choice_hint() -> None:
    controller = make_headless_controller()
    controller._board = chess.Board("k7/4P3/8/8/8/8/8/K7 w - - 0 1")
    controller._selected_square = "e7"
    controller._valid_moves = [
        move for move in controller._board.legal_moves
        if chess.square_name(move.from_square) == "e7"
    ]

    state = controller.get_mcp_state()

    assert state["selected_square"] == "e7"
    assert state["selection_hint"] == "Promotion: choose target square, then pick a piece."
    assert state["pending_promotion"] == {"pending": False}
    assert {"queen", "rook", "bishop", "knight"}.issubset(
        {str(move["promotion"]) for move in state["selected_legal_moves"]}
    )


def test_human_promotion_click_waits_for_piece_choice() -> None:
    controller = make_headless_controller()
    controller._session.configure_local_sandbox()
    controller._board = chess.Board("k7/4P3/8/8/8/8/8/K7 w - - 0 1")

    controller._select_piece("e7")
    controller._handle_click("e8")

    pending = controller.get_pending_promotion_info()
    assert pending["pending"] is True
    assert pending["from"] == "e7"
    assert pending["to"] == "e8"
    assert {str(choice["piece"]) for choice in pending["choices"]} == {"queen", "rook", "bishop", "knight"}
    assert controller._board.piece_at(chess.E7) == chess.Piece(chess.PAWN, chess.WHITE)


def test_reselecting_piece_clears_pending_promotion() -> None:
    controller = make_headless_controller()
    controller._session.configure_local_sandbox()
    controller._pending_promotion = {
        "pending": True,
        "from": "e7",
        "to": "e8",
        "choices": [{"piece": "queen", "label": "Queen", "uci": "e7e8q", "san": "e8=Q+"}],
    }

    controller._select_piece("e2")

    assert controller.get_pending_promotion_info() == {"pending": False}


def test_choose_promotion_executes_selected_piece_move() -> None:
    controller = make_headless_controller()
    executed: list[str] = []
    controller._pending_promotion = {
        "pending": True,
        "from": "e7",
        "to": "e8",
        "choices": [
            {"piece": "queen", "label": "Queen", "uci": "e7e8q", "san": "e8=Q+"},
            {"piece": "rook", "label": "Rook", "uci": "e7e8r", "san": "e8=R+"},
        ],
    }

    def execute(move: chess.Move, trigger_bot: bool = True, actor: object = MoveActor.human()) -> bool:
        executed.append(move.uci())
        return True

    controller._execute_move = execute

    controller.choose_promotion("rook")

    assert executed == ["e7e8r"]
    assert controller._pending_promotion is None


def test_captured_summary_reports_missing_pieces_by_capturing_side() -> None:
    controller = make_headless_controller()
    controller._board = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN1 w Qkq - 0 1")

    state = controller.get_mcp_state()

    assert state["captured"]["by_white"] == []
    assert state["captured"]["by_black"] == [{"piece": "rook", "symbol": "R", "count": 1}]
