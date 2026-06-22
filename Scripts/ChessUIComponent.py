"""Chess game UI panel — buttons and status display."""

from __future__ import annotations

import subprocess
import sys

from termin.ui_components import UIComponent
from tcgui.widgets import Button, Label, Panel, Separator, VStack, px

print("[ChessUI] ChessUIComponent module loaded.")


class ChessUIComponent(UIComponent):

    def __init__(self):
        print("[ChessUI] ChessUIComponent.__init__()")
        super().__init__(priority=100)
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
        self._status_label = None
        self._turn_label = None
        self._mode_label = None
        self._owners_label = None
        self._last_move_label = None
        self._captures_label = None
        self._board_hint_label = None
        self._files_label = None
        self._ranks_label = None
        self._connection_labels = {}
        self._promotion_panel_visible = False
        if self._game_controller is not None and self._game_controller.is_start_menu_visible():
            self._build_start_menu()
            return
        self._build_game_panel()

    def _build_start_menu(self):
        root_panel = Panel()
        root_panel.anchor = "center"
        root_panel.preferred_width = px(300)
        root_panel.padding = 16
        root_panel.background_color = (0.10, 0.11, 0.14, 0.92)
        root_panel.border_radius = 8

        stack = VStack()
        stack.spacing = 10
        stack.alignment = "center"
        stack.preferred_width = px(268)

        title = Label()
        title.text = "Chess"
        title.font_size = 26
        title.color = (1.0, 1.0, 1.0, 1.0)
        title.alignment = "center"
        title.preferred_width = px(268)
        title.preferred_height = px(34)
        stack.add_child(title)

        sep = Separator()
        sep.orientation = "horizontal"
        sep.color = (0.4, 0.4, 0.5, 0.65)
        sep.preferred_width = px(268)
        stack.add_child(sep)

        stack.add_child(self._make_button("Start Game With Agent", self._on_start_human_vs_agent, width=268))
        stack.add_child(self._make_button("Start Two-Agent Game", self._on_start_agent_vs_agent, width=268))
        stack.add_child(self._make_button("Local Sandbox", self._on_start_local_sandbox, width=268))

        sep2 = Separator()
        sep2.orientation = "horizontal"
        sep2.color = (0.4, 0.4, 0.5, 0.65)
        sep2.preferred_width = px(268)
        stack.add_child(sep2)

        btn_exit = self._make_button("Quit", self._on_exit, width=268)
        btn_exit.background_color = (0.5, 0.15, 0.15, 1.0)
        btn_exit.hover_color = (0.65, 0.2, 0.2, 1.0)
        btn_exit.pressed_color = (0.4, 0.1, 0.1, 1.0)
        stack.add_child(btn_exit)

        root_panel.add_child(stack)
        self.root = root_panel
        print("[ChessUI] Start menu root widget set")

    def _build_game_panel(self):
        # Root panel — right side of screen
        connection_info = self._connection_info()
        content_width = 296 if connection_info["ok"] else 176
        root_panel = Panel()
        root_panel.anchor = "top-right"
        root_panel.offset_x = -10
        root_panel.offset_y = 10
        root_panel.preferred_width = px(content_width + 24)
        root_panel.padding = 12
        root_panel.background_color = (0.12, 0.12, 0.15, 0.85)
        root_panel.border_radius = 8

        # Vertical stack for content
        stack = VStack()
        stack.spacing = 8
        stack.alignment = "center"
        stack.preferred_width = px(content_width)

        # Title
        title = Label()
        title.text = "Chess"
        title.font_size = 20
        title.color = (1.0, 1.0, 1.0, 1.0)
        title.alignment = "center"
        title.preferred_width = px(content_width)
        title.preferred_height = px(28)
        stack.add_child(title)

        # Separator
        sep1 = Separator()
        sep1.orientation = "horizontal"
        sep1.color = (0.4, 0.4, 0.5, 0.6)
        sep1.preferred_width = px(content_width)
        stack.add_child(sep1)

        self._mode_label = Label()
        self._mode_label.text = self._mode_text()
        self._mode_label.font_size = 12
        self._mode_label.color = (0.72, 0.78, 0.88, 1.0)
        self._mode_label.alignment = "center"
        self._mode_label.preferred_width = px(content_width)
        self._mode_label.preferred_height = px(18)
        stack.add_child(self._mode_label)

        self._owners_label = Label()
        self._owners_label.text = ""
        self._owners_label.font_size = 12
        self._owners_label.color = (0.78, 0.80, 0.86, 1.0)
        self._owners_label.alignment = "center"
        self._owners_label.preferred_width = px(content_width)
        self._owners_label.preferred_height = px(18)
        stack.add_child(self._owners_label)

        # Turn label
        self._turn_label = Label()
        self._turn_label.text = "White to move"
        self._turn_label.font_size = 14
        self._turn_label.color = (0.9, 0.9, 0.8, 1.0)
        self._turn_label.alignment = "center"
        self._turn_label.preferred_width = px(content_width)
        self._turn_label.preferred_height = px(20)
        stack.add_child(self._turn_label)

        # Status label (check, checkmate, etc.)
        self._status_label = Label()
        self._status_label.text = ""
        self._status_label.font_size = 13
        self._status_label.color = (1.0, 0.6, 0.2, 1.0)
        self._status_label.alignment = "center"
        self._status_label.preferred_width = px(content_width)
        self._status_label.preferred_height = px(18)
        stack.add_child(self._status_label)

        self._last_move_label = Label()
        self._last_move_label.text = "Last move: none"
        self._last_move_label.font_size = 12
        self._last_move_label.color = (0.72, 0.74, 0.80, 1.0)
        self._last_move_label.alignment = "center"
        self._last_move_label.preferred_width = px(content_width)
        self._last_move_label.preferred_height = px(18)
        stack.add_child(self._last_move_label)

        self._captures_label = Label()
        self._captures_label.text = "Captured: none"
        self._captures_label.font_size = 12
        self._captures_label.color = (0.72, 0.74, 0.80, 1.0)
        self._captures_label.alignment = "center"
        self._captures_label.preferred_width = px(content_width)
        self._captures_label.preferred_height = px(18)
        stack.add_child(self._captures_label)

        self._board_hint_label = Label()
        self._board_hint_label.text = "Board: white view"
        self._board_hint_label.font_size = 11
        self._board_hint_label.color = (0.62, 0.66, 0.74, 1.0)
        self._board_hint_label.alignment = "center"
        self._board_hint_label.preferred_width = px(content_width)
        self._board_hint_label.preferred_height = px(18)
        stack.add_child(self._board_hint_label)

        self._files_label = Label()
        self._files_label.text = "Files: a b c d e f g h"
        self._files_label.font_size = 11
        self._files_label.color = (0.62, 0.66, 0.74, 1.0)
        self._files_label.alignment = "center"
        self._files_label.preferred_width = px(content_width)
        self._files_label.preferred_height = px(18)
        stack.add_child(self._files_label)

        self._ranks_label = Label()
        self._ranks_label.text = "Ranks: 1 2 3 4 5 6 7 8"
        self._ranks_label.font_size = 11
        self._ranks_label.color = (0.62, 0.66, 0.74, 1.0)
        self._ranks_label.alignment = "center"
        self._ranks_label.preferred_width = px(content_width)
        self._ranks_label.preferred_height = px(18)
        stack.add_child(self._ranks_label)

        promotion_info = self._promotion_info()
        if bool(promotion_info["pending"]):
            self._promotion_panel_visible = True
            self._add_promotion_section(stack, promotion_info, content_width)

        # Separator
        sep2 = Separator()
        sep2.orientation = "horizontal"
        sep2.color = (0.4, 0.4, 0.5, 0.6)
        sep2.preferred_width = px(content_width)
        stack.add_child(sep2)

        if connection_info["ok"]:
            self._add_connection_section(stack, connection_info, content_width)

        # New Game button
        btn_new = self._make_button("New Game", self._on_new_game, width=content_width)
        stack.add_child(btn_new)

        # Copy FEN button
        btn_fen = self._make_button("Copy FEN", self._on_copy_fen, width=content_width)
        stack.add_child(btn_fen)

        btn_pgn = self._make_button("Copy PGN", self._on_copy_pgn, width=content_width)
        stack.add_child(btn_pgn)

        btn_menu = self._make_button("Return to Menu", self._on_return_to_menu, width=content_width)
        stack.add_child(btn_menu)

        # Separator
        sep3 = Separator()
        sep3.orientation = "horizontal"
        sep3.color = (0.4, 0.4, 0.5, 0.6)
        sep3.preferred_width = px(content_width)
        stack.add_child(sep3)

        # Exit button
        btn_exit = self._make_button("Exit", self._on_exit, width=content_width)
        btn_exit.background_color = (0.5, 0.15, 0.15, 1.0)
        btn_exit.hover_color = (0.65, 0.2, 0.2, 1.0)
        btn_exit.pressed_color = (0.4, 0.1, 0.1, 1.0)
        stack.add_child(btn_exit)

        root_panel.add_child(stack)
        self.root = root_panel
        print("[ChessUI] Root widget set")

    def _add_connection_section(self, stack: VStack, info: dict[str, object], width: int) -> None:
        title = self._make_info_label("MCP Connection", width=width, font_size=14)
        title.color = (0.92, 0.95, 1.0, 1.0)
        stack.add_child(title)

        active_seats = self._seat_payloads(info)
        if active_seats:
            agent_memo_title = self._make_info_label("Agent Mnemo:", width=width, font_size=13)
            agent_memo_title.color = (1.0, 0.78, 0.36, 1.0)
            stack.add_child(agent_memo_title)
        for seat in active_seats:
            memo_button = self._make_button(
                self._agent_memo_button_label(seat, active_seats),
                lambda seat_payload=seat: self._copy_text(
                    f"{str(seat_payload['side'])} agent memo",
                    self._agent_memo_text(info, seat_payload),
                ),
                width=width,
            )
            self._style_agent_memo_button(memo_button)
            stack.add_child(memo_button)

        url = str(info["url"])
        session_file = str(info["session_file"])
        self._connection_labels["endpoint"] = self._make_info_label(f"URL: {url}", width=width)
        stack.add_child(self._connection_labels["endpoint"])
        stack.add_child(self._make_button("Copy URL", lambda value=url: self._copy_text("MCP URL", value), width=width))

        self._connection_labels["session_file"] = self._make_info_label(
            f"Session: {self._short_path(session_file)}",
            width=width,
        )
        stack.add_child(self._connection_labels["session_file"])
        stack.add_child(
            self._make_button(
                "Copy Session File",
                lambda value=session_file: self._copy_text("MCP session file", value),
                width=width,
            )
        )

        self._connection_labels["connection_turn"] = self._make_info_label("", width=width)
        stack.add_child(self._connection_labels["connection_turn"])
        self._connection_labels["last_event"] = self._make_info_label("", width=width)
        stack.add_child(self._connection_labels["last_event"])

        for seat in active_seats:
            side = str(seat["side"])
            label = self._make_info_label("", width=width)
            self._connection_labels[f"{side}_status"] = label
            stack.add_child(label)
            token = str(seat["token"])
            stack.add_child(
                self._make_button(
                    f"Copy {side.title()} Token",
                    lambda seat_side=side, value=token: self._copy_text(f"{seat_side} token", value),
                    width=width,
                )
            )

        self._refresh_connection_info()

    @staticmethod
    def _make_info_label(text: str, *, width: int, font_size: int = 12) -> Label:
        label = Label()
        label.text = text
        label.font_size = font_size
        label.color = (0.78, 0.80, 0.86, 1.0)
        label.alignment = "center"
        label.preferred_width = px(width)
        label.preferred_height = px(18)
        return label

    @staticmethod
    def _make_button(text: str, callback, *, width: int = 176) -> Button:
        btn = Button()
        btn.text = text
        btn.font_size = 14
        btn.preferred_width = px(width)
        btn.preferred_height = px(34)
        btn.border_radius = 5
        btn.background_color = (0.25, 0.28, 0.35, 1.0)
        btn.hover_color = (0.35, 0.38, 0.48, 1.0)
        btn.pressed_color = (0.18, 0.2, 0.25, 1.0)
        btn.text_color = (1.0, 1.0, 1.0, 1.0)
        btn.on_click = callback
        return btn

    @staticmethod
    def _style_agent_memo_button(btn: Button) -> None:
        btn.font_size = 15
        btn.background_color = (0.82, 0.50, 0.12, 1.0)
        btn.hover_color = (0.96, 0.62, 0.18, 1.0)
        btn.pressed_color = (0.62, 0.34, 0.08, 1.0)
        btn.text_color = (0.08, 0.06, 0.04, 1.0)

    @staticmethod
    def _agent_memo_button_label(seat: dict[str, object], active_seats: list[dict[str, object]]) -> str:
        if len(active_seats) == 1:
            return "Copy & Paste to Your Agent"
        side = str(seat["side"]).title()
        return f"Copy & Paste to {side} Agent"

    def _add_promotion_section(self, stack: VStack, info: dict[str, object], width: int) -> None:
        title = self._make_info_label(self._promotion_title(info), width=width, font_size=13)
        title.color = (1.0, 0.82, 0.36, 1.0)
        stack.add_child(title)

        for choice in self._promotion_choices(info):
            piece = str(choice["piece"])
            label = str(choice["label"])
            stack.add_child(
                self._make_button(
                    f"Promote: {label}",
                    lambda value=piece: self._on_choose_promotion(value),
                    width=width,
                )
            )

        cancel = self._make_button("Cancel Promotion", self._on_cancel_promotion, width=width)
        cancel.background_color = (0.35, 0.24, 0.18, 1.0)
        cancel.hover_color = (0.48, 0.32, 0.22, 1.0)
        cancel.pressed_color = (0.24, 0.16, 0.12, 1.0)
        stack.add_child(cancel)

    # --- Button callbacks ---

    def _on_start_human_vs_agent(self):
        print("[ChessUI] 'Start Game With Agent' clicked")
        if self._game_controller is not None:
            self._game_controller.start_human_vs_agent()
            self._build_ui()
            self._update_status()
        else:
            print("[ChessUI] No game controller found!")

    def _on_start_agent_vs_agent(self):
        print("[ChessUI] 'Start Two-Agent Game' clicked")
        if self._game_controller is not None:
            self._game_controller.start_agent_vs_agent()
            self._build_ui()
            self._update_status()
        else:
            print("[ChessUI] No game controller found!")

    def _on_start_local_sandbox(self):
        print("[ChessUI] 'Local Sandbox' clicked")
        if self._game_controller is not None:
            self._game_controller.start_local_sandbox()
            self._build_ui()
            self._update_status()
        else:
            print("[ChessUI] No game controller found!")

    def _on_new_game(self):
        print("[ChessUI] 'New Game' clicked")
        if self._game_controller is not None:
            self._game_controller.new_game()
            self._update_status()
        else:
            print("[ChessUI] No game controller found!")

    def _on_return_to_menu(self):
        print("[ChessUI] 'Return to Menu' clicked")
        if self._game_controller is not None:
            self._game_controller.return_to_start_menu()
            self._build_ui()
        else:
            print("[ChessUI] No game controller found!")

    def _on_copy_fen(self):
        print("[ChessUI] 'Copy FEN' clicked")
        if self._game_controller is None:
            print("[ChessUI] No game controller!")
            return

        fen = self._game_controller.get_fen()
        print(f"[ChessUI] FEN: {fen}")
        self._copy_text("FEN", fen)

    def _on_copy_pgn(self):
        print("[ChessUI] 'Copy PGN' clicked")
        if self._game_controller is None:
            print("[ChessUI] No game controller!")
            return

        pgn = self._game_controller.get_pgn()
        print(f"[ChessUI] PGN:\n{pgn}")
        self._copy_text("PGN", pgn)

    def _on_choose_promotion(self, piece_name: str):
        print(f"[ChessUI] promotion choice clicked: {piece_name}")
        if self._game_controller is None:
            print("[ChessUI] No game controller!")
            return
        self._game_controller.choose_promotion(piece_name)
        self._build_ui()
        self._update_status()

    def _on_cancel_promotion(self):
        print("[ChessUI] promotion cancelled")
        if self._game_controller is None:
            print("[ChessUI] No game controller!")
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
                print(f"[ChessUI] {label} copied to clipboard ({command[0]})")
                return
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                print(f"[ChessUI] clipboard command failed for {label}: {command[0]} ({exc})")
        names = "/".join(command[0] for command in self._clipboard_commands())
        print(f"[ChessUI] WARNING: {names} not found or failed, cannot copy {label} to clipboard")

    @staticmethod
    def _clipboard_commands(platform: str | None = None) -> list[list[str]]:
        current_platform = sys.platform if platform is None else platform
        if current_platform.startswith("win"):
            return [
                ["powershell.exe", "-NoProfile", "-Command", "Set-Clipboard"],
                ["pwsh.exe", "-NoProfile", "-Command", "Set-Clipboard"],
                ["clip.exe"],
            ]
        if current_platform == "darwin":
            return [["pbcopy"]]
        return [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]

    def _on_exit(self):
        print("[ChessUI] 'Exit' clicked")
        from termin.player import request_quit
        if not request_quit(0):
            print("[ChessUI] Player runtime is not active; exit request ignored")

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
        return self._game_controller.get_mcp_state()

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

        self._turn_label.text = self._turn_text(info)
        status_text = self._status_text(info)
        self._status_label.text = status_text
        self._apply_status_color(status_text)
        if self._owners_label is not None:
            self._owners_label.text = self._owners_text(info)
        if self._last_move_label is not None:
            self._last_move_label.text = self._last_move_text(info)
        if self._captures_label is not None:
            self._captures_label.text = self._captures_text(info)
        if self._board_hint_label is not None:
            self._board_hint_label.text = self._board_hint_text(info)
        if self._files_label is not None:
            self._files_label.text = self._files_text(info)
        if self._ranks_label is not None:
            self._ranks_label.text = self._ranks_text(info)
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
        self._connection_labels["last_event"].text = self._last_event_text(info)
        for seat in self._seat_payloads(info):
            side = str(seat["side"])
            key = f"{side}_status"
            if key in self._connection_labels:
                self._connection_labels[key].text = self._seat_status_text(seat)

    @staticmethod
    def _seat_payloads(info: dict[str, object]) -> list[dict[str, object]]:
        seats = info["seats"]
        if not isinstance(seats, list):
            return []
        return [seat for seat in seats if isinstance(seat, dict) and bool(seat["active"])]

    @staticmethod
    def _seat_status_text(seat: dict[str, object]) -> str:
        side = str(seat["side"]).title()
        state = "connected" if bool(seat["connected"]) else "waiting"
        requests = int(seat["request_count"])
        method = seat["last_method"]
        method_text = str(method) if method is not None else "no calls"
        return f"{side}: {state}, {requests} req, {method_text}"

    @staticmethod
    def _agent_memo_text(info: dict[str, object], seat: dict[str, object]) -> str:
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

    @staticmethod
    def _last_event_text(info: dict[str, object]) -> str:
        event = info["last_event"]
        return ChessUIComponent._event_text(event, prefix="Last event")

    @staticmethod
    def _last_move_text(info: dict[str, object]) -> str:
        event = info["last_move"]
        return ChessUIComponent._event_text(event, prefix="Last move")

    @staticmethod
    def _event_text(event: object, *, prefix: str) -> str:
        if not isinstance(event, dict):
            return f"{prefix}: none"
        event_type = str(event["type"])
        san = event.get("san")
        actor = event.get("actor")
        if san is None:
            return f"{prefix}: {event_type}"
        return f"{prefix}: {san} by {actor}"

    @staticmethod
    def _owners_text(info: dict[str, object]) -> str:
        owners = info["side_owners"]
        if not isinstance(owners, dict):
            return "White: unknown | Black: unknown"
        white = str(owners["white"]).replace("_", " ")
        black = str(owners["black"]).replace("_", " ")
        return f"White: {white} | Black: {black}"

    @staticmethod
    def _captures_text(info: dict[str, object]) -> str:
        captured = info.get("captured")
        if not isinstance(captured, dict):
            return "Captured: none"
        by_white = ChessUIComponent._captured_side_text(captured.get("by_white"))
        by_black = ChessUIComponent._captured_side_text(captured.get("by_black"))
        if by_white == "-" and by_black == "-":
            return "Captured: none"
        return f"Captured W: {by_white} | B: {by_black}"

    @staticmethod
    def _captured_side_text(items: object) -> str:
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

    @staticmethod
    def _board_view(info: dict[str, object]) -> str:
        human_sides = info.get("human_sides")
        if not isinstance(human_sides, list):
            return "white"
        sides = {str(side) for side in human_sides}
        if sides == {"black"}:
            return "black"
        return "white"

    @staticmethod
    def _board_hint_text(info: dict[str, object]) -> str:
        human_sides = info.get("human_sides")
        if not isinstance(human_sides, list):
            return "Board: white view"
        sides = {str(side) for side in human_sides}
        if sides == {"white", "black"}:
            return "Board: sandbox white view"
        if not sides:
            return "Board: default white view"
        view = ChessUIComponent._board_view(info)
        return f"Board: {view} view"

    @staticmethod
    def _files_text(info: dict[str, object]) -> str:
        files = list("abcdefgh")
        if ChessUIComponent._board_view(info) == "black":
            files.reverse()
        return f"Files: {' '.join(files)}"

    @staticmethod
    def _ranks_text(info: dict[str, object]) -> str:
        ranks = [str(rank) for rank in range(1, 9)]
        if ChessUIComponent._board_view(info) == "black":
            ranks.reverse()
        return f"Ranks: {' '.join(ranks)}"

    @staticmethod
    def _turn_text(info: dict[str, object]) -> str:
        turn = str(info["turn"]).title()
        turn_owner = info["turn_owner"]
        actor = "unknown"
        if isinstance(turn_owner, dict):
            actor = str(turn_owner["actor"])
        return f"{turn} to move ({actor})"

    @staticmethod
    def _status_text(info: dict[str, object]) -> str:
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
            return ChessUIComponent._promotion_title(promotion)
        if bool(info["game_over"]):
            return "Game over"
        hint = info.get("selection_hint")
        if hint is not None:
            return str(hint)
        return ""

    def _apply_status_color(self, status_text: str) -> None:
        if self._status_label is None:
            return
        if "checkmate" in status_text.lower() or "stalemate" in status_text.lower() or "draw:" in status_text.lower():
            self._status_label.color = (1.0, 0.3, 0.3, 1.0)
        elif "check" in status_text.lower():
            self._status_label.color = (1.0, 0.6, 0.2, 1.0)
        else:
            self._status_label.color = (0.7, 0.7, 0.7, 1.0)

    @staticmethod
    def _short_path(path: str) -> str:
        if len(path) <= 34:
            return path
        return f"...{path[-31:]}"

    @staticmethod
    def _promotion_title(info: dict[str, object]) -> str:
        from_sq = str(info["from"])
        to_sq = str(info["to"])
        return f"Promote {from_sq}-{to_sq}"

    @staticmethod
    def _promotion_choices(info: dict[str, object]) -> list[dict[str, object]]:
        choices = info["choices"]
        if not isinstance(choices, list):
            return []
        return [choice for choice in choices if isinstance(choice, dict)]
