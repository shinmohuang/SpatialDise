# -*- coding: utf-8 -*-
"""Remove all SVG files from SpatialDise/assets/lucide."""

from pathlib import Path


def delete_svgs(root: Path) -> int:
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")
    removed = 0
    for path in root.glob("*.svg"):
        try:
            path.unlink()
            removed += 1
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"Failed to delete {path.name}: {exc}")
    return removed


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "assets" / "lucide"
    count = delete_svgs(target)
    print(f"Deleted {count} svg files under {target}")
