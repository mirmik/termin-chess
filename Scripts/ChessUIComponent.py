"""Chess game UI panel — buttons and status display."""

from __future__ import annotations

import logging
import subprocess
import sys

from termin.scene import PythonComponent
from termin.ui_components import UIComponent
from termin.gui_native import (
    Button, Label, VStack, CrossAxisAlignment, EdgeInsets, LayoutPolicy,
    OverlayAnchor, Point, Size, SrgbColor, StyleField, StyleOverride,
    UiDocumentAsset,
)

from Scripts import chess_ui_text as ui_text

log = logging.getLogger(__name__)
log.debug("[ChessUI] ChessUIComponent module loaded.")


class ChessUIComponent(PythonComponent):

    def __init__(self):
        log.debug("[ChessUI] ChessUIComponent.__init__()")
        super().__init__()
        self._ui = None
        self._layout_dirty = False
        self._status_label: Label | None = None
        self._turn_label: Label | None = None
        self._mode_label: Label | None = None
        self._owners_label: Label | None = None
        self._last_move_label: Label | None = None
        self._captures_label: Label | None = None
        self._board_hint_label: Label | None = None
        self._files_label: Label | None = None
        self._ranks_label: Label | None = None
        self._connection_labels: dict[str, Label] = {}
        self._promotion_panel_visible = False
        self._game_controller = None

    def start(self) -> None:
        log.info("[ChessUI] start() called")
        super().start()
        self._find_game_controller()
        self._rebuild_ui()
        log.info("[ChessUI] UI built successfully")

    def on_destroy(self) -> None:
        self._game_controller = None
        self._ui = None
        self._document = None
        self._overlay = None
        self._connection_labels.clear()
        for field in ("status", "turn", "mode", "owners", "last_move", "captures",
                      "board_hint", "files", "ranks"):
            setattr(self, f"_{field}_label", None)

    def _find_game_controller(self):
        scene = self.entity.scene
        comps = scene.get_components_of_type("ChessGameController")
        if comps:
            self._game_controller = comps[0]
            log.info("[ChessUI] Found ChessGameController")
        else:
            log.warning("[ChessUI] ChessGameController not found in scene")

    def _build_ui(self):
        # Button callbacks run inside native input dispatch. Rebuild next frame,
        # after the widget that owns the callback has finished dispatching.
        self._layout_dirty = True

    def update(self, dt: float) -> None:
        if self._layout_dirty:
            self._rebuild_ui()
            self._update_status()

    def _rebuild_ui(self):
        self._layout_dirty = False
        if self._ui is None:
            self._ui = self.entity.get_component(UIComponent)
            if self._ui is None:
                self._ui = UIComponent(priority=100)
                self.entity.add_component(self._ui)
            asset = UiDocumentAsset.declare_source(
                "chess-runtime-ui", "Chess UI", "chess-runtime-ui.uiscript",
                "uiscript: 2\nroot: {type: termin.gui.OverlayLayout}\n",
            )
            self._ui.ui_layout = asset
        self._document = self._ui.document
        while self._document.root_count:
            self._document.destroy_widget_recursive(self._document.root_at(0))
        self._overlay = self._document.create_overlay_layout()
        self._overlay.widget.mouse_transparent = True
        self._document.add_root(self._overlay.handle)
        for field in ("status", "turn", "mode", "owners", "last_move", "captures",
                      "board_hint", "files", "ranks"):
            setattr(self, f"_{field}_label", None)
        self._connection_labels = {}
        self._promotion_panel_visible = False
        if self._game_controller is not None and self._game_controller.is_start_menu_visible():
            self._build_start_menu()
        else:
            self._build_game_panel()

    def _stack(self, width: int, *, padding: int = 0) -> VStack:
        stack = self._document.create_vstack()
        stack.set_spacing(8)
        stack.set_padding(EdgeInsets(padding, padding, padding, padding))
        stack.set_cross_axis_alignment(CrossAxisAlignment.Center)
        stack.preferred_size = Size(width, 0)
        return stack

    @staticmethod
    def _add(stack: VStack, child) -> None:
        stack.add_child(child.widget, LayoutPolicy.Preferred)

    def _separator(self, stack: VStack, width: int) -> None:
        separator = self._document.create_separator()
        separator.set_color(SrgbColor(0.4, 0.4, 0.5, 0.6))
        separator.preferred_size = Size(width, 2)
        self._add(stack, separator)

    def _mount_panel(self, stack: VStack, *, centered: bool = False) -> None:
        stack.set_background(SrgbColor(0.12, 0.12, 0.15, 0.94))
        stack.set_corner_radius(8)
        # The MCP panel can exceed the viewport height. Keep every action reachable.
        scroll = self._document.create_scroll_area()
        scroll.set_content(stack.widget)
        scroll.widget.preferred_size = Size(stack.preferred_size.width + 16, 260 if centered else 680)
        if centered:
            row = self._document.create_hstack()
            row.set_cross_axis_alignment(CrossAxisAlignment.Center)
            left = self._document.create_spacer(Size())
            right = self._document.create_spacer(Size())
            row.add_child(left.widget, LayoutPolicy.Flex, 1)
            row.add_child(scroll.widget, LayoutPolicy.Preferred)
            row.add_child(right.widget, LayoutPolicy.Flex, 1)
            self._overlay.add_child(row.widget, OverlayAnchor.Fill)
        else:
            self._overlay.add_child(scroll.widget, OverlayAnchor.TopRight, Point(-10, 10))

    def _build_start_menu(self):
        stack = self._stack(300, padding=16)
        self._add(stack, self._make_info_label("Chess", width=268, font_size=26))
        self._separator(stack, 268)
        for text, callback in (
            ("Start Game With Agent", self._on_start_human_vs_agent),
            ("Start Two-Agent Game", self._on_start_agent_vs_agent),
            ("Local Sandbox", self._on_start_local_sandbox),
            ("Quit", self._on_exit),
        ):
            self._add(stack, self._make_button(text, callback, width=268))
        self._mount_panel(stack, centered=True)

    def _build_game_panel(self):
        connection_info = self._connection_info()
        width = 296 if connection_info["ok"] else 240
        stack = self._stack(width + 24, padding=12)
        self._add(stack, self._make_info_label("Chess", width=width, font_size=20))
        for field, text in (
            ("mode", self._mode_text()), ("owners", ""), ("turn", "White to move"),
            ("status", ""), ("last_move", "Last move: none"), ("captures", "Captured: none"),
            ("board_hint", "Board: white view"), ("files", "Files: a b c d e f g h"),
            ("ranks", "Ranks: 1 2 3 4 5 6 7 8"),
        ):
            label = self._make_info_label(text, width=width)
            setattr(self, f"_{field}_label", label)
            self._add(stack, label)
        promotion_info = self._promotion_info()
        if promotion_info["pending"]:
            self._promotion_panel_visible = True
            self._add_promotion_section(stack, promotion_info, width)
        self._separator(stack, width)
        if connection_info["ok"]:
            self._add_connection_section(stack, connection_info, width)
        for text, callback in (
            ("New Game", self._on_new_game), ("Copy FEN", self._on_copy_fen),
            ("Copy PGN", self._on_copy_pgn), ("Return to Menu", self._on_return_to_menu),
            ("Exit", self._on_exit),
        ):
            self._add(stack, self._make_button(text, callback, width=width))
        self._mount_panel(stack)

    def _add_connection_section(self, stack: VStack, info: dict[str, object], width: int) -> None:
        title = self._make_info_label("MCP Connection", width=width, font_size=14)
        title.set_color(SrgbColor(0.92, 0.95, 1.0, 1.0))
        self._add(stack, title)

        active_seats = ui_text.seat_payloads(info)
        if active_seats:
            agent_memo_title = self._make_info_label("Agent Mnemo:", width=width, font_size=13)
            agent_memo_title.set_color(SrgbColor(1.0, 0.78, 0.36, 1.0))
            self._add(stack, agent_memo_title)
        for seat in active_seats:
            memo_button = self._make_button(
                ui_text.agent_memo_button_label(seat, active_seats),
                lambda seat_payload=seat: self._copy_text(
                    f"{str(seat_payload['side'])} agent memo",
                    ui_text.agent_memo_text(info, seat_payload),
                ),
                width=width,
            )
            self._style_agent_memo_button(memo_button)
            self._add(stack, memo_button)

        url = str(info["url"])
        session_file = str(info["session_file"])
        self._connection_labels["endpoint"] = self._make_info_label(f"URL: {url}", width=width)
        self._add(stack, self._connection_labels["endpoint"])
        self._add(stack, self._make_button("Copy URL", lambda value=url: self._copy_text("MCP URL", value), width=width))

        self._connection_labels["session_file"] = self._make_info_label(
            f"Session: {ui_text.short_path(session_file)}",
            width=width,
        )
        self._add(stack, self._connection_labels["session_file"])
        self._add(stack,
            self._make_button(
                "Copy Session File",
                lambda value=session_file: self._copy_text("MCP session file", value),
                width=width,
            )
        )

        self._connection_labels["connection_turn"] = self._make_info_label("", width=width)
        self._add(stack, self._connection_labels["connection_turn"])
        self._connection_labels["last_event"] = self._make_info_label("", width=width)
        self._add(stack, self._connection_labels["last_event"])

        for seat in active_seats:
            side = str(seat["side"])
            label = self._make_info_label("", width=width)
            self._connection_labels[f"{side}_status"] = label
            self._add(stack, label)
            token = str(seat["token"])
            self._add(stack,
                self._make_button(
                    f"Copy {side.title()} Token",
                    lambda seat_side=side, value=token: self._copy_text(f"{seat_side} token", value),
                    width=width,
                )
            )

        self._refresh_connection_info()

    def _make_info_label(self, text: str, *, width: int, font_size: int = 12) -> Label:
        label = self._document.create_label(text)
        label.set_font_size(font_size)
        label.set_color(SrgbColor(0.78, 0.80, 0.86, 1.0))
        label.preferred_size = Size(width, max(18, font_size + 8))
        return label

    def _make_button(self, text: str, callback, *, width: int = 176) -> Button:
        button = self._document.create_button(text, debug_name=text)
        button.widget.preferred_size = Size(width, 34)
        button.connect_clicked(callback)
        return button

    @staticmethod
    def _style_agent_memo_button(button: Button) -> None:
        style = StyleOverride()
        style.fields = StyleField.Background | StyleField.Foreground | StyleField.FontSize
        style.value.background = SrgbColor(0.82, 0.50, 0.12, 1.0)
        style.value.foreground = SrgbColor(0.08, 0.06, 0.04, 1.0)
        style.value.font_size = 15
        button.widget.style_override = style

    def _add_promotion_section(self, stack: VStack, info: dict[str, object], width: int) -> None:
        title = self._make_info_label(ui_text.promotion_title(info), width=width, font_size=13)
        title.set_color(SrgbColor(1.0, 0.82, 0.36, 1.0))
        self._add(stack, title)

        for choice in ui_text.promotion_choices(info):
            piece = str(choice["piece"])
            label = str(choice["label"])
            self._add(stack,
                self._make_button(
                    f"Promote: {label}",
                    lambda value=piece: self._on_choose_promotion(value),
                    width=width,
                )
            )

        cancel = self._make_button("Cancel Promotion", self._on_cancel_promotion, width=width)
        self._add(stack, cancel)

    # --- Button callbacks ---

    def _on_start_human_vs_agent(self):
        log.info("[ChessUI] 'Start Game With Agent' clicked")
        if self._game_controller is not None:
            self._game_controller.start_human_vs_agent()
            self._build_ui()
            self._update_status()
        else:
            log.warning("[ChessUI] No game controller found")

    def _on_start_agent_vs_agent(self):
        log.info("[ChessUI] 'Start Two-Agent Game' clicked")
        if self._game_controller is not None:
            self._game_controller.start_agent_vs_agent()
            self._build_ui()
            self._update_status()
        else:
            log.warning("[ChessUI] No game controller found")

    def _on_start_local_sandbox(self):
        log.info("[ChessUI] 'Local Sandbox' clicked")
        if self._game_controller is not None:
            self._game_controller.start_local_sandbox()
            self._build_ui()
            self._update_status()
        else:
            log.warning("[ChessUI] No game controller found")

    def _on_new_game(self):
        log.info("[ChessUI] 'New Game' clicked")
        if self._game_controller is not None:
            self._game_controller.new_game()
            self._update_status()
        else:
            log.warning("[ChessUI] No game controller found")

    def _on_return_to_menu(self):
        log.info("[ChessUI] 'Return to Menu' clicked")
        if self._game_controller is not None:
            self._game_controller.return_to_start_menu()
            self._build_ui()
        else:
            log.warning("[ChessUI] No game controller found")

    def _on_copy_fen(self):
        log.info("[ChessUI] 'Copy FEN' clicked")
        if self._game_controller is None:
            log.warning("[ChessUI] No game controller")
            return

        fen = self._game_controller.get_fen()
        log.debug("[ChessUI] FEN: %s", fen)
        self._copy_text("FEN", fen)

    def _on_copy_pgn(self):
        log.info("[ChessUI] 'Copy PGN' clicked")
        if self._game_controller is None:
            log.warning("[ChessUI] No game controller")
            return

        pgn = self._game_controller.get_pgn()
        log.debug("[ChessUI] PGN:\n%s", pgn)
        self._copy_text("PGN", pgn)

    def _on_choose_promotion(self, piece_name: str):
        log.info("[ChessUI] promotion choice clicked: %s", piece_name)
        if self._game_controller is None:
            log.warning("[ChessUI] No game controller")
            return
        self._game_controller.choose_promotion(piece_name)
        self._build_ui()
        self._update_status()

    def _on_cancel_promotion(self):
        log.info("[ChessUI] promotion cancelled")
        if self._game_controller is None:
            log.warning("[ChessUI] No game controller")
            return
        self._game_controller.cancel_promotion()
        self._build_ui()
        self._update_status()

    def _copy_text(self, label: str, text: str) -> None:
        for command in self._clipboard_commands():
            try:
                subprocess.run(
                    command,
                    input=text,
                    text=True,
                    check=True,
                )
                log.info("[ChessUI] %s copied to clipboard (%s)", label, command[0])
                return
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                log.debug("[ChessUI] clipboard command failed for %s: %s (%s)", label, command[0], exc)
        names = "/".join(command[0] for command in self._clipboard_commands())
        log.warning("[ChessUI] %s not found or failed, cannot copy %s to clipboard", names, label)

    @staticmethod
    def _clipboard_commands(platform: str | None = None) -> list[list[str]]:
        current_platform = sys.platform if platform is None else platform
        if current_platform.startswith("win"):
            return [
                ["clip.exe"],
                ["powershell.exe", "-NoProfile", "-Command", "Set-Clipboard"],
                ["pwsh.exe", "-NoProfile", "-Command", "Set-Clipboard"],
            ]
        if current_platform == "darwin":
            return [["pbcopy"]]
        return [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]

    def _on_exit(self):
        log.info("[ChessUI] 'Exit' clicked")
        from termin.player import request_quit
        if not request_quit(0):
            log.info("[ChessUI] Player runtime is not active; exit request ignored")

    # --- Status update (called by game controller) ---

    def update_status(self, turn_text: str, status_text: str = ""):
        """Update displayed status labels."""
        if self._promotion_layout_changed():
            self._build_ui()
        if self._mode_label is not None:
            self._mode_label.text = self._mode_text()
        hud_refreshed = self._refresh_hud_info()
        self._refresh_connection_info()
        if not hud_refreshed:
            if self._turn_label is not None:
                self._turn_label.text = turn_text
            if self._status_label is not None:
                self._status_label.text = status_text
                self._apply_status_color(status_text)

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

    def _mode_text(self) -> str:
        if self._game_controller is None:
            return "Mode: unknown"
        mode = self._game_controller.current_mode().replace("_", " ")
        return f"Mode: {mode}"

    def _connection_info(self) -> dict[str, object]:
        if self._game_controller is None:
            return {"ok": False, "error": "No game controller"}
        return self._game_controller.get_connection_panel_info()

    def _game_state_info(self) -> dict[str, object]:
        if self._game_controller is None:
            return {"ok": False, "error": "No game controller"}
        return self._game_controller.get_game_state()

    def _promotion_info(self) -> dict[str, object]:
        if self._game_controller is None:
            return {"pending": False}
        return self._game_controller.get_pending_promotion_info()

    def _promotion_layout_changed(self) -> bool:
        pending = bool(self._promotion_info()["pending"])
        return pending != self._promotion_panel_visible

    def _refresh_hud_info(self) -> bool:
        if self._turn_label is None or self._status_label is None:
            return False
        info = self._game_state_info()
        if not info["ok"]:
            return False

        self._turn_label.text = ui_text.turn_text(info)
        status_text = ui_text.status_text(info)
        self._status_label.text = status_text
        self._apply_status_color(status_text)
        if self._owners_label is not None:
            self._owners_label.text = ui_text.owners_text(info)
        if self._last_move_label is not None:
            self._last_move_label.text = ui_text.last_move_text(info)
        if self._captures_label is not None:
            self._captures_label.text = ui_text.captures_text(info)
        if self._board_hint_label is not None:
            self._board_hint_label.text = ui_text.board_hint_text(info)
        if self._files_label is not None:
            self._files_label.text = ui_text.files_text(info)
        if self._ranks_label is not None:
            self._ranks_label.text = ui_text.ranks_text(info)
        return True

    def _refresh_connection_info(self) -> None:
        if not self._connection_labels:
            return
        info = self._connection_info()
        if not info["ok"]:
            return

        turn = str(info["turn"]).title()
        status = str(info["status"])
        self._connection_labels["connection_turn"].text = f"Turn: {turn} / {status}"
        self._connection_labels["last_event"].text = ui_text.last_event_text(info)
        for seat in ui_text.seat_payloads(info):
            side = str(seat["side"])
            key = f"{side}_status"
            if key in self._connection_labels:
                self._connection_labels[key].text = ui_text.seat_status_text(seat)

    def _apply_status_color(self, status_text: str) -> None:
        if self._status_label is None:
            return
        if "checkmate" in status_text.lower() or "stalemate" in status_text.lower() or "draw:" in status_text.lower():
            self._status_label.set_color(SrgbColor(1.0, 0.3, 0.3, 1.0))
        elif "check" in status_text.lower():
            self._status_label.set_color(SrgbColor(1.0, 0.6, 0.2, 1.0))
        else:
            self._status_label.set_color(SrgbColor(0.7, 0.7, 0.7, 1.0))
