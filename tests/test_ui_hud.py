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
        "last_move": {"type": "move", "san": "e4", "actor": "human"},
    }

    assert ChessUIComponent._owners_text(info) == "White: human | Black: agent"
    assert ChessUIComponent._turn_text(info) == "Black to move (agent:black)"
    assert ChessUIComponent._status_text(info) == "Check!"
    assert ChessUIComponent._last_move_text(info) == "Last move: e4 by human"


def test_hud_status_text_formats_game_over_results() -> None:
    checkmate = {"status": "checkmate:white", "game_over": True}
    stalemate = {"status": "stalemate", "game_over": True}
    insufficient = {"status": "draw:insufficient_material", "game_over": True}

    assert ChessUIComponent._status_text(checkmate) == "Checkmate! White wins!"
    assert ChessUIComponent._status_text(stalemate) == "Stalemate! Draw."
    assert ChessUIComponent._status_text(insufficient) == "Draw: insufficient material"


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
