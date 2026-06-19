"""
BoardCreatorComponent component.
"""

from __future__ import annotations

from termin.scene import PythonComponent
from termin.inspect import InspectField
from termin.geombase import Vec3
from termin.mesh import TcMesh
from termin.materials import TcMaterial
from termin.render_components import WorldTextAnchor, WorldTextComponent, WorldTextOrientation  # noqa: F401 - registers native component

print("BoardCreatorComponent loaded.")

TILE_SIZE = 2
TILE_HEIGHT = 0.5
BOARD_COORDINATES_ENTITY = "BoardCoordinates"
BOARD_FIRST_FILE_CENTER = -4 * TILE_SIZE
BOARD_LAST_FILE_CENTER = 3 * TILE_SIZE
BOARD_FIRST_RANK_CENTER = -4 * TILE_SIZE
BOARD_LAST_RANK_CENTER = 3 * TILE_SIZE
BOARD_EDGE_MIN = BOARD_FIRST_FILE_CENTER - TILE_SIZE * 0.5
BOARD_EDGE_MAX = BOARD_LAST_FILE_CENTER + TILE_SIZE * 0.5
COORDINATE_LABEL_OFFSET = 1.2
COORDINATE_LABEL_Z = 0.45
COORDINATE_LABEL_SIZE = 0.7
COORDINATE_LABEL_COLOR = (0.86, 0.82, 0.72, 1.0)


def _on_make_board_click(component: "BoardCreatorComponent") -> None:
    """Called when the "Make Board" button is clicked."""
    print("Make Board button clicked.")
    component.make_board()


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
        self.ensure_coordinate_labels()

    def update(self, dt: float) -> None:
        """Called every frame.

        Args:
            dt: Delta time in seconds.
        """
        pass


    def make_board(self):
        self.entity.destroy_children()
        for i in range(-4, 4):
            for j in range(-4, 4):
                file = chr(i + 4 + ord('a'))
                rank = j + 5
                square_name = f"{file}{rank}"
                child = self.entity.create_child(name=square_name)
                mesh_component = child.add_component_by_name("MeshComponent")
                mr = child.add_component_by_name("MeshRenderer")

                child.transform.set_local_scale(Vec3(TILE_SIZE, TILE_SIZE, TILE_HEIGHT))

                mesh = TcMesh.from_name("Cube")
                white_material = TcMaterial.from_name("WhiteMaterial")
                black_material = TcMaterial.from_name("BlackMaterial")

                white_or_black = white_material if (i + j) % 2 == 0 else black_material

                mesh_component.set_field("mesh", mesh)
                mr.set_field("material", white_or_black)

                child.transform.set_local_position(Vec3(i * TILE_SIZE, j * TILE_SIZE, 0))

                col = child.add_component_by_name("ColliderComponent")
                col.set_field("collider_type", "Box")
                col.set_field("box_size", [1, 1, 1])

        self.ensure_coordinate_labels(rebuild=True)

        from termin.editor_core.render_request import request_scene_tree_rebuild
        request_scene_tree_rebuild()

        print("Board created.")

    def ensure_coordinate_labels(self, rebuild: bool = False) -> None:
        labels_root = self._find_child(BOARD_COORDINATES_ENTITY)
        if labels_root is not None and not rebuild:
            return
        if labels_root is not None:
            labels_root.destroy()

        labels_root = self.entity.create_child(name=BOARD_COORDINATES_ENTITY)
        labels_root.pickable = False
        labels_root.selectable = False

        bottom_y = BOARD_EDGE_MIN - COORDINATE_LABEL_OFFSET
        top_y = BOARD_EDGE_MAX + COORDINATE_LABEL_OFFSET
        left_x = BOARD_EDGE_MIN - COORDINATE_LABEL_OFFSET
        right_x = BOARD_EDGE_MAX + COORDINATE_LABEL_OFFSET

        for file_index, file_name in enumerate("abcdefgh"):
            x = (file_index - 4) * TILE_SIZE
            self._make_coordinate_label(
                labels_root,
                f"file-{file_name}-bottom",
                file_name,
                Vec3(x, bottom_y, COORDINATE_LABEL_Z),
                Vec3(0, 1, 0),
            )
            self._make_coordinate_label(
                labels_root,
                f"file-{file_name}-top",
                file_name,
                Vec3(x, top_y, COORDINATE_LABEL_Z),
                Vec3(0, -1, 0),
            )

        for rank in range(1, 9):
            y = (rank - 5) * TILE_SIZE
            text = str(rank)
            self._make_coordinate_label(
                labels_root,
                f"rank-{rank}-left",
                text,
                Vec3(left_x, y, COORDINATE_LABEL_Z),
                Vec3(1, 0, 0),
            )
            self._make_coordinate_label(
                labels_root,
                f"rank-{rank}-right",
                text,
                Vec3(right_x, y, COORDINATE_LABEL_Z),
                Vec3(-1, 0, 0),
            )

        print("Board coordinate labels ready.")

    def _find_child(self, name: str):
        for child in self.entity.children():
            if child.name == name:
                return child
        return None

    def _make_coordinate_label(self, parent, name: str, text: str, position: Vec3, text_up: Vec3) -> None:
        label = parent.create_child(name=name)
        label.pickable = False
        label.selectable = False
        label.transform.set_local_position(position)

        text_ref = label.add_component_by_name("WorldTextComponent")
        text_component = text_ref.to_python()
        text_component.text = text
        text_component.size = COORDINATE_LABEL_SIZE
        text_component.color = COORDINATE_LABEL_COLOR
        text_component.anchor = WorldTextAnchor.Center
        text_component.orientation = WorldTextOrientation.Fixed
        text_component.plane_normal = (0, 0, 1)
        text_component.text_up = (text_up.x, text_up.y, text_up.z)
        text_component.phase_mark = "transparent"
