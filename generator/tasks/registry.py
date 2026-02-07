"""
Task registry mapping canonical task names to generator classes.
Supports file names beginning with digits by loading via importlib from paths.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Dict, Type

ROOT = Path(__file__).resolve().parent / "3d"

# Map task key to (filename, class name) inside tasks/3d/
TASK_FILES = {
    "3d_rotation": ("3d_rotation.py", "Rotation3DGenerator"),
    "3d_combination": ("3d_combination.py", "Combination3DGenerator"),
    "3d_projection": ("3d_projection.py", "Projection3DGenerator"),
    "3d_folding": ("3d_folding.py", "Folding3DGenerator"),
    "3d_shape_finding": ("3d_shape_finding.py", "ShapeFinding3DGenerator"),
}

def normalize_task_name(name: str) -> str:
    task_name = name.strip()
    if task_name in TASK_FILES:
        return task_name
    raise ValueError(f"Unknown task name: {name}")


def _load_module(task_key: str):
    filename, _ = TASK_FILES[task_key]
    path = ROOT / filename
    module_name = f"SpatialDise.generator.tasks.dynamic_{task_key.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load task module for {task_key} at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


def get_generator_class(name: str):
    task_key = normalize_task_name(name)
    filename, class_name = TASK_FILES[task_key]
    module = _load_module(task_key)
    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise RuntimeError(f"Class {class_name} not found in {filename}") from exc


TASKS: Dict[str, Type] = {k: None for k in TASK_FILES.keys()}  # filled dynamically when accessed
