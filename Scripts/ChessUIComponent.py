"""Chess game UI panel — buttons and status display."""

from __future__ import annotations

import subprocess

from termin.visualization.ui.widgets.component import UIComponent
from termin.visualization.ui.widgets.containers import Panel, VStack
from termin.visualization.ui.widgets.basic import Button, Label, Separator
from termin.visualization.ui.widgets.units import px, pct

print("[ChessUI] ChessUIComponent module loaded.")


class ChessUIComponent(UIComponent):

    def __init__(self):
        print("[ChessUI] ChessUIComponent.__init__()")
        super().__init__(priority=100)
        self._status_label: Label | None = None
        self._turn_label: Label | None = None
        self._game_controller = None

    def start(self) -> None:
        print("[ChessUI] start() called")
        super().start()
        self._find_game_controller()
        self._build_ui()
        print("[ChessUI] UI built successfully")

    def _find_game_controller(self):
        from Scripts.ChessGameController import ChessGameController
        scene = self.entity.scene
        comps = scene.get_components_of_type("ChessGameController")
        if comps:
            self._game_controller = comps[0]
            print(f"[ChessUI] Found ChessGameController")
        else:
            print("[ChessUI] WARNING: ChessGameController not found in scene!")

    def _build_ui(self):
        # Root panel — right side of screen
        root_panel = Panel()
        root_panel.anchor = "top-right"
        root_panel.offset_x = -10
        root_panel.offset_y = 10
        root_panel.preferred_width = px(200)
        root_panel.padding = 12
        root_panel.background_color = (0.12, 0.12, 0.15, 0.85)
        root_panel.border_radius = 8

        # Vertical stack for content
        stack = VStack()
        stack.spacing = 8
        stack.alignment = "center"
        stack.preferred_width = px(176)

        # Title
        title = Label()
        title.text = "Chess"
        title.font_size = 20
        title.color = (1.0, 1.0, 1.0, 1.0)
        title.alignment = "center"
        title.preferred_width = px(176)
        title.preferred_height = px(28)
        stack.add_child(title)

        # Separator
        sep1 = Separator()
        sep1.orientation = "horizontal"
        sep1.color = (0.4, 0.4, 0.5, 0.6)
        sep1.preferred_width = px(176)
        stack.add_child(sep1)

        # Turn label
        self._turn_label = Label()
        self._turn_label.text = "White to move"
        self._turn_label.font_size = 14
        self._turn_label.color = (0.9, 0.9, 0.8, 1.0)
        self._turn_label.alignment = "center"
        self._turn_label.preferred_width = px(176)
        self._turn_label.preferred_height = px(20)
        stack.add_child(self._turn_label)

        # Status label (check, checkmate, etc.)
        self._status_label = Label()
        self._status_label.text = ""
        self._status_label.font_size = 13
        self._status_label.color = (1.0, 0.6, 0.2, 1.0)
        self._status_label.alignment = "center"
        self._status_label.preferred_width = px(176)
        self._status_label.preferred_height = px(18)
        stack.add_child(self._status_label)

        # Separator
        sep2 = Separator()
        sep2.orientation = "horizontal"
        sep2.color = (0.4, 0.4, 0.5, 0.6)
        sep2.preferred_width = px(176)
        stack.add_child(sep2)

        # New Game button
        btn_new = self._make_button("New Game", self._on_new_game)
        stack.add_child(btn_new)

        # Copy FEN button
        btn_fen = self._make_button("Copy FEN", self._on_copy_fen)
        stack.add_child(btn_fen)

        # Separator
        sep3 = Separator()
        sep3.orientation = "horizontal"
        sep3.color = (0.4, 0.4, 0.5, 0.6)
        sep3.preferred_width = px(176)
        stack.add_child(sep3)

        # Exit button
        btn_exit = self._make_button("Exit", self._on_exit)
        btn_exit.background_color = (0.5, 0.15, 0.15, 1.0)
        btn_exit.hover_color = (0.65, 0.2, 0.2, 1.0)
        btn_exit.pressed_color = (0.4, 0.1, 0.1, 1.0)
        stack.add_child(btn_exit)

        root_panel.add_child(stack)
        self.root = root_panel
        print("[ChessUI] Root widget set")

    @staticmethod
    def _make_button(text: str, callback) -> Button:
        btn = Button()
        btn.text = text
        btn.font_size = 14
        btn.preferred_width = px(176)
        btn.preferred_height = px(34)
        btn.border_radius = 5
        btn.background_color = (0.25, 0.28, 0.35, 1.0)
        btn.hover_color = (0.35, 0.38, 0.48, 1.0)
        btn.pressed_color = (0.18, 0.2, 0.25, 1.0)
        btn.text_color = (1.0, 1.0, 1.0, 1.0)
        btn.on_click = callback
        return btn

    # --- Button callbacks ---

    def _on_new_game(self):
        print("[ChessUI] 'New Game' clicked")
        if self._game_controller is not None:
            self._game_controller.new_game()
            self._update_status()
        else:
            print("[ChessUI] No game controller found!")

    def _on_copy_fen(self):
        print("[ChessUI] 'Copy FEN' clicked")
        if self._game_controller is None:
            print("[ChessUI] No game controller!")
            return

        fen = self._game_controller.get_fen()
        print(f"[ChessUI] FEN: {fen}")

        try:
            proc = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=fen.encode("utf-8"))
            print("[ChessUI] FEN copied to clipboard (xclip)")
        except FileNotFoundError:
            try:
                proc = subprocess.Popen(
                    ["xsel", "--clipboard", "--input"],
                    stdin=subprocess.PIPE,
                )
                proc.communicate(input=fen.encode("utf-8"))
                print("[ChessUI] FEN copied to clipboard (xsel)")
            except FileNotFoundError:
                print("[ChessUI] WARNING: xclip/xsel not found, cannot copy to clipboard")

    def _on_exit(self):
        print("[ChessUI] 'Exit' clicked")
        import sys
        sys.exit(0)

    # --- Status update (called by game controller) ---

    def update_status(self, turn_text: str, status_text: str = ""):
        """Update displayed status labels."""
        if self._turn_label is not None:
            self._turn_label.text = turn_text
        if self._status_label is not None:
            self._status_label.text = status_text
            if "checkmate" in status_text.lower() or "stalemate" in status_text.lower():
                self._status_label.color = (1.0, 0.3, 0.3, 1.0)
            elif "check" in status_text.lower():
                self._status_label.color = (1.0, 0.6, 0.2, 1.0)
            else:
                self._status_label.color = (0.7, 0.7, 0.7, 1.0)

    def _update_status(self):
        """Pull status from game controller."""
        if self._game_controller is None:
            return
        board = self._game_controller.get_board()
        if board is None:
            return

        turn = "White to move" if board.turn else "Black to move"

        status = ""
        if board.is_checkmate():
            winner = "Black wins!" if board.turn else "White wins!"
            status = f"Checkmate! {winner}"
        elif board.is_stalemate():
            status = "Stalemate! Draw."
        elif board.is_check():
            status = "Check!"

        self.update_status(turn, status)
