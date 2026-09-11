from __future__ import annotations

import errno
import json
import os
import pty
import signal
import subprocess
import threading
import time
import textwrap
import urllib.request
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMIN_BIN = Path(os.environ.get("TERMIN_BIN", str(PROJECT_ROOT.parent / "termin" / "sdk" / "bin" / "termin")))


pytestmark = pytest.mark.skipif(
    os.environ.get("CHESS_PLAY_SMOKE") != "1",
    reason="set CHESS_PLAY_SMOKE=1 to run Termin play-mode MCP smoke tests",
)


def rpc(url: str, token: str, request_id: int, name: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def tool_payload(response: dict[str, object]) -> dict[str, object]:
    result = response["result"]
    assert isinstance(result, dict)
    structured = result["structuredContent"]
    assert isinstance(structured, dict)
    return structured


def wait_for_session_file(path: Path, process: subprocess.Popen[str]) -> dict[str, object]:
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            break
        time.sleep(0.1)
    raise TimeoutError(f"session file was not written: {path}")


class PlayProcess:
    def __init__(self, *, mode: str, port: int, session_file: Path) -> None:
        self.player_port = port + 10000
        self.player_token = "chess-player-smoke"
        self.session_file = session_file
        self.log_file = session_file.with_suffix(session_file.suffix + ".log")
        self.white_token = f"white-{mode}-token"
        self.black_token = f"black-{mode}-token"
        self.output = ""
        self._output_chunks: list[str] = []
        self._stopped = False
        session_file.unlink(missing_ok=True)
        self.log_file.unlink(missing_ok=True)
        self._pty_master_fd, pty_slave_fd = pty.openpty()
        self._reader_thread = threading.Thread(target=self._read_output, name=f"termin-play-{mode}-log")
        self._reader_thread.start()
        env = os.environ.copy()
        env.update(
            {
                "TERMIN_PLAYER_MCP_PORT": str(self.player_port),
                "TERMIN_PLAYER_MCP_TOKEN": self.player_token,
                "TERMIN_PLAYER_MCP_SESSION_FILE": str(session_file.with_suffix(".player.json")),
                "CHESS_MCP": "1",
                "CHESS_GAME_MODE": mode,
                "CHESS_MCP_PORT": str(port),
                "CHESS_MCP_WHITE_TOKEN": self.white_token,
                "CHESS_MCP_BLACK_TOKEN": self.black_token,
                "CHESS_MCP_SESSION_FILE": str(session_file),
            }
        )
        launch = (["run", "dev-linux"] if os.environ.get("CHESS_SMOKE_PACKAGED") == "1"
                  else ["play", ".", "--scene", "scene2.scene"])
        try:
            self.process = subprocess.Popen(
                [str(TERMIN_BIN), *launch,
                 "--mcp", "--mcp-port", str(self.player_port),
                 "--mcp-token", self.player_token,
                 "--mcp-session-file", str(session_file.with_suffix(".player.json"))],
                cwd=PROJECT_ROOT,
                env=env,
                stdout=pty_slave_fd,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            os.close(pty_slave_fd)
        try:
            self.session = wait_for_session_file(session_file, self.process)
            wait_for_session_file(session_file.with_suffix(".player.json"), self.process)
        except Exception as exc:
            self.stop(assert_clean=False)
            self._skip_if_backend_unavailable()
            raise AssertionError(f"session file was not written; player output:\n{self.output[-4000:]}") from exc

    def execute(self, script: str) -> dict[str, object]:
        result = tool_payload(rpc(
            f"http://127.0.0.1:{self.player_port}/mcp", self.player_token, 1,
            "execute_python_script", {"script": textwrap.dedent(script)},
        ))
        assert result["ok"], result.get("output", result)
        return result

    def _read_output(self) -> None:
        while True:
            try:
                data = os.read(self._pty_master_fd, 4096)
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.EBADF):
                    return
                raise
            if not data:
                return
            self._output_chunks.append(data.decode("utf-8", errors="replace"))

    def stop(self, *, assert_clean: bool = True) -> None:
        if self._stopped:
            return
        self._stopped = True
        shutdown_error = None
        if assert_clean and self.process.poll() is None:
            try:
                self.execute("request_quit(0)")
                self.process.wait(timeout=5)
            except Exception as exc:
                shutdown_error = exc
        try:
            if self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        finally:
            self._reader_thread.join(timeout=2)
            try:
                os.close(self._pty_master_fd)
            except OSError:
                pass
            self._reader_thread.join(timeout=2)
            self.output = "".join(self._output_chunks)
            self.log_file.write_text(self.output, encoding="utf-8")
            self.session_file.unlink(missing_ok=True)

        if shutdown_error is not None:
            raise AssertionError(f"player did not shut down cleanly: {self.output[-4000:]}") from shutdown_error
        if assert_clean:
            self._assert_no_fatal_python_shutdown()

    def _assert_no_fatal_python_shutdown(self) -> None:
        forbidden_fragments = (
            "Failed to prepare registered component",
            "Module runtime shutdown failed",
            "PythonComponent::start",
            "PythonComponent::update",
            "Fatal Python error",
            "PyThreadState_Get",
            "Python runtime state: finalizing",
        )
        for fragment in forbidden_fragments:
            assert fragment not in self.output, self.output[-4000:]

    def _skip_if_backend_unavailable(self) -> None:
        if "[PlayerRuntime] Failed to create backend window" in self.output:
            pytest.skip("termin play backend window is unavailable in this subprocess environment")

    def __enter__(self) -> "PlayProcess":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.stop(assert_clean=exc_type is None)


def test_play_human_vs_agent_black_waits_for_human(tmp_path: Path) -> None:
    with PlayProcess(mode="human_vs_agent", port=8821, session_file=tmp_path / "hva.json") as play:
        assert play.session["mode"] == "human_vs_agent"
        assert play.session["active_mcp_sides"] == ["black"]
        assert play.session["turn_owner"]["actor"] == "human:white"

        url = str(play.session["url"])
        state = tool_payload(rpc(url, play.black_token, 1, "get_state"))
        black_move = tool_payload(rpc(url, play.black_token, 2, "make_move", {"move": "e7e5", "timeout": 5}))
        wait = tool_payload(rpc(url, play.black_token, 3, "wait_for_move", {"timeout": 0}))

        assert state["caller_side"] == "black"
        assert state["caller_can_move"] is False
        assert state["caller_error"] == "white is controlled by human"
        assert black_move["ok"] is False
        assert black_move["error"] == "white is controlled by human"
        assert wait["ok"] is False
        assert wait["timeout"] is True
        assert wait["waiting_for"]["actor"] == "human:white"


def test_play_agent_vs_agent_alternates_side_tokens(tmp_path: Path) -> None:
    with PlayProcess(mode="agent_vs_agent", port=8822, session_file=tmp_path / "ava.json") as play:
        assert play.session["mode"] == "agent_vs_agent"
        assert play.session["active_mcp_sides"] == ["white", "black"]
        assert play.session["agents"]["white"]["active"] is True
        assert play.session["agents"]["black"]["active"] is True
        assert play.session["turn_owner"]["actor"] == "agent:white"

        url = str(play.session["url"])
        black_early = tool_payload(rpc(url, play.black_token, 1, "make_move", {"move": "e7e5", "timeout": 5}))
        white_move = tool_payload(rpc(url, play.white_token, 2, "make_move", {"move": "e2e4", "timeout": 5}))
        black_move = tool_payload(rpc(url, play.black_token, 3, "make_move", {"move": "e7e5", "timeout": 5}))

        assert black_early["ok"] is False
        assert black_early["error"] == "white is controlled by agent"
        assert white_move["ok"] is True
        assert white_move["move"] == "e2e4"
        assert white_move["state"]["turn_owner"]["actor"] == "agent:black"
        assert black_move["ok"] is True
        assert black_move["move"] == "e7e5"
        assert black_move["state"]["ply"] == 2
        assert black_move["state"]["turn_owner"]["actor"] == "agent:white"


def test_native_ui_and_scene_regeneration(tmp_path: Path) -> None:
    with PlayProcess(mode="agent_vs_agent", port=8823, session_file=tmp_path / "ui.json") as play:
        play.execute("""
            from termin.gui_native import Rect, PointerEvent, PointerEventType
            controller = scene.get_components_of_type("ChessGameController")[0]
            ui = scene.get_components_of_type("ChessUIComponent")[0]
            assert len(controller._tiles) == 64
            assert controller._piece_sync.piece_count == 32
            assert ui._ui.has_document
            assert ui._status_label is not None
            memo = next(w for w in ui._ui.document.inspect_snapshot()["widgets"]
                        if w["debug_name"] == "Copy & Paste to White Agent")
            assert memo["style_override"].value.font_size == 15
            ui._on_return_to_menu()
        """)
        play.execute("""
            assert controller.is_start_menu_visible()
            assert not ui._layout_dirty
            document = ui._ui.document
            document.layout_roots(Rect(0, 0, 1280, 710))
            def click_button(text):
                widget = next(w for w in document.inspect_snapshot()["widgets"] if w["debug_name"] == text)
                bounds = document.ref(widget["handle"]).bounds_in_document
                event = PointerEvent()
                event.x = bounds.x + bounds.width / 2
                event.y = bounds.y + bounds.height / 2
                event.type = PointerEventType.Down
                document.dispatch_pointer_event(event)
                event.type = PointerEventType.Up
                document.dispatch_pointer_event(event)
        """)
        screenshot = tool_payload(rpc(
            f"http://127.0.0.1:{play.player_port}/mcp", play.player_token, 2,
            "capture_player_screenshot", {"path": str(tmp_path / "menu.png")},
        ))
        assert screenshot["ok"], screenshot
        play.execute("""
            click_button("Local Sandbox")
        """)
        play.execute("""
            assert not controller.is_start_menu_visible()
            assert controller._piece_sync.piece_count == 32
            assert ui._turn_label.text.startswith("White to move")
            from Scripts.BoardCreator import BoardCreatorComponent
            board = scene.find_entity_by_name("ChessBoard")
            board.get_component(BoardCreatorComponent).make_board()
            controller._scan_board()
            ui._on_new_game()
            assert len(controller._tiles) == 64
            assert controller._piece_sync.piece_count == 32
            coords = next(child for child in board.children() if child.name == "BoardCoordinates")
            assert len(coords.children()) == 36
        """)
        play.execute("""
            from types import SimpleNamespace
            from termin.base import Action, MouseButton
            from termin.geombase import Vec3, Rect2
            from termin.render_components import CameraComponent
            test_camera = scene.find_entity_by_name("GameCamera").get_component(CameraComponent)
            test_viewport = viewport
            assert test_viewport is not None
            def board_click(x, y, z):
                projected = test_camera.try_project_world_point(Vec3(x, y, z), Rect2(0, 0, 1280, 710))
                controller.on_mouse_button(SimpleNamespace(
                    viewport=test_viewport, button=MouseButton.LEFT, action=Action.PRESS,
                    x=projected.screen.x, y=projected.screen.y,
                ))
            board_click(0, -6, 0.5)
            assert controller._selected_square == "e2", controller._selected_square
            board_click(0, -2, 0.25)
            assert controller._board.peek().uci() == "e2e4"
            assert controller._piece_sync.piece_at("e4") is not None
        """)
