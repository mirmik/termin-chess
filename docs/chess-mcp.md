# Chess agent connection and MCP

Chess can expose a game-level MCP endpoint from inside the running game. This
is separate from Termin player/editor diagnostic MCP and only exposes chess
state and chess actions.

## Agent CLI

The in-game “Подключение агента” panel previews and edits an invitation. The
primary local client is `Scripts/chess_agent_cli.py`, a standalone Python 3
script included in the game module and packaged app. Run it directly, not as
`python -m Scripts...`, which would import native Termin components.

The server creates side-specific files next to the operator session file:
`chess-game-mcp.white.json` and `chess-game-mcp.black.json` for active seats only.
Each contains only its own token, URL, side and game ID. They are written
atomically with private permissions and removed on orderly shutdown.

```bash
python3 Scripts/chess_agent_cli.py --session /tmp/chess-game-mcp.black.json status
python3 Scripts/chess_agent_cli.py --session /tmp/chess-game-mcp.black.json wait --timeout 60
python3 Scripts/chess_agent_cli.py --session /tmp/chess-game-mcp.black.json move e7e5
python3 Scripts/chess_agent_cli.py --session /tmp/chess-game-mcp.black.json pgn
```

`connect` is an alias for the initial status check. Add `--json` before the
subcommand for structured output. A successful status/wait/move stores the last
observed position in a private `.position.json` file beside the seat file.
`move` submits that position's `game_id` and `expected_fen`; it does not silently
read a newer position before applying an old choice. After a game changes,
obtain a fresh invitation and run status again. Normal wait timeouts exit 0;
errors exit 1. The CLI's wait timeout is limited to 0–300 seconds.

## Start

```bash
CHESS_MCP=1 termin play . --scene scene2.scene
```

By default the endpoint binds to `127.0.0.1:8790` and writes connection data to:

```text
/tmp/chess-game-mcp.json
```

The session file contains the URL, side-scoped bearer tokens, resource URIs and
tool names. It is written with mode `0600`. For two-agent games, both agents use
the same URL and pick their side from `agents.white` or `agents.black`.
Clients should still probe `/health` before using a discovered endpoint: an
abrupt external kill can leave an old session file behind.

Environment options:

```bash
CHESS_MCP=1
CHESS_MCP_HOST=127.0.0.1
CHESS_MCP_PORT=8790
CHESS_MCP_TOKEN=optional-fixed-black-seat-token
CHESS_MCP_WHITE_TOKEN=optional-fixed-white-seat-token
CHESS_MCP_BLACK_TOKEN=optional-fixed-black-seat-token
CHESS_MCP_SESSION_FILE=/tmp/chess-game-mcp.json
CHESS_GAME_MODE=human_vs_agent
CHESS_AGENT_SIDE=black
CHESS_BOT_COLOR=black
CHESS_BOT_ENABLED=0
```

When `CHESS_MCP=1` is set, the built-in bot is disabled unless
`CHESS_BOT_ENABLED` is explicitly set. The current default mode is human vs
agent: the local player owns white, and the black MCP seat owns black.

`CHESS_GAME_MODE` can force `local_sandbox`, `human_vs_agent`,
`agent_vs_agent`, or `human_vs_bot` for automated runs that should bypass the
in-game start menu. `CHESS_AGENT_SIDE` is used by `human_vs_agent`;
`CHESS_BOT_COLOR` is used by `human_vs_bot`.

Without `CHESS_MCP=1` and without an explicit `CHESS_GAME_MODE`, Chess starts
at the in-game menu. MCP-backed menu choices start the game MCP server from the
running game, using the same host, port, token and session-file environment
options listed above.

In MCP-backed modes the in-game right panel shows the endpoint URL, session
file, active seat token copy buttons, connection status, current turn and last
event. The session file remains the machine-readable handoff for agents.

`CHESS_MCP_TOKEN` is kept as a convenience alias for the black seat token. New
clients should prefer `tokens.black`, `tokens.white`, or the `seats` array in
the session file. The session file also contains a stable `session_id`,
`started_at`, initial `turn_owner`, active seats, and `board_input_enabled` for
the running game MCP process.

## Resources

- `chess://game/connection`: endpoint, caller seat, mode, side ownership and
  connection hints.
- `chess://game/help`: short Markdown usage guide for connected agents.
- `chess://game/state`: JSON position snapshot.
- `chess://game/pgn`: PGN move history for the current game, requested explicitly.
- `chess://game/events`: recent move/reset/bot events.

Subscriptions are not advertised or supported. Use `wait_for_move` when an agent
needs to block until its side can move. The request/response MCP transport returns
JSON, HTTP 202 for notifications and HTTP 405 for GET /mcp. It validates Origin
and rejects unsupported explicit MCP-Protocol-Version headers. The supported
protocol version is 2025-06-18; no permanent server installation is required.

## Tools

- `get_state`: compact caller-aware state: FEN, board ASCII, side to move,
  turn owner, status, last move and legal UCI/SAN move lists.
- `get_connection_info`: endpoint, caller seat, mode, live seat status and
  connection hints.
- `legal_moves`: legal UCI and SAN move lists plus caller/turn ownership.
- `make_move`: make a legal UCI or SAN move for the MCP seat identified by the
  request token.
- `wait_for_move`: wait until the caller's side can move, or until the game
  ends. If the caller is already allowed to move, returns immediately with
  `ready: true`; timeout and success responses include `waiting_for` and compact `state`.
- `get_pgn`: explicitly return PGN move history for agents that want the move list.

`new_game` and `set_bot_enabled` are operator controls, absent from tools/list
and still rejected if a legacy client calls them.

In-game reset starts a new game ID and MCP session id, clears live seat connection status,
and rewrites the session file. Seat tokens stay stable for the running server. Last move and move history are
reset. Opening the menu pauses play without changing the game ID, position or
invitations; state exposes `paused` and agents cannot move until resume.

`make_move` accepts optional `game_id` and `expected_fen` guards. Their checks run
on the main thread immediately before applying the move. Mismatches return
`game_changed` or `stale_position` with the current state. Legacy calls without
guards remain accepted; they are guarded against changes after admission to the
command queue, but cannot detect a position change before the request arrived.
The CLI always supplies both guards. `wait_for_move` accepts `game_id` and returns
`game_changed` if a different game is observed, including during a pending wait.
Server shutdown wakes pending waits and cancels queued commands before joining
HTTP workers.

## State Payload

`get_state` and `chess://game/state` return the same compact caller-aware
snapshot. Important fields for agents:

- `game_id`: identifier of the chess game, replaced on reset.
- `paused`: true while the in-game menu is open.
- `fen`: full FEN string.
- `board_ascii`: simple text board.
- `turn`: `white` or `black`.
- `turn_owner`: owner, label and actor for the side to move.
- `ply`: half-move count from the start of the game.
- `status`, `check`, `game_over`: game result state.
- `last_move`: compact last move object with `uci`, `san`, `actor` and optional
  `promotion`, or `null`.
- `caller_side`, `caller_can_move`, `caller_error`: authorization state for
  the request token.
- `legal_moves[]`: legal UCI strings for the side to move, including promotion
  suffixes such as `e7e8q`.
- `legal_moves_san[]`: legal SAN strings in the same order as `legal_moves[]`.

The compact state intentionally omits UI-only selection/highlight/capture data,
seat metadata, event counters and move history. Use `get_connection_info` for
seat metadata, `get_pgn` or `chess://game/pgn` for move history, and
`chess://game/events` for recent events.

## Curl Examples

Read the session file:

```bash
SESSION=/tmp/chess-game-mcp.json
URL=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["url"])' "$SESSION")
TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$SESSION")
BLACK_TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tokens"]["black"])' "$SESSION")
WHITE_TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tokens"]["white"])' "$SESSION")
```

For human-vs-agent play, use `BLACK_TOKEN` for the default black agent. `TOKEN`
is a legacy alias for `BLACK_TOKEN`. For two-agent play, give `WHITE_TOKEN` to
the white agent and `BLACK_TOKEN` to the black agent.

List tools:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Get state:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_state","arguments":{}}}'
```

Get connection info:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $BLACK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"get_connection_info","arguments":{}}}'
```

The connection payload includes:

- `session.id` and `session.started_at`
- `endpoint.url` and `endpoint.health_url`
- `caller.side`, `caller.can_move`, `caller.error`
- `caller.seat_status`
- `side_owners`
- `game_seats[]`
- `mcp_seats[]`
- `active_mcp_sides`
- `board_input_enabled` and `board_input_error`
- `seats[].connected`
- `seats[].first_seen_at`
- `seats[].last_seen_at`
- `seats[].request_count`
- `seats[].last_method`
- `tool_policy.allowed_tools`
- `tool_policy.restricted_tools`

Only the caller seat includes its own `token` and `authorization` fields. Other
seat tokens are returned as `null`.

Make a move:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $BLACK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"make_move","arguments":{"move":"e7e5"}}}'
```

Two-agent opening example:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $WHITE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":31,"method":"tools/call","params":{"name":"make_move","arguments":{"move":"e2e4"}}}'

curl -s "$URL" \
  -H "Authorization: Bearer $BLACK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":32,"method":"tools/call","params":{"name":"make_move","arguments":{"move":"e7e5"}}}'
```

Wait until the caller can move:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"wait_for_move","arguments":{"timeout":60}}}'
```

Read the state resource:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":5,"method":"resources/read","params":{"uri":"chess://game/state"}}'
```

Read the connection resource:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $BLACK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":7,"method":"resources/read","params":{"uri":"chess://game/connection"}}'
```

Read recent events:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $BLACK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":8,"method":"resources/read","params":{"uri":"chess://game/events"}}'
```
