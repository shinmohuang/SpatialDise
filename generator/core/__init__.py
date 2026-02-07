"""Core utilities for SpatialDise generators.

Avoid importing Blender-only modules at package import time so pure-Python
helpers (e.g. config/path/cli parsing) remain usable outside Blender.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .base_generator import BaseGenerator

__all__ = ["BaseGenerator"]


def __getattr__(name: str):
    if name == "BaseGenerator":
        from .base_generator import BaseGenerator

        return BaseGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
