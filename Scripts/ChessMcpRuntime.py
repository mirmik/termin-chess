"""Runtime state owned by the chess MCP bridge."""

from __future__ import annotations

from copy import deepcopy
import queue
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from Scripts.ChessMcpPayloads import GameStatePayload, McpEventPayload

Command = dict[str, object]


class ChessMcpRuntime:
    """Owns MCP command queue, event log, waiting, and cached state snapshots."""

    def __init__(self, *, max_events: int = 200) -> None:
        self._state_lock = threading.RLock()
        self._commands: queue.Queue[Command] = queue.Queue()
        self._condition = threading.Condition()
        self._events: list[McpEventPayload] = []
        self._next_event_id = 1
        self._max_events = max_events
        self._server_stopping = False
        self._state_revision = 0
        self._state_cache_revision = -1
        self._state_cache: GameStatePayload | None = None

    @contextmanager
    def locked(self) -> Iterator[None]:
        with self._state_lock:
            yield

    @property
    def next_event_id(self) -> int:
        return self._next_event_id

    @property
    def server_stopping(self) -> bool:
        return self._server_stopping

    def mark_state_dirty(self) -> None:
        self._state_revision += 1
        self._state_cache = None
        self._state_cache_revision = -1

    def get_state(
        self,
        build_state: Callable[[], GameStatePayload],
        apply_caller_fields: Callable[[GameStatePayload], None] | None = None,
    ) -> GameStatePayload:
        with self._state_lock:
            if self._state_cache is None or self._state_cache_revision != self._state_revision:
                cache = build_state()
                self._state_cache = cache
                self._state_cache_revision = self._state_revision
            else:
                cache = self._state_cache

            state = deepcopy(cache)
            if apply_caller_fields is not None:
                apply_caller_fields(state)
            return state

    def reset_server_stopping(self) -> None:
        with self._condition:
            self._server_stopping = False

    def notify_server_stopping(self) -> None:
        with self._condition:
            self._server_stopping = True
            self._condition.notify_all()

    def wait_for_event_change(self, observed_next_event_id: int, timeout: float) -> tuple[bool, int]:
        with self._condition:
            if not self._server_stopping and self._next_event_id == observed_next_event_id:
                self._condition.wait(timeout=timeout)
            return self._server_stopping, self._next_event_id

    def events_payload(self) -> dict[str, object]:
        with self._condition:
            return {
                "ok": True,
                "events": list(self._events),
                "next_event_id": self._next_event_id,
            }

    def last_move_event(self) -> McpEventPayload | None:
        with self._condition:
            for event in reversed(self._events):
                if event.get("type") == "move":
                    return dict(event)
        return None

    def record_event(
        self,
        event: McpEventPayload,
        *,
        fen: str,
        turn: str,
        ply: int,
        status: str,
    ) -> None:
        with self._state_lock:
            payload = dict(event)
            payload["id"] = self._next_event_id
            payload["fen"] = fen
            payload["turn"] = turn
            payload["ply"] = ply
            payload["status"] = status

            with self._condition:
                self._events.append(payload)
                if len(self._events) > self._max_events:
                    del self._events[:len(self._events) - self._max_events]
                self._next_event_id += 1
                self.mark_state_dirty()
                self._condition.notify_all()

    def submit_command(self, command: Command, *, timeout: float) -> dict[str, object] | None:
        wait_timeout = max(timeout, 0.0)
        done = threading.Event()
        command["done"] = done
        command["result"] = None
        command["cancelled"] = False
        command["expires_at"] = time.monotonic() + wait_timeout
        self._commands.put(command)
        if not done.wait(timeout=wait_timeout):
            command["cancelled"] = True
            return None
        result = command.get("result")
        return result if isinstance(result, dict) else None

    def next_command(self) -> Command | None:
        try:
            return self._commands.get_nowait()
        except queue.Empty:
            return None

    @staticmethod
    def command_cancelled_or_expired(command: Command) -> bool:
        if bool(command.get("cancelled")):
            return True
        expires_at = command.get("expires_at")
        if isinstance(expires_at, (int, float)) and time.monotonic() > float(expires_at):
            command["cancelled"] = True
            return True
        return False

    @staticmethod
    def complete_command(command: Command, result: dict[str, object]) -> None:
        command["result"] = result
        done = command.get("done")
        if isinstance(done, threading.Event):
            done.set()
