#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-download Lucide icons to SpatialDise/assets/lucide as PNG (SVG fallback only if requested).
Usage:
  blender --background --python SpatialDise/generator/scripts/cache_lucide_icons.py -- [options]
  or run with a regular Python interpreter if cairosvg is available.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add the root directory of SpatialDise to sys.path
script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(script_dir.parent.parent.parent))

from generator.core import icons as icon_utils
from generator.core.logging import info, warn


def parse_args():
    parser = argparse.ArgumentParser(description="Cache Lucide icons locally")
    parser.add_argument("--icons", type=str, nargs="*", default=None,
                        help="Icon names to download (defaults to built-in list)")
    parser.add_argument("--icons-file", type=str, default=None,
                        help="Path to a JSON/txt file containing icon names (one per line or JSON array)")
    parser.add_argument("--all", action="store_true",
                        help="Download all available Lucide icons (from icons.json)")
    parser.add_argument("--prefer-png", action="store_true", default=True,
                        help="Prefer PNG output (default on)")
    parser.add_argument("--allow-svg-fallback", action="store_true", default=True,
                        help="Keep SVG if PNG conversion fails (useful if cairosvg is missing)")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])


def load_icon_list(args) -> list[str]:
    if args.all:
        names = icon_utils.fetch_all_icon_names()
        if names:
            return names
        warn("Failed to fetch full icon list; falling back to defaults")

    if args.icons_file:
        path = Path(args.icons_file)
        if not path.exists():
            raise FileNotFoundError(f"icons-file not found: {path}")
        if path.suffix.lower() in {".json"}:
            names = json.loads(path.read_text())
            if not isinstance(names, list):
                raise ValueError("icons-file JSON must be an array of strings")
            return [str(x) for x in names]
        # fallback: one per line
        return [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if args.icons:
        return args.icons
    return list(icon_utils.DEFAULT_LUCIDE_ICONS)


def main():
    args = parse_args()
    names = load_icon_list(args)
    info(f"Downloading {len(names)} Lucide icons...")
    icons = icon_utils.ensure_lucide_icons(
        names,
        download=True,
        prefer_png=args.prefer_png,
        allow_svg_fallback=args.allow_svg_fallback,
    )
    png_count = len([p for p in icons if p.lower().endswith(".png")])
    svg_count = len([p for p in icons if p.lower().endswith(".svg")])
    if icons:
        info(f"Cached {len(icons)} icons under {icon_utils.ASSETS_ROOT} (PNG={png_count}, SVG={svg_count})")
        if png_count == 0:
            warn("No PNGs cached; install cairosvg if you want textures usable in Blender, or allow SVG fallback in configs.")
    else:
        warn("No icons cached. Check network/cairosvg availability.")


if __name__ == "__main__":
    main()
