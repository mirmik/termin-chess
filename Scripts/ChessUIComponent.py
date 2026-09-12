"""Native chess menus, game HUD and editable agent invitations."""
from __future__ import annotations

import logging
import subprocess
import sys
import time

from termin.scene import PythonComponent
from termin.ui_components import UIComponent
from termin.gui_native import (
    CrossAxisAlignment, EdgeInsets, LayoutPolicy, OverlayAnchor, Point, Size,
    SrgbColor, StyleField, StyleOverride, UiDocumentAsset,
)
from Scripts import chess_ui_text as ui_text

log = logging.getLogger(__name__)

MODES = ("human_vs_agent", "local_sandbox", "agent_vs_agent", "human_vs_bot")
MODE_LABELS = ("С агентом", "Вдвоём за доской", "Два агента", "Со встроенным ботом")
COLORS = ("white", "black", "random")
COLOR_LABELS = ("Белые", "Чёрные", "Случайно")
INK = (0.95, 0.97, 0.95, 1.0)
MUTED = (0.80, 0.86, 0.82, 1.0)
ACCENT = (0.76, 0.92, 0.81, 1.0)


class ChessUIComponent(PythonComponent):
    def __init__(self):
        super().__init__()
        self._ui = None
        self._document = None
        self._overlay = None
        self._game_controller = None
        self._layout_dirty = False
        self._screen = "game"
        self._setup_mode = "human_vs_agent"
        self._setup_color = "white"
        self._invite_side = "black"
        self._draft_game_id = None
        self._drafts = {}
        self._memo_editor = None
        self._feedback = ""
        self._feedback_label = None
        self._status_label = None
        self._turn_label = None
        self._history_label = None
        self._labels = {}
        self._promotion_panel_visible = False
        self._viewport = (1280, 710)
        self._refresh_elapsed = 0.0
        self._connection_labels = {}

    def start(self):
        super().start()
        controllers = self.entity.scene.get_components_of_type("ChessGameController")
        if controllers:
            self._game_controller = controllers[0]
        self._rebuild_ui()

    def on_destroy(self):
        self._memo_editor = None
        self._labels.clear()
        self._connection_labels.clear()
        self._game_controller = None
        self._ui = self._document = self._overlay = None

    def blocks_board_input(self):
        return self._screen != "game" or self._game_controller.is_start_menu_visible()

    def _build_ui(self):
        # Never destroy the widget whose input callback is currently running.
        self._layout_dirty = True

    def update(self, dt):
        if self._overlay is not None:
            bounds = self._overlay.widget.bounds_in_document
            if bounds.width > 0 and bounds.height > 0:
                size = (round(bounds.width), round(bounds.height))
                if size != self._viewport:
                    self._viewport = size
                    self._build_ui()
        self._refresh_elapsed += dt
        if self._refresh_elapsed >= 0.5:
            self._refresh_elapsed = 0
            self._sync_invitation_game()
            self._update_status()
        if self._layout_dirty:
            self._rebuild_ui()

    def _rebuild_ui(self):
        self._layout_dirty = False
        if self._ui is None:
            self._ui = self.entity.get_component(UIComponent)
            if self._ui is None:
                self._ui = UIComponent(priority=100)
                self.entity.add_component(self._ui)
            self._ui.ui_layout = UiDocumentAsset.declare_source(
                "chess-runtime-ui", "Chess UI", "chess-runtime-ui.uiscript",
                "uiscript: 2\nroot: {type: termin.gui.OverlayLayout}\n",
            )
        self._document = self._ui.document
        self._memo_editor = None
        self._feedback_label = None
        self._labels = {}
        self._connection_labels = {}
        self._status_label = self._turn_label = self._history_label = None
        while self._document.root_count:
            self._document.destroy_widget_recursive(self._document.root_at(0))
        self._overlay = self._document.create_overlay_layout()
        self._overlay.widget.mouse_transparent = True
        self._document.add_root(self._overlay.handle)
        self._promotion_panel_visible = False
        if self._game_controller is None:
            return
        self._sync_invitation_game()
        if self._game_controller.is_start_menu_visible():
            self._build_start_menu()
        elif self._screen == "invite":
            self._build_invitation()
        elif self._screen == "export":
            self._build_export()
        else:
            self._build_game_panel()
        self._update_status()

    def _stack(self, width, padding=20):
        stack = self._document.create_vstack()
        stack.set_spacing(10)
        stack.set_padding(EdgeInsets(padding, padding, padding, padding))
        stack.set_cross_axis_alignment(CrossAxisAlignment.Start)
        stack.preferred_size = Size(width, 0)
        return stack

    @staticmethod
    def _add(stack, child):
        stack.add_child(child.widget, LayoutPolicy.Preferred)

    def _label(self, stack, text, width, *, size=14, color=MUTED, field=None, height=None):
        label = self._document.create_label(text)
        label.set_font_size(size)
        label.set_color(SrgbColor(*color))
        label.preferred_size = Size(width, height or (size + 10) * (text.count("\n") + 1))
        self._add(stack, label)
        if field:
            self._labels[field] = label
        return label

    def _button(self, stack, text, callback, width, *, primary=False, selected=False):
        button = self._document.create_button(text, debug_name=text)
        button.widget.preferred_size = Size(width, 40)
        style = StyleOverride()
        style.fields = StyleField.Background | StyleField.Foreground | StyleField.FontSize
        style.value.background = SrgbColor(*(ACCENT if primary or selected else (0.34, 0.41, 0.36, 1)))
        style.value.foreground = SrgbColor(*((0.08, 0.14, 0.10, 1) if primary or selected else INK))
        style.value.font_size = 14
        button.widget.style_override = style
        button.connect_clicked(callback)
        self._add(stack, button)
        return button

    def _row_buttons(self, stack, choices, width):
        row = self._document.create_hstack()
        row.set_spacing(8)
        each = (width - 8 * (len(choices) - 1)) / len(choices)
        for text, callback, selected in choices:
            self._button(row, text, callback, each, selected=selected)
        self._add(stack, row)

    def _separator(self, stack, width):
        line = self._document.create_separator()
        line.set_color(SrgbColor(0.28, 0.36, 0.30, 1))
        line.preferred_size = Size(width, 1)
        self._add(stack, line)

    def _mount_panel(self, stack, *, centered=False, height=600):
        stack.set_background(SrgbColor(0.26, 0.31, 0.28, 1.0))
        stack.set_corner_radius(14)
        scroll = self._document.create_scroll_area()
        scroll.set_content(stack.widget)
        scroll.widget.preferred_size = Size(stack.preferred_size.width + 12, min(height, self._viewport[1] - 24))
        if centered:
            row = self._document.create_hstack()
            row.set_cross_axis_alignment(CrossAxisAlignment.Center)
            for child, policy in ((self._document.create_spacer(Size()), LayoutPolicy.Flex),
                                  (scroll, LayoutPolicy.Preferred),
                                  (self._document.create_spacer(Size()), LayoutPolicy.Flex)):
                row.add_child(child.widget, policy, 1)
            self._overlay.add_child(row.widget, OverlayAnchor.Fill)
        else:
            self._overlay.add_child(scroll.widget, OverlayAnchor.TopRight, Point(-12, 12))

    def _panel(self, preferred):
        width = min(preferred, max(260, self._viewport[0] - 40))
        return self._stack(width), width - 40

    def _combo(self, stack, items, selected, callback, width):
        combo = self._document.create_combo_box()
        for item in items:
            combo.add_item(item)
        combo.selected_index = selected
        combo.widget.preferred_size = Size(width, 40)
        combo.connect_changed(callback)
        self._add(stack, combo)
        return combo

    def _build_start_menu(self):
        controller = self._game_controller
        stack, width = self._panel(440)
        self._label(stack, "TERMIN CHESS", width, size=14, color=ACCENT)
        self._label(stack, "Новая партия", width, size=28, color=INK)
        if controller.is_game_started():
            self._label(stack, "Текущая партия на паузе", width)
            self._button(stack, "Продолжить партию", self._on_resume, width, primary=True)
            self._separator(stack, width)
        self._label(stack, "С кем играем", width, color=INK)
        self._combo(stack, MODE_LABELS, MODES.index(self._setup_mode), self._select_mode, width)
        if self._setup_mode in ("human_vs_agent", "human_vs_bot"):
            self._label(stack, "Ваш цвет", width, color=INK)
            self._row_buttons(stack, [(label, lambda c=color: self._select_color(c), color == self._setup_color)
                                     for color, label in zip(COLORS, COLOR_LABELS, strict=True)], width)
            hints = {"white": "Вы делаете первый ход.", "black": "Соперник делает первый ход.", "random": "Цвет определится при создании партии."}
            self._label(stack, hints[self._setup_color], width)
        else:
            self._label(stack, "Два приглашения — по одному на сторону." if self._setup_mode == "agent_vs_agent"
                        else "Оба игрока ходят на этом компьютере.", width)
        text = "Начать новую партию" if controller.is_game_started() else "Создать партию"
        self._button(stack, text, self._on_create_game, width, primary=not controller.is_game_started())
        self._button(stack, "Выйти из игры", self._on_exit, width)
        self._mount_panel(stack, centered=True, height=480 if controller.is_game_started() else 400)

    def _select_mode(self, index, _text):
        self._setup_mode = MODES[index]
        self._build_ui()

    def _select_color(self, color):
        self._setup_color = color
        self._build_ui()

    def _on_create_game(self):
        self._feedback = ""
        self._game_controller.start_game(self._setup_mode, self._setup_color)
        self._screen = "game"
        info = self._connection_info()
        if info["ok"]:
            seats = ui_text.seat_payloads(info)
            if seats:
                self._invite_side = seats[0]["side"]
                self._screen = "invite"
        self._sync_invitation_game()
        self._build_ui()

    def _on_resume(self):
        self._screen = "game"
        self._game_controller.resume_game()
        self._build_ui()

    def _build_game_panel(self):
        stack, width = self._panel(296)
        self._label(stack, "TERMIN CHESS", width, size=14, color=ACCENT)
        self._label(stack, MODE_LABELS[MODES.index(self._game_controller.current_mode())], width)
        self._separator(stack, width)
        self._label(stack, "", width, field="white", color=INK)
        self._label(stack, "", width, field="black", color=INK)
        self._turn_label = self._label(stack, "", width, size=20, color=ACCENT, field="turn")
        self._status_label = self._label(stack, "", width, field="status")
        self._label(stack, "", width, field="last_move")
        self._separator(stack, width)
        self._label(stack, "Ходы партии", width, color=INK)
        history = self._document.create_scroll_area()
        self._history_label = self._document.create_label("")
        self._history_label.set_color(SrgbColor(*INK))
        self._history_label.set_font_size(14)
        self._history_label.preferred_size = Size(width - 12, 40)
        history.set_content(self._history_label.widget)
        history.widget.preferred_size = Size(width, min(150, max(70, self._viewport[1] - 520)))
        self._add(stack, history)
        promotion = self._game_controller.get_pending_promotion_info()
        if promotion["pending"]:
            self._promotion_panel_visible = True
            self._label(stack, "Превращение пешки", width, color=ACCENT)
            names = {"queen": "Ферзь", "rook": "Ладья", "bishop": "Слон", "knight": "Конь"}
            for choice in promotion["choices"]:
                piece = choice["piece"]
                self._button(stack, names.get(piece, piece), lambda p=piece: self._on_choose_promotion(p), width)
            self._button(stack, "Отменить превращение", self._on_cancel_promotion, width)
        if self._game_controller.current_mode() in ("human_vs_agent", "agent_vs_agent"):
            info = self._connection_info()
            if info["ok"]:
                for seat in ui_text.seat_payloads(info):
                    side = seat["side"]
                    label = "Пригласить агента" if len(info["active_mcp_sides"]) == 1 else f"Агент: {ui_text.side_label(side)}"
                    self._button(stack, label, lambda s=side: self._open_invitation(s), width)
            else:
                self._label(stack, "Не удалось запустить подключение", width, color=ACCENT)
                self._button(stack, "Повторить подключение", self._retry_connection, width)
                self._label(stack, str(info["error"]), width, size=12, height=44)
        self._button(stack, "Перевернуть доску", self._game_controller.flip_board, width)
        self._row_buttons(stack, [("Экспорт", self._open_export, False), ("Меню", self._on_return_to_menu, False)], width)
        self._mount_panel(stack, height=self._viewport[1] - 24)

    def _retry_connection(self):
        self._game_controller.retry_agent_connection()
        self._build_ui()

    def _open_invitation(self, side):
        self._screen = "invite"
        self._invite_side = side
        self._feedback = ""
        self._build_ui()

    def _sync_invitation_game(self):
        if self._game_controller is None:
            return
        game_id = self._game_controller.get_game_state()["game_id"]
        if game_id != self._draft_game_id:
            self._drafts.clear()
            self._draft_game_id = game_id
            self._feedback = ""
            if self._memo_editor is not None:
                self._build_ui()

    def _build_invitation(self):
        info = self._connection_info()
        seats = ui_text.seat_payloads(info) if info["ok"] else []
        if not seats:
            self._screen = "game"
            self._build_game_panel()
            return
        seat = next((s for s in seats if s["side"] == self._invite_side), seats[0])
        self._invite_side = seat["side"]
        stack, width = self._panel(690)
        self._label(stack, "ПОДКЛЮЧЕНИЕ АГЕНТА", width, size=14, color=ACCENT)
        self._label(stack, "Пригласить агента", width, size=26, color=INK)
        if len(seats) > 1:
            self._row_buttons(stack, [(ui_text.side_label(s["side"]), lambda side=s["side"]: self._open_invitation(side), s["side"] == self._invite_side) for s in seats], width)
        self._label(stack, f"Агент играет: {ui_text.side_label(self._invite_side)}", width, color=INK)
        self._label(stack, "Измените сообщение и передайте его агенту.", width)
        self._connection_labels["activity"] = self._label(stack, self._activity_text(seat), width)
        if self._invite_side not in self._drafts:
            self._drafts[self._invite_side] = ui_text.agent_memo_text(info, seat)
        editor = self._document.create_text_area(self._drafts[self._invite_side])
        editor.widget.preferred_size = Size(width, min(280, max(140, self._viewport[1] - 370)))
        self._add(stack, editor)
        self._memo_editor = editor
        self._style_editor(editor)
        identity = self._draft_game_id
        side = self._invite_side
        editor.connect_changed(lambda text: self._save_draft(identity, side, text))
        self._button(stack, "Скопировать сообщение", self._copy_invitation, width, primary=True)
        self._row_buttons(stack, [("Вернуть шаблон", self._reset_invitation, False), ("К доске", self._close_overlay, False)], width)
        self._feedback_label = self._label(stack, self._feedback, width, color=ACCENT, height=40)
        self._mount_panel(stack, centered=True, height=590)

    @staticmethod
    def _style_editor(editor):
        style = StyleOverride()
        style.fields = StyleField.Background | StyleField.Foreground | StyleField.FontSize
        style.value.background = SrgbColor(0.21, 0.26, 0.23, 1)
        style.value.foreground = SrgbColor(*INK)
        style.value.font_size = 15
        editor.widget.style_override = style

    def _save_draft(self, game_id, side, text):
        if game_id == self._draft_game_id:
            self._drafts[side] = text

    def _copy_invitation(self):
        # Catch an operator reset before a periodic UI refresh as well.
        previous = self._draft_game_id
        self._sync_invitation_game()
        if previous != self._draft_game_id:
            self._show_feedback("Партия изменилась. Проверьте новое приглашение.")
            self._build_ui()
            return
        self._copy_text("Сообщение", self._drafts[self._invite_side])

    def _reset_invitation(self):
        info = self._connection_info()
        seat = next(s for s in ui_text.seat_payloads(info) if s["side"] == self._invite_side)
        self._memo_editor.text = ui_text.agent_memo_text(info, seat)
        self._show_feedback("Шаблон восстановлен")

    def _close_overlay(self):
        self._screen = "game"
        self._build_ui()

    def _open_export(self):
        self._screen = "export"
        self._feedback = ""
        self._build_ui()

    def _build_export(self):
        stack, width = self._panel(620)
        self._label(stack, "Экспорт партии", width, size=26, color=INK)
        self._label(stack, "PGN — история, FEN — текущая позиция.", width)
        editor = self._document.create_text_area(self._game_controller.get_pgn())
        self._style_editor(editor)
        editor.widget.preferred_size = Size(width, 220)
        self._add(stack, editor)
        self._button(stack, "Скопировать PGN", self._on_copy_pgn, width, primary=True)
        self._button(stack, "Скопировать FEN", self._on_copy_fen, width)
        self._button(stack, "К доске", self._close_overlay, width)
        self._feedback_label = self._label(stack, self._feedback, width, color=ACCENT, height=40)
        self._mount_panel(stack, centered=True, height=520)

    def _on_return_to_menu(self):
        self._screen = "game"
        self._game_controller.return_to_start_menu()
        self._build_ui()

    def _on_new_game(self):
        self._game_controller.new_game()
        self._sync_invitation_game()
        self._build_ui()

    def _on_copy_pgn(self):
        self._copy_text("PGN", self._game_controller.get_pgn())

    def _on_copy_fen(self):
        self._copy_text("FEN", self._game_controller.get_fen())

    def _on_choose_promotion(self, piece):
        self._game_controller.choose_promotion(piece)
        self._build_ui()

    def _on_cancel_promotion(self):
        self._game_controller.cancel_promotion()
        self._build_ui()

    def _show_feedback(self, text):
        self._feedback = text
        if self._feedback_label is not None:
            self._feedback_label.text = text

    def _copy_text(self, label, text):
        for command in self._clipboard_commands():
            try:
                subprocess.run(command, input=text, text=True, check=True, timeout=2,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._show_feedback(f"{label}: скопировано")
                return True
            except (OSError, subprocess.SubprocessError):
                continue
        self._show_feedback("Не удалось скопировать. Выделите текст и нажмите Ctrl+C.")
        return False

    @staticmethod
    def _clipboard_commands(platform=None):
        platform = sys.platform if platform is None else platform
        if platform.startswith("win"):
            return [["clip.exe"], ["powershell.exe", "-NoProfile", "-Command", "Set-Clipboard"],
                    ["pwsh.exe", "-NoProfile", "-Command", "Set-Clipboard"]]
        if platform == "darwin":
            return [["pbcopy"]]
        return [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]

    def _on_exit(self):
        from termin.player import request_quit
        request_quit(0)

    def _connection_info(self):
        return self._game_controller.get_connection_panel_info()

    @staticmethod
    def _activity_text(seat):
        seen = seat.get("last_seen_at")
        if seen is None:
            return "Ожидаем первого обращения агента"
        seconds = max(0, int(time.time() - float(seen)))
        return f"Последнее обращение: {seconds} с назад"

    def update_status(self, turn_text="", status_text=""):
        self._update_status()

    def _update_status(self):
        if self._game_controller is None:
            return
        state = self._game_controller.get_game_state()
        if bool(state["pending_promotion"]["pending"]) != self._promotion_panel_visible and self._screen == "game" and not self._game_controller.is_start_menu_visible():
            self._build_ui()
        for side in ("white", "black"):
            if side in self._labels:
                owner = {"human": "Вы" if len(state["human_sides"]) == 1 else "Игрок", "agent": "Агент", "local_bot": "Бот"}.get(state["side_owners"][side], "Игрок")
                self._labels[side].text = f"{ui_text.side_label(side)}  ·  {owner}"
        if self._turn_label is not None:
            self._turn_label.text = "Партия окончена" if state["game_over"] else f"Ход: {ui_text.side_label(state['turn']).lower()}"
            self._status_label.text = ui_text.game_status_ru(state)
            last = state["last_move"]
            self._labels["last_move"].text = f"Последний ход: {last['san']}" if last else "Первый ход — за белыми"
        if self._history_label is not None:
            moves = state["move_history"]
            rows = [f"{i // 2 + 1}.  {moves[i]}    {moves[i + 1] if i + 1 < len(moves) else ''}" for i in range(0, len(moves), 2)]
            self._history_label.text = "\n".join(rows) or "Ходов пока нет"
            self._history_label.preferred_size = Size(self._history_label.preferred_size.width, max(30, len(rows) * 24))
        if "activity" in self._connection_labels:
            info = self._connection_info()
            if info["ok"]:
                seat = next((s for s in info["seats"] if s["side"] == self._invite_side), None)
                if seat is not None:
                    self._connection_labels["activity"].text = self._activity_text(seat)
