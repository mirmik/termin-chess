# Chess Game MCP

Chess can expose a game-level MCP endpoint from inside the running game. This
is separate from Termin player/editor diagnostic MCP and only exposes chess
state and chess actions.

## Start

```bash
CHESS_MCP=1 termin play .
```

By default the endpoint binds to `127.0.0.1:8790` and writes connection data to:

```text
/tmp/chess-game-mcp.json
```

The session file contains the URL, side-scoped bearer tokens, resource URIs and
tool names. It is written with mode `0600`.
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
CHESS_BOT_ENABLED=0
```

When `CHESS_MCP=1` is set, the built-in bot is disabled unless
`CHESS_BOT_ENABLED` is explicitly set. The current default mode is human vs
agent: the local player owns white, and the black MCP seat owns black.

`CHESS_MCP_TOKEN` is kept as a convenience alias for the black seat token. New
clients should prefer `tokens.black`, `tokens.white`, or the `seats` array in
the session file.

## Resources

- `chess://game/state`: JSON position snapshot.
- `chess://game/pgn`: PGN for the current game.
- `chess://game/events`: recent move/reset/bot events.

The server accepts `resources/subscribe`, but the current local HTTP endpoint is
request/response. Use `wait_for_move` when an agent needs to block until the
user or another actor moves.

## Tools

- `get_state`: current FEN, board ASCII, side to move, legal moves, status and
  counters.
- `legal_moves`: legal moves in UCI and SAN.
- `make_move`: make a legal UCI or SAN move for the MCP seat identified by the
  request token.
- `wait_for_move`: wait for a new event after an event id or ply.
- `new_game`: reset to the initial position.
- `set_bot_enabled`: enable or disable the built-in bot.

## Curl Examples

Read the session file:

```bash
SESSION=/tmp/chess-game-mcp.json
URL=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["url"])' "$SESSION")
TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$SESSION")
BLACK_TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tokens"]["black"])' "$SESSION")
WHITE_TOKEN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tokens"]["white"])' "$SESSION")
```

For current human-vs-agent play, use `BLACK_TOKEN` for the agent. `TOKEN` is a
legacy alias for `BLACK_TOKEN`.

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

Make a move:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $BLACK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"make_move","arguments":{"move":"e7e5"}}}'
```

Wait for the next event after the current ply:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"wait_for_move","arguments":{"after_ply":1,"timeout":60}}}'
```

Read the state resource:

```bash
curl -s "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":5,"method":"resources/read","params":{"uri":"chess://game/state"}}'
```
