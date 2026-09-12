from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import load_script_module

cli = load_script_module('chess_cli_under_test', 'chess_agent_cli.py')


def invitation(tmp_path: Path):
    path = tmp_path / 'white.json'
    cli.write_private_json(path, {'url': 'http://127.0.0.1:8790/mcp', 'token': 'white-token', 'side': 'white', 'game_id': 'game-1'})
    return path


def position():
    return {'ok': True, 'fen': 'position-1', 'game_id': 'game-1', 'caller_side': 'white', 'caller_can_move': True,
            'board_ascii': 'board', 'status': 'playing', 'game_over': False, 'turn': 'white', 'legal_moves': ['e2e4']}


def test_cli_uses_position_read_before_move_and_rejects_replaced_game(tmp_path):
    path = invitation(tmp_path)
    client = cli.ChessClient(path)
    with pytest.raises(cli.ClientError, match='Read the position'):
        client.run('move', move='e2e4')
    client.call = lambda *a, **kw: position()
    client.run('status')
    calls = []
    def move_reply(name, arguments):
        calls.append((name, arguments))
        return {'ok': True, 'state': {**position(), 'fen': 'position-2', 'caller_can_move': False}}
    client.call = move_reply
    assert client.run('move', move='e2e4')['ok']
    assert calls == [('make_move', {'move': 'e2e4', 'game_id': 'game-1', 'expected_fen': 'position-1', 'timeout': 10})]
    cli.write_private_json(path, {**json.loads(path.read_text()), 'game_id': 'game-2'})
    replaced = cli.ChessClient(path)
    for command in ('wait', 'move'):
        with pytest.raises(cli.ClientError, match='game changed'):
            replaced.run(command, move='e2e4')


def test_cli_rejects_operator_file_and_wrong_seat_response(tmp_path):
    path = invitation(tmp_path)
    client = cli.ChessClient(path)
    client.call = lambda *a, **kw: {**position(), 'caller_side': 'black'}
    with pytest.raises(cli.ClientError, match='different seat'):
        client.run('status')
    cli.write_private_json(path, {**json.loads(path.read_text()), 'tokens': {'white': 'secret', 'black': 'another'}})
    with pytest.raises(cli.ClientError, match='operator file'):
        cli.ChessClient(path)


def test_cli_reports_missing_invitation_as_json(tmp_path, capsys):
    assert cli.main(['--session', str(tmp_path / 'missing.json'), '--json', 'status']) == 1
    assert json.loads(capsys.readouterr().out)['ok'] is False
