# Chess Tests

Fast tests live outside the `Scripts` package on purpose. `chess.pymodule`
packages only `Scripts`, so this directory is not copied into the Termin
runtime package and is not imported by the game module scanner.

Run:

```bash
python3 -m pytest tests
```

The unit tests load selected files from `Scripts` with `importlib` instead of
importing `Scripts.*`, because `Scripts/__init__.py` imports runtime components
that need Termin native bindings.

## Current SDK integration

The opt-in tests launch the real player with Vulkan, then exercise side ownership,
MCP moves, native UI button input, HUD styling, board/piece regeneration, camera
picking, screenshots, and clean shutdown. They use the sibling `../termin/sdk`
by default; set `TERMIN_BIN` to use another SDK CLI.

```bash
CHESS_PLAY_SMOKE=1 python3 -m pytest tests/test_mcp_play_smoke.py -q

# Linux without a desktop session (requires Xvfb and Vulkan)
SDL_VIDEODRIVER=x11 CHESS_PLAY_SMOKE=1 xvfb-run -a \
  python3 -m pytest tests/test_mcp_play_smoke.py -q

# Test the previously built dev-linux bundle
SDL_VIDEODRIVER=x11 CHESS_PLAY_SMOKE=1 CHESS_SMOKE_PACKAGED=1 xvfb-run -a \
  python3 -m pytest tests/test_mcp_play_smoke.py -q
```

Tests use game MCP ports 8821–8823 and diagnostic MCP ports 18821–18823.
Logs and screenshots are saved under pytest's temporary directory. Native tests
skip when the player cannot create a display; a skip does not verify rendering.
The fast tests use import stubs only for domain/formatting checks; the old
`tcgui` property-based styling test has moved to the native integration scenario.

Validation on 2026-09-11 used the Linux SDK from Termin checkout `364acf04f`
(Python 3.14t). The `dev-linux` bundle was built with strict resource validation.
Windows profile parsing was checked; Windows execution was not tested.

Known SDK issues recorded on the Termin board: #1659 (editor startup UI metrics)
and #2350 (packaged CLI ignores diagnostic MCP flags). The integration launcher
also supplies `TERMIN_PLAYER_MCP_*` environment variables to support the native
packaged host. These are diagnostic settings, separate from game `CHESS_MCP_*`.
