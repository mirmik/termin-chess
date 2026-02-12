"""Coordinate utilities for chess board mapping.

Tile naming: Tile_{i}_{j}, i,j in [-4, 3]
World position: (i*W, j*W, 0), W=2
Chess mapping: i=-4 -> file 'a', j=-4 -> rank 1
"""

from termin.geombase._geom_native import Vec3

W = 2


def ij_to_square(i: int, j: int) -> str:
    file = chr(i + 4 + ord('a'))
    rank = j + 5
    return f"{file}{rank}"


def square_to_ij(sq: str) -> tuple[int, int]:
    file = sq[0].lower()
    rank = int(sq[1])
    i = ord(file) - ord('a') - 4
    j = rank - 5
    return (i, j)


def square_to_world(sq: str) -> Vec3:
    i, j = square_to_ij(sq)
    return Vec3(i * W, j * W, 0)


def world_to_ij(x: float, y: float):
    i = round(x / W)
    j = round(y / W)
    if -4 <= i <= 3 and -4 <= j <= 3:
        return (i, j)
    return None


def entity_to_square(entity) -> str | None:
    pos = entity.transform.local_position()
    result = world_to_ij(pos.x, pos.y)
    if result is None:
        return None
    i, j = result
    return ij_to_square(i, j)


def tile_name_to_square(name: str) -> str | None:
    parts = name.split("_")
    if len(parts) != 3 or parts[0] != "Tile":
        return None
    i = int(parts[1])
    j = int(parts[2])
    return ij_to_square(i, j)
