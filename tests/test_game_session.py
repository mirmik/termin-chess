from __future__ import annotations

import chess

from conftest import load_script_module


session_module = load_script_module("chess_game_session_under_test", "ChessGameSession.py")

ChessGameSession = session_module.ChessGameSession
GameMode = session_module.GameMode
MoveActor = session_module.MoveActor
SideOwner = session_module.SideOwner


def test_local_sandbox_allows_human_board_input_and_has_no_mcp_seats() -> None:
    session = ChessGameSession()
    session.configure_local_sandbox()
    board = chess.Board()

    human = session.can_move_now(actor=MoveActor.human(), board=board, game_state="idle")
    white_agent = session.can_move_now(actor=MoveActor.agent(chess.WHITE), board=board, game_state="idle")

    assert session.mode == GameMode.LOCAL_SANDBOX
    assert session.side_owners_payload() == {"white": "human", "black": "human"}
    assert session.active_mcp_sides_payload() == []
    assert human.ok is True
    assert white_agent.ok is False
    assert white_agent.error == "white is controlled by human"


def test_human_vs_agent_blocks_agent_until_human_moves() -> None:
    session = ChessGameSession()
    session.configure_human_vs_agent(agent_side=chess.BLACK)
    board = chess.Board()

    black_agent_before_white = session.can_move_now(
        actor=MoveActor.agent(chess.BLACK),
        board=board,
        game_state="idle",
    )
    white_human = session.can_make_move(
        actor=MoveActor.human(),
        board=board,
        game_state="idle",
        move=chess.Move.from_uci("e2e4"),
    )

    board.push(chess.Move.from_uci("e2e4"))
    black_agent_after_white = session.can_make_move(
        actor=MoveActor.agent(chess.BLACK),
        board=board,
        game_state="idle",
        move=chess.Move.from_uci("e7e5"),
    )
    human_after_white = session.can_move_now(actor=MoveActor.human(), board=board, game_state="idle")

    assert session.mode == GameMode.HUMAN_VS_AGENT
    assert session.side_owners_payload() == {"white": "human", "black": "agent"}
    assert session.active_mcp_sides_payload() == ["black"]
    assert session.turn_owner_payload(chess.WHITE)["actor"] == "human:white"
    assert session.turn_owner_payload(chess.BLACK)["actor"] == "agent:black"
    assert black_agent_before_white.ok is False
    assert black_agent_before_white.error == "white is controlled by human"
    assert white_human.ok is True
    assert black_agent_after_white.ok is True
    assert human_after_white.ok is False
    assert human_after_white.error == "black is controlled by agent"


def test_agent_vs_agent_requires_matching_side_to_move() -> None:
    session = ChessGameSession()
    session.configure_agent_vs_agent()
    board = chess.Board()

    white_agent = session.can_make_move(
        actor=MoveActor.agent(chess.WHITE),
        board=board,
        game_state="idle",
        move=chess.Move.from_uci("e2e4"),
    )
    black_agent_too_early = session.can_move_now(
        actor=MoveActor.agent(chess.BLACK),
        board=board,
        game_state="idle",
    )
    human = session.can_move_now(actor=MoveActor.human(), board=board, game_state="idle")

    board.push(chess.Move.from_uci("e2e4"))
    black_agent = session.can_make_move(
        actor=MoveActor.agent(chess.BLACK),
        board=board,
        game_state="idle",
        move=chess.Move.from_uci("e7e5"),
    )

    assert session.mode == GameMode.AGENT_VS_AGENT
    assert session.side_owners_payload() == {"white": "agent", "black": "agent"}
    assert session.active_mcp_sides_payload() == ["white", "black"]
    assert session.sides_for_owner_payload(SideOwner.AGENT) == ["white", "black"]
    assert white_agent.ok is True
    assert black_agent_too_early.ok is False
    assert black_agent_too_early.error == "white is controlled by agent"
    assert human.ok is False
    assert human.error == "white is controlled by agent"
    assert black_agent.ok is True


def test_game_over_blocks_all_actors() -> None:
    session = ChessGameSession()
    session.configure_agent_vs_agent()
    board = chess.Board()

    authorization = session.can_move_now(
        actor=MoveActor.agent(chess.WHITE),
        board=board,
        game_state="game_over",
    )

    assert authorization.ok is False
    assert authorization.error == "game is over"
