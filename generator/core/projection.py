"""Projection helpers for 3D → 2D block views."""

from __future__ import annotations

from typing import Iterable, Set, Tuple

import bpy  # type: ignore


def project_block_positions(
    blocks: Iterable[bpy.types.Object],
    view_name: str,
) -> Set[Tuple[int, int]]:
    """
    Project block locations to a 2D grid for a named orthographic view.

    This mirrors the legacy get_projected_positions behavior used by
    the original view-matching generator. Coordinates are rounded to
    integer grid cells and axes are mirrored as before.
    """
    positions: Set[Tuple[int, int]] = set()
    for block in blocks:
        pos = getattr(block, "location", None)
        if pos is None:
            continue

        if "top" in view_name:
            projection = (round(pos.x), round(pos.y))
        elif "front" in view_name:
            projection = (round(pos.x), round(pos.z))
        elif "back" in view_name:
            projection = (-round(pos.x), round(pos.z))
        elif "right" in view_name:
            projection = (round(pos.y), round(pos.z))
        elif "left" in view_name:
            projection = (-round(pos.y), round(pos.z))
        else:
            projection = (round(pos.x), round(pos.y))

        positions.add(projection)

    return positions

