# Termin Chess Refactor Plan

This plan lists useful follow-up refactors after the MCP state/cache and lint cleanup pass.
Each task should be small enough to run as a separate goal with its own tests.

## 1. Replace hot-path `print()` tracing with logging

Priority: high

Goal:
Move runtime diagnostics to `logging` so normal gameplay and MCP polling are not dominated by synchronous stdout writes.

Scope:
- Add module loggers in `ChessGameController`, `ChessMcpServer`, `ChessUIComponent`, `BoardCreator`, and `UnitsCreator`.
- Keep warnings/errors visible at `warning`/`error`.
- Move click/raycast/highlight/scan/move trace output to `debug`.
- Avoid expensive message construction in high-frequency paths when debug logging is disabled.

Done when:
- No hot-path gameplay code uses raw `print()`.
- Startup/editor button messages are either logging calls or intentionally documented exceptions.
- `ruff check .` and `pytest -q` pass.

## 2. Extract scene piece synchronization from `ChessGameController`

Priority: high

Goal:
Move entity scanning, movement, capture, castling, en passant, and promotion scene operations into a focused helper.

Candidate module:
`Scripts/ChessPieceSceneSync.py`

Scope:
- Own `_pieces`, `_units_entity`, piece scanning, and piece entity mutation.
- Expose methods such as `scan()`, `apply_visual_move(board, move)`, and `piece_at(square)`.
- Keep the current invariant: logical `board.push(move)` must not happen if the visual move fails.
- Add focused tests for visual failure paths using fake entities.

Done when:
- `ChessGameController` no longer contains `_move_piece_entity`, `_capture_piece`, `_do_normal_move`, `_do_castling`, `_do_en_passant`, or `_do_promotion`.
- Controller move execution reads as authorize -> apply visual move -> push board -> emit event.
- `ruff check .` and `pytest -q` pass.

## 3. Extract MCP runtime state from `ChessGameController`

Priority: medium-high

Goal:
Separate MCP queueing, event log, waiting, and cached state handling from input/scene control.

Candidate module:
`Scripts/ChessMcpRuntime.py`

Scope:
- Move command queue, condition variable, event list, next event id, server stopping flag, and state cache.
- Keep `ChessMcpServer` as the HTTP/JSON-RPC adapter.
- Keep `ChessGameController` responsible for chess rules and scene updates.
- Preserve the current public MCP payload contract.

Done when:
- Controller has no direct `queue.Queue`, `threading.Condition`, or MCP event ring-buffer fields.
- Existing MCP tests still cover `wait_for_move`, command timeout, game-over behavior, and caller-scoped state.
- `ruff check .` and `pytest -q` pass.

## 4. Type the MCP payload contract

Priority: medium

Goal:
Make the state/event payload shape explicit enough to reduce key drift and accidental contract breaks.

Scope:
- Introduce `TypedDict` definitions for legal move payloads, move/reset events, seat metadata, and MCP state.
- Extract helper functions for repeated payload construction.
- Keep serialized JSON field names stable.
- Update tests to assert important contract fields rather than relying only on broad dict access.

Done when:
- `get_mcp_state()` and `ChessMcpServer` methods use named payload types for returned dictionaries.
- No behavior changes for existing clients.
- `ruff check .` and `pytest -q` pass.

## 5. Split UI text/formatting helpers out of `ChessUIComponent`

Priority: medium

Goal:
Reduce `ChessUIComponent` size and make HUD/connection text formatting easier to test without UI stubs.

Candidate module:
`Scripts/chess_ui_text.py`

Scope:
- Move pure helpers such as owner text, turn text, status text, last move text, captures text, board orientation labels, and agent memo formatting.
- Keep widget construction in `ChessUIComponent`.
- Move or add tests against the new pure module.

Done when:
- `ChessUIComponent` mostly handles widgets and callbacks.
- Formatting tests do not need to load UI widget stubs.
- `ruff check .` and `pytest -q` pass.

## Deferred: move the local bot calculation off the render update path

Status: do not start yet

Reason:
The current bot heuristic is shallow and cheap. Moving it to a worker thread would add cancellation, stale-result, and synchronization complexity before the bot actually needs deeper search.

Return to this when:
- bot search depth or heuristic cost increases enough to cause visible frame stalls;
- the project needs stronger local bot play;
- there is a clear cancellation model for new game, return to menu, and shutdown.

Scope:
- Compute bot moves on a worker thread or task.
- Apply chosen moves back on the main/update path.
- Define cancellation behavior for new game, return to menu, and game shutdown.

Done when:
- Bot move computation cannot mutate `python-chess` board state off the main path.
- New game/menu transitions cannot apply a stale bot move.
- Focused tests cover stale/cancelled bot move behavior.
- `ruff check .` and `pytest -q` pass.

## Suggested Order

1. Logging cleanup.
2. Piece scene synchronization extraction.
3. MCP runtime extraction.
4. MCP payload typing.
5. UI text helper extraction.

Do not start the deferred bot worker task until bot strength/search depth work makes it necessary.
