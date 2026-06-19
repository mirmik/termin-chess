from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMIN_BIN = Path(os.environ.get("TERMIN_BIN", "/home/mirmik/project/termin/sdk/bin/termin"))


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


def wait_for_session_file(path: Path) -> dict[str, object]:
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(0.1)
    raise TimeoutError(f"session file was not written: {path}")


class PlayProcess:
    def __init__(self, *, mode: str, port: int, session_file: Path) -> None:
        self.session_file = session_file
        self.white_token = f"white-{mode}-token"
        self.black_token = f"black-{mode}-token"
        env = os.environ.copy()
        env.update(
            {
                "CHESS_MCP": "1",
                "CHESS_GAME_MODE": mode,
                "CHESS_MCP_PORT": str(port),
                "CHESS_MCP_WHITE_TOKEN": self.white_token,
                "CHESS_MCP_BLACK_TOKEN": self.black_token,
                "CHESS_MCP_SESSION_FILE": str(session_file),
            }
        )
        session_file.unlink(missing_ok=True)
        self.process = subprocess.Popen(
            [str(TERMIN_BIN), "play", "."],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.session = wait_for_session_file(session_file)

    def stop(self) -> None:
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)

    def __enter__(self) -> "PlayProcess":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.stop()


def test_play_human_vs_agent_black_waits_for_human(tmp_path: Path) -> None:
    with PlayProcess(mode="human_vs_agent", port=8821, session_file=tmp_path / "hva.json") as play:
        assert play.session["mode"] == "human_vs_agent"
        assert play.session["active_mcp_sides"] == ["black"]
        assert play.session["turn_owner"]["actor"] == "human:white"

        url = str(play.session["url"])
        state = tool_payload(rpc(url, play.black_token, 1, "get_state"))
        black_move = tool_payload(rpc(url, play.black_token, 2, "make_move", {"move": "e7e5", "timeout": 5}))
        wait = tool_payload(rpc(url, play.black_token, 3, "wait_for_move", {"after_ply": 0, "timeout": 0}))

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
