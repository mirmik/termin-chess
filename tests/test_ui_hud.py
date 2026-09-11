from __future__ import annotations

import sys
import types

from conftest import SCRIPTS_DIR, load_script_module


def load_ui_module():
    scripts_pkg = types.ModuleType("Scripts")
    scripts_pkg.__path__ = [str(SCRIPTS_DIR)]
    sys.modules["Scripts"] = scripts_pkg
    sys.modules["Scripts.chess_ui_text"] = load_script_module("Scripts.chess_ui_text", "chess_ui_text.py")

    termin_pkg = types.ModuleType("termin")
    termin_pkg.__path__ = []
    sys.modules["termin"] = termin_pkg

    scene = types.ModuleType("termin.scene")
    scene.PythonComponent = type("PythonComponent", (), {})
    sys.modules["termin.scene"] = scene
    components = types.ModuleType("termin.ui_components")
    components.UIComponent = type("UIComponent", (), {})
    sys.modules["termin.ui_components"] = components
    gui = types.ModuleType("termin.gui_native")
    for name in ("Button", "Label", "VStack", "CrossAxisAlignment", "EdgeInsets",
                 "LayoutPolicy", "OverlayAnchor", "Point", "Size", "SrgbColor",
                 "StyleField", "StyleOverride", "UiDocumentAsset"):
        setattr(gui, name, type(name, (), {}))
    sys.modules["termin.gui_native"] = gui

    return load_script_module("chess_ui_component_under_test", "ChessUIComponent.py")


ui_module = load_ui_module()
ChessUIComponent = ui_module.ChessUIComponent
ui_text = sys.modules["Scripts.chess_ui_text"]


def test_hud_text_helpers_format_mode_ownership_turn_status_and_last_move() -> None:
    info = {
        "turn": "black",
        "turn_owner": {"actor": "agent:black"},
        "status": "check",
        "game_over": False,
        "side_owners": {"white": "human", "black": "agent"},
        "human_sides": ["white"],
        "last_move": {"type": "move", "san": "e4", "actor": "human"},
        "captured": {
            "by_white": [{"piece": "pawn", "symbol": "P", "count": 2}],
            "by_black": [{"piece": "rook", "symbol": "R", "count": 1}],
        },
    }

    assert ui_text.owners_text(info) == "White: human | Black: agent"
    assert ui_text.turn_text(info) == "Black to move (agent:black)"
    assert ui_text.status_text(info) == "Check!"
    assert ui_text.last_move_text(info) == "Last move: e4 by human"
    assert ui_text.captures_text(info) == "Captured W: Px2 | B: R"
    assert ui_text.board_hint_text(info) == "Board: white view"
    assert ui_text.files_text(info) == "Files: a b c d e f g h"
    assert ui_text.ranks_text(info) == "Ranks: 1 2 3 4 5 6 7 8"


def test_hud_coordinate_helpers_follow_local_player_orientation() -> None:
    black_human = {"human_sides": ["black"]}
    sandbox = {"human_sides": ["white", "black"]}
    agent_only = {"human_sides": []}

    assert ui_text.board_hint_text(black_human) == "Board: black view"
    assert ui_text.files_text(black_human) == "Files: h g f e d c b a"
    assert ui_text.ranks_text(black_human) == "Ranks: 8 7 6 5 4 3 2 1"

    assert ui_text.board_hint_text(sandbox) == "Board: sandbox white view"
    assert ui_text.files_text(sandbox) == "Files: a b c d e f g h"
    assert ui_text.ranks_text(sandbox) == "Ranks: 1 2 3 4 5 6 7 8"

    assert ui_text.board_hint_text(agent_only) == "Board: default white view"


def test_hud_status_text_formats_game_over_results() -> None:
    checkmate = {"status": "checkmate:white", "game_over": True}
    stalemate = {"status": "stalemate", "game_over": True}
    insufficient = {"status": "draw:insufficient_material", "game_over": True}
    selection = {
        "status": "playing",
        "game_over": False,
        "selection_hint": "Promotion: choose target square, then pick a piece.",
    }
    promotion = {
        "status": "playing",
        "game_over": False,
        "pending_promotion": {
            "pending": True,
            "from": "e7",
            "to": "e8",
            "choices": [],
        },
    }

    assert ui_text.status_text(checkmate) == "Checkmate! White wins!"
    assert ui_text.status_text(stalemate) == "Stalemate! Draw."
    assert ui_text.status_text(insufficient) == "Draw: insufficient material"
    assert ui_text.status_text(selection) == "Promotion: choose target square, then pick a piece."
    assert ui_text.status_text(promotion) == "Promote e7-e8"


def test_copy_pgn_uses_controller_pgn_payload() -> None:
    class FakeController:
        def get_pgn(self) -> str:
            return "1. e4 e5 *"

    copied: list[tuple[str, str]] = []
    component = ChessUIComponent.__new__(ChessUIComponent)
    component._game_controller = FakeController()
    component._copy_text = lambda label, text: copied.append((label, text))

    component._on_copy_pgn()

    assert copied == [("PGN", "1. e4 e5 *")]


def test_agent_memo_contains_connection_and_conduct_hints() -> None:
    info = {
        "url": "http://127.0.0.1:8790/mcp",
        "session_file": "/tmp/chess-game-mcp.json",
        "mode": "human_vs_agent",
        "active_mcp_sides": ["black"],
    }
    seat = {
        "side": "black",
        "token": "black-token",
        "authorization": "Bearer black-token",
    }

    memo = ui_text.agent_memo_text(info, seat)

    assert "Endpoint URL: http://127.0.0.1:8790/mcp" in memo
    assert "Authorization header: Bearer black-token" in memo
    assert "Your side: black" in memo
    assert "Do not ask the user/operator to choose moves for you." in memo
    assert "Do not use external tools" in memo
    assert "wait_for_move" in memo
    assert "new_game" in memo


def test_agent_memo_button_label_says_copy_paste_to_agent() -> None:
    white = {"side": "white"}
    black = {"side": "black"}

    assert ui_text.agent_memo_button_label(black, [black]) == "Copy & Paste to Your Agent"
    assert ui_text.agent_memo_button_label(white, [white, black]) == "Copy & Paste to White Agent"
    assert ui_text.agent_memo_button_label(black, [white, black]) == "Copy & Paste to Black Agent"


def test_clipboard_commands_include_windows_backends() -> None:
    commands = ChessUIComponent._clipboard_commands("win32")

    assert commands[0] == ["clip.exe"]
    assert ["powershell.exe", "-NoProfile", "-Command", "Set-Clipboard"] in commands
    assert ["pwsh.exe", "-NoProfile", "-Command", "Set-Clipboard"] in commands


def test_clipboard_commands_keep_linux_backends() -> None:
    assert ChessUIComponent._clipboard_commands("linux") == [
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]
