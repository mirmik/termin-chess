# Termin Chess

Шахматы на Termin: локальная игра, человек против MCP-агента и два MCP-агента.

Используется текущий собранный SDK из `../termin/sdk`. Python игры и зависимости
из `chess.pymodule` загружает сам Termin; старое окружение `.venv` игре не требуется.

```bash
# Редактор
../termin/sdk/bin/termin editor .

# Игра с начальным меню
../termin/sdk/bin/termin play . --scene scene2.scene

# Два агента; параметры подключения появятся в HUD и /tmp/chess-game-mcp.json
CHESS_MCP=1 CHESS_GAME_MODE=agent_vs_agent ../termin/sdk/bin/termin play . --scene scene2.scene

# Автономное Linux-приложение
../termin/sdk/bin/termin build dev-linux
../termin/sdk/bin/termin run dev-linux
```

Профили сборки используют схему v2. `dev` и `dev-linux` предназначены для
Linux x86_64; `dev-windows` — для Windows x86_64 и требует соответствующий SDK
и `fxc` для D3D11. Рабочая игровая сцена — `scene2.scene`; `scene.scene` сохранена
как ранняя версия сцены.

[Протокол MCP](docs/chess-mcp.md) · [Проверки](tests/README.md)
