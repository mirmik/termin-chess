"""Synchronize chess piece entities with a python-chess board move."""

from __future__ import annotations

import logging

import chess

from Scripts.chess_coords import entity_to_square, square_to_world

log = logging.getLogger(__name__)


class ChessPieceSceneSync:
    """Owns ChessUnits scanning and visual piece mutations."""

    def __init__(self, owner: object) -> None:
        self._owner = owner
        self._pieces: dict[str, object] = {}
        self._units_entity = None

    @property
    def piece_count(self) -> int:
        return len(self._pieces)

    def piece_squares(self) -> list[str]:
        return sorted(self._pieces.keys())

    def piece_at(self, square: str) -> object | None:
        return self._pieces.get(square)

    def scan(self) -> None:
        log.debug("[Chess] Scanning pieces...")
        scene = self._owner.entity.scene
        self._units_entity = scene.find_entity_by_name("ChessUnits")
        self._pieces.clear()
        if self._units_entity is None:
            log.error("[Chess] ChessUnits entity not found")
            return
        log.debug("[Chess] Found ChessUnits entity: %s", self._units_entity.name)
        children = self._units_entity.children()
        log.debug("[Chess] ChessUnits has %s children", len(children))
        for child in children:
            pos = child.transform.local_position()
            square = entity_to_square(child)
            log.debug(
                "[Chess] piece %r pos=(%.1f,%.1f,%.1f) -> square=%s",
                child.name,
                pos.x,
                pos.y,
                pos.z,
                square,
            )
            if square:
                self._pieces[square] = child
            else:
                log.warning("[Chess] could not map piece %r to square", child.name)
        log.debug("[Chess] Scanned %s pieces", len(self._pieces))

    def remove_all(self) -> None:
        for entity in list(self._pieces.values()):
            scene = entity.scene
            if scene:
                scene.remove(entity)
        self._pieces.clear()

    def recreate_starting_position(self) -> bool:
        scene = self._owner.entity.scene
        units_entity = scene.find_entity_by_name("ChessUnits")
        if not units_entity:
            log.warning("[Chess] ChessUnits entity not found")
            return False

        from Scripts.UnitsCreator import UnitsCreator

        creator = units_entity.get_component(UnitsCreator)
        if not creator:
            log.warning("[Chess] UnitsCreator not found on ChessUnits")
            return False
        creator.make_units()
        log.info("[Chess] Pieces recreated via UnitsCreator.make_units()")
        return True

    def apply_visual_move(self, board: chess.Board, move: chess.Move) -> bool:
        if board.is_castling(move):
            log.debug("[Chess] move type: CASTLING")
            return self._do_castling(move)
        if board.is_en_passant(move):
            log.debug("[Chess] move type: EN PASSANT")
            return self._do_en_passant(board, move)
        if move.promotion:
            log.debug("[Chess] move type: PROMOTION to %s", chess.piece_name(move.promotion))
            return self._do_promotion(board, move)

        to_square = chess.square_name(move.to_square)
        log.debug("[Chess] move type: %s", "CAPTURE" if self.piece_at(to_square) is not None else "NORMAL")
        return self._do_normal_move(board, move)

    def _move_piece_entity(self, from_square: str, to_square: str) -> bool:
        if from_square not in self._pieces:
            log.warning(
                "[Chess] no piece entity at %s; pieces=%s",
                from_square,
                sorted(self._pieces.keys()),
            )
            return False
        entity = self._pieces.pop(from_square)
        world_pos = square_to_world(to_square)
        log.debug(
            "[Chess] moving entity %r from %s to %s world=(%.1f,%.1f,%.1f)",
            entity.name,
            from_square,
            to_square,
            world_pos.x,
            world_pos.y,
            world_pos.z,
        )
        entity.transform.set_local_position(world_pos)
        self._pieces[to_square] = entity
        return True

    def _capture_piece(self, square: str) -> bool:
        if square not in self._pieces:
            log.warning("[Chess] no piece to capture at %s", square)
            return False
        entity = self._pieces.pop(square)
        log.debug("[Chess] capturing %r at %s", entity.name, square)
        scene = entity.scene
        if scene:
            scene.remove(entity)
        else:
            log.warning("[Chess] captured entity has no scene")
        return True

    def _do_normal_move(self, board: chess.Board, move: chess.Move) -> bool:
        from_square = chess.square_name(move.from_square)
        to_square = chess.square_name(move.to_square)
        if from_square not in self._pieces:
            log.warning("[Chess] no moving piece entity at %s", from_square)
            return False
        if board.is_capture(move) and to_square not in self._pieces:
            log.warning("[Chess] capture target entity missing at %s", to_square)
            return False
        if to_square in self._pieces and not self._capture_piece(to_square):
            return False
        return self._move_piece_entity(from_square, to_square)

    def _do_castling(self, move: chess.Move) -> bool:
        from_square = chess.square_name(move.from_square)
        to_square = chess.square_name(move.to_square)
        rook_move: tuple[str, str] | None = None
        if move.to_square == chess.G1:
            rook_move = ("h1", "f1")
        elif move.to_square == chess.C1:
            rook_move = ("a1", "d1")
        elif move.to_square == chess.G8:
            rook_move = ("h8", "f8")
        elif move.to_square == chess.C8:
            rook_move = ("a8", "d8")
        if rook_move is None:
            return False
        rook_from, rook_to = rook_move
        if from_square not in self._pieces or rook_from not in self._pieces:
            log.warning(
                "[Chess] castling entity missing king=%s rook=%s",
                from_square in self._pieces,
                rook_from in self._pieces,
            )
            return False
        return self._move_piece_entity(from_square, to_square) and self._move_piece_entity(rook_from, rook_to)

    def _do_en_passant(self, board: chess.Board, move: chess.Move) -> bool:
        from_square = chess.square_name(move.from_square)
        to_square = chess.square_name(move.to_square)
        captured_square = f"{to_square[0]}{from_square[1]}"
        log.debug("[Chess] en passant: capturing pawn at %s", captured_square)

        if from_square not in self._pieces or captured_square not in self._pieces:
            log.warning(
                "[Chess] en passant entity missing mover=%s captured=%s",
                from_square in self._pieces,
                captured_square in self._pieces,
            )
            return False
        return self._capture_piece(captured_square) and self._move_piece_entity(from_square, to_square)

    def _do_promotion(self, board: chess.Board, move: chess.Move) -> bool:
        from_square = chess.square_name(move.from_square)
        to_square = chess.square_name(move.to_square)

        if from_square not in self._pieces:
            log.warning("[Chess] promotion pawn entity missing at %s", from_square)
            return False
        if board.is_capture(move) and to_square not in self._pieces:
            log.warning("[Chess] promotion capture target entity missing at %s", to_square)
            return False

        is_white = board.turn
        piece_type = chess.piece_name(move.promotion)
        log.debug("[Chess] promotion: creating %s at %s, is_white=%s", piece_type, to_square, is_white)
        scene = self._owner.entity.scene
        units_entity = scene.find_entity_by_name("ChessUnits")
        if not units_entity:
            log.warning("[Chess] ChessUnits entity not found for promotion")
            return False

        from Scripts.UnitsCreator import UnitsCreator

        creator = units_entity.get_component(UnitsCreator)
        if not creator:
            log.warning("[Chess] UnitsCreator component not found on ChessUnits")
            return False
        new_entity = creator.create_piece(piece_type, is_white, to_square)
        if not new_entity:
            log.warning("[Chess] create_piece returned None")
            return False
        if to_square in self._pieces and not self._capture_piece(to_square):
            return False
        if not self._capture_piece(from_square):
            return False
        self._pieces[to_square] = new_entity
        log.debug("[Chess] promotion: %s entity created: %r", piece_type, new_entity.name)
        return True
