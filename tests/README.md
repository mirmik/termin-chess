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
