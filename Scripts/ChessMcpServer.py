"""Game-level MCP endpoint for the Chess project."""

from __future__ import annotations

import json
import math
import os
import secrets
import signal
import tempfile
import threading
import time
import atexit
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
from pathlib import Path
from typing import Any

import chess

from Scripts.ChessMcpPayloads import ConnectionPayload, GameStatePayload, UiConnectionPayload

log = logging.getLogger(__name__)

SIDE_SEAT_ALLOWED_TOOLS = frozenset(
    {
        "get_state",
        "get_connection_info",
        "legal_moves",
        "make_move",
        "wait_for_move",
        "get_pgn",
    }
)

SIDE_SEAT_RESTRICTED_TOOLS: dict[str, str] = {
    "new_game": "new_game is reserved for in-game UI or system control",
    "set_bot_enabled": "set_bot_enabled is a local sandbox/debug control and is not available to side seats",
}


@dataclass(frozen=True)
class ChessMcpConfig:
    host: str
    port: int
    white_token: str
    black_token: str
    session_file: Path


@dataclass
class McpSeatStatus:
    side: bool
    connected: bool = False
    first_seen_at: float | None = None
    last_seen_at: float | None = None
    request_count: int = 0
    last_method: str | None = None

    def mark_seen(self, *, method: str, now: float) -> None:
        if self.first_seen_at is None:
            self.first_seen_at = now
        self.connected = True
        self.last_seen_at = now
        self.request_count += 1
        self.last_method = method

    def payload(self) -> dict[str, object]:
        return {
            "side": _side_name(self.side),
            "connected": self.connected,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "request_count": self.request_count,
            "last_method": self.last_method,
        }


class ChessMcpHttpServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = False
    block_on_close = True


def chess_mcp_enabled() -> bool:
    value = os.environ.get("CHESS_MCP")
    if value is None:
        value = os.environ.get("CHESS_GAME_MCP")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_chess_mcp_config() -> ChessMcpConfig:
    host = os.environ.get("CHESS_MCP_HOST", "127.0.0.1")
    port = _env_int("CHESS_MCP_PORT", 8790)
    legacy_token = os.environ.get("CHESS_MCP_TOKEN")
    white_token = os.environ.get("CHESS_MCP_WHITE_TOKEN")
    black_token = os.environ.get("CHESS_MCP_BLACK_TOKEN")
    if white_token is None:
        white_token = secrets.token_urlsafe(24)
    if black_token is None:
        black_token = legacy_token if legacy_token is not None else secrets.token_urlsafe(24)
    default_session_file = Path(tempfile.gettempdir()) / "chess-game-mcp.json"
    session_file = Path(os.environ.get("CHESS_MCP_SESSION_FILE", str(default_session_file)))
    return ChessMcpConfig(
        host=host,
        port=port,
        white_token=white_token,
        black_token=black_token,
        session_file=session_file,
    )


class ChessGameMcpServer:
    def __init__(self, controller: Any, config: ChessMcpConfig) -> None:
        self._controller = controller
        self._config = config
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._resource_subscriptions: set[str] = set()
        self._stop_lock = threading.Lock()
        self._stopped = False
        self._atexit_registered = False
        self._previous_signal_handlers: dict[int, object] = {}
        self._started_at = time.time()
        self._session_id = secrets.token_hex(8)
        self._seat_state_lock = threading.Lock()
        self._seat_status: dict[bool, McpSeatStatus] = {
            chess.WHITE: McpSeatStatus(chess.WHITE),
            chess.BLACK: McpSeatStatus(chess.BLACK),
        }

    @property
    def url(self) -> str:
        server = self._httpd
        if server is None:
            return f"http://{self._config.host}:{self._config.port}/mcp"
        host, port = server.server_address
        return f"http://{host}:{port}/mcp"

    def start(self) -> bool:
        try:
            self._httpd = ChessMcpHttpServer(
                (self._config.host, self._config.port),
                self._make_handler(),
            )
        except OSError as exc:
            log.error("[ChessMCP] failed to bind %s:%s: %s", self._config.host, self._config.port, exc)
            return False

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="chess-game-mcp",
            daemon=False,
        )
        self._thread.start()
        self._register_atexit()
        self._install_signal_handlers()
        self._write_session_file()
        log.info("[ChessMCP] listening on %s", self.url)
        log.info("[ChessMCP] session file: %s", self._config.session_file)
        return True

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
            self._unregister_atexit()
            self._restore_signal_handlers()
            self._controller.notify_mcp_server_stopping()
            self._remove_session_file()

            server = self._httpd
            thread = self._thread
            self._httpd = None
            self._thread = None

        if server is not None:
            try:
                server.shutdown()
            except Exception:
                log.exception("[ChessMCP] failed to shutdown HTTP server")
            try:
                server.server_close()
            except Exception:
                log.exception("[ChessMCP] failed to close HTTP server")

        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if thread.is_alive():
                log.warning("[ChessMCP] HTTP server thread did not stop within 2 seconds")

    def _remove_session_file(self) -> None:
        try:
            self._config.session_file.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("[ChessMCP] failed to remove session file: %s", exc)

    def reset_session_state(self) -> None:
        """Clear live seat status for a new in-game chess session."""
        with self._seat_state_lock:
            self._session_id = secrets.token_hex(8)
            self._started_at = time.time()
            self._seat_status = {
                chess.WHITE: McpSeatStatus(chess.WHITE),
                chess.BLACK: McpSeatStatus(chess.BLACK),
            }
        self._write_session_file()

    def ui_connection_payload(self) -> UiConnectionPayload:
        state: GameStatePayload = self._controller.get_game_state()
        seat_statuses = self._seat_status_payload()
        seats = []
        active_sides = set(state["active_mcp_sides"])
        for side in (chess.WHITE, chess.BLACK):
            side_text = _side_name(side)
            status = seat_statuses[side_text]
            token = self._token_for_side(side)
            seats.append(
                {
                    "side": side_text,
                    "owner": state["side_owners"][side_text],
                    "active": side_text in active_sides,
                    "token": token,
                    "authorization": f"Bearer {token}",
                    "connected": status["connected"],
                    "last_seen_at": status["last_seen_at"],
                    "request_count": status["request_count"],
                    "last_method": status["last_method"],
                }
            )

        return {
            "ok": True,
            "url": self.url,
            "health_url": self._health_url(),
            "session_file": str(self._config.session_file),
            "session_id": self._session_id,
            "mode": state["mode"],
            "turn": state["turn"],
            "turn_owner": state["turn_owner"],
            "status": state["status"],
            "last_event": state["last_move"],
            "active_mcp_sides": state["active_mcp_sides"],
            "seats": seats,
        }

    def _register_atexit(self) -> None:
        if self._atexit_registered:
            return
        atexit.register(self.stop)
        self._atexit_registered = True

    def _unregister_atexit(self) -> None:
        if not self._atexit_registered:
            return
        try:
            atexit.unregister(self.stop)
        except ValueError:
            pass
        except Exception:
            log.exception("[ChessMCP] failed to unregister atexit cleanup")
        finally:
            self._atexit_registered = False

    def _install_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            log.warning("[ChessMCP] signal handlers are only installed from the main thread")
            return

        for signum in (signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(signum)
            self._previous_signal_handlers[signum] = previous

            def handler(received: int, frame: object, *, previous_handler: object = previous) -> None:
                log.info("[ChessMCP] received signal %s; stopping server", received)
                self.stop()
                if callable(previous_handler):
                    previous_handler(received, frame)
                    return
                if previous_handler == signal.SIG_IGN:
                    return
                raise SystemExit(128 + received)

            try:
                signal.signal(signum, handler)
            except ValueError as exc:
                log.warning("[ChessMCP] failed to install signal handler %s: %s", signum, exc)

    def _restore_signal_handlers(self) -> None:
        if not self._previous_signal_handlers:
            return
        for signum, previous in list(self._previous_signal_handlers.items()):
            try:
                signal.signal(signum, previous)
            except ValueError as exc:
                log.warning("[ChessMCP] failed to restore signal handler %s: %s", signum, exc)
        self._previous_signal_handlers.clear()

    def _write_session_file(self) -> None:
        state = self._controller.get_game_state()
        payload = {
            "pid": os.getpid(),
            "url": self.url,
            "token": self._config.black_token,
            "side": "black",
            "legacy_default_side": "black",
            "session_id": self._session_id,
            "mode": state["mode"],
            "turn": state["turn"],
            "turn_owner": state["turn_owner"],
            "status": state["status"],
            "ply": state["ply"],
            "board_input_enabled": state["board_input_enabled"],
            "board_input_error": state["board_input_error"],
            "side_owners": state["side_owners"],
            "game_seats": state["seats"],
            "mcp_seats": state["mcp_seats"],
            "active_mcp_sides": state["active_mcp_sides"],
            "tokens": {
                "white": self._config.white_token,
                "black": self._config.black_token,
            },
            "seats": [
                {
                    "side": "white",
                    "token": self._config.white_token,
                    "authorization": f"Bearer {self._config.white_token}",
                },
                {
                    "side": "black",
                    "token": self._config.black_token,
                    "authorization": f"Bearer {self._config.black_token}",
                },
            ],
            "agents": {
                "white": {
                    "active": "white" in state["active_mcp_sides"],
                    "token": self._config.white_token,
                    "authorization": f"Bearer {self._config.white_token}",
                },
                "black": {
                    "active": "black" in state["active_mcp_sides"],
                    "token": self._config.black_token,
                    "authorization": f"Bearer {self._config.black_token}",
                },
            },
            "started_at": self._started_at,
            "server": "chess-game",
            "tools": [tool["name"] for tool in self._tool_schemas()],
            "resources": [resource["uri"] for resource in self._resources()],
        }
        try:
            path = self._config.session_file
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(path)
        except OSError as exc:
            log.warning("[ChessMCP] failed to write session file: %s", exc)

    def _make_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ChessGameMCP/0.1"

            def do_GET(self) -> None:
                if self.path == "/health":
                    self._send_json({"ok": True, "server": "chess-game"})
                    return
                self.send_error(404)

            def do_POST(self) -> None:
                if self.path not in ("/mcp", "/jsonrpc"):
                    self.send_error(404)
                    return
                mcp_side = self._authorized_side()
                if mcp_side is None:
                    self._send_json(owner._rpc_error(None, -32001, "Unauthorized"), status=401)
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(length).decode("utf-8")
                    request = json.loads(body)
                except Exception as exc:
                    log.warning("[ChessMCP] invalid request JSON: %s", exc)
                    self._send_json(owner._rpc_error(None, -32700, "Parse error"))
                    return

                if isinstance(request, list):
                    responses = [
                        response
                        for item in request
                        if (response := owner._handle_rpc(item, mcp_side=mcp_side)) is not None
                    ]
                    self._send_json(responses)
                    return

                response = owner._handle_rpc(request, mcp_side=mcp_side)
                if response is None:
                    self.send_response(204)
                    self.end_headers()
                    return
                self._send_json(response)

            def log_message(self, fmt: str, *args: object) -> None:
                return

            def _authorized_side(self) -> bool | None:
                token = self._request_token()
                if token is None:
                    return None
                return owner._side_for_token(token)

            def _request_token(self) -> str | None:
                header = self.headers.get("Authorization", "")
                prefix = "Bearer "
                if header.startswith(prefix):
                    return header[len(prefix):]
                token = self.headers.get("X-Chess-MCP-Token", "")
                return token if token != "" else None

            def _send_json(self, payload: Any, *, status: int = 200) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler

    def _side_for_token(self, token: str) -> bool | None:
        if secrets.compare_digest(token, self._config.white_token):
            return chess.WHITE
        if secrets.compare_digest(token, self._config.black_token):
            return chess.BLACK
        return None

    def _handle_rpc(self, request: Any, *, mcp_side: bool) -> dict[str, object] | None:
        if not isinstance(request, dict):
            return self._rpc_error(None, -32600, "Invalid Request")

        request_id = request.get("id")
        method = request.get("method")
        method_name = method if isinstance(method, str) else "<invalid>"
        self._mark_seat_seen(mcp_side, method=method_name)
        try:
            if method == "initialize":
                return self._rpc_result(
                    request_id,
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"subscribe": True, "listChanged": False},
                        },
                        "serverInfo": {"name": "chess-game", "version": "0.1.0"},
                    },
                )
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return self._rpc_result(request_id, {})
            if method == "tools/list":
                return self._rpc_result(request_id, {"tools": self._tool_schemas()})
            if method == "tools/call":
                return self._handle_tool_call(request_id, request.get("params"), mcp_side=mcp_side)
            if method == "resources/list":
                return self._rpc_result(request_id, {"resources": self._resources()})
            if method == "resources/read":
                return self._handle_resource_read(request_id, request.get("params"), mcp_side=mcp_side)
            if method == "resources/subscribe":
                return self._handle_resource_subscribe(request_id, request.get("params"))
            if method == "resources/unsubscribe":
                return self._handle_resource_unsubscribe(request_id, request.get("params"))
            return self._rpc_error(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            log.exception("[ChessMCP] request handling failed")
            return self._rpc_error(request_id, -32603, f"Internal error: {exc}")

    def _handle_tool_call(self, request_id: object, params: object, *, mcp_side: bool) -> dict[str, object]:
        if not isinstance(params, dict):
            return self._rpc_error(request_id, -32602, "Invalid params")
        name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return self._rpc_error(request_id, -32602, "Tool arguments must be an object")

        if name in SIDE_SEAT_RESTRICTED_TOOLS:
            payload = self._restricted_tool_payload(str(name), mcp_side)
        elif name == "get_state":
            payload = self._controller.get_agent_state(caller_side=mcp_side)
        elif name == "get_connection_info":
            payload = self._connection_payload(mcp_side)
        elif name == "legal_moves":
            state = self._controller.get_agent_state(caller_side=mcp_side)
            payload = {
                "ok": True,
                "moves": state["legal_moves"],
                "legal_moves": state["legal_moves"],
                "legal_moves_san": state.get("legal_moves_san", []),
                "turn": state["turn"],
                "turn_owner": state["turn_owner"],
                "caller_side": state["caller_side"],
                "caller_can_move": state["caller_can_move"],
                "caller_error": state["caller_error"],
            }
        elif name == "make_move":
            timeout = self._timeout_argument(arguments, default=10.0)
            if timeout is None:
                return self._rpc_error(request_id, -32602, "timeout must be a non-negative finite number")
            payload = self._controller.request_mcp_move(
                str(arguments.get("move", "")),
                side=mcp_side,
                timeout=timeout,
            )
        elif name == "wait_for_move":
            timeout = self._timeout_argument(arguments, default=60.0)
            if timeout is None:
                return self._rpc_error(request_id, -32602, "timeout must be a non-negative finite number")
            payload = self._controller.wait_for_mcp_event(
                timeout=timeout,
                caller_side=mcp_side,
            )
        elif name == "get_pgn":
            payload = {"ok": True, "pgn": self._controller.get_mcp_pgn()}
        else:
            return self._rpc_error(request_id, -32602, f"Unknown tool: {name}")

        text = self._compact_json(payload)
        is_timeout = bool(payload.get("timeout") is True and payload.get("error") is None)
        return self._rpc_result(
            request_id,
            {
                "content": [{"type": "text", "text": text}],
                "isError": not (bool(payload.get("ok", True)) or is_timeout),
                "structuredContent": payload,
            },
        )

    @staticmethod
    def _compact_json(payload: object) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _timeout_argument(arguments: dict[str, object], *, default: float) -> float | None:
        value = arguments.get("timeout", default)
        if isinstance(value, bool):
            return None
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(timeout) or timeout < 0:
            return None
        return timeout

    def _handle_resource_read(self, request_id: object, params: object, *, mcp_side: bool) -> dict[str, object]:
        if not isinstance(params, dict):
            return self._rpc_error(request_id, -32602, "Invalid params")
        uri = params.get("uri")
        if not isinstance(uri, str):
            return self._rpc_error(request_id, -32602, "Resource URI must be a string")

        if uri == "chess://game/state":
            text = self._compact_json(self._controller.get_agent_state(caller_side=mcp_side))
            mime_type = "application/json"
        elif uri == "chess://game/connection":
            text = self._compact_json(self._connection_payload(mcp_side))
            mime_type = "application/json"
        elif uri == "chess://game/help":
            text = self._help_text(mcp_side)
            mime_type = "text/markdown"
        elif uri == "chess://game/pgn":
            text = self._controller.get_mcp_pgn()
            mime_type = "text/plain"
        elif uri == "chess://game/events":
            text = self._compact_json(self._controller.get_mcp_events())
            mime_type = "application/json"
        else:
            return self._rpc_error(request_id, -32002, f"Resource not found: {uri}")

        return self._rpc_result(
            request_id,
            {"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]},
        )

    def _handle_resource_subscribe(self, request_id: object, params: object) -> dict[str, object]:
        uri = self._resource_uri_param(params)
        if uri is None:
            return self._rpc_error(request_id, -32602, "Resource URI must be a string")
        if uri not in {resource["uri"] for resource in self._resources()}:
            return self._rpc_error(request_id, -32002, f"Resource not found: {uri}")
        self._resource_subscriptions.add(uri)
        return self._rpc_result(request_id, {})

    def _handle_resource_unsubscribe(self, request_id: object, params: object) -> dict[str, object]:
        uri = self._resource_uri_param(params)
        if uri is None:
            return self._rpc_error(request_id, -32602, "Resource URI must be a string")
        self._resource_subscriptions.discard(uri)
        return self._rpc_result(request_id, {})

    @staticmethod
    def _resource_uri_param(params: object) -> str | None:
        if not isinstance(params, dict):
            return None
        uri = params.get("uri")
        return uri if isinstance(uri, str) else None

    def _tool_schemas(self) -> list[dict[str, object]]:
        return [
            {
                "name": "get_state",
                "description": "Return a compact caller-aware chess position snapshot with FEN, board ASCII and legal UCI/SAN move lists.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "get_connection_info",
                "description": "Return endpoint, caller seat, mode, side ownership and resource metadata for this MCP connection.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "legal_moves",
                "description": "Return legal UCI and SAN move lists for the side to move plus caller/turn ownership.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "make_move",
                "description": "Play a legal move for the MCP seat identified by the request token. Accepts UCI such as e2e4 or SAN such as Nf3.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "move": {"type": "string"},
                        "timeout": {"type": "number", "default": 10},
                    },
                    "required": ["move"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "wait_for_move",
                "description": "Wait until the caller's side can move, or until the game ends. The response includes caller-aware state and waiting_for.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "timeout": {"type": "number", "default": 60},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_pgn",
                "description": "Return PGN move history for the current game when explicitly requested.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "new_game",
                "description": "Reset the game to the initial chess position. Side-seat MCP callers are rejected; use in-game UI or future system control.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"timeout": {"type": "number", "default": 10}},
                    "additionalProperties": False,
                },
            },
            {
                "name": "set_bot_enabled",
                "description": "Enable or disable the built-in chess bot. Side-seat MCP callers are rejected; this is a local sandbox/debug control.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "timeout": {"type": "number", "default": 10},
                    },
                    "required": ["enabled"],
                    "additionalProperties": False,
                },
            },
        ]

    @staticmethod
    def _resources() -> list[dict[str, object]]:
        return [
            {
                "uri": "chess://game/connection",
                "name": "connection",
                "title": "Chess MCP connection info",
                "description": "Endpoint, caller seat, side ownership and connection hints.",
                "mimeType": "application/json",
            },
            {
                "uri": "chess://game/help",
                "name": "help",
                "title": "Chess MCP help",
                "description": "Short usage guide for agents connected to the chess game.",
                "mimeType": "text/markdown",
            },
            {
                "uri": "chess://game/state",
                "name": "state",
                "title": "Chess game state",
                "description": "Current position, legal moves, status and last event.",
                "mimeType": "application/json",
            },
            {
                "uri": "chess://game/pgn",
                "name": "pgn",
                "title": "Chess game PGN",
                "description": "Move list for the current game.",
                "mimeType": "text/plain",
            },
            {
                "uri": "chess://game/events",
                "name": "events",
                "title": "Chess game events",
                "description": "Recent move/reset events.",
                "mimeType": "application/json",
            },
        ]

    def _connection_payload(self, mcp_side: bool) -> ConnectionPayload:
        state: GameStatePayload = self._controller.get_game_state(caller_side=mcp_side)
        caller_token = self._token_for_side(mcp_side)
        seat_statuses = self._seat_status_payload()
        seats = []
        for side in (chess.WHITE, chess.BLACK):
            caller = side == mcp_side
            side_text = _side_name(side)
            status = seat_statuses[side_text]
            seats.append(
                {
                    "side": side_text,
                    "owner": state["side_owners"][side_text],
                    "caller": caller,
                    "token": caller_token if caller else None,
                    "authorization": f"Bearer {caller_token}" if caller else None,
                    "connected": status["connected"],
                    "first_seen_at": status["first_seen_at"],
                    "last_seen_at": status["last_seen_at"],
                    "request_count": status["request_count"],
                    "last_method": status["last_method"],
                }
            )

        return {
            "ok": True,
            "server": {
                "name": "chess-game",
                "version": "0.1.0",
            },
            "session": {
                "id": self._session_id,
                "started_at": self._started_at,
            },
            "endpoint": {
                "url": self.url,
                "health_url": self._health_url(),
            },
            "session_file": str(self._config.session_file),
            "mode": state["mode"],
            "turn": state["turn"],
            "turn_owner": state["turn_owner"],
            "status": state["status"],
            "side_owners": state["side_owners"],
            "game_seats": state["seats"],
            "mcp_seats": state["mcp_seats"],
            "active_mcp_sides": state["active_mcp_sides"],
            "board_input_enabled": state["board_input_enabled"],
            "board_input_error": state["board_input_error"],
            "caller": {
                "side": state["caller_side"],
                "can_move": state["caller_can_move"],
                "error": state["caller_error"],
                "token": caller_token,
                "authorization": f"Bearer {caller_token}",
                "seat_status": seat_statuses[_side_name(mcp_side)],
            },
            "seats": seats,
            "hints": {
                "default_human_vs_agent_agent_side": "black",
                "session_token_field_alias": "black",
                "two_agent_mode_uses_one_endpoint": True,
                "use_wait_for_move_for_updates": True,
            },
            "tool_policy": self._tool_policy_payload(mcp_side),
            "tools": [tool["name"] for tool in self._tool_schemas()],
            "resources": [resource["uri"] for resource in self._resources()],
        }

    def _help_text(self, mcp_side: bool) -> str:
        connection = self._connection_payload(mcp_side)
        caller = connection["caller"]
        return "\n".join(
            [
                "# Chess Game MCP",
                "",
                f"- Endpoint: `{self.url}`",
                f"- Caller side: `{caller['side']}`",
                f"- Mode: `{connection['mode']}`",
                f"- Turn: `{connection['turn']}`",
                f"- Turn owner: `{connection['turn_owner']['actor']}`",
                f"- Caller can move now: `{caller['can_move']}`",
                f"- Active MCP sides: `{', '.join(connection['active_mcp_sides'])}`",
                "",
                "## Common Flow",
                "",
                "1. Call `get_state` or read `chess://game/state`.",
                "2. If it is not your turn, call `wait_for_move`.",
                "3. When `caller_can_move` is true, call `legal_moves` and choose a legal UCI or SAN move.",
                "4. Call `make_move` with that move.",
                "",
                "Side seats cannot call `new_game` or `set_bot_enabled`; use the in-game UI for reset/debug controls.",
                "",
                "Use `get_connection_info` or `chess://game/connection` to inspect your seat and endpoint metadata.",
            ]
        )

    def _health_url(self) -> str:
        if self.url.endswith("/mcp"):
            return f"{self.url[:-4]}/health"
        return f"{self.url}/health"

    def _token_for_side(self, side: bool) -> str:
        return self._config.white_token if side == chess.WHITE else self._config.black_token

    def _mark_seat_seen(self, side: bool, *, method: str) -> None:
        now = time.time()
        with self._seat_state_lock:
            self._seat_status[side].mark_seen(method=method, now=now)

    def _seat_status_payload(self) -> dict[str, dict[str, object]]:
        with self._seat_state_lock:
            return {
                _side_name(chess.WHITE): dict(self._seat_status[chess.WHITE].payload()),
                _side_name(chess.BLACK): dict(self._seat_status[chess.BLACK].payload()),
            }

    def _restricted_tool_payload(self, tool_name: str, mcp_side: bool) -> dict[str, object]:
        reason = SIDE_SEAT_RESTRICTED_TOOLS[tool_name]
        log.info("[ChessMCP] rejected side-seat tool %r for %s: %s", tool_name, _side_name(mcp_side), reason)
        return {
            "ok": False,
            "error": reason,
            "tool": tool_name,
            "caller_side": _side_name(mcp_side),
            "policy": self._tool_policy_payload(mcp_side),
            "state": self._controller.get_agent_state(caller_side=mcp_side),
        }

    @staticmethod
    def _tool_policy_payload(mcp_side: bool) -> dict[str, object]:
        return {
            "caller_side": _side_name(mcp_side),
            "allowed_tools": sorted(SIDE_SEAT_ALLOWED_TOOLS),
            "restricted_tools": dict(SIDE_SEAT_RESTRICTED_TOOLS),
        }

    @staticmethod
    def _rpc_result(request_id: object, result: dict[str, object]) -> dict[str, object]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _rpc_error(request_id: object, code: int, message: str) -> dict[str, object]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        log.warning("[ChessMCP] invalid %s=%r; using %s", name, value, default)
        return default

def _side_name(side: bool) -> str:
    return "white" if side == chess.WHITE else "black"
