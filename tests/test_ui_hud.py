from __future__ import annotations

import sys
import types

from conftest import load_script_module


def load_ui_module():
    termin_pkg = types.ModuleType("termin")
    termin_pkg.__path__ = []
    sys.modules["termin"] = termin_pkg

    visualization_pkg = types.ModuleType("termin.visualization")
    visualization_pkg.__path__ = []
    sys.modules["termin.visualization"] = visualization_pkg

    ui_pkg = types.ModuleType("termin.visualization.ui")
    ui_pkg.__path__ = []
    sys.modules["termin.visualization.ui"] = ui_pkg

    widgets_pkg = types.ModuleType("termin.visualization.ui.widgets")
    widgets_pkg.__path__ = []
    sys.modules["termin.visualization.ui.widgets"] = widgets_pkg

    component_module = types.ModuleType("termin.visualization.ui.widgets.component")

    class UIComponent:
        def __init__(self, *, priority: int = 0) -> None:
            self.priority = priority

        def start(self) -> None:
            return None

    component_module.UIComponent = UIComponent
    sys.modules["termin.visualization.ui.widgets.component"] = component_module

    tcgui_pkg = types.ModuleType("tcgui")
    tcgui_pkg.__path__ = []
    sys.modules["tcgui"] = tcgui_pkg

    tcgui_widgets = types.ModuleType("tcgui.widgets")

    class Widget:
        def __init__(self) -> None:
            self.children = []

        def add_child(self, child: object) -> None:
            self.children.append(child)

    class Button(Widget):
        pass

    class Label(Widget):
        pass

    class Panel(Widget):
        pass

    class Separator(Widget):
        pass

    class VStack(Widget):
        pass

    def px(value: int) -> int:
        return value

    tcgui_widgets.Button = Button
    tcgui_widgets.Label = Label
    tcgui_widgets.Panel = Panel
    tcgui_widgets.Separator = Separator
    tcgui_widgets.VStack = VStack
    tcgui_widgets.px = px
    sys.modules["tcgui.widgets"] = tcgui_widgets

    return load_script_module("chess_ui_component_under_test", "ChessUIComponent.py")


ui_module = load_ui_module()
ChessUIComponent = ui_module.ChessUIComponent


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

    assert ChessUIComponent._owners_text(info) == "White: human | Black: agent"
    assert ChessUIComponent._turn_text(info) == "Black to move (agent:black)"
    assert ChessUIComponent._status_text(info) == "Check!"
    assert ChessUIComponent._last_move_text(info) == "Last move: e4 by human"
    assert ChessUIComponent._captures_text(info) == "Captured W: Px2 | B: R"
    assert ChessUIComponent._board_hint_text(info) == "Board: white view"
    assert ChessUIComponent._files_text(info) == "Files: a b c d e f g h"
    assert ChessUIComponent._ranks_text(info) == "Ranks: 1 2 3 4 5 6 7 8"


def test_hud_coordinate_helpers_follow_local_player_orientation() -> None:
    black_human = {"human_sides": ["black"]}
    sandbox = {"human_sides": ["white", "black"]}
    agent_only = {"human_sides": []}

    assert ChessUIComponent._board_hint_text(black_human) == "Board: black view"
    assert ChessUIComponent._files_text(black_human) == "Files: h g f e d c b a"
    assert ChessUIComponent._ranks_text(black_human) == "Ranks: 8 7 6 5 4 3 2 1"

    assert ChessUIComponent._board_hint_text(sandbox) == "Board: sandbox white view"
    assert ChessUIComponent._files_text(sandbox) == "Files: a b c d e f g h"
    assert ChessUIComponent._ranks_text(sandbox) == "Ranks: 1 2 3 4 5 6 7 8"

    assert ChessUIComponent._board_hint_text(agent_only) == "Board: default white view"


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

    assert ChessUIComponent._status_text(checkmate) == "Checkmate! White wins!"
    assert ChessUIComponent._status_text(stalemate) == "Stalemate! Draw."
    assert ChessUIComponent._status_text(insufficient) == "Draw: insufficient material"
    assert ChessUIComponent._status_text(selection) == "Promotion: choose target square, then pick a piece."
    assert ChessUIComponent._status_text(promotion) == "Promote e7-e8"


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
