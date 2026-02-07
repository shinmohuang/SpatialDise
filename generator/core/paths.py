"""Path helpers for SpatialDise generators."""

import os
from typing import Optional


def default_output_dir(task_name: str, root: Optional[str] = None) -> str:
    """Return default output directory per canonical task name."""
    base = root or "blender_dataset"
    default_dirs = {
        "3d_rotation": os.path.join(base, "3D_rotation"),
        "3d_projection": os.path.join(base, "3D_projection"),
        "3d_combination": os.path.join(base, "3D_combination"),
        "3d_folding": os.path.join(base, "3D_folding"),
        "3d_shape_finding": os.path.join(base, "3D_shape_finding"),
    }
    return default_dirs.get(task_name, os.path.join(base, task_name))


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path
