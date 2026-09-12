#!/usr/bin/env python3
"""Chess agent client. Runs without Termin, python-chess or an MCP installation."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.request


class ClientError(Exception):
    pass


def write_private_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("expected an object")
        return result
    except (OSError, ValueError) as exc:
        raise ClientError(f"Cannot read {path}: {exc}") from exc


class ChessClient:
    def __init__(self, session_file: Path):
        self.session_file = session_file
        self.session = read_json(session_file)
        if self.session.get("side") not in ("white", "black") or not self.session.get("token") or not self.session.get("url"):
            raise ClientError("Use the side-specific invitation file supplied by the game.")
        if "tokens" in self.session:
            raise ClientError("This is an operator file. Use its .white.json or .black.json invitation instead.")
        self.cache_file = session_file.with_suffix(".position.json")

    def call(self, name: str, arguments: dict | None = None, *, timeout: float = 15) -> dict:
        request = urllib.request.Request(
            self.session["url"],
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": arguments or {}}}).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                     "MCP-Protocol-Version": "2025-06-18", "Authorization": f"Bearer {self.session['token']}"},
        )
        try:
            # A local connection must not be routed through a shell's HTTP proxy.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=timeout) as response:
                rpc = json.load(response)
        except urllib.error.HTTPError as exc:
            raise ClientError(f"Game returned HTTP {exc.code}. Check that your invitation is current.") from exc
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise ClientError("Cannot reach the game. Keep it running and check the invitation.") from exc
        if "error" in rpc:
            raise ClientError(str(rpc["error"].get("message", "Protocol error")))
        payload = rpc.get("result", {}).get("structuredContent")
        if not isinstance(payload, dict):
            raise ClientError("Game returned an invalid response.")
        return payload

    def run(self, command: str, *, move: str | None = None, timeout: float = 60) -> dict:
        if command in ("connect", "status"):
            result = self.call("get_state")
        elif command == "wait":
            if self.cache_file.exists() and read_json(self.cache_file).get("game_id") != self.session.get("game_id"):
                raise ClientError("The game changed. Get a new invitation and read its position with status.")
            args = {"timeout": timeout, "game_id": self.session.get("game_id")}
            result = self.call("wait_for_move", args, timeout=timeout + 5)
        elif command == "move":
            if not self.cache_file.exists():
                raise ClientError("Read the position with status or wait before choosing a move.")
            position = read_json(self.cache_file)
            if position.get("game_id") != self.session.get("game_id"):
                raise ClientError("The game changed. Get a new invitation and read its position.")
            if not position.get("caller_can_move"):
                raise ClientError("It is not your turn. Use wait to receive your next position.")
            result = self.call("make_move", {"move": move, "game_id": position["game_id"],
                                             "expected_fen": position["fen"], "timeout": 10})
        elif command == "pgn":
            result = self.call("get_pgn")
        else:
            raise ClientError(f"Unknown command: {command}")
        state = result.get("state", result)
        if "fen" in state and (result.get("ok") or result.get("timeout")):
            if state.get("caller_side") != self.session["side"]:
                raise ClientError("Server returned a different seat from the invitation.")
            if state.get("game_id") != self.session.get("game_id"):
                raise ClientError("The invitation belongs to another game. Get a new invitation.")
            try:
                write_private_json(self.cache_file, state)
            except OSError as exc:
                raise ClientError(f"Cannot save the position: {exc}") from exc
        return result


def human_text(payload: dict) -> str:
    if "pgn" in payload:
        return str(payload["pgn"])
    state = payload.get("state", payload)
    lines = []
    if payload.get("error"):
        lines.append(str(payload["error"]))
    if payload.get("timeout"):
        lines.append("Still waiting. Run wait again.")
    if "fen" not in state:
        return "\n".join(lines) or json.dumps(payload)
    lines.extend([f"You: {state['caller_side']} | Turn: {state['turn']} | {state['status']}",
                  "Your move." if state["caller_can_move"] else ("Game over." if state["game_over"] else "Wait for your turn."),
                  str(state["board_ascii"]), f"FEN: {state['fen']}"])
    if state.get("last_move"):
        lines.append(f"Last move: {state['last_move']['san']}")
    if state["caller_can_move"]:
        lines.append("Legal UCI: " + " ".join(state["legal_moves"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, type=Path, help="Your side's invitation JSON file")
    parser.add_argument("--json", action="store_true", help="Print a structured response")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("connect", "status", "pgn"):
        sub.add_parser(command)
    waiter = sub.add_parser("wait", help="Wait for your turn or the end of the game")
    waiter.add_argument("--timeout", type=float, default=60)
    mover = sub.add_parser("move", help="Play UCI or SAN against the position you last read")
    mover.add_argument("move")
    args = parser.parse_args(argv)
    try:
        timeout = getattr(args, "timeout", 60)
        if not math.isfinite(timeout) or not 0 <= timeout <= 300:
            raise ClientError("Timeout must be between 0 and 300 seconds.")
        payload = ChessClient(args.session).run(args.command, move=getattr(args, "move", None), timeout=timeout)
        code = 0 if payload.get("ok", False) or (payload.get("timeout") and not payload.get("error")) else 1
    except ClientError as exc:
        payload = {"ok": False, "error": str(exc)}
        code = 1
    print(json.dumps(payload, ensure_ascii=False) if args.json else human_text(payload))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
