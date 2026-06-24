"""
UnitsCreator component.
"""

from __future__ import annotations

import logging

from termin.scene import PythonComponent
from termin.inspect import InspectField
from termin.geombase import Quat, Vec3
from termin.mesh import TcMesh
from termin.materials import TcMaterial

W = 2
H = 0.5
WHITE_PIECE_ROTATION = Quat(0.0, 0.0, 1.0, 0.0)

log = logging.getLogger(__name__)

class UnitsCreator(PythonComponent):
    """
    Custom component.

    Attributes:
        speed: Movement speed.
    """

    inspect_fields = {
        "Make Units": InspectField(
            label="Make Units",
            kind="button",
            action=lambda component: component.make_units(),
            is_serializable=False,
        ),
    }

    def __init__(self, speed: float = 1.0):
        super().__init__()
        self.speed = speed

    def start(self) -> None:
        """Called when the component is first activated."""
        super().start()

    def update(self, dt: float) -> None:
        """Called every frame.

        Args:
            dt: Delta time in seconds.
        """
        pass

    SCALE = Vec3(0.05, 0.05, 0.05)

    def chessboard_position_to_world(self, chesspos: str) -> Vec3:
        file = chesspos[0].lower()
        rank = int(chesspos[1])
        x = ord(file) - ord('a') - 4
        y = rank - 1 - 4
        return Vec3(x, y, 0)

    def make_unit(self, material, mesh, position, name="Unit", rotation=None):
        xpos = position.x * W
        ypos = position.y * W
        zpos = position.z * H

        pawn_mesh = mesh
        pawn = self.entity.create_child(name=name)
        pawn.transform.set_local_scale(UnitsCreator.SCALE)
        if rotation is not None:
            pawn.transform.set_local_rotation(rotation)
        pawn_mesh_component = pawn.add_component_by_name("MeshComponent")
        pawn_mr = pawn.add_component_by_name("MeshRenderer")
        pawn_mesh_component.set_field("mesh", pawn_mesh)
        pawn_mr.set_field("material", material)
        pawn.transform.set_local_position(Vec3(xpos, ypos, zpos))

        col = pawn.add_component_by_name("ColliderComponent")
        col.set_field("collider_type", "Box")
        col.set_field("box_size", [20, 20, 40])
        return pawn

    def make_pawn(self, material, position, rotation=None):
        pawn_mesh = TcMesh.from_name("Hex_Pawn")
        return self.make_unit(material, pawn_mesh, position, name="Pawn", rotation=rotation)

    def make_rook(self, material, position, rotation=None):
        rook_mesh = TcMesh.from_name("Hex_Rook")
        log.debug("Making rook at %s: %s", position, rook_mesh)
        return self.make_unit(material, rook_mesh, position, name="Rook", rotation=rotation)

    def make_knight(self, material, position, rotation=None):
        knight_mesh = TcMesh.from_name("Hex_Knight")
        return self.make_unit(material, knight_mesh, position, name="Knight", rotation=rotation)

    def make_bishop(self, material, position, rotation=None):
        bishop_mesh = TcMesh.from_name("Hex_Bishop")
        return self.make_unit(material, bishop_mesh, position, name="Bishop", rotation=rotation)

    def make_queen(self, material, position, rotation=None):
        queen_mesh = TcMesh.from_name("Hex_Queen")
        return self.make_unit(material, queen_mesh, position, name="Queen", rotation=rotation)

    def make_king(self, material, position, rotation=None):
        king_mesh = TcMesh.from_name("Hex_King")
        return self.make_unit(material, king_mesh, position, name="King", rotation=rotation)

    PIECE_MESHES = {
        "pawn": "Hex_Pawn",
        "rook": "Hex_Rook",
        "knight": "Hex_Knight",
        "bishop": "Hex_Bishop",
        "queen": "Hex_Queen",
        "king": "Hex_King",
    }

    def create_piece(self, piece_type: str, is_white: bool, square: str):
        """Create a single piece for promotion or other runtime needs.
        piece_type: 'pawn','rook','knight','bishop','queen','king'
        """
        mesh = TcMesh.from_name(self.PIECE_MESHES[piece_type])
        material = TcMaterial.from_name("WhiteFigure" if is_white else "BlackFigure")
        pos = self.chessboard_position_to_world(square)
        name = piece_type.capitalize()
        rotation = WHITE_PIECE_ROTATION if is_white else None
        return self.make_unit(material, mesh, pos, name=name, rotation=rotation)

    def make_units(self):
        log.info("Make Units button clicked.")

        self.entity.destroy_children()

        white_material = TcMaterial.from_name("WhiteFigure")
        black_material = TcMaterial.from_name("BlackFigure")

        for file in 'abcdefgh':
            self.make_pawn(white_material, self.chessboard_position_to_world(f"{file}2"), rotation=WHITE_PIECE_ROTATION)
            self.make_pawn(black_material, self.chessboard_position_to_world(f"{file}7"))

        self.make_rook(white_material, self.chessboard_position_to_world("a1"), rotation=WHITE_PIECE_ROTATION)
        self.make_rook(white_material, self.chessboard_position_to_world("h1"), rotation=WHITE_PIECE_ROTATION)
        self.make_rook(black_material, self.chessboard_position_to_world("a8"))
        self.make_rook(black_material, self.chessboard_position_to_world("h8"))
        self.make_knight(white_material, self.chessboard_position_to_world("b1"), rotation=WHITE_PIECE_ROTATION)
        self.make_knight(white_material, self.chessboard_position_to_world("g1"), rotation=WHITE_PIECE_ROTATION)
        self.make_knight(black_material, self.chessboard_position_to_world("b8"))
        self.make_knight(black_material, self.chessboard_position_to_world("g8"))
        self.make_bishop(white_material, self.chessboard_position_to_world("c1"), rotation=WHITE_PIECE_ROTATION)
        self.make_bishop(white_material, self.chessboard_position_to_world("f1"), rotation=WHITE_PIECE_ROTATION)
        self.make_bishop(black_material, self.chessboard_position_to_world("c8"))
        self.make_bishop(black_material, self.chessboard_position_to_world("f8"))
        self.make_queen(white_material, self.chessboard_position_to_world("d1"), rotation=WHITE_PIECE_ROTATION)
        self.make_queen(black_material, self.chessboard_position_to_world("d8"))
        self.make_king(white_material, self.chessboard_position_to_world("e1"), rotation=WHITE_PIECE_ROTATION)
        self.make_king(black_material, self.chessboard_position_to_world("e8"))

        from termin.editor_core.render_request import request_scene_tree_rebuild
        request_scene_tree_rebuild()
