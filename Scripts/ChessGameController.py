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

print("[Chess] ChessGameController module loaded.")

STATE_IDLE = "idle"
STATE_SELECTED = "piece_selected"
STATE_GAME_OVER = "game_over"


class ChessGameController(InputComponent):

    def __init__(self):
        print("[Chess] ChessGameController.__init__()")
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
        print("[Chess] ChessGameController.start() called")
        super().start()
        self._board = chess.Board()
        print("[Chess] chess.Board created, initial position loaded")

        self._create_highlight_materials()
        self._scan_board()
        self._scan_pieces()

        print(f"[Chess] Init complete. tiles={len(self._tiles)}, pieces={len(self._pieces)}")
        print(f"[Chess] Tiles: {sorted(self._tiles.keys())}")
        print(f"[Chess] Pieces: {sorted(self._pieces.keys())}")
        print("[Chess] White to move.")

    def _create_highlight_materials(self):
        print("[Chess] Creating highlight materials...")
        self._highlight_selected = TcMaterial.create("SelectedMaterial")
        self._highlight_selected.set_color(0.9, 0.9, 0.2, 1.0)
        print(f"[Chess]   SelectedMaterial created: {self._highlight_selected}")

        self._highlight_valid = TcMaterial.create("ValidMoveMaterial")
        self._highlight_valid.set_color(0.2, 0.8, 0.3, 1.0)
        print(f"[Chess]   ValidMoveMaterial created: {self._highlight_valid}")

    def _scan_board(self):
        print("[Chess] Scanning board tiles...")
        scene = self.entity.scene
        print(f"[Chess]   scene={scene}")
        self._board_entity = scene.find_entity_by_name("ChessBoard")
        if self._board_entity is None:
            print("[Chess]   ERROR: ChessBoard entity not found!")
            return
        print(f"[Chess]   Found ChessBoard entity: {self._board_entity.name}")
        children = self._board_entity.children()
        print(f"[Chess]   ChessBoard has {len(children)} children")
        for child in children:
            sq = tile_name_to_square(child.name)
            if sq:
                self._tiles[sq] = child
                mr = child.get_component_by_type("MeshRenderer")
                if mr:
                    mat = mr.get_field("material")
                    self._original_materials[sq] = mat
                else:
                    print(f"[Chess]   WARNING: tile {child.name} ({sq}) has no MeshRenderer")
            else:
                print(f"[Chess]   WARNING: could not parse tile name '{child.name}'")
        print(f"[Chess]   Scanned {len(self._tiles)} tiles, {len(self._original_materials)} materials saved")

    def _scan_pieces(self):
        print("[Chess] Scanning pieces...")
        scene = self.entity.scene
        self._units_entity = scene.find_entity_by_name("ChessUnits")
        if self._units_entity is None:
            print("[Chess]   ERROR: ChessUnits entity not found!")
            return
        print(f"[Chess]   Found ChessUnits entity: {self._units_entity.name}")
        children = self._units_entity.children()
        print(f"[Chess]   ChessUnits has {len(children)} children")
        for child in children:
            pos = child.transform.local_position()
            sq = entity_to_square(child)
            print(f"[Chess]   piece '{child.name}' pos=({pos.x:.1f},{pos.y:.1f},{pos.z:.1f}) -> square={sq}")
            if sq:
                self._pieces[sq] = child
            else:
                print(f"[Chess]   WARNING: could not map piece '{child.name}' to square")
        print(f"[Chess]   Scanned {len(self._pieces)} pieces")

    def _is_ancestor_of(self, entity, ancestor_name: str) -> bool:
        current = entity.parent
        while current is not None:
            if current.name == ancestor_name:
                return True
            current = current.parent
        return False

    def on_mouse_button(self, event):
        print("[Chess] On mouse button")
        if event.button != MouseButton.LEFT or event.action != Action.PRESS:
            return
        if self._state == STATE_GAME_OVER:
            print("[Chess] Game is over, ignoring click.")
            return

        print(f"[Chess] --- LEFT CLICK at pixel ({event.x:.0f}, {event.y:.0f}) ---")

        ray = event.viewport.screen_point_to_ray(event.x, event.y)
        if ray is None:
            print("[Chess]   screen_point_to_ray returned None, no camera?")
            return
        print(f"[Chess]   ray origin=({ray.origin.x:.2f},{ray.origin.y:.2f},{ray.origin.z:.2f}) dir=({ray.direction.x:.2f},{ray.direction.y:.2f},{ray.direction.z:.2f})")

        scene = event.viewport.scene
        hit = scene.raycast(ray)

        if hit is None or not hit.valid:
            print("[Chess]   raycast: no hit -> clearing selection")
            self._clear_selection()
            return

        hit_entity = hit.entity
        if hit_entity is None:
            print("[Chess]   raycast: hit.valid but hit.entity is None -> clearing selection")
            self._clear_selection()
            return

        print(f"[Chess]   raycast hit: entity='{hit_entity.name}' distance={hit.distance:.3f}")

        # Walk up parents for debug
        p = hit_entity.parent
        parents = []
        while p is not None:
            parents.append(p.name)
            p = p.parent
        print(f"[Chess]   hit entity parents: {' -> '.join(parents) if parents else '(root)'}")

        square = None
        if self._is_ancestor_of(hit_entity, "ChessUnits"):
            square = entity_to_square(hit_entity)
            print(f"[Chess]   identified as PIECE entity -> square={square}")
        elif self._is_ancestor_of(hit_entity, "ChessBoard"):
            square = tile_name_to_square(hit_entity.name)
            print(f"[Chess]   identified as TILE entity '{hit_entity.name}' -> square={square}")
        else:
            print(f"[Chess]   hit entity is NOT a child of ChessUnits or ChessBoard -> ignoring")
            return

        if square is None:
            print("[Chess]   could not determine square -> clearing selection")
            self._clear_selection()
            return

        self._handle_click(square)

    def _handle_click(self, square: str):
        sq_index = chess.parse_square(square)
        piece = self._board.piece_at(sq_index)
        turn_str = "WHITE" if self._board.turn else "BLACK"
        print(f"[Chess]   handle_click: square={square}, piece={piece}, state={self._state}, turn={turn_str}")

        if self._state == STATE_IDLE:
            if piece and piece.color == self._board.turn:
                print(f"[Chess]   -> selecting own piece {piece} at {square}")
                self._select_piece(square)
            else:
                print(f"[Chess]   -> idle, no own piece at {square} (piece={piece}), ignoring")
        elif self._state == STATE_SELECTED:
            if piece and piece.color == self._board.turn:
                print(f"[Chess]   -> reselecting own piece {piece} at {square}")
                self._clear_highlight()
                self._select_piece(square)
                return

            move = self._find_valid_move(self._selected_square, square)
            if move:
                print(f"[Chess]   -> valid move found: {move.uci()}")
                self._execute_move(move)
            else:
                print(f"[Chess]   -> {square} is not a valid move from {self._selected_square}, clearing")
                self._clear_selection()

    def _select_piece(self, square: str):
        self._selected_square = square
        self._state = STATE_SELECTED
        self._valid_moves = [
            m for m in self._board.legal_moves
            if chess.square_name(m.from_square) == square
        ]
        move_strs = [m.uci() for m in self._valid_moves]
        print(f"[Chess]   selected {square}, valid moves ({len(self._valid_moves)}): {move_strs}")
        self._apply_highlight()

    def _find_valid_move(self, from_sq: str, to_sq: str) -> chess.Move | None:
        for move in self._valid_moves:
            if (chess.square_name(move.from_square) == from_sq and
                    chess.square_name(move.to_square) == to_sq):
                return move
        return None

    def _apply_highlight(self):
        self._clear_highlight()
        if self._selected_square and self._selected_square in self._tiles:
            tile = self._tiles[self._selected_square]
            mr = tile.get_component_by_type("MeshRenderer")
            if mr:
                mr.set_field("material", self._highlight_selected)
                print(f"[Chess]   highlight SELECTED: {self._selected_square}")
            else:
                print(f"[Chess]   WARNING: tile {self._selected_square} has no MeshRenderer for highlight")

        for move in self._valid_moves:
            to_name = chess.square_name(move.to_square)
            if to_name in self._tiles:
                tile = self._tiles[to_name]
                mr = tile.get_component_by_type("MeshRenderer")
                if mr:
                    mr.set_field("material", self._highlight_valid)

        valid_sqs = [chess.square_name(m.to_square) for m in self._valid_moves]
        print(f"[Chess]   highlight VALID MOVES: {valid_sqs}")

    def _clear_highlight(self):
        restored = 0
        for sq, mat in self._original_materials.items():
            if sq in self._tiles:
                tile = self._tiles[sq]
                mr = tile.get_component_by_type("MeshRenderer")
                if mr:
                    mr.set_field("material", mat)
                    restored += 1
        print(f"[Chess]   cleared highlight, restored {restored} tile materials")

    def _clear_selection(self):
        print(f"[Chess]   clearing selection (was: {self._selected_square})")
        self._clear_highlight()
        self._selected_square = None
        self._valid_moves = []
        self._state = STATE_IDLE

    def _execute_move(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        print(f"[Chess] === EXECUTING MOVE: {move.uci()} ({from_sq} -> {to_sq}) ===")

        if self._board.is_castling(move):
            print(f"[Chess]   move type: CASTLING")
            self._do_castling(move)
        elif self._board.is_en_passant(move):
            print(f"[Chess]   move type: EN PASSANT")
            self._do_en_passant(move)
        elif move.promotion:
            print(f"[Chess]   move type: PROMOTION to {chess.piece_name(move.promotion)}")
            self._do_promotion(move)
        else:
            is_capture = to_sq in self._pieces
            print(f"[Chess]   move type: {'CAPTURE' if is_capture else 'NORMAL'}")
            self._do_normal_move(move)

        self._board.push(move)
        print(f"[Chess]   board.push done. FEN: {self._board.fen()}")
        self._clear_selection()

        turn_str = "White" if self._board.turn else "Black"
        if self._board.is_checkmate():
            winner = "Black" if self._board.turn else "White"
            print(f"[Chess] *** CHECKMATE! {winner} wins! ***")
            self._state = STATE_GAME_OVER
        elif self._board.is_stalemate():
            print(f"[Chess] *** STALEMATE! Draw. ***")
            self._state = STATE_GAME_OVER
        elif self._board.is_check():
            print(f"[Chess] CHECK! {turn_str} to move.")
        else:
            print(f"[Chess] {turn_str} to move.")

    def _move_piece_entity(self, from_sq: str, to_sq: str):
        if from_sq not in self._pieces:
            print(f"[Chess]   WARNING: _move_piece_entity: no piece entity at {from_sq}! pieces={sorted(self._pieces.keys())}")
            return
        entity = self._pieces.pop(from_sq)
        world_pos = square_to_world(to_sq)
        print(f"[Chess]   moving entity '{entity.name}' from {from_sq} to {to_sq} world=({world_pos.x:.1f},{world_pos.y:.1f},{world_pos.z:.1f})")
        entity.transform.set_local_position(world_pos)
        self._pieces[to_sq] = entity

    def _capture_piece(self, sq: str):
        if sq in self._pieces:
            entity = self._pieces.pop(sq)
            print(f"[Chess]   capturing '{entity.name}' at {sq}")
            scene = entity.scene
            if scene:
                scene.remove(entity)
            else:
                print(f"[Chess]   WARNING: captured entity has no scene!")
        else:
            print(f"[Chess]   WARNING: _capture_piece: no piece at {sq}")

    def _do_normal_move(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        if to_sq in self._pieces:
            self._capture_piece(to_sq)
        self._move_piece_entity(from_sq, to_sq)

    def _do_castling(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        self._move_piece_entity(from_sq, to_sq)

        if move.to_square == chess.G1:
            print("[Chess]   castling: white kingside, rook h1->f1")
            self._move_piece_entity("h1", "f1")
        elif move.to_square == chess.C1:
            print("[Chess]   castling: white queenside, rook a1->d1")
            self._move_piece_entity("a1", "d1")
        elif move.to_square == chess.G8:
            print("[Chess]   castling: black kingside, rook h8->f8")
            self._move_piece_entity("h8", "f8")
        elif move.to_square == chess.C8:
            print("[Chess]   castling: black queenside, rook a8->d8")
            self._move_piece_entity("a8", "d8")

    def _do_en_passant(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        captured_file = to_sq[0]
        captured_rank = from_sq[1]
        captured_sq = f"{captured_file}{captured_rank}"
        print(f"[Chess]   en passant: capturing pawn at {captured_sq}")

        self._capture_piece(captured_sq)
        self._move_piece_entity(from_sq, to_sq)

    def _do_promotion(self, move: chess.Move):
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)

        if to_sq in self._pieces:
            self._capture_piece(to_sq)

        self._capture_piece(from_sq)

        is_white = self._board.turn
        print(f"[Chess]   promotion: creating queen at {to_sq}, is_white={is_white}")
        scene = self.entity.scene
        units_entity = scene.find_entity_by_name("ChessUnits")
        if units_entity:
            from Scripts.UnitsCreator import UnitsCreator
            uc = units_entity.get_component(UnitsCreator)
            if uc:
                new_entity = uc.create_piece("queen", is_white, to_sq)
                if new_entity:
                    self._pieces[to_sq] = new_entity
                    print(f"[Chess]   promotion: queen entity created: '{new_entity.name}'")
                else:
                    print("[Chess]   WARNING: create_piece returned None!")
            else:
                print("[Chess]   WARNING: UnitsCreator component not found on ChessUnits!")
        else:
            print("[Chess]   WARNING: ChessUnits entity not found for promotion!")
