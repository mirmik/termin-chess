# Chess Game Design

This document describes the target shape of the Chess sample game for Termin.
The goal is not to re-document chess rules. The goal is to define the game shell,
agent connection model, MCP contract, and player-facing UX needed to make this
project a useful end-to-end Termin sample.

## Goals

- Present Chess as a normal playable game, not only as a technical scene.
- Support local human play against an MCP-connected agent.
- Support agent-vs-agent games launched from the game itself.
- Keep the game-level MCP separate from Termin editor/player diagnostic MCP.
- Make side ownership explicit so clients can only move for their assigned side.
- Make connection instructions visible in-game and simple enough to hand to an
  agent.
- Keep all game state authoritative in the running Chess scene.

## Non-Goals

- Implement a strong built-in chess engine.
- Explain chess rules or teach chess.
- Reuse the editor diagnostic MCP as the game API.
- Support internet-exposed multiplayer. The default endpoint remains loopback.
- Add persistence, ratings, clocks, or matchmaking in the first polished version.

## First-Run Experience

When the scene starts, the player sees a start menu instead of immediately
playing a live board.

The menu provides these primary actions:

- Start Game With Agent
- Start Two-Agent Game
- Local Sandbox
- Quit

The board can remain visible behind the menu, but input into the board is locked
until a mode starts.

Current implementation: when no explicit runtime mode is provided, the scene
starts with the menu open, the board is visible, and board clicks are ignored
until a mode button is pressed. `CHESS_MCP=1` or `CHESS_GAME_MODE=...` still
starts directly in a mode for automated MCP smoke runs.

## Game Modes

### Human vs Agent

The user plays one side in the Termin window. An MCP client controls the other
side.

Default setup:

- Human: white
- Agent: black
- Built-in bot: disabled
- Board input: enabled only for the human side and only when it is the human
  side's turn

The setup UI may later allow color selection. For the first polished version,
white-for-human is acceptable if the menu text makes it explicit.

After the user clicks Start Game With Agent:

1. The game creates or enables a game MCP server.
2. The UI shows a connection panel with endpoint details.
3. The game waits for an agent to connect or for the user to make the first move,
   depending on side assignment.
4. The agent uses MCP tools to observe state, wait for user moves, and make its
   own moves.

Current implementation: the menu button starts a fresh Human vs Agent game,
disables the built-in bot, assigns human to white and MCP agent to black, and
starts the game MCP server. `get_state`, `legal_moves`, `get_connection_info`,
and `wait_for_move` expose `turn_owner`/`waiting_for` so the connected black
agent can distinguish "waiting for human:white" from "agent:black can move".

### Two-Agent Game

The game exposes two logical seats: white agent and black agent. Human board
input is disabled except for menu controls.

Two implementation options are acceptable:

- One MCP endpoint with two join tokens, one token per side.
- Two MCP endpoints, one for each side.

The preferred first version is one endpoint with side-scoped seat tokens. This
keeps session discovery simpler and makes all tools/resources available through
one server while preserving move authorization.

After the user clicks Start Two-Agent Game:

1. The game starts a new board.
2. The game creates white and black agent seats.
3. The UI shows a connection panel for both seats.
4. Each agent receives only its own side token.
5. The game waits for moves from the side to move.

Current implementation: the menu button starts a fresh Two-Agent Game with both
MCP seats active and local board movement disabled by side ownership. Both
agents use one endpoint with side-scoped bearer tokens from the session file:
`agents.white.authorization` and `agents.black.authorization`.

### Local Sandbox

This mode is for manual testing. Both colors can be moved by the local user. MCP
can be disabled by default here.

Local Sandbox replaces the current always-live scene behavior and is useful when
debugging board geometry, clicking, piece movement, or UI without an agent.

Current implementation: the menu button starts a fresh local sandbox game with
both sides assigned to the local human and no MCP server. The same mode can be
forced for smoke/manual runs with `CHESS_GAME_MODE=local_sandbox`.

## Connection Panel

The connection panel appears after starting an MCP-backed mode.

For Human vs Agent, it shows:

- Mode: Human vs Agent
- Human side
- Agent side
- MCP URL
- Token or path to the session file
- A short command snippet for an agent/operator
- Connection status
- Last move/event id

For Two-Agent Game, it shows one section per seat:

- White agent URL
- White token or session file key
- Black agent URL
- Black token or session file key
- Seat connection status
- Current turn

The panel should avoid relying on clipboard commands as the only path. Copy
buttons are useful, but the values must also be visible.

Current implementation: MCP-backed game modes show a connection section in the
right game panel. It includes the endpoint URL, session file path, current
turn/status, last event, active MCP seat status, and copy buttons for URL,
session file, and active seat tokens. In Two-Agent Game both active seats are
shown.

## Board Input Rules

The controller must have a clear game mode and side ownership model.

Human board input is accepted only when:

- The game mode allows human input.
- The clicked piece belongs to a human-controlled side.
- The selected side is the side to move.
- The game is not over.

MCP moves are accepted only when:

- The token maps to a seat.
- The seat owns the side to move.
- The requested move is legal.
- The game is not over.

These checks should happen before move parsing/mutation whenever possible so
errors are clear and do not create partial UI state.

## MCP Seat Model

The MCP server resolves the caller seat from the bearer token. The current
implementation writes separate white and black side tokens to the session file;
the legacy `token` field is an alias for the black seat.

Suggested concepts:

- `GameMode`: `local_sandbox`, `human_vs_agent`, `agent_vs_agent`,
  `human_vs_bot`
- `SideOwner`: `human`, `agent`, `local_bot`, `none`
- `PlayerSeat`: side, owner, player-facing label
- `McpSeat`: side, token, display name, connected flag, last seen timestamp
- `MoveActor`: `human`, `agent:white`, `agent:black`, `bot`, `system`

In Human vs Agent, the black side token is the active agent seat by default. In
Two-Agent Game, both side tokens become active agent seats.

The server should keep the public endpoint stable while resolving the seat from
the bearer token.

Current implementation:

- `ChessGameSession` owns the authoritative mode, player seats, MCP seat
  activation, and move authorization.
- `get_state`, the session file, and `get_connection_info` expose
  `side_owners`, `seats`, `mcp_seats`, `active_mcp_sides`, `turn_owner`, and
  the local `board_input_enabled` gate.
- Runtime mode can be forced before the start menu exists with
  `CHESS_GAME_MODE=local_sandbox|human_vs_agent|agent_vs_agent|human_vs_bot`.
- `CHESS_AGENT_SIDE=white|black` selects the agent side for `human_vs_agent`;
  default is black.
- `CHESS_BOT_COLOR=white|black` selects the built-in bot side for
  `human_vs_bot`; default is black.

## MCP Tools

Existing tools remain useful, but their semantics need side ownership.

### `get_state`

Returns the full public position snapshot plus caller-specific seat metadata.

Important fields:

- FEN
- board ASCII
- turn
- turn owner
- legal moves for side to move
- game status
- last move
- next event id
- mode
- side owners
- human, agent and local bot side lists
- board input enabled/error for local clicks
- caller seat, if authenticated as a seat
- whether caller can move now

### `legal_moves`

Returns legal moves as parallel UCI and SAN string lists. If called by a side-scoped seat, it should indicate whether
the seat is allowed to play any of them now.

### `make_move`

Attempts to make a move for the authenticated seat.

Required behavior:

- Reject if no seat owns the side to move.
- Reject if the caller's seat side is not the side to move.
- Reject illegal UCI/SAN.
- Include current state on both success and failure.

### `wait_for_move`

Keeps the current long-poll behavior. It should allow an agent to wait for:

- its side to become ready to move
- game over

The move wait path is intentionally not indexed by ply or event id. A caller
that is already allowed to move receives an immediate `ready: true` response.

Current implementation: responses include caller-aware state and a
`waiting_for` object with side, owner, label, and actor. A timeout is a normal
tool result with `timeout: true`, not an MCP tool error.

### `new_game`

Should be restricted to menu/system control by default. Allowing any connected
agent to reset the game is surprising.

Possible policy:

- Disabled for side seats.
- Allowed for an admin token if one exists.
- Available from in-game UI.

Current implementation: disabled for side seats. No admin token exists yet, so
reset remains an in-game UI/system action.

### `set_bot_enabled`

This belongs to Local Sandbox/debugging and should not be exposed to ordinary
agent seats in the polished modes.

Current implementation: side-seat MCP callers receive a structured rejection.

### Proposed New Tools

- `join_game`: optional explicit handshake that marks a seat connected and
  accepts a display name.
- `get_connection_info`: returns mode, seats, endpoint, and session metadata.
- `resign`: lets a side-scoped seat resign.
- `offer_draw` and `respond_draw`: optional later feature.

## MCP Resources

Existing resources remain:

- `chess://game/state`
- `chess://game/pgn`
- `chess://game/events`

Add or extend:

- `chess://game/connection`: endpoint, seats, connection status.
- `chess://game/help`: short usage guide for agents.

The HTTP transport remains request/response for now. Subscriptions can stay as
declared capability, but agents should use `wait_for_move` until the transport
can push server notifications.

## Event Log

Events should carry enough context for agents and for UI debugging.

Move event fields:

- id
- type
- actor
- side
- uci
- san
- from
- to
- promotion
- fen
- turn after move
- ply
- status

System events:

- game started
- game reset
- seat connected
- seat disconnected or stale
- game over
- invalid move attempt, if useful for debugging

Invalid move attempts should be logged carefully. They are useful during
development but should not spam normal play.

## UI Structure

Target UI layers:

- Start menu
- In-game status panel
- MCP connection panel
- Game-over panel

The current right-side status panel can evolve into the in-game panel, but the
start menu should be a distinct overlay.

### Start Menu

Fields/actions:

- Title: Chess
- Start Game With Agent
- Start Two-Agent Game
- Local Sandbox
- Quit

### In-Game Status Panel

Fields/actions:

- Current turn
- Mode
- Side ownership
- Last move
- Check/checkmate/stalemate status
- New Game
- Return to Menu
- Copy FEN
- Copy PGN

Current implementation: the right-side game panel shows mode, side ownership,
turn owner, check/checkmate/stalemate/draw status, last move, and actions for
New Game, Return to Menu, Copy FEN, and Copy PGN.

### MCP Connection Panel

Fields/actions:

- Endpoint URL
- Session file path
- Seat token display
- Copy endpoint
- Copy token
- Copy agent prompt or command snippet
- Connection status per seat

### Game-Over Panel

Fields/actions:

- Result
- Final move
- New Game Same Mode
- Return to Menu
- Copy PGN

## Visual Polish

Minimum polish target:

- Board starts in a readable camera framing.
- Selected piece and legal move highlights are clear but not noisy.
- Last move highlight is shown on the origin and destination squares.
- Check state is visually distinct on the checked king square.
- Captured piece summary is visible in the HUD.
- HUD includes a compact board orientation and coordinate hint.
- Full board-edge coordinate labels are visible in the 3D scene.
- Menu panels use consistent spacing, sizing, and colors.
- Text is readable at common desktop resolutions.
- Promotion chooser appears in the HUD after a human selects a promotion target
  square.
- The HUD shows file/rank order for the current local-player view; two-agent
  and sandbox modes use a default white-view coordinate guide.

Nice-to-have later:

- Move list / PGN sidebar.
- Optional board flip when human plays black.
- Simple piece movement animation.

## Error Handling and Logging

All rejected MCP actions should produce:

- A clear JSON error result for the caller.
- A concise game log line with actor, side, reason, and move text when relevant.

Examples:

- seat not authorized
- not your turn
- move is illegal
- game is over
- malformed move
- seat token is stale or unknown

The game should not silently ignore these cases.

## Implementation Plan

### Phase 1: Documented Target and Small Refactor

- Add this design document.
- Keep `docs/chess-mcp.md` as the protocol quickstart.
- Introduce internal mode/seat data structures without changing UI yet.
- Add side ownership checks to controller input and MCP `make_move`.

### Phase 2: MCP Polishing

- Add side-scoped tokens.
- Add connection/session metadata for one-seat and two-seat games.
- Add `join_game` or equivalent connection status tracking.
- Restrict `new_game` and debugging tools from ordinary side seats.
- Add resource/help text for agents.

### Phase 3: Game Menu

- Add start menu overlay.
- Add Human vs Agent flow.
- Add Two-Agent Game flow.
- Add Local Sandbox flow.
- Add connection panel with visible endpoint/token/session data.

### Phase 4: Game UX

- Add last move highlight.
- Add check-square highlight.
- Report selected-piece move count and promotion target hint in the HUD.
- Add HUD promotion chooser for queen/rook/bishop/knight.
- Add captured-piece summary and compact board orientation/coordinate hint to
  the HUD.
- Improve status and game-over panels.
- Add PGN/move list if UI widgets make this practical.

### Phase 5: Verification

- Test Human vs Agent manually with one MCP client.
- Test Two-Agent Game with two tokens or two clients.
- Verify illegal side moves are rejected through UI and MCP.
- Verify reset/new game does not leave stale seat state.
- Verify session file cleanup on normal quit and Ctrl-C.

## Open Questions

- Should Human vs Agent let the user choose white/black in the first version?
- Should Two-Agent Game expose one endpoint with two tokens or two endpoints?
- Should an admin token exist for reset/new game from external tools?
- How much of the connection panel can be copied to clipboard reliably across
  Linux desktop setups?
- Do we want MCP server notifications later through a transport that can push,
  or is long-polling `wait_for_move` enough for this sample?
