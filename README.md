# Termin Chess

Шахматы на Termin: игра с агентом, вдвоём за доской, два агента и встроенный бот.

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

## Игра с агентом

В меню выберите соперника и свой цвет: белые, чёрные или случайно. Камера
поворачивается к вашей стороне; кнопка «Перевернуть доску» меняет только вид.
После создания партии откроется приглашение: его можно прочитать, отредактировать
и скопировать. Черновики белого и чёрного агентов сохраняются отдельно до новой
партии. «Меню» ставит партию на паузу; «Продолжить партию» сохраняет позицию.

Основной способ управления для агента — автономный Python 3 клиент. Пути к нему
и файлу своего места указаны в приглашении. Например, для чёрного агента:

```bash
python3 Scripts/chess_agent_cli.py --session /tmp/chess-game-mcp.black.json status
python3 Scripts/chess_agent_cli.py --session /tmp/chess-game-mcp.black.json wait --timeout 60
python3 Scripts/chess_agent_cli.py --session /tmp/chess-game-mcp.black.json move e7e5
```

Команду `move` нужно вызывать после чтения позиции через `status` или `wait`:
клиент проверяет партию и позицию, на основании которой выбран ход.
`--json` перед подкомандой включает структурированный ответ; `pgn` возвращает
историю. Клиент не требует Termin, python-chess или установленного MCP.
Файлы приглашений создаются только для активных агентских мест; общий
`chess-game-mcp.json` предназначен для оператора и содержит оба токена.

MCP остаётся дополнительным способом подключиться к тому же игровому серверу.

[Протокол и подключение](docs/chess-mcp.md) · [Проверки](tests/README.md)
