"""Chess game controller — handles click input, move validation, and piece movement."""

from __future__ import annotations

from copy import deepcopy
import random
import os
import queue
import threading
import time

import chess
import chess.pgn

from tcbase import Action, MouseButton
from termin.input import InputComponent
from termin.collision import CollisionWorld
from termin.materials import TcMaterial

from Scripts.chess_coords import (
    square_to_world,
    entity_to_square,
    tile_name_to_square,
)
from Scripts.ChessGameSession import ChessGameSession, GameMode, MoveActor, SideOwner, side_name

print("[Chess] ChessGameController module loaded.")

STATE_IDLE = "idle"
STATE_SELECTED = "piece_selected"
STATE_GAME_OVER = "game_over"

BOT_PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

GAME_MODE_ENV_VALUES: dict[str, GameMode] = {
    "sandbox": GameMode.LOCAL_SANDBOX,
    "local": GameMode.LOCAL_SANDBOX,
    "local_sandbox": GameMode.LOCAL_SANDBOX,
    "human_vs_agent": GameMode.HUMAN_VS_AGENT,
    "agent": GameMode.HUMAN_VS_AGENT,
    "agent_vs_agent": GameMode.AGENT_VS_AGENT,
    "two_agent": GameMode.AGENT_VS_AGENT,
    "two_agents": GameMode.AGENT_VS_AGENT,
    "human_vs_bot": GameMode.HUMAN_VS_BOT,
    "bot": GameMode.HUMAN_VS_BOT,
}

PROMOTION_CHOICES: tuple[tuple[int, str], ...] = (
    (chess.QUEEN, "Queen"),
    (chess.ROOK, "Rook"),
    (chess.BISHOP, "Bishop"),
    (chess.KNIGHT, "Knight"),
)


class ChessGameController(InputComponent):

    def __init__(self):
        print("[Chess] ChessGameController.__init__()")
        super().__init__(enabled=True, active_in_editor=False)
        self._board: chess.Board = chess.Board()
        self._pieces: dict[str, object] = {}      # "e2" -> entity
        self._tiles: dict[str, object] = {}        # "a1" -> entity
        self._original_materials: dict[str, object] = {}  # "a1" -> material
        self._selected_square: str | None = None
        self._valid_moves: list[chess.Move] = []
        self._state: str = STATE_IDLE
        self._highlight_selected: TcMaterial | None = None
        self._highlight_valid: TcMaterial | None = None
        self._highlight_last_move: TcMaterial | None = None
        self._highlight_check: TcMaterial | None = None
        self._last_move_squares: tuple[str, str] | None = None
        self._check_square: str | None = None
        self._pending_promotion: dict[str, object] | None = None
        self._board_entity = None
        self._units_entity = None
        self._bot_enabled = True
        self._bot_color = chess.BLACK
        self._bot_is_moving = False
        self._game_mcp_enabled = False
        self._game_started = False
        self._start_menu_visible = True
        self._session = ChessGameSession()
        self._mcp_server = None
        self._mcp_state_lock = threading.RLock()
        self._mcp_commands: queue.Queue[dict[str, object]] = queue.Queue()
        self._mcp_condition = threading.Condition()
        self._mcp_events: list[dict[str, object]] = []
        self._mcp_next_event_id = 1
        self._mcp_max_events = 200
        self._mcp_server_stopping = False
        self._ui_refresh_accum = 0.0
        self._ui_dirty = True
        self._mcp_state_revision = 0
        self._mcp_state_cache_revision = -1
        self._mcp_state_cache: dict[str, object] | None = None
        self._dirty_highlight_squares: set[str] = set()

    def start(self) -> None:
        print("[Chess] ChessGameController.start() called")
        super().start()
        self._board = chess.Board()
        print("[Chess] chess.Board created, initial position loaded")
        self._configure_runtime_options()

        self._create_highlight_materials()
        self._scan_board()
        self._scan_pieces()
        self._find_ui()
        self._start_mcp_server()

        print(f"[Chess] Init complete. tiles={len(self._tiles)}, pieces={len(self._pieces)}")
        print(f"[Chess] Tiles: {sorted(self._tiles.keys())}")
        print(f"[Chess] Pieces: {sorted(self._pieces.keys())}")
        print("[Chess] White to move.")
        self._notify_ui()
        self._maybe_make_bot_move()

    def update(self, dt: float) -> None:
        self._process_mcp_commands()
        self._ui_refresh_accum += dt
        if self._ui_refresh_accum >= 0.5 and getattr(self, "_ui_dirty", True):
            self._ui_refresh_accum = 0.0
            self._notify_ui()

    def on_destroy(self) -> None:
        self._stop_mcp_server()

    def _configure_runtime_options(self) -> None:
        from Scripts.ChessMcpServer import chess_mcp_enabled

        mcp_enabled = chess_mcp_enabled()
        self._game_mcp_enabled = mcp_enabled
        bot_env = os.environ.get("CHESS_BOT_ENABLED")
        if bot_env is not None:
            self._bot_enabled = bot_env.strip().lower() in {"1", "true", "yes", "on"}
        self._bot_color = self._side_from_env("CHESS_BOT_COLOR", self._bot_color)

        requested_mode = self._game_mode_from_env()
        if requested_mode is not None:
            self._game_started = True
            self._start_menu_visible = False
            self._configure_requested_game_mode(requested_mode)
        else:
            if mcp_enabled:
                self._game_started = True
                self._start_menu_visible = False
                self._bot_enabled = False
                self._session.configure_runtime(
                    mcp_enabled=mcp_enabled,
                    bot_enabled=self._bot_enabled,
                    bot_color=self._bot_color,
                )
            else:
                self._configure_menu_idle_mode()
        print(f"[Chess] Bot enabled: {self._bot_enabled}")
        print(f"[Chess] Game mode: {self._session.mode.value}, owners={self._session.side_owners_payload()}")

    def _game_mode_from_env(self) -> GameMode | None:
        value = os.environ.get("CHESS_GAME_MODE")
        if value is None:
            value = os.environ.get("CHESS_MODE")
        if value is None:
            return None

        key = value.strip().lower().replace("-", "_")
        mode = GAME_MODE_ENV_VALUES.get(key)
        if mode is None:
            print(f"[Chess] WARNING: unknown CHESS_GAME_MODE='{value}', using default runtime mode")
        return mode

    def _configure_requested_game_mode(self, mode: GameMode) -> None:
        if mode == GameMode.LOCAL_SANDBOX:
            self._game_mcp_enabled = False
            self._bot_enabled = False
            self._session.configure_local_sandbox()
            return
        if mode == GameMode.HUMAN_VS_AGENT:
            self._bot_enabled = False
            self._game_mcp_enabled = True
            agent_side = self._side_from_env("CHESS_AGENT_SIDE", chess.BLACK)
            self._session.configure_human_vs_agent(agent_side=agent_side)
            return
        if mode == GameMode.AGENT_VS_AGENT:
            self._bot_enabled = False
            self._game_mcp_enabled = True
            self._session.configure_agent_vs_agent()
            return
        if mode == GameMode.HUMAN_VS_BOT:
            self._game_mcp_enabled = False
            if os.environ.get("CHESS_BOT_ENABLED") is None:
                self._bot_enabled = True
            self._session.configure_human_vs_bot(bot_color=self._bot_color)
            return
        print(f"[Chess] WARNING: unsupported game mode '{mode.value}', using local sandbox")
        self._game_mcp_enabled = False
        self._bot_enabled = False
        self._session.configure_local_sandbox()

    def _configure_menu_idle_mode(self) -> None:
        self._game_mcp_enabled = False
        self._bot_enabled = False
        self._session.configure_local_sandbox()

    @staticmethod
    def _side_from_env(name: str, default: bool) -> bool:
        value = os.environ.get(name)
        if value is None:
            return default
        key = value.strip().lower()
        if key in {"white", "w", "1", "true"}:
            return chess.WHITE
        if key in {"black", "b", "0", "false"}:
            return chess.BLACK
        print(f"[Chess] WARNING: invalid {name}='{value}', using {side_name(default)}")
        return default

    def _start_mcp_server(self) -> None:
        from Scripts.ChessMcpServer import (
            ChessGameMcpServer,
            load_chess_mcp_config,
        )

        if not self._game_mcp_enabled:
            return
        if self._mcp_server is not None:
            return

        with self._mcp_condition:
            self._mcp_server_stopping = False
        server = ChessGameMcpServer(self, load_chess_mcp_config())
        if server.start():
            self._mcp_server = server

    def _stop_mcp_server(self) -> None:
        if self._mcp_server is not None:
            self._mcp_server.stop()
            self._mcp_server = None

    def notify_mcp_server_stopping(self) -> None:
        with self._mcp_condition:
            self._mcp_server_stopping = True
            self._mcp_condition.notify_all()

    def _find_ui(self):
        """Find ChessUIComponent in scene for status updates."""
        self._ui_component = None
        scene = self.entity.scene
        comps = scene.get_components_of_type("ChessUIComponent")
        if comps:
            self._ui_component = comps[0]
            print("[Chess] Found ChessUIComponent for status updates")
        else:
            print("[Chess] ChessUIComponent not found (no UI status updates)")

    # --- Public API (called by UI) ---

    def get_fen(self) -> str:
        return self._board.fen()

    def get_pgn(self) -> str:
        return self.get_mcp_pgn()

    def get_board(self):
        return self._board

    def get_pending_promotion_info(self) -> dict[str, object]:
        if self._pending_promotion is None:
            return {"pending": False}
        return dict(self._pending_promotion)

    def _mark_state_dirty(self, *, ui: bool = True) -> None:
        self._mcp_state_revision = getattr(self, "_mcp_state_revision", 0) + 1
        self._mcp_state_cache = None
        self._mcp_state_cache_revision = -1
        if ui:
            self._ui_dirty = True

    def is_game_started(self) -> bool:
        return self._game_started

    def is_start_menu_visible(self) -> bool:
        return self._start_menu_visible

    def current_mode(self) -> str:
        return self._session.mode.value

    def get_connection_panel_info(self) -> dict[str, object]:
        if self._mcp_server is None:
            return {
                "ok": False,
                "mode": self._session.mode.value,
                "turn": "white" if self._board.turn == chess.WHITE else "black",
                "status": self._mcp_status(),
                "error": "MCP server is not running",
            }
        return self._mcp_server.ui_connection_payload()

    def start_local_sandbox(self) -> None:
        self._start_selected_mode(GameMode.LOCAL_SANDBOX)

    def start_human_vs_agent(self) -> None:
        self._start_selected_mode(GameMode.HUMAN_VS_AGENT)

    def start_agent_vs_agent(self) -> None:
        self._start_selected_mode(GameMode.AGENT_VS_AGENT)

    def choose_promotion(self, piece_name: str) -> None:
        pending = self._pending_promotion
        if pending is None:
            print(f"[Chess] promotion choice '{piece_name}' ignored: no pending promotion")
            return

        normalized = piece_name.strip().lower()
        for choice in pending["choices"]:
            if not isinstance(choice, dict):
                continue
            if str(choice["piece"]) != normalized:
                continue
            move = chess.Move.from_uci(str(choice["uci"]))
            print(f"[Chess] promotion choice selected: {normalized} ({move.uci()})")
            self._pending_promotion = None
            self._execute_move(move, actor=MoveActor.human())
            return

        print(f"[Chess] invalid promotion choice '{piece_name}'")

    def cancel_promotion(self) -> None:
        if self._pending_promotion is None:
            return
        print("[Chess] promotion selection cancelled")
        self._pending_promotion = None
        self._clear_selection()
        self._notify_ui()

    def return_to_start_menu(self) -> None:
        print("[Chess] Returning to start menu")
        self._stop_mcp_server()
        self._game_started = False
        self._start_menu_visible = True
        self._configure_menu_idle_mode()
        self._mark_state_dirty()
        self.new_game(trigger_bot=False)
        self._notify_ui()

    def _start_selected_mode(self, mode: GameMode) -> None:
        print(f"[Chess] Starting mode from menu: {mode.value}")
        self._stop_mcp_server()
        self._game_started = True
        self._start_menu_visible = False
        self._configure_requested_game_mode(mode)
        self._mark_state_dirty()
        self.new_game(trigger_bot=False)
        self._start_mcp_server()
        self._notify_ui()
        self._maybe_make_bot_move()

    def get_mcp_state(self, *, caller_side: bool | None = None) -> dict[str, object]:
        with self._mcp_state_lock:
            revision = getattr(self, "_mcp_state_revision", 0)
            cache_revision = getattr(self, "_mcp_state_cache_revision", -1)
            cache = getattr(self, "_mcp_state_cache", None)
            if cache is None or cache_revision != revision:
                cache = self._build_mcp_state()
                self._mcp_state_cache = cache
                self._mcp_state_cache_revision = revision

            state = deepcopy(cache)
            if caller_side is not None:
                caller_authorization = self._session.can_move_now(
                    actor=MoveActor.agent(caller_side),
                    board=self._board,
                    game_state=self._state,
                )
                state["caller_side"] = side_name(caller_side)
                state["caller_can_move"] = caller_authorization.ok
                state["caller_error"] = caller_authorization.error if not caller_authorization.ok else None
            return state

    def _build_mcp_state(self) -> dict[str, object]:
        legal_moves = []
        for move in self._board.legal_moves:
            legal_moves.append(
                {
                    "uci": move.uci(),
                    "san": self._board.san(move),
                    "from": chess.square_name(move.from_square),
                    "to": chess.square_name(move.to_square),
                    "promotion": chess.piece_name(move.promotion) if move.promotion else None,
                    "capture": self._board.is_capture(move),
                    "check": self._board.gives_check(move),
                }
            )
        human_authorization = self._session.can_move_now(
            actor=MoveActor.human(),
            board=self._board,
            game_state=self._state,
        )

        return {
            "ok": True,
            "fen": self._board.fen(),
            "board_ascii": str(self._board),
            "turn": "white" if self._board.turn == chess.WHITE else "black",
            "turn_owner": self._session.turn_owner_payload(self._board.turn),
            "fullmove_number": self._board.fullmove_number,
            "ply": len(self._board.move_stack),
            "legal_moves": legal_moves,
            "selected_legal_moves": self._selected_move_payloads(),
            "selection_hint": self._selection_hint(),
            "pending_promotion": self.get_pending_promotion_info(),
            "last_move": self._last_mcp_move_event(),
            "last_move_squares": list(self._last_move_squares) if self._last_move_squares is not None else [],
            "check_square": self._check_square,
            "captured": self._captured_summary_payload(),
            "status": self._mcp_status(),
            "check": self._board.is_check(),
            "checkmate": self._board.is_checkmate(),
            "stalemate": self._board.is_stalemate(),
            "game_over": self._board.is_game_over(),
            "game_started": self._game_started,
            "start_menu_visible": self._start_menu_visible,
            "board_input_enabled": self._game_started and human_authorization.ok,
            "board_input_error": human_authorization.error if self._game_started and not human_authorization.ok else None,
            "selected_square": self._selected_square,
            "mode": self._session.mode.value,
            "side_owners": self._session.side_owners_payload(),
            "human_sides": self._session.sides_for_owner_payload(SideOwner.HUMAN),
            "agent_sides": self._session.sides_for_owner_payload(SideOwner.AGENT),
            "local_bot_sides": self._session.sides_for_owner_payload(SideOwner.LOCAL_BOT),
            "seats": self._session.player_seats_payload(),
            "mcp_seats": self._session.mcp_seats_payload(),
            "active_mcp_sides": self._session.active_mcp_sides_payload(),
            "mcp_side": side_name(self._session.mcp_side) if self._session.mcp_side is not None else None,
            "caller_side": None,
            "caller_can_move": None,
            "caller_error": None,
            "bot_enabled": self._bot_enabled,
            "bot_color": "white" if self._bot_color == chess.WHITE else "black",
            "next_event_id": self._mcp_next_event_id,
        }

    def get_mcp_pgn(self) -> str:
        with self._mcp_state_lock:
            game = chess.pgn.Game.from_board(self._board)
            return str(game)

    def get_mcp_events(self) -> dict[str, object]:
        with self._mcp_condition:
            return {
                "ok": True,
                "events": list(self._mcp_events),
                "next_event_id": self._mcp_next_event_id,
            }

    def request_mcp_move(self, move_text: str, *, side: bool, timeout: float) -> dict[str, object]:
        move_text = move_text.strip()
        if move_text == "":
            return {"ok": False, "error": "move must not be empty", "state": self.get_mcp_state(caller_side=side)}
        return self._submit_mcp_command({"kind": "move", "move": move_text, "side": side}, timeout=timeout)

    def request_mcp_new_game(self, *, timeout: float) -> dict[str, object]:
        return {
            "ok": False,
            "error": "new_game is reserved for in-game UI or system control",
            "state": self.get_mcp_state(),
        }

    def request_mcp_set_bot_enabled(self, enabled: bool, *, timeout: float) -> dict[str, object]:
        return {
            "ok": False,
            "error": "set_bot_enabled is a local sandbox/debug control and is not available to MCP side seats",
            "state": self.get_mcp_state(),
        }

    def wait_for_mcp_event(
        self,
        *,
        timeout: float,
        caller_side: bool | None = None,
    ) -> dict[str, object]:
        def ready_payload(state: dict[str, object]) -> dict[str, object]:
            return {"ok": True, "ready": True, "event": None, "waiting_for": state["turn_owner"], "state": state}

        def game_over_payload(state: dict[str, object]) -> dict[str, object]:
            return {
                "ok": True,
                "ready": False,
                "game_over": True,
                "event": state["last_move"],
                "waiting_for": state["turn_owner"],
                "state": state,
            }

        state = self.get_mcp_state(caller_side=caller_side)
        if state["caller_can_move"] is True:
            return ready_payload(state)
        if state["game_over"] is True:
            return game_over_payload(state)

        if timeout > 0:
            remaining = timeout
            end_time = time.monotonic() + timeout
            observed_next_event_id = state["next_event_id"]
            while remaining > 0:
                with self._mcp_condition:
                    if (
                        not self._mcp_server_stopping
                        and self._mcp_next_event_id == observed_next_event_id
                    ):
                        self._mcp_condition.wait(timeout=remaining)
                    if self._mcp_server_stopping:
                        break
                    observed_next_event_id = self._mcp_next_event_id

                state = self.get_mcp_state(caller_side=caller_side)
                if state["caller_can_move"] is True:
                    return ready_payload(state)
                if state["game_over"] is True:
                    return game_over_payload(state)
                remaining = end_time - time.monotonic()

                if observed_next_event_id == state["next_event_id"]:
                    # No state-changing event occurred; this was a timeout or spurious wake.
                    continue
                observed_next_event_id = state["next_event_id"]

        state = self.get_mcp_state(caller_side=caller_side)
        if self._mcp_server_stopping:
            return {
                "ok": False,
                "shutdown": True,
                "error": "MCP server is shutting down",
                "waiting_for": state["turn_owner"],
                "state": state,
            }
        return {"ok": False, "timeout": True, "waiting_for": state["turn_owner"], "state": state}

    def new_game(self, *, trigger_bot: bool = True):
        """Reset the board and pieces to starting position."""
        with self._mcp_state_lock:
            print("[Chess] === NEW GAME ===")
            self._last_move_squares = None
            self._check_square = None
            self._pending_promotion = None
            self._clear_selection()
            self._board = chess.Board()
            self._state = STATE_IDLE

            # Destroy all piece entities
            for _sq, entity in list(self._pieces.items()):
                scene = entity.scene
                if scene:
                    scene.remove(entity)
            self._pieces.clear()

            # Recreate pieces via UnitsCreator
            scene = self.entity.scene
            units_entity = scene.find_entity_by_name("ChessUnits")
            if units_entity:
                from Scripts.UnitsCreator import UnitsCreator
                uc = units_entity.get_component(UnitsCreator)
                if uc:
                    uc.make_units()
                    print("[Chess] Pieces recreated via UnitsCreator.make_units()")
                else:
                    print("[Chess] WARNING: UnitsCreator not found on ChessUnits!")
            else:
                print("[Chess] WARNING: ChessUnits entity not found!")

            # Re-scan pieces
            self._scan_pieces()
            self._mark_state_dirty()
            self._record_mcp_event({"type": "reset", "actor": "system"})
            self._reset_mcp_session_state()
            self._notify_ui()
            print(f"[Chess] New game started. pieces={len(self._pieces)}")
            if trigger_bot:
                self._maybe_make_bot_move()

    def _reset_mcp_session_state(self) -> None:
        if self._mcp_server is not None:
            self._mcp_server.reset_session_state()

    def _submit_mcp_command(self, command: dict[str, object], *, timeout: float) -> dict[str, object]:
        wait_timeout = max(timeout, 0.0)
        done = threading.Event()
        command["done"] = done
        command["result"] = None
        command["cancelled"] = False
        command["expires_at"] = time.monotonic() + wait_timeout
        self._mcp_commands.put(command)
        if not done.wait(timeout=wait_timeout):
            command["cancelled"] = True
            return {"ok": False, "timeout": True, "state": self.get_mcp_state()}
        result = command.get("result")
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "MCP command did not produce a result", "state": self.get_mcp_state()}

    def _process_mcp_commands(self) -> None:
        processed = 0
        while processed < 8:
            try:
                command = self._mcp_commands.get_nowait()
            except queue.Empty:
                return

            done = command.get("done")
            try:
                if self._mcp_command_cancelled_or_expired(command):
                    command["result"] = self._expired_mcp_command_result(command)
                else:
                    command["result"] = self._handle_mcp_command(command)
            except Exception as exc:
                command["result"] = {
                    "ok": False,
                    "error": f"MCP command failed: {exc}",
                    "state": self.get_mcp_state(),
                }
                print(f"[ChessMCP] command failed: {exc}")
            finally:
                if isinstance(done, threading.Event):
                    done.set()
            processed += 1

    def _mcp_command_cancelled_or_expired(self, command: dict[str, object]) -> bool:
        if bool(command.get("cancelled")):
            return True
        expires_at = command.get("expires_at")
        if isinstance(expires_at, (int, float)) and time.monotonic() > float(expires_at):
            command["cancelled"] = True
            return True
        return False

    def _expired_mcp_command_result(self, command: dict[str, object]) -> dict[str, object]:
        side = command.get("side")
        caller_side = side if isinstance(side, bool) else None
        return {
            "ok": False,
            "timeout": True,
            "cancelled": True,
            "error": "MCP command timed out before it could be processed",
            "state": self.get_mcp_state(caller_side=caller_side),
        }

    def _handle_mcp_command(self, command: dict[str, object]) -> dict[str, object]:
        kind = command.get("kind")
        if kind == "move":
            side = command.get("side")
            if not isinstance(side, bool):
                return {"ok": False, "error": "MCP move command has no seat side", "state": self.get_mcp_state()}
            return self._apply_mcp_move(str(command.get("move", "")), side=side)
        return {"ok": False, "error": f"Unknown MCP command kind: {kind}", "state": self.get_mcp_state()}

    def _apply_mcp_move(self, move_text: str, *, side: bool) -> dict[str, object]:
        with self._mcp_state_lock:
            if self._state == STATE_GAME_OVER or self._board.is_game_over():
                return {"ok": False, "error": "game is over", "state": self.get_mcp_state(caller_side=side)}

            actor = MoveActor.agent(side)
            turn_authorization = self._session.can_move_now(
                actor=actor,
                board=self._board,
                game_state=self._state,
            )
            if not turn_authorization.ok:
                print(f"[ChessMCP] rejected move request from {actor.event_label()}: {turn_authorization.error}")
                return {
                    "ok": False,
                    "error": turn_authorization.error,
                    "state": self.get_mcp_state(caller_side=side),
                }

            move = self._parse_mcp_move(move_text)
            if move is None:
                return {
                    "ok": False,
                    "error": f"illegal or unparseable move: {move_text}",
                    "state": self.get_mcp_state(caller_side=side),
                }

            authorization = self._session.can_make_move(
                actor=actor,
                board=self._board,
                game_state=self._state,
                move=move,
            )
            if not authorization.ok:
                print(f"[ChessMCP] rejected move {move.uci()}: {authorization.error}")
                return {"ok": False, "error": authorization.error, "state": self.get_mcp_state(caller_side=side)}

            self._execute_move(move, actor=actor)
            return {"ok": True, "move": move.uci(), "state": self.get_mcp_state(caller_side=side)}

    def _parse_mcp_move(self, move_text: str) -> chess.Move | None:
        try:
            move = chess.Move.from_uci(move_text)
        except ValueError:
            move = None
        if move is not None and move in self._board.legal_moves:
            return move

        try:
            move = self._board.parse_san(move_text)
        except ValueError:
            return None
        return move if move in self._board.legal_moves else None

    def _mcp_status(self) -> str:
        if self._board.is_checkmate():
            winner = "black" if self._board.turn == chess.WHITE else "white"
            return f"checkmate:{winner}"
        if self._board.is_stalemate():
            return "stalemate"
        if self._board.is_insufficient_material():
            return "draw:insufficient_material"
        if self._board.can_claim_threefold_repetition():
            return "draw:threefold_repetition_claim_available"
        if self._board.can_claim_fifty_moves():
            return "draw:fifty_move_claim_available"
        if self._board.is_check():
            return "check"
        return "playing"

    def _last_mcp_move_event(self) -> dict[str, object] | None:
        with self._mcp_condition:
            for event in reversed(self._mcp_events):
                if event.get("type") == "move":
                    return dict(event)
        return None

    def _record_mcp_event(self, event: dict[str, object]) -> None:
        with self._mcp_state_lock:
            payload = dict(event)
            payload["id"] = self._mcp_next_event_id
            payload["fen"] = self._board.fen()
            payload["turn"] = "white" if self._board.turn == chess.WHITE else "black"
            payload["ply"] = len(self._board.move_stack)
            payload["status"] = self._mcp_status()

            with self._mcp_condition:
                self._mcp_events.append(payload)
                if len(self._mcp_events) > self._mcp_max_events:
                    del self._mcp_events[:len(self._mcp_events) - self._mcp_max_events]
                self._mcp_next_event_id += 1
                self._mark_state_dirty()
                self._mcp_condition.notify_all()

    def _create_highlight_materials(self):
        print("[Chess] Loading highlight materials...")
        self._highlight_selected = TcMaterial.from_name("SelectedMaterial")
        print(f"[Chess]   SelectedMaterial: {self._highlight_selected}, valid={self._highlight_selected.is_valid if self._highlight_selected else False}")

        self._highlight_valid = TcMaterial.from_name("ValidMoveMaterial")
        print(f"[Chess]   ValidMoveMaterial: {self._highlight_valid}, valid={self._highlight_valid.is_valid if self._highlight_valid else False}")

        self._highlight_last_move = TcMaterial.from_name("LastMoveMaterial")
        print(f"[Chess]   LastMoveMaterial: {self._highlight_last_move}, valid={self._highlight_last_move.is_valid if self._highlight_last_move else False}")

        self._highlight_check = TcMaterial.from_name("CheckMaterial")
        print(f"[Chess]   CheckMaterial: {self._highlight_check}, valid={self._highlight_check.is_valid if self._highlight_check else False}")

    def _scan_board(self):
        print("[Chess] Scanning board tiles...")
        scene = self.entity.scene
        print(f"[Chess]   scene={scene}")
        self._board_entity = scene.find_entity_by_name("ChessBoard")
        if self._board_entity is None:
            print("[Chess]   ERROR: ChessBoard entity not found!")
            return
        print(f"[Chess]   Found ChessBoard entity: {self._board_entity.name}")
        children = self._board_entity.children()
        print(f"[Chess]   ChessBoard has {len(children)} children")
        for child in children:
            if child.name == "BoardCoordinates":
                continue
            sq = tile_name_to_square(child.name)
            if sq:
                self._tiles[sq] = child
                mr = self._get_mesh_renderer_ref(child)
                if mr:
                    mat = mr.get_field("material")
                    self._original_materials[sq] = mat
                else:
                    print(f"[Chess]   WARNING: tile {child.name} ({sq}) has no MeshRenderer")
            else:
                print(f"[Chess]   WARNING: could not parse tile name '{child.name}'")
        print(f"[Chess]   Scanned {len(self._tiles)} tiles, {len(self._original_materials)} materials saved")

    def _scan_pieces(self):
        print("[Chess] Scanning pieces...")
        scene = self.entity.scene
        self._units_entity = scene.find_entity_by_name("ChessUnits")
        self._pieces.clear()
        if self._units_entity is None:
            print("[Chess]   ERROR: ChessUnits entity not found!")
            return
        print(f"[Chess]   Found ChessUnits entity: {self._units_entity.name}")
        children = self._units_entity.children()
        print(f"[Chess]   ChessUnits has {len(children)} children")
        for child in children:
            pos = child.transform.local_position()
            sq = entity_to_square(child)
            print(f"[Chess]   piece '{child.name}' pos=({pos.x:.1f},{pos.y:.1f},{pos.z:.1f}) -> square={sq}")
            if sq:
                self._pieces[sq] = child
            else:
                print(f"[Chess]   WARNING: could not map piece '{child.name}' to square")
        print(f"[Chess]   Scanned {len(self._pieces)} pieces")

    @staticmethod
    def _get_mesh_renderer_ref(entity):
        """Get MeshRenderer as TcComponentRef (has get_field/set_field)."""
        return entity.get_tc_component("MeshRenderer")

    def _is_ancestor_of(self, entity, ancestor_name: str) -> bool:
        current = entity.parent
        while current is not None:
            if current.name == ancestor_name:
                return True
            current = current.parent
        return False

    def on_mouse_button(self, event):
        print("[Chess] On mouse button")
        if event.button != MouseButton.LEFT or event.action != Action.PRESS:
            return
        if not self._game_started:
            print("[Chess] Game has not started, ignoring board click.")
            return
        if self._state == STATE_GAME_OVER:
            print("[Chess] Game is over, ignoring click.")
            return
        authorization = self._session.can_move_now(
            actor=MoveActor.human(),
            board=self._board,
            game_state=self._state,
        )
        if not authorization.ok:
            print(f"[Chess] Player click ignored: {authorization.error}")
            return

        print(f"[Chess] --- LEFT CLICK at pixel ({event.x:.0f}, {event.y:.0f}) ---")

        ray = event.viewport.screen_point_to_ray(event.x, event.y)
        if ray is None:
            print("[Chess]   screen_point_to_ray returned None, no camera?")
            return
        print(f"[Chess]   ray origin=({ray.origin.x:.2f},{ray.origin.y:.2f},{ray.origin.z:.2f}) dir=({ray.direction.x:.2f},{ray.direction.y:.2f},{ray.direction.z:.2f})")

        scene = event.viewport.scene
        collision_world = CollisionWorld.from_scene(scene)
        if collision_world is None:
            print("[Chess]   ERROR: scene has no CollisionWorld extension")
            return

        hit = collision_world.raycast_closest(ray)
        if hit is None or not hit.hit():
            print("[Chess]   raycast: no hit -> clearing selection")
            self._clear_selection()
            return

        try:
            hit_entity = hit.collider.transform().entity
        except Exception as exc:
            print(f"[Chess]   ERROR: raycast hit collider has no attached entity: {exc}")
            self._clear_selection()
            return

        if hit_entity is None:
            print("[Chess]   raycast: hit valid but attached entity is None -> clearing selection")
            self._clear_selection()
            return

        print(f"[Chess]   raycast hit: entity='{hit_entity.name}' distance={hit.distance:.3f}")

        # Walk up parents for debug
        p = hit_entity.parent
        parents = []
        while p is not None:
            parents.append(p.name)
            p = p.parent
        print(f"[Chess]   hit entity parents: {' -> '.join(parents) if parents else '(root)'}")

        square = None
        if self._is_ancestor_of(hit_entity, "ChessUnits"):
            square = entity_to_square(hit_entity)
            print(f"[Chess]   identified as PIECE entity -> square={square}")
        elif self._is_ancestor_of(hit_entity, "ChessBoard"):
            square = tile_name_to_square(hit_entity.name)
            print(f"[Chess]   identified as TILE entity '{hit_entity.name}' -> square={square}")
        else:
            print("[Chess]   hit entity is NOT a child of ChessUnits or ChessBoard -> ignoring")
            return

        if square is None:
            print("[Chess]   could not determine square -> clearing selection")
            self._clear_selection()
            return

        self._handle_click(square)

    def _handle_click(self, square: str):
        authorization = self._session.can_move_now(
            actor=MoveActor.human(),
            board=self._board,
            game_state=self._state,
        )
        if not authorization.ok:
            print(f"[Chess]   ignoring click on {square}: {authorization.error}")
            return

        sq_index = chess.parse_square(square)
        piece = self._board.piece_at(sq_index)
        turn_str = "WHITE" if self._board.turn else "BLACK"
        print(f"[Chess]   handle_click: square={square}, piece={piece}, state={self._state}, turn={turn_str}")

        if self._state == STATE_IDLE:
            if piece and piece.color == self._board.turn:
                print(f"[Chess]   -> selecting own piece {piece} at {square}")
                self._select_piece(square)
            else:
                print(f"[Chess]   -> idle, no own piece at {square} (piece={piece}), ignoring")
        elif self._state == STATE_SELECTED:
            if piece and piece.color == self._board.turn:
                print(f"[Chess]   -> reselecting own piece {piece} at {square}")
                self._clear_highlight()
                self._select_piece(square)
                return

            matching_moves = self._matching_valid_moves(self._selected_square, square)
            if self._has_promotion_choices(matching_moves):
                self._set_pending_promotion(self._selected_square, square, matching_moves)
                return

            move = self._preferred_move(matching_moves)
            if move:
                print(f"[Chess]   -> valid move found: {move.uci()}")
                self._execute_move(move, actor=MoveActor.human())
            else:
                print(f"[Chess]   -> {square} is not a valid move from {self._selected_square}, clearing")
                self._clear_selection()

    def _select_piece(self, square: str):
        self._pending_promotion = None
        self._selected_square = square
        self._state = STATE_SELECTED
        self._valid_moves = [
            m for m in self._board.legal_moves
            if chess.square_name(m.from_square) == square
        ]
        move_strs = [m.uci() for m in self._valid_moves]
        print(f"[Chess]   selected {square}, valid moves ({len(self._valid_moves)}): {move_strs}")
        self._apply_highlight()
        self._mark_state_dirty()

    def _matching_valid_moves(self, from_sq: str | None, to_sq: str) -> list[chess.Move]:
        if from_sq is None:
            return []
        matching_moves = []
        for move in self._valid_moves:
            if (chess.square_name(move.from_square) == from_sq and
                    chess.square_name(move.to_square) == to_sq):
                matching_moves.append(move)
        return matching_moves

    @staticmethod
    def _has_promotion_choices(moves: list[chess.Move]) -> bool:
        return len(moves) > 1 and any(move.promotion is not None for move in moves)

    @staticmethod
    def _preferred_move(matching_moves: list[chess.Move]) -> chess.Move | None:
        for move in matching_moves:
            if move.promotion == chess.QUEEN:
                return move
        return matching_moves[0] if matching_moves else None

    def _set_pending_promotion(self, from_sq: str | None, to_sq: str, moves: list[chess.Move]) -> None:
        if from_sq is None:
            return
        choices = []
        by_piece = {move.promotion: move for move in moves if move.promotion is not None}
        for piece_type, label in PROMOTION_CHOICES:
            move = by_piece.get(piece_type)
            if move is None:
                continue
            choices.append(
                {
                    "piece": chess.piece_name(piece_type),
                    "label": label,
                    "uci": move.uci(),
                    "san": self._board.san(move),
                }
            )
        self._pending_promotion = {
            "pending": True,
            "from": from_sq,
            "to": to_sq,
            "choices": choices,
        }
        print(f"[Chess] promotion pending: {from_sq}->{to_sq}, choices={[choice['piece'] for choice in choices]}")
        self._mark_state_dirty()
        self._notify_ui()

    def _apply_highlight(self):
        self._refresh_board_highlights()

    def _refresh_board_highlights(self):
        self._clear_highlight()
        if self._last_move_squares is not None:
            for sq in self._last_move_squares:
                self._set_tile_material(sq, self._highlight_last_move, "LAST MOVE")

        if self._check_square is not None:
            self._set_tile_material(self._check_square, self._highlight_check, "CHECK")

        if self._selected_square and self._selected_square in self._tiles:
            self._set_tile_material(self._selected_square, self._highlight_selected, "SELECTED")

        for move in self._valid_moves:
            to_name = chess.square_name(move.to_square)
            self._set_tile_material(to_name, self._highlight_valid, "VALID")

        valid_sqs = [chess.square_name(m.to_square) for m in self._valid_moves]
        print(
            "[Chess]   board highlights: "
            f"last={self._last_move_squares}, check={self._check_square}, "
            f"selected={self._selected_square}, valid={valid_sqs}"
        )

    def _set_tile_material(self, square: str, material: object | None, label: str) -> bool:
        if material is None:
            return False
        if square not in self._tiles:
            return False
        tile = self._tiles[square]
        mr = self._get_mesh_renderer_ref(tile)
        if not mr:
            print(f"[Chess]   WARNING: tile {square} has no MeshRenderer for {label} highlight")
            return False
        mr.set_field("material", material)
        dirty = getattr(self, "_dirty_highlight_squares", None)
        if dirty is None:
            dirty = set()
            self._dirty_highlight_squares = dirty
        dirty.add(square)
        return True

    def _clear_highlight(self):
        restored = 0
        dirty = getattr(self, "_dirty_highlight_squares", set())
        for sq in list(dirty):
            mat = self._original_materials.get(sq)
            if mat is None or sq not in self._tiles:
                continue
            tile = self._tiles[sq]
            mr = self._get_mesh_renderer_ref(tile)
            if mr:
                mr.set_field("material", mat)
                restored += 1
        dirty.clear()
        print(f"[Chess]   cleared highlight, restored {restored} tile materials")

    def _clear_selection(self):
        print(f"[Chess]   clearing selection (was: {self._selected_square})")
        self._pending_promotion = None
        self._selected_square = None
        self._valid_moves = []
        self._state = STATE_IDLE
        self._refresh_board_highlights()
        self._mark_state_dirty()

    def _execute_move(self, move: chess.Move, trigger_bot: bool = True, actor: MoveActor | None = None) -> bool:
        with self._mcp_state_lock:
            if actor is None:
                actor = MoveActor.human()
            authorization = self._session.can_make_move(
                actor=actor,
                board=self._board,
                game_state=self._state,
                move=move,
            )
            if not authorization.ok:
                print(f"[Chess] rejected move {move.uci()} from {actor.event_label()}: {authorization.error}")
                return False

            from_sq = chess.square_name(move.from_square)
            to_sq = chess.square_name(move.to_square)
            san = self._board.san(move)
            print(f"[Chess] === EXECUTING MOVE: {move.uci()} ({from_sq} -> {to_sq}) ===")

            visual_move_ok = False
            if self._board.is_castling(move):
                print("[Chess]   move type: CASTLING")
                visual_move_ok = self._do_castling(move)
            elif self._board.is_en_passant(move):
                print("[Chess]   move type: EN PASSANT")
                visual_move_ok = self._do_en_passant(move)
            elif move.promotion:
                print(f"[Chess]   move type: PROMOTION to {chess.piece_name(move.promotion)}")
                visual_move_ok = self._do_promotion(move)
            else:
                is_capture = to_sq in self._pieces
                print(f"[Chess]   move type: {'CAPTURE' if is_capture else 'NORMAL'}")
                visual_move_ok = self._do_normal_move(move)

            if not visual_move_ok:
                print(f"[Chess] ERROR: visual move failed for {move.uci()}, logical board was not advanced")
                self._scan_pieces()
                self._mark_state_dirty()
                self._notify_ui()
                return False

            self._board.push(move)
            self._last_move_squares = (from_sq, to_sq)
            self._update_check_square()
            print(f"[Chess]   board.push done. FEN: {self._board.fen()}")
            self._clear_selection()
            self._record_mcp_event(
                {
                    "type": "move",
                    "actor": actor.event_label(),
                    "uci": move.uci(),
                    "san": san,
                    "from": from_sq,
                    "to": to_sq,
                    "promotion": chess.piece_name(move.promotion) if move.promotion else None,
                }
            )

            turn_str = "White" if self._board.turn else "Black"
            if self._board.is_checkmate():
                winner = "Black" if self._board.turn else "White"
                print(f"[Chess] *** CHECKMATE! {winner} wins! ***")
                self._state = STATE_GAME_OVER
            elif self._board.is_stalemate():
                print("[Chess] *** STALEMATE! Draw. ***")
                self._state = STATE_GAME_OVER
            elif self._board.is_check():
                print(f"[Chess] CHECK! {turn_str} to move.")
            else:
                print(f"[Chess] {turn_str} to move.")

            self._mark_state_dirty()
            self._notify_ui()
            if trigger_bot:
                self._maybe_make_bot_move()
            return True

    def _update_check_square(self) -> None:
        if not self._board.is_check():
            self._check_square = None
            return
        king_square = self._board.king(self._board.turn)
        self._check_square = chess.square_name(king_square) if king_square is not None else None

    def _is_bot_turn(self) -> bool:
        return self._game_started and self._bot_enabled and self._session.can_move_now(
            actor=MoveActor.bot(),
            board=self._board,
            game_state=self._state,
        ).ok

    def _maybe_make_bot_move(self) -> None:
        if not self._is_bot_turn():
            return
        if self._bot_is_moving:
            print("[ChessBot] Bot move already in progress, skipping nested call.")
            return

        self._bot_is_moving = True
        try:
            move = self._choose_bot_move()
            if move is None:
                print("[ChessBot] No legal move found.")
                return
            print(f"[ChessBot] Selected move: {move.uci()}")
            self._execute_move(move, trigger_bot=False, actor=MoveActor.bot())
        finally:
            self._bot_is_moving = False

    def _choose_bot_move(self) -> chess.Move | None:
        legal_moves = list(self._board.legal_moves)
        if not legal_moves:
            return None

        best_score = None
        best_moves: list[chess.Move] = []
        for move in legal_moves:
            score = self._score_bot_move(move)
            if best_score is None or score > best_score:
                best_score = score
                best_moves = [move]
            elif score == best_score:
                best_moves.append(move)

        return random.choice(best_moves)

    def _score_bot_move(self, move: chess.Move) -> int:
        score = 0

        if self._move_is_checkmate(move):
            return 1_000_000

        if self._board.is_capture(move):
            captured_piece = self._captured_piece_for_move(move)
            moving_piece = self._board.piece_at(move.from_square)
            if captured_piece is not None:
                score += BOT_PIECE_VALUES[captured_piece.piece_type] * 10
            if moving_piece is not None:
                score -= BOT_PIECE_VALUES[moving_piece.piece_type]

        if move.promotion:
            score += BOT_PIECE_VALUES[move.promotion]

        if self._board.gives_check(move):
            score += 75

        return score

    def _move_is_checkmate(self, move: chess.Move) -> bool:
        self._board.push(move)
        is_checkmate = self._board.is_checkmate()
        self._board.pop()
        return is_checkmate

    def _captured_piece_for_move(self, move: chess.Move) -> chess.Piece | None:
        if self._board.is_en_passant(move):
            direction = -8 if self._board.turn == chess.WHITE else 8
            return self._board.piece_at(move.to_square + direction)
        return self._board.piece_at(move.to_square)

    def _notify_ui(self):
        """Push status to ChessUIComponent."""
        if self._ui_component is None:
            self._ui_dirty = False
            return
        turn = "White to move" if self._board.turn else "Black to move"
        status = ""
        if self._board.is_checkmate():
            winner = "Black wins!" if self._board.turn else "White wins!"
            status = f"Checkmate! {winner}"
        elif self._board.is_stalemate():
            status = "Stalemate! Draw."
        elif self._board.is_check():
            status = "Check!"
        self._ui_component.update_status(turn, status)
        self._ui_dirty = False

    def _selected_move_payloads(self) -> list[dict[str, object]]:
        moves = []
        for move in self._valid_moves:
            moves.append(
                {
                    "uci": move.uci(),
                    "san": self._board.san(move),
                    "from": chess.square_name(move.from_square),
                    "to": chess.square_name(move.to_square),
                    "promotion": chess.piece_name(move.promotion) if move.promotion else None,
                    "capture": self._board.is_capture(move),
                    "check": self._board.gives_check(move),
                }
            )
        return moves

    def _selection_hint(self) -> str | None:
        if self._selected_square is None:
            return None
        if self._pending_promotion is not None:
            return f"Choose promotion for {self._pending_promotion['from']}-{self._pending_promotion['to']}"
        if not self._valid_moves:
            return f"No legal moves from {self._selected_square}"
        for move in self._valid_moves:
            if move.promotion:
                return "Promotion: choose target square, then pick a piece."
        count = len({chess.square_name(move.to_square) for move in self._valid_moves})
        return f"{count} legal move{'s' if count != 1 else ''} from {self._selected_square}"

    def _captured_summary_payload(self) -> dict[str, object]:
        white_remaining = self._piece_counts(chess.WHITE)
        black_remaining = self._piece_counts(chess.BLACK)
        return {
            "by_white": self._missing_piece_payload(black_remaining),
            "by_black": self._missing_piece_payload(white_remaining),
        }

    def _piece_counts(self, color: bool) -> dict[int, int]:
        counts = {
            chess.PAWN: 0,
            chess.KNIGHT: 0,
            chess.BISHOP: 0,
            chess.ROOK: 0,
            chess.QUEEN: 0,
        }
        for piece_type in counts:
            counts[piece_type] = len(self._board.pieces(piece_type, color))
        return counts

    @staticmethod
    def _missing_piece_payload(remaining: dict[int, int]) -> list[dict[str, object]]:
        starting_counts = {
            chess.PAWN: 8,
            chess.KNIGHT: 2,
            chess.BISHOP: 2,
            chess.ROOK: 2,
            chess.QUEEN: 1,
        }
        payload = []
        for piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
            count = starting_counts[piece_type] - remaining[piece_type]
            if count > 0:
                payload.append(
                    {
                        "piece": chess.piece_name(piece_type),
                        "symbol": chess.Piece(piece_type, chess.WHITE).symbol().upper(),
                        "count": count,
                    }
                )
        return payload

    def _move_piece_entity(self, from_sq: str, to_sq: str) -> bool:
        if from_sq not in self._pieces:
            print(f"[Chess]   WARNING: _move_piece_entity: no piece entity at {from_sq}! pieces={sorted(self._pieces.keys())}")
            return False
        entity = self._pieces.pop(from_sq)
        world_pos = square_to_world(to_sq)
        print(f"[Chess]   moving entity '{entity.name}' from {from_sq} to {to_sq} world=({world_pos.x:.1f},{world_pos.y:.1f},{world_pos.z:.1f})")
        entity.transform.set_local_position(world_pos)
        self._pieces[to_sq] = entity
        return True

    def _capture_piece(self, sq: str) -> bool:
        if sq in self._pieces:
            entity = self._pieces.pop(sq)
            print(f"[Chess]   capturing '{entity.name}' at {sq}")
            scene = entity.scene
            if scene:
                scene.remove(entity)
            else:
                print("[Chess]   WARNING: captured entity has no scene!")
            return True
        else:
            print(f"[Chess]   WARNING: _capture_piece: no piece at {sq}")
            return False

    def _do_normal_move(self, move: chess.Move) -> bool:
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        if from_sq not in self._pieces:
            print(f"[Chess]   WARNING: no moving piece entity at {from_sq}")
            return False
        if self._board.is_capture(move) and to_sq not in self._pieces:
            print(f"[Chess]   WARNING: capture target entity missing at {to_sq}")
            return False
        if to_sq in self._pieces and not self._capture_piece(to_sq):
            return False
        return self._move_piece_entity(from_sq, to_sq)

    def _do_castling(self, move: chess.Move) -> bool:
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        rook_move: tuple[str, str] | None = None
        if move.to_square == chess.G1:
            print("[Chess]   castling: white kingside, rook h1->f1")
            rook_move = ("h1", "f1")
        elif move.to_square == chess.C1:
            print("[Chess]   castling: white queenside, rook a1->d1")
            rook_move = ("a1", "d1")
        elif move.to_square == chess.G8:
            print("[Chess]   castling: black kingside, rook h8->f8")
            rook_move = ("h8", "f8")
        elif move.to_square == chess.C8:
            print("[Chess]   castling: black queenside, rook a8->d8")
            rook_move = ("a8", "d8")
        if rook_move is None:
            return False
        rook_from, rook_to = rook_move
        if from_sq not in self._pieces or rook_from not in self._pieces:
            print(f"[Chess]   WARNING: castling entity missing king={from_sq in self._pieces}, rook={rook_from in self._pieces}")
            return False
        return self._move_piece_entity(from_sq, to_sq) and self._move_piece_entity(rook_from, rook_to)

    def _do_en_passant(self, move: chess.Move) -> bool:
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        captured_file = to_sq[0]
        captured_rank = from_sq[1]
        captured_sq = f"{captured_file}{captured_rank}"
        print(f"[Chess]   en passant: capturing pawn at {captured_sq}")

        if from_sq not in self._pieces or captured_sq not in self._pieces:
            print(f"[Chess]   WARNING: en passant entity missing mover={from_sq in self._pieces}, captured={captured_sq in self._pieces}")
            return False
        return self._capture_piece(captured_sq) and self._move_piece_entity(from_sq, to_sq)

    def _do_promotion(self, move: chess.Move) -> bool:
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        if from_sq not in self._pieces:
            print(f"[Chess]   WARNING: promotion pawn entity missing at {from_sq}")
            return False
        if self._board.is_capture(move) and to_sq not in self._pieces:
            print(f"[Chess]   WARNING: promotion capture target entity missing at {to_sq}")
            return False

        is_white = self._board.turn
        piece_type = chess.piece_name(move.promotion)
        print(f"[Chess]   promotion: creating {piece_type} at {to_sq}, is_white={is_white}")
        scene = self.entity.scene
        units_entity = scene.find_entity_by_name("ChessUnits")
        if not units_entity:
            print("[Chess]   WARNING: ChessUnits entity not found for promotion!")
            return False
        from Scripts.UnitsCreator import UnitsCreator
        uc = units_entity.get_component(UnitsCreator)
        if not uc:
            print("[Chess]   WARNING: UnitsCreator component not found on ChessUnits!")
            return False
        new_entity = uc.create_piece(piece_type, is_white, to_sq)
        if not new_entity:
            print("[Chess]   WARNING: create_piece returned None!")
            return False
        if to_sq in self._pieces and not self._capture_piece(to_sq):
            return False
        if not self._capture_piece(from_sq):
            return False
        self._pieces[to_sq] = new_entity
        print(f"[Chess]   promotion: {piece_type} entity created: '{new_entity.name}'")
        return True
