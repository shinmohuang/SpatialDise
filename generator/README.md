# SpatialDise Generator Notes

## Lucide Icons (Folding / Shape Finding)
- Icons are sourced from the Lucide icon set (ISC license). Cached under `SpatialDise/assets/lucide/`. A license note is stored as `LICENSE_LUCIDE.txt`.
- Use `SpatialDise/generator/scripts/cache_lucide_icons.py` to pre-download icons (PNG preferred). You can provide `--icons-file` (JSON/txt), `--icons ...` list, or `--all` to fetch the full set via Lucide’s `icons.json` or GitHub contents (`https://github.com/lucide-icons/lucide/tree/main/icons`). Run once online, then set `lucide_download=False` for offline runs.
- Default icon list includes simple, stable slugs (e.g., circle, square, triangle, star, heart, moon, sun, cloud, flame, diamond, box, layers, bolt, key, anchor, shield, arrow-*). Override with `config["lucide_icons"]`.
- PNG is preferred; if PNG conversion fails and only SVG exists, icons are skipped to avoid OpenImageIO errors (fallback to patterns). Install `cairosvg` in the Blender Python env to convert SVG→PNG during caching.
- Selection is deterministic: icon choices are derived from the per-question seed so renders repeat across runs.
- Icon mapping behavior matches the legacy implementation: textures use REPEAT with a scale of `1.0/texture_scale` (per-face corrections for left/back), so icons can tile to cover faces. Adjust `texture_scale` to control density.
- If no icons are available (offline and cache empty), generators fall back to geometric patterns.
- In this repo, Lucide PNGs under `SpatialDise/assets/lucide` are **pre-flattened onto a white background**, and SVG sources are removed after caching. Generators therefore treat Lucide icons as opaque RGB textures on white, and no longer rely on complex alpha/brightness heuristics when building materials.

## Regression Test
- `SpatialDise/generator/tests/test_regression.py` renders all 3D tasks by default. It verifies metadata fields (including seeds) and checks image resolutions. For folding/shape-finding it will warn if `icons_used` is empty.
