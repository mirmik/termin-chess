"""
UnitsCreator component.
"""

from __future__ import annotations

from termin.visualization.core.python_component import PythonComponent
from termin.editor.inspect_field import InspectField
from termin.geombase._geom_native import Vec3, Vec4
from termin.visualization.core.mesh import TcMesh
from termin.visualization.core.material import TcMaterial

W = 2
H = 0.5

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
            action=lambda component: component.to_python().make_units(),
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

    def make_unit(self, material, mesh, position, name="Unit"):
        xpos = position.x * W
        ypos = position.y * W
        zpos = position.z * H 

        pawn_mesh = mesh
        pawn = self.entity.create_child(name=name)
        pawn.transform.set_local_scale(UnitsCreator.SCALE)
        pawn_mr = pawn.add_component_by_name("MeshRenderer")
        pawn_mr.set_field("mesh", pawn_mesh)
        pawn_mr.set_field("material", material)
        pawn.transform.set_local_position(Vec3(xpos, ypos, zpos))

    def make_pawn(self, material, position):
        pawn_mesh = TcMesh.from_name("Hex_Pawn")
        self.make_unit(material, pawn_mesh, position, name="Pawn")
    
    def make_rook(self, material, position):
        rook_mesh = TcMesh.from_name("Hex_Rook")
        print(f"Making rook at {position}: {rook_mesh}")
        self.make_unit(material, rook_mesh, position, name="Rook")
    
    def make_knight(self, material, position):
        knight_mesh = TcMesh.from_name("Hex_Knight")
        self.make_unit(material, knight_mesh, position, name="Knight")
    
    def make_bishop(self, material, position):
        bishop_mesh = TcMesh.from_name("Hex_Bishop")
        self.make_unit(material, bishop_mesh, position, name="Bishop")

    def make_queen(self, material, position):
        queen_mesh = TcMesh.from_name("Hex_Queen")
        self.make_unit(material, queen_mesh, position, name="Queen")

    def make_king(self, material, position):
        king_mesh = TcMesh.from_name("Hex_King")
        self.make_unit(material, king_mesh, position, name="King")

    def make_units(self):
        print("Make Units button clicked.")

        self.entity.destroy_children()

        pawn_mesh = TcMesh.from_name("Hex_Pawn")
        rook_mesh = TcMesh.from_name("Hex_Rook")
        knight_mesh = TcMesh.from_name("Hex_Knight")
        bishop_mesh = TcMesh.from_name("Hex_Bishop")
        queen_mesh = TcMesh.from_name("Hex_Queen")
        king_mesh = TcMesh.from_name("Hex_King")

        white_material = TcMaterial.from_name("WhiteFigure")
        black_material = TcMaterial.from_name("BlackFigure")

        for file in 'abcdefgh':
            self.make_pawn(white_material, self.chessboard_position_to_world(f"{file}2"))
            self.make_pawn(black_material, self.chessboard_position_to_world(f"{file}7"))

        self.make_rook(white_material, self.chessboard_position_to_world("a1"))
        self.make_rook(white_material, self.chessboard_position_to_world("h1"))
        self.make_rook(black_material, self.chessboard_position_to_world("a8"))
        self.make_rook(black_material, self.chessboard_position_to_world("h8"))
        self.make_knight(white_material, self.chessboard_position_to_world("b1"))
        self.make_knight(white_material, self.chessboard_position_to_world("g1"))
        self.make_knight(black_material, self.chessboard_position_to_world("b8"))
        self.make_knight(black_material, self.chessboard_position_to_world("g8"))
        self.make_bishop(white_material, self.chessboard_position_to_world("c1"))
        self.make_bishop(white_material, self.chessboard_position_to_world("f1"))
        self.make_bishop(black_material, self.chessboard_position_to_world("c8"))
        self.make_bishop(black_material, self.chessboard_position_to_world("f8"))
        self.make_queen(white_material, self.chessboard_position_to_world("d1"))
        self.make_queen(black_material, self.chessboard_position_to_world("d8"))
        self.make_king(white_material, self.chessboard_position_to_world("e1"))
        self.make_king(black_material, self.chessboard_position_to_world("e8"))

        from termin.editor.render_request import request_scene_tree_rebuild                                                    
        request_scene_tree_rebuild()