# -*- coding: utf-8 -*-
"""Flatten Lucide PNG assets onto a white background."""

from pathlib import Path

from PIL import Image


def flatten(root: Path) -> int:
    """Flatten all PNGs under root, overwriting in place."""
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")

    processed = 0
    for path in sorted(root.glob("*.png")):
        try:
            img = Image.open(path).convert("RGBA")
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            bg.alpha_composite(img)
            bg.convert("RGB").save(path)
            processed += 1
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"Failed {path.name}: {exc}")

    return processed


if __name__ == "__main__":
    assets_dir = Path(__file__).resolve().parent.parent / "assets" / "lucide"
    count = flatten(assets_dir)
    print(f"Flattened {count} PNGs to white background in {assets_dir}")
