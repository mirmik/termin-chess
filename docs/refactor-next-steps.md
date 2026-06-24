# Termin Chess Refactor Next Steps

This document captures the next useful refactoring direction after the first cleanup pass:
logging cleanup, piece scene synchronization extraction, MCP runtime extraction, MCP payload typing,
and UI text helper extraction.

The code is now easier to change, but `ChessGameController` is still the main architectural pressure
point. It coordinates too many concerns: chess state, move application, UI state, MCP commands,
side ownership policy, local bot decisions, and Termin scene lifecycle.

The goal of the next refactor pass should be to keep `ChessGameController` as a thin scene/component
coordinator and move domain decisions into focused modules.

## 1. Extract Game State

Candidate module:
`Scripts/ChessGameState.py`

Goal:
Move the core game state out of `ChessGameController`.

Scope:
- Own the `chess.Board`.
- Own selection state, pending promotion state, game-started flags, last move squares, check square,
  board input errors, and game mode state.
- Provide a stable snapshot for UI and MCP payload generation.
- Avoid any dependency on Termin entities, UI widgets, or HTTP/MCP server code.

Why:
The board and surrounding state are the core source of truth. Keeping them in a focused object makes
controller logic easier to read and makes state transitions easier to test without scene stubs.

Done when:
- `ChessGameController` no longer directly owns most game-state fields.
- Game status and state snapshots can be tested without loading Termin UI/component stubs.
- Existing MCP and UI behavior stays unchanged.

## 2. Extract Move Execution

Candidate module:
`Scripts/ChessMoveExecutor.py`

Goal:
Move the move pipeline into a focused service.

Expected flow:

```text
authorize -> apply scene move -> push board -> update state -> build move event
```

Scope:
- Validate legal moves.
- Preserve the current invariant: if the visual scene move fails, `board.push()` must not happen.
- Coordinate `ChessPieceSceneSync` and `ChessGameState`.
- Return a structured result for UI/MCP callers.
- Build or expose enough information for move events.

Why:
Move execution is domain logic, not component lifecycle logic. Pulling it out reduces the risk of
breaking the board/scene consistency invariant while simplifying controller callbacks.

Done when:
- Controller move handling reads as a high-level delegation.
- Scene failure paths are covered by focused tests.
- Promotion, castling, en passant, captures, and regular moves still pass existing tests.

## 3. Extract Side Ownership Policy

Candidate module:
`Scripts/ChessSeatPolicy.py` or `Scripts/ChessSidePolicy.py`

Goal:
Centralize the rules for who owns each side and who may act.

Scope:
- Own side-owner configuration.
- Compute human, MCP-agent, and local-bot sides.
- Compute the current turn owner.
- Decide whether a caller may move.
- Produce seat metadata for UI and MCP.
- Keep reserved controls such as `new_game` and `set_bot_enabled` restricted to the UI/operator path.

Why:
Ownership rules are currently mixed with UI, MCP, bot, and controller logic. This makes mode changes
risky because one feature can accidentally loosen or block another feature's permissions.

Done when:
- MCP caller permissions can be tested without controller scene setup.
- UI and MCP both use the same ownership policy output.
- Adding a new game mode does not require changing multiple unrelated controller methods.

## 4. Extract MCP Command Handling

Candidate module:
`Scripts/ChessMcpCommandHandler.py`

Goal:
Separate command semantics from MCP queueing and HTTP/JSON-RPC transport.

Current direction:
- `ChessMcpServer` should remain the HTTP/JSON-RPC adapter.
- `ChessMcpRuntime` should own queues, events, waiting, and cached state.
- A new command handler should interpret commands and call the game API.

Scope:
- Handle commands such as `make_move`, `new_game`, `get_state`, `legal_moves`, `wait_for_move`,
  and bot controls.
- Apply caller/side policy consistently.
- Return typed result payloads.
- Keep command timeout/cancellation behavior in `ChessMcpRuntime`.

Why:
The runtime and server layers are already clearer, but command meaning is still too close to the
controller. A command handler gives MCP a stable boundary while leaving the controller focused on
scene lifecycle and user interaction.

Done when:
- `ChessGameController._process_mcp_commands()` is only a small delegation point or disappears.
- MCP command behavior is covered by focused tests.
- Existing MCP clients see no JSON contract changes.

## 5. Introduce Dataclass Snapshots Before JSON Payloads

Candidate module:
`Scripts/ChessStateSnapshot.py`

Goal:
Make internal state snapshots explicit before converting them to `TypedDict` JSON payloads.

Possible shape:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ChessStateSnapshot:
    fen: str
    turn: str
    status: str
    # ...
```

Then convert at the boundary:

```python
def to_mcp_payload(snapshot: ChessStateSnapshot) -> McpStatePayload:
    ...
```

Scope:
- Keep `TypedDict` types for serialized MCP payloads.
- Use dataclasses for internal immutable snapshots.
- Let UI and MCP consume the same snapshot data through separate formatting/serialization functions.

Why:
`TypedDict` helps document JSON shape, but internal code still passes broad `dict[str, object]`
values around. Dataclass snapshots make internal contracts easier to refactor and harder to mutate
accidentally.

Done when:
- UI and MCP state builders no longer assemble large unrelated dicts directly from controller fields.
- Snapshot tests cover important fields and state transitions.
- Serialized field names remain stable.

## 6. Reduce the Controller API Surface

Goal:
Make `ChessGameController` primarily responsible for Termin lifecycle and wiring.

Target responsibilities:
- Component lifecycle: `start`, `update`, shutdown/destruction.
- UI callbacks.
- Scene callbacks.
- Delegation to game state, move executor, side policy, MCP command handler, and scene sync.

Rule of thumb:
If a method does not need direct access to Termin entity/component lifecycle, it probably should not
live in `ChessGameController`.

Done when:
- Controller methods are mostly orchestration.
- Domain decisions live in focused modules.
- New tests can exercise game behavior without constructing a large fake controller.

## 7. Add Scenario-Level Tests

Goal:
Cover the behavior that matters across the newly separated modules.

Useful scenarios:
- Human move succeeds.
- Human move is rejected when the side is MCP-owned.
- MCP move succeeds only for the caller's side.
- Promotion flow works end to end.
- Reset/new game clears selection, promotion, events, and state cache.
- Scene visual failure prevents `board.push()`.
- Game-over blocks further moves.

These do not need to be full Termin end-to-end tests. Fake scene/controller tests are enough if they
exercise the real game modules.

## Deferred: Move Local Bot Calculation Off the Render Update Path

Do not start this yet.

Reason:
The current local bot heuristic is shallow and cheap. Moving it to a worker thread now would add
cancellation, stale-result handling, synchronization, shutdown behavior, and new-game race handling
before the bot actually needs deeper search.

Return to this when:
- bot search depth or heuristic cost causes visible frame stalls;
- the project needs stronger local bot play;
- there is a clear cancellation model for new game, menu transitions, and shutdown.

## Suggested Order

1. Extract side ownership policy.
2. Extract game state.
3. Extract move execution.
4. Extract MCP command handling.
5. Introduce dataclass snapshots.
6. Add scenario-level tests around the new boundaries.

This order keeps each step useful on its own and avoids starting the bot worker-thread task before it
has a concrete performance reason.
