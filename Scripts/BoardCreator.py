"""
BoardCreatorComponent component.
"""

from __future__ import annotations

from termin.visualization.core.python_component import PythonComponent
from termin.editor.inspect_field import InspectField
from termin.geombase._geom_native import Vec3, Vec4
from termin.visualization.core.mesh import TcMesh
from termin.visualization.core.material import TcMaterial

print("BoardCreatorComponent loaded.")

def _on_make_board_click(component: "BoardCreatorComponent") -> None:
    """Called when the "Make Board" button is clicked."""
    print("Make Board button clicked.")
    component.to_python().make_board()


class BoardCreatorComponent(PythonComponent):
    """
    Custom component.

    Attributes:
        speed: Movement speed.
    """

    inspect_fields = {
        "Make Board": InspectField(
            label="Make Board",
            kind="button",
            action=_on_make_board_click,
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


    def make_board(self):
        self.entity.destroy_children()
        for i in range(-4, 5):
            for j in range(-4, 5):
                child = self.entity.create_child(name=f"Tile_{i}_{j}")
                mr = child.add_component_by_name("MeshRenderer")
            
                W = 2
                H = 0.5

                child.transform.set_local_scale(Vec3(W,W,H))

                mesh = TcMesh.from_name("Cube")
                white_material = TcMaterial.from_name("WhiteMaterial")
                black_material = TcMaterial.from_name("BlackMaterial")

                white_or_black = white_material if (i + j) % 2 == 0 else black_material

                mr.set_field("mesh", mesh)
                mr.set_field("material", white_or_black)

                child.transform.set_local_position(Vec3(i * W, j * W, 0))

        from termin.editor.render_request import request_scene_tree_rebuild                                                    
        request_scene_tree_rebuild()

        print("Board created.")
