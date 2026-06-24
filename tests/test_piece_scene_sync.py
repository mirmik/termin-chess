from __future__ import annotations

import sys
import types
from pathlib import Path

import chess

from conftest import SCRIPTS_DIR, load_script_module


def load_piece_scene_sync_module():
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    scripts_pkg = types.ModuleType("Scripts")
    scripts_pkg.__path__ = [str(SCRIPTS_DIR)]
    sys.modules["Scripts"] = scripts_pkg

    termin_pkg = types.ModuleType("termin")
    termin_pkg.__path__ = []
    sys.modules["termin"] = termin_pkg

    geombase = types.ModuleType("termin.geombase")

    class Vec3:
        def __init__(self, x: float, y: float, z: float) -> None:
            self.x = x
            self.y = y
            self.z = z

    geombase.Vec3 = Vec3
    sys.modules["termin.geombase"] = geombase

    return load_script_module("chess_piece_scene_sync_under_test", "ChessPieceSceneSync.py")


piece_scene_sync_module = load_piece_scene_sync_module()
ChessPieceSceneSync = piece_scene_sync_module.ChessPieceSceneSync


class FakeTransform:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self._position = sys.modules["termin.geombase"].Vec3(x, y, z)

    def local_position(self):
        return self._position

    def set_local_position(self, value: object) -> None:
        self._position = value


class FakePiece:
    def __init__(self, name: str, x: float, y: float, scene: "FakeScene") -> None:
        self.name = name
        self.transform = FakeTransform(x, y)
        self.scene = scene


class FakeUnits:
    name = "ChessUnits"

    def __init__(self, children: list[FakePiece]) -> None:
        self._children = children

    def children(self) -> list[FakePiece]:
        return list(self._children)


class FakeScene:
    def __init__(self, pieces: list[FakePiece]) -> None:
        self.removed: list[FakePiece] = []
        self.units = FakeUnits(pieces)

    def find_entity_by_name(self, name: str) -> FakeUnits | None:
        if name == "ChessUnits":
            return self.units
        return None

    def remove(self, entity: FakePiece) -> None:
        self.removed.append(entity)


class FakeOwnerEntity:
    def __init__(self, scene: FakeScene) -> None:
        self.scene = scene


class FakeOwner:
    def __init__(self, scene: FakeScene) -> None:
        self.entity = FakeOwnerEntity(scene)


def make_sync(pieces: list[FakePiece]) -> tuple[ChessPieceSceneSync, FakeScene]:
    scene = FakeScene(pieces)
    sync = ChessPieceSceneSync(FakeOwner(scene))
    sync.scan()
    return sync, scene


def test_apply_visual_move_moves_piece_entity_without_advancing_board() -> None:
    scene = FakeScene([])
    pawn = FakePiece("Pawn", 0.0, -6.0, scene)
    sync, _scene = make_sync([pawn])
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")

    assert sync.apply_visual_move(board, move) is True
    assert board.fen() == chess.STARTING_FEN
    assert sync.piece_at("e2") is None
    assert sync.piece_at("e4") is pawn


def test_apply_visual_move_fails_when_moving_piece_entity_is_missing() -> None:
    sync, _scene = make_sync([])
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")

    assert sync.apply_visual_move(board, move) is False
    assert board.fen() == chess.STARTING_FEN
    assert sync.piece_at("e4") is None
