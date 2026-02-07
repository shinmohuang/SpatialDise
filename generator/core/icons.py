"""Lucide icon utilities: download/cache icons and provide deterministic selection."""

from __future__ import annotations

import os
import random
import urllib.request
from pathlib import Path
from typing import Iterable, List, Sequence
import json
import math

from generator.core.paths import ensure_dir
from generator.core import logging as log

try:
    import bpy  # type: ignore
except Exception:  # pragma: no cover - import guard for non-Blender envs
    bpy = None

# Default icon set (short, high-contrast shapes that translate well to textures)
DEFAULT_LUCIDE_ICONS: Sequence[str] = (
    # Keep to simple shapes/icons that have stable Lucide slugs (PNG cached)
    "circle",
    "square",
    "triangle",
    "star",
    "heart",
    "moon",
    "sun",
    "cloud",
    "flame",
    "diamond",
    "box",
    "layers",
    "bolt",
    "key",
    "anchor",
    "shield",
    "arrow-up",
    "arrow-right",
    "arrow-down",
    "arrow-left",
)

# Icon cache dirs:
# - Lucide cache: SpatialDise/assets/lucide/
# - Custom override: SpatialDise/assets/customize/
ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets" / "lucide"
ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
CUSTOM_ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets" / "customize"
CUSTOM_ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
LICENSE_PATH = ASSETS_ROOT / "LICENSE_LUCIDE.txt"

# Lucide static endpoints (SVG-first; PNG converted locally if possible)
LUCIDE_SVG_URL = "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/{name}.svg"
LUCIDE_RAW_URL = "https://unpkg.com/lucide-static@latest/icons/{name}.svg"
LUCIDE_INDEX_URLS = (
    "https://unpkg.com/lucide-static@latest/icons.json",
    "https://raw.githubusercontent.com/lucide-icons/lucide-static/main/icons.json",
    "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons.json",  # fallback if present
)
LUCIDE_GITHUB_CONTENTS = "https://api.github.com/repos/lucide-icons/lucide/contents/icons"


def _write_license_note() -> None:
    if LICENSE_PATH.exists():
        return
    note = (
        "Lucide Icons\n"
        "Source: https://lucide.dev\n"
        "License: ISC\n"
        "Copyright (c) Lucide Contributors\n"
    )
    LICENSE_PATH.write_text(note, encoding="utf-8")


def _download(url: str, dest: Path) -> bool:
    try:
        with urllib.request.urlopen(url) as resp:  # nosec: trusted host
            data = resp.read()
        dest.write_bytes(data)
        return True
    except Exception as exc:  # pragma: no cover - network dependent
        log.warn(f"Failed to download {url}: {exc}")
        return False


def fetch_all_icon_names() -> List[str]:
    """Attempt to fetch the full Lucide icon name list from known endpoints."""
    # Preferred: icons.json (if present)
    for url in LUCIDE_INDEX_URLS:
        try:
            with urllib.request.urlopen(url) as resp:  # nosec
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                # Each entry may be an object or a string
                names: List[str] = []
                for item in data:
                    if isinstance(item, str):
                        names.append(item)
                    elif isinstance(item, dict) and "name" in item:
                        names.append(str(item["name"]))
                if names:
                    return sorted(set(names))
        except Exception as exc:  # pragma: no cover
            log.warn(f"Failed to fetch icon index from {url}: {exc}")
    # Fallback: GitHub contents API for /icons directory
    try:
        with urllib.request.urlopen(LUCIDE_GITHUB_CONTENTS) as resp:  # nosec
            data = json.loads(resp.read().decode("utf-8"))
        names: List[str] = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("name", "").endswith(".svg"):
                    names.append(item["name"].removesuffix(".svg"))
        if names:
            return sorted(set(names))
    except Exception as exc:  # pragma: no cover
        log.warn(f"Failed to fetch icon list from GitHub contents: {exc}")
    return []


def _convert_svg_to_png(svg_path: Path, png_path: Path) -> bool:
    try:
        import cairosvg  # type: ignore
    except Exception:
        log.warn("cairosvg not available; keeping SVG only")
        return False
    try:
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path))
        return True
    except Exception as exc:  # pragma: no cover - depends on cairo env
        log.warn(f"cairosvg failed for {svg_path}: {exc}")
        return False


def _resolve_local_icon(
    name: str,
    root: Path,
    prefer_png: bool,
    allow_svg_fallback: bool,
) -> str | None:
    """Resolve a named icon under one directory root."""
    png_path = root / f"{name}.png"
    svg_path = root / f"{name}.svg"

    if png_path.exists():
        return str(png_path)

    if svg_path.exists() and prefer_png:
        converted = _convert_svg_to_png(svg_path, png_path)
        if converted and png_path.exists():
            return str(png_path)
        if allow_svg_fallback:
            return str(svg_path)

    if svg_path.exists() and (allow_svg_fallback or not prefer_png):
        return str(svg_path)

    return None


def ensure_lucide_icons(
    icon_names: Iterable[str] | None = None,
    download: bool = True,
    prefer_png: bool = True,
    allow_svg_fallback: bool = False,
) -> List[str]:
    """
    Ensure requested icons are present.
    Lookup order per icon name:
      1) assets/customize (local custom override)
      2) assets/lucide cache
      3) download Lucide SVG (if allowed)
    Returns a sorted list of usable icon file paths (PNG preferred, SVG fallback).
    """
    _write_license_note()
    ensure_dir(str(ASSETS_ROOT))
    ensure_dir(str(CUSTOM_ASSETS_ROOT))
    names = list(icon_names or DEFAULT_LUCIDE_ICONS)
    available: List[str] = []

    for name in names:
        # 1) Custom local override
        custom_icon = _resolve_local_icon(
            name=name,
            root=CUSTOM_ASSETS_ROOT,
            prefer_png=prefer_png,
            allow_svg_fallback=allow_svg_fallback,
        )
        if custom_icon:
            available.append(custom_icon)
            continue

        # 2) Lucide local cache
        png_path = ASSETS_ROOT / f"{name}.png"
        svg_path = ASSETS_ROOT / f"{name}.svg"

        if png_path.exists():
            available.append(str(png_path))
            continue
        if svg_path.exists() and prefer_png:
            converted = _convert_svg_to_png(svg_path, png_path)
            if converted and png_path.exists():
                available.append(str(png_path))
                continue
            if allow_svg_fallback:
                available.append(str(svg_path))
                continue
        if svg_path.exists() and (allow_svg_fallback or not prefer_png):
            available.append(str(svg_path))
            continue

        if not download:
            continue

        # Try primary SVG source, then raw GitHub as fallback
        fetched = _download(LUCIDE_SVG_URL.format(name=name), svg_path)
        if not fetched:
            fetched = _download(LUCIDE_RAW_URL.format(name=name), svg_path)
        if not fetched:
            continue

        if prefer_png:
            converted = _convert_svg_to_png(svg_path, png_path)
            if converted and png_path.exists():
                available.append(str(png_path))
            elif allow_svg_fallback:
                available.append(str(svg_path))
        else:
            available.append(str(svg_path))

    return sorted(set(available))


def list_custom_icons(
    prefer_png: bool = True,
    allow_svg_fallback: bool = False,
    root: Path | None = None,
) -> List[str]:
    """List all usable icons under assets/customize (or provided root)."""
    icon_root = root or CUSTOM_ASSETS_ROOT
    ensure_dir(str(icon_root))

    stems = set()
    for path in icon_root.iterdir():
        if path.is_file() and path.suffix.lower() in {".png", ".svg"}:
            stems.add(path.stem)

    resolved: List[str] = []
    for stem in sorted(stems):
        icon_path = _resolve_local_icon(
            name=stem,
            root=icon_root,
            prefer_png=prefer_png,
            allow_svg_fallback=allow_svg_fallback,
        )
        if icon_path:
            resolved.append(icon_path)

    return resolved


def resolve_task_icons(
    icon_names: Iterable[str] | None = None,
    download: bool = True,
    prefer_png: bool = True,
    allow_svg_fallback: bool = False,
) -> List[str]:
    """Resolve icons for tasks.

    Behavior:
    - If `icon_names` is provided: resolve each name (customize -> lucide -> download).
    - If `icon_names` is not provided:
      - use all icons under assets/customize if any exist,
      - otherwise use default Lucide icon names.
    """
    if icon_names is None:
        custom_icons = list_custom_icons(
            prefer_png=prefer_png,
            allow_svg_fallback=allow_svg_fallback,
        )
        if custom_icons:
            return sorted(set(custom_icons))
        icon_names = DEFAULT_LUCIDE_ICONS

    return ensure_lucide_icons(
        icon_names=icon_names,
        download=download,
        prefer_png=prefer_png,
        allow_svg_fallback=allow_svg_fallback,
    )


def select_icons_deterministic(seed: int | None, icons: Sequence[str], count: int) -> List[str]:
    """Deterministically select up to `count` icons using the provided seed."""
    if not icons:
        return []
    rng = random.Random(seed)
    if len(icons) <= count:
        ordered = sorted(icons)
        rng.shuffle(ordered)
        return ordered
    return rng.sample(sorted(icons), count)


# ---------------------------------------------------------------------------
# Material helpers (icon-on-white for cubes and unfolded nets)
# ---------------------------------------------------------------------------

def create_icon_material_for_cube(name: str, icon_path: str, base_color, texture_scale: float = 1.0, face_name: str | None = None):
    """
    Create a simple Principled BSDF material for a cube face:
    - White background.
    - Icon texture overlaid on top, using UVs.
    - Optional orientation tweaks for specific faces via Mapping.

    This helper assumes the icon PNG already has a white background (no heavy alpha logic).
    """
    if bpy is None:
        raise RuntimeError("create_icon_material_for_cube must be called inside Blender (bpy not available)")

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (100, 0)
    # Use white as base; icon will fully cover it in most cases
    bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bsdf.inputs["Alpha"].default_value = 1.0
    mat.blend_method = "OPAQUE"

    # Load image
    if not os.path.exists(icon_path):
        log.warn(f"Icon file not found for cube material: {icon_path}")
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        return mat

    image_name = os.path.basename(icon_path)
    img = bpy.data.images.get(image_name)
    if img is None:
        img = bpy.data.images.load(icon_path, check_existing=True)

    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (-100, 0)
    tex.image = img
    tex.extension = "REPEAT"

    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-400, 0)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-250, 0)

    # Scale: smaller scale => larger icon
    adjusted_scale = 1.0 / float(texture_scale or 1.0)

    if face_name == "left":
        mapping.inputs["Scale"].default_value = (-adjusted_scale, adjusted_scale, 1.0)
    elif face_name == "back":
        mapping.inputs["Scale"].default_value = (adjusted_scale, -adjusted_scale, 1.0)
    else:
        mapping.inputs["Scale"].default_value = (adjusted_scale, adjusted_scale, 1.0)

    mapping.inputs["Location"].default_value = (0.0, 0.0, 0.0)

    links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def create_icon_material_for_unfolded(name: str, icon_path: str, base_color, texture_scale: float = 1.0, rotation_angle: float = 0.0):
    """
    Create a simple Emission-based material for unfolded net faces:
    - White background.
    - Icon texture mapped via UV and optional Z-rotation.
    - Emission output avoids shading artifacts in 2D net renders.
    """
    if bpy is None:
        raise RuntimeError("create_icon_material_for_unfolded must be called inside Blender (bpy not available)")

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)

    emission = nodes.new("ShaderNodeEmission")
    emission.location = (100, 0)
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0

    if not os.path.exists(icon_path):
        log.warn(f"Icon file not found for unfolded material: {icon_path}")
        links.new(emission.outputs["Emission"], out.inputs["Surface"])
        return mat

    image_name = os.path.basename(icon_path)
    img = bpy.data.images.get(image_name)
    if img is None:
        img = bpy.data.images.load(icon_path, check_existing=True)

    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (-100, 0)
    tex.image = img
    tex.extension = "REPEAT"

    coord = nodes.new("ShaderNodeTexCoord")
    coord.location = (-400, 0)

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-250, 0)

    adjusted_scale = 1.0 / float(texture_scale or 1.0)
    mapping.inputs["Scale"].default_value = (adjusted_scale, adjusted_scale, 1.0)

    if rotation_angle:
        mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(rotation_angle))

    mapping.inputs["Location"].default_value = (0.0, 0.0, 0.0)

    links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], out.inputs["Surface"])
    return mat
