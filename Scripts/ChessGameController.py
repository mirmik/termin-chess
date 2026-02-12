"""Chess game controller — handles click input, move validation, and piece movement."""

from __future__ import annotations

import chess

from termin.visualization.core.python_component import InputComponent
from termin.visualization.core.input_events import MouseButton, Action
from termin.visualization.core.material import TcMaterial
from termin.visualization.core.mesh import TcMesh
from termin.geombase._geom_native import Vec3

from Scripts.chess_coords import (
    ij_to_square,
    square_to_ij,
    square_to_world,
    entity_to_square,
    tile_name_to_square,
    W,
)

STATE_IDLE = "idle"
STATE_SELECTED = "piece_selected"
STATE_GAME_OVER = "game_over"


class ChessGameController(InputComponent):

    def __init__(self):
        super().__init__(enabled=True, active_in_editor=False)
        self._board: chess.Board = chess.Board()
        self._pieces: dict[str, object] = {}      # "e2" -> entity
        self._tiles: dict[str, object] = {}        # "a1" -> entity
        self._original_materials: dict[str, object] = {}  # "a1" -> material
        self._selected_square: str | None = None
        self._valid_moves: list[chess.Move] = []
        self._state: str = STATE_IDLE
        self._highlight_selected: TcMaterial | None = None
        self._highlight_valid: TcMaterial | None = None
        self._board_entity = None
        self._units_entity = None

    def start(self) -> None:
        super().start()
        self._board = chess.Board()
        self._create_highlight_materials()
        self._scan_board()
        self._scan_pieces()
        print("ChessGameController started. White to move.")

    def _create_highlight_materials(self):
        self._highlight_selected = TcMaterial.create("SelectedMaterial")
        self._highlight_selected.set_color(0.9, 0.9, 0.2, 1.0)

        self._highlight_valid = TcMaterial.create("ValidMoveMaterial")
        self._highlight_valid.set_color(0.2, 0.8, 0.3, 1.0)

    def _scan_board(self):
        scene = self.entity.scene
        self._board_entity = scene.find_entity_by_name("ChessBoard")
        if self._board_entity is None:
            print("ERROR: ChessBoard entity not found!")
            return
        for child in self._board_entity.children():
            sq = tile_name_to_square(child.name)
            if sq:
                self._tiles[sq] = child
                mr = child.get_component_by_type("MeshRenderer")
                if mr:
                    mat = mr.get_field("material")
                    self._original_materials[sq] = mat

    def _scan_pieces(self):
        scene = self.entity.scene
        self._units_entity = scene.find_entity_by_name("ChessUnits")
        if self._units_entity is None:
            print("ERROR: ChessUnits entity not found!")
            return
        for child in self._units_entity.children():
            sq = entity_to_square(child)
            if sq:
                self._pieces[sq] = child

    def _is_ancestor_of(self, entity, ancestor_name: str) -> bool:
        current = entity.parent
        while current is not None:
            if current.name == ancestor_name:
                return True
            current = current.parent
        return False

    def on_mouse_button(self, event):
        if event.button != MouseButton.LEFT or event.action != Action.PRESS:
            return
        if self._state == STATE_GAME_OVER:
            return

        ray = event.viewport.screen_point_to_ray(event.x, event.y)
        if ray is None:
            return

        scene = event.viewport.scene
        hit = scene.raycast(ray)

        if hit is None or not hit.valid:
            self._clear_selection()
            return

        hit_entity = hit.entity
        if hit_entity is None:
            self._clear_selection()
            return

        square = None
        if self._is_ancestor_of(hit_entity, "ChessUnits"):
            square = entity_to_square(hit_entity)
        elif self._is_ancestor_of(hit_entity, "ChessBoard"):
            square = tile_name_to_square(hit_entity.name)

        if square is None:
            self._clear_selection()
            return

        self._handle_click(square)

    def _handle_click(self, square: str):
        sq_index = chess.parse_square(square)
        piece = self._board.piece_at(sq_index)

        if self._state == STATE_IDLE:
            if piece and piece.color == self._board.turn:
                self._select_piece(square)
        elif self._state == STATE_SELECTED:
            # Check if clicking on own piece -> reselect
            if piece and piece.color == self._board.turn:
                self._clear_highlight()
                self._select_piece(square)
                return

            # Check if this is a valid move
            move = self._find_valid_move(self._selected_square, square)
            if move:
                self._execute_move(move)
            else:
                self._clear_selection()

    def _select_piece(self, square: str):
        self._selected_square = square
        self._state = STATE_SELECTED
        self._valid_moves = [
            m for m in self._board.legal_moves
            if chess.square_name(m.from_square) == square
        ]
        self._apply_highlight()

    def _find_valid_move(self, from_sq: str, to_sq: str) -> chess.Move | None:
        for move in self._valid_moves:
            if (chess.square_name(move.from_square) == from_sq and
                    chess.square_name(move.to_square) == to_sq):
                return move
        return None

    def _apply_highlight(self):
        self._clear_highlight()
        # Highlight selected square
        if self._selected_square and self._selected_square in self._tiles:
            tile = self._tiles[self._selected_square]
            mr = tile.get_component_by_type("MeshRenderer")
            if mr:
                mr.set_field("material", self._highlight_selected)

        # Highlight valid moves
        for move in self._valid_moves:
            to_name = chess.square_name(move.to_square)
            if to_name in self._tiles:
                tile = self._tiles[to_name]
                mr = tile.get_component_by_type("MeshRenderer")
                if mr:
                    mr.set_field("material", self._highlight_valid)

    def _clear_highlight(self):
        for sq, mat in self._original_materials.items():
            if sq in self._tiles:
                tile = self._tiles[sq]
                mr = tile.get_component_by_type("MeshRenderer")
                if mr:
                    mr.set_field("material", mat)

    def _clear_selection(self):
        self._clear_highlight()
        self._selected_square = None
        self._valid_moves = []
        self._state = STATE_IDLE

    def _execute_move(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        # Handle castling
        if self._board.is_castling(move):
            self._do_castling(move)
        # Handle en passant
        elif self._board.is_en_passant(move):
            self._do_en_passant(move)
        # Handle promotion
        elif move.promotion:
            self._do_promotion(move)
        else:
            # Normal move or capture
            self._do_normal_move(move)

        # Push the move on the board
        self._board.push(move)
        self._clear_selection()

        # Check game state
        turn_str = "White" if self._board.turn else "Black"
        if self._board.is_checkmate():
            winner = "Black" if self._board.turn else "White"
            print(f"Checkmate! {winner} wins!")
            self._state = STATE_GAME_OVER
        elif self._board.is_stalemate():
            print("Stalemate! Draw.")
            self._state = STATE_GAME_OVER
        elif self._board.is_check():
            print(f"Check! {turn_str} to move.")
        else:
            print(f"{turn_str} to move.")

    def _move_piece_entity(self, from_sq: str, to_sq: str):
        if from_sq not in self._pieces:
            return
        entity = self._pieces.pop(from_sq)
        world_pos = square_to_world(to_sq)
        entity.transform.set_local_position(world_pos)
        self._pieces[to_sq] = entity

    def _capture_piece(self, sq: str):
        if sq in self._pieces:
            entity = self._pieces.pop(sq)
            scene = entity.scene
            if scene:
                scene.remove(entity)

    def _do_normal_move(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        # Capture if destination occupied
        if to_sq in self._pieces:
            self._capture_piece(to_sq)
        self._move_piece_entity(from_sq, to_sq)

    def _do_castling(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        # Move king
        self._move_piece_entity(from_sq, to_sq)

        # Determine rook squares
        if move.to_square == chess.G1:  # White kingside
            self._move_piece_entity("h1", "f1")
        elif move.to_square == chess.C1:  # White queenside
            self._move_piece_entity("a1", "d1")
        elif move.to_square == chess.G8:  # Black kingside
            self._move_piece_entity("h8", "f8")
        elif move.to_square == chess.C8:  # Black queenside
            self._move_piece_entity("a8", "d8")

    def _do_en_passant(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        # The captured pawn is on the same file as to_sq but same rank as from_sq
        captured_file = to_sq[0]
        captured_rank = from_sq[1]
        captured_sq = f"{captured_file}{captured_rank}"

        self._capture_piece(captured_sq)
        self._move_piece_entity(from_sq, to_sq)

    def _do_promotion(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        # Capture if needed
        if to_sq in self._pieces:
            self._capture_piece(to_sq)

        # Remove the pawn
        self._capture_piece(from_sq)

        # Create new piece (auto-queen)
        is_white = self._board.turn  # current turn (before push)
        scene = self.entity.scene
        units_entity = scene.find_entity_by_name("ChessUnits")
        if units_entity:
            from Scripts.UnitsCreator import UnitsCreator
            uc = units_entity.get_component(UnitsCreator)
            if uc:
                new_entity = uc.create_piece("queen", is_white, to_sq)
                if new_entity:
                    self._pieces[to_sq] = new_entity
