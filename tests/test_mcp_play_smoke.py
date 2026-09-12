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
        packaged = os.environ.get("CHESS_SMOKE_PACKAGED") == "1"
        executable = PROJECT_ROOT / "dist/Chess-linux/Chess" if packaged else TERMIN_BIN
        launch = [] if packaged else ["play", ".", "--scene", "scene2.scene"]
        try:
            self.process = subprocess.Popen(
                [str(executable), *launch,
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
            ui._select_mode(1, "Вдвоём за доской")
        """)
        play.execute("""
            click_button("Начать новую партию")
        """)
        play.execute("""
            assert not controller.is_start_menu_visible()
            assert controller._piece_sync.piece_count == 32
            assert ui._turn_label.text == "Ход: белые"
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


def test_native_white_agent_invitation_and_black_player(tmp_path: Path) -> None:
    with PlayProcess(mode="agent_vs_agent", port=8824, session_file=tmp_path / "colors.json") as play:
        play.execute('''
            from termin.gui_native import Rect, PointerEvent, PointerEventType
            controller = scene.get_components_of_type("ChessGameController")[0]
            ui = scene.get_components_of_type("ChessUIComponent")[0]
            def click_button(text):
                document = ui._document
                widget = next(w for w in document.inspect_snapshot()["widgets"] if w["debug_name"] == text)
                bounds = document.ref(widget["handle"]).bounds_in_document
                event = PointerEvent()
                event.x, event.y = bounds.x + bounds.width / 2, bounds.y + bounds.height / 2
                event.type = PointerEventType.Down
                document.dispatch_pointer_event(event)
                event.type = PointerEventType.Up
                document.dispatch_pointer_event(event)
            ui._on_return_to_menu()
        ''')
        play.execute('click_button("Чёрные")')
        play.execute('click_button("Начать новую партию")')
        play.execute('''
            assert controller.get_game_state()["human_sides"] == ["black"]
            assert controller.get_game_state()["board_view"] == "black"
            assert ui._screen == "invite"
            assert ui._invite_side == "white"
            assert "Your side: white" in ui._memo_editor.text
            assert ui._document.set_focus(ui._memo_editor.handle)
            ui._memo_editor.caret = len(ui._memo_editor.text.encode("utf-8"))
            ui._document.dispatch_text_event("\\nОсобое пожелание: объясняй ходы.")
            assert "Особое пожелание" in ui._drafts["white"]
        ''')
        shot = tool_payload(rpc(f"http://127.0.0.1:{play.player_port}/mcp", play.player_token, 1,
                               "capture_player_screenshot", {"path": str(tmp_path / "invitation.png")}))
        assert shot['ok']
        play.execute('''
            click_button("К доске")
        ''')
        play.execute('click_button("Пригласить агента")')
        play.execute('''
            assert "Особое пожелание" in ui._memo_editor.text
            copied_invites = []
            ui._copy_text = lambda label, text: copied_invites.append(text)
            click_button("Скопировать сообщение")
            assert copied_invites == [ui._memo_editor.text]
            click_button("К доске")
        ''')
        session_path = (tmp_path / "colors.json").with_suffix(".white.json")
        cli = (PROJECT_ROOT / "dist/Chess-linux/package/modules/python/Scripts/chess_agent_cli.py"
               if os.environ.get("CHESS_SMOKE_PACKAGED") == "1" else PROJECT_ROOT / "Scripts/chess_agent_cli.py")
        import sys
        prefix = [sys.executable, str(cli), "--session", str(session_path), "--json"]
        def cli_call(*args):
            result = subprocess.run([*prefix, *args], capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stdout + result.stderr
            return json.loads(result.stdout)
        state = cli_call('status')
        assert state['caller_side'] == 'white' and state['caller_can_move']
        moved = cli_call('move', 'e2e4')
        assert moved['ok'] and moved['state']['turn'] == 'black'
        play.execute('''
            from types import SimpleNamespace
            from termin.base import Action, MouseButton
            from termin.geombase import Vec3, Rect2
            from termin.render_components import CameraComponent
            camera = scene.find_entity_by_name("GameCamera").get_component(CameraComponent)
            def board_click(x, y, z):
                projected = camera.try_project_world_point(Vec3(x, y, z), Rect2(0, 0, 1280, 710))
                controller.on_mouse_button(SimpleNamespace(viewport=viewport, button=MouseButton.LEFT,
                    action=Action.PRESS, x=projected.screen.x, y=projected.screen.y))
            board_click(0, 4, 0.5)
            assert controller._selected_square == "e7", controller._selected_square
            board_click(0, 0, 0.25)
            assert controller._board.peek().uci() == "e7e5"
            assert controller._piece_sync.piece_at("e5") is not None
            before_menu = controller.get_fen()
            before_game = controller._game_id
            ui._on_return_to_menu()
        ''')
        play.execute('click_button("Продолжить партию")')
        play.execute('''
            assert controller.get_fen() == before_menu
            assert controller._game_id == before_game
        ''')
        shot = tool_payload(rpc(f"http://127.0.0.1:{play.player_port}/mcp", play.player_token, 1,
                               "capture_player_screenshot", {"path": str(tmp_path / "black-view.png")}))
        assert shot['ok']
        ready = cli_call('wait', '--timeout', '0')
        assert ready['ready']
        assert '1. e4 e5' in cli_call('pgn')['pgn']
        play.execute('''
            for test_width, test_height in ((640, 480), (360, 640)):
                ui._viewport = (test_width, test_height)
                ui._screen = "invite"
                ui._rebuild_ui()
                document = ui._document
                document.layout_roots(Rect(0, 0, test_width, test_height))
                editor_bounds = ui._memo_editor.widget.bounds_in_document
                assert 0 <= editor_bounds.x and editor_bounds.x + editor_bounds.width <= test_width
                event = PointerEvent()
                event.type = PointerEventType.Wheel
                event.x, event.y, event.wheel_y = test_width / 2, test_height - 40, -1000
                document.dispatch_pointer_event(event)
                document.layout_roots(Rect(0, 0, test_width, test_height))
                copy_widget = next(w for w in document.inspect_snapshot()["widgets"] if w["debug_name"] == "Скопировать сообщение")
                copy_bounds = document.ref(copy_widget["handle"]).bounds_in_document
                assert 0 <= copy_bounds.y < test_height, copy_bounds.y
            ui._viewport = (1280, 710)
            ui._screen = "game"
            ui._build_ui()
        ''')


@pytest.mark.skipif(not os.environ.get('CHESS_MCP_CLIENT_PYTHON'), reason='set CHESS_MCP_CLIENT_PYTHON to a Python with mcp SDK')
def test_standard_mcp_client(tmp_path: Path):
    with PlayProcess(mode='agent_vs_agent', port=8825, session_file=tmp_path / 'sdk.json') as play:
        import urllib.error
        headers = {"Authorization": "Bearer " + play.white_token, "Content-Type": "application/json"}
        notification = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode()
        request = urllib.request.Request(str(play.session['url']), data=notification, headers=headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 202 and response.read() == b''
        for extra, expected in [({}, 405), ({"MCP-Protocol-Version": "unsupported"}, 400), ({"Origin": "https://unrelated.example"}, 403)]:
            request = urllib.request.Request(str(play.session['url']), headers={**headers, **extra})
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=5)
            assert error.value.code == expected
        result = subprocess.run([os.environ['CHESS_MCP_CLIENT_PYTHON'], str(PROJECT_ROOT / 'tests/mcp_client_probe.py'),
                                 str(play.session_file.with_suffix('.white.json'))],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
