# Dataset Generation Pipeline for Spatial-DISE [ICLR 2026]

[![PDF (OpenReview)](https://img.shields.io/badge/PDF-OpenReview-B31B1B?logo=readthedocs&logoColor=white)](https://openreview.net/forum?id=bMINsPQpME)
[![Dataset (Hugging Face)](https://img.shields.io/badge/Dataset-Hugging%20Face-FFB000?logo=huggingface&logoColor=black)](https://huggingface.co/collections/TACPS-liv/spatial-dise)
[![Project Page](https://img.shields.io/badge/Project%20Page-SpatialDise-2D7FF9?logo=googlechrome&logoColor=white)](https://shinmohuang.github.io/spatialdise_page/)

SpatialDise is a Blender-based dataset generator for 3D spatial reasoning tasks.
It creates rendered images plus JSON metadata for:

- `3d_rotation`
- `3d_projection`
- `3d_combination`
- `3d_folding`
- `3d_shape_finding`

## Requirements

- Python `>= 3.10`
- Blender (recommended `3.6+`) available as `blender` in your shell
- `uv` (recommended for dependency management)

## Repository Layout

- `generator/core/`: shared camera/scene/render/geometry utilities
- `generator/tasks/3d/`: task implementations
- `generator/cli/`: command-line entrypoints
- `generator/scripts/`: helper scripts (for example icon caching)
- `generator/tests/test_regression.py`: Blender regression smoke test
- `tests/`: pure Python unit tests
- `configs/spatialdise_3d.yaml`: sample multi-task config
- `assets/lucide/`: cached icon assets used by folding/shape-finding tasks

## Install

From repository root:

```bash
uv venv .venv
source .venv/bin/activate
uv sync --group dev
```

This installs runtime dependencies and `pytest` for local tests.


If this fails, install Blender and add it to your `PATH`.

## Install Blender

1. Download Blender from the official site: <https://www.blender.org/download/>
2. Install Blender.
3. Make sure `blender` is callable from your terminal:

```bash
blender --version
```

If your shell cannot find `blender`, add Blender to `PATH`:

- Linux/macOS: add the Blender executable directory to your shell profile.
- Windows: add Blender install directory to Environment Variables `Path`.


## Quick Start (Single Task)

Run one generator directly inside Blender:

```bash
blender --background --python generator/cli/generate.py -- \
  --task 3d_rotation \
  --num-questions 5 \
  --difficulty-level easy \
  --resolution 640x480 \
  --output-dir blender_dataset/3D_rotation_demo
```

Notes:

- Arguments after `--` are passed to the Python script.
- `--difficulty-level` is the discrete level (`easy|medium|hard`).
- `--difficulty` in this CLI is a numeric distractor scale.

## Run Multiple Tasks from Config

Use the sample config:

```bash
blender --background --python generator/cli/config_generate.py -- \
  --config configs/spatialdise_3d.yaml
```

Dry run (show planned jobs only):

```bash
blender --background --python generator/cli/config_generate.py -- \
  --config configs/spatialdise_3d.yaml \
  --dry-run
```

Run only selected tasks from config:

```bash
blender --background --python generator/cli/config_generate.py -- \
  --config configs/spatialdise_3d.yaml \
  --task 3d_folding \
  --task 3d_shape_finding
```

## Config System

SpatialDise supports two config styles:

1. Multi-task config (recommended): `defaults` + `tasks`
2. Single-task config: one task object at root

Example (multi-task):

```yaml
defaults:
  output_root: blender_dataset
  image_resolution: [640, 480]
  num_questions: 20
  difficulty: medium
  use_gpu: true

tasks:
  - task: 3d_rotation
    difficulty: hard
    num_questions: 30

  - task: 3d_folding
    difficulty: medium
    lucide_download: false
```

Config behavior:

- Each task config is merged as: `task_item` overrides `defaults`.
- `task` is required per job (or `name` / `generator` as fallback).
- `preset` is ignored in `config_generate.py`; use explicit fields like
  `difficulty`, `num_cells_min`, `num_cells_max`, `distractor_difficulty`.
- `image_resolution` can be `[W, H]`; it is normalized to `(W, H)` internally.

Output directory behavior:

- If `output_dir` is set in a task, it is used directly.
- Else if `output_root` is set, output is:
  `output_root/<TaskDefaultName>/<difficulty>` (difficulty suffix only when set).
- Else default output is used (`blender_dataset/3D_*`, with optional difficulty suffix).

Available example configs:

- Basic example: `configs/spatialdise_3d.yaml`
- Full-parameter example: `configs/spatialdise_3d_full_example.yaml`

## Task Names

Supported task names:

- `3d_rotation`
- `3d_projection`
- `3d_combination`
- `3d_folding`
- `3d_shape_finding`

## Output Structure

By default, output folders are under `blender_dataset/`:

- `3d_rotation` -> `blender_dataset/3D_rotation`
- `3d_projection` -> `blender_dataset/3D_projection`
- `3d_combination` -> `blender_dataset/3D_combination`
- `3d_folding` -> `blender_dataset/3D_folding`
- `3d_shape_finding` -> `blender_dataset/3D_shape_finding`

Each task writes:

- rendered images (`*_Q.png`, `*_A*.png`, etc.)
- per-question metadata JSON
- a summary file

## Icon Sources (Folding / Shape Finding)

`3d_folding` and `3d_shape_finding` can use:

- Lucide icons under `assets/lucide/`
- Custom icons under `assets/customize/`

Recommended format: **PNG**.

- Put custom icons in `assets/customize/*.png` whenever possible.
- `3d_shape_finding` uses `allow_svg_fallback=false`, so SVG-only icons may be skipped.

### Runtime Resolution Rules

When `lucide_icons` is **not set**:

- If `assets/customize/` has icons, use all available custom icons.
- Otherwise, use the default Lucide icon list.

When `lucide_icons` **is set**:

Each icon name is resolved in this order:

1) `assets/customize/{name}.png|.svg`  
2) `assets/lucide/{name}.png|.svg`  
3) download from Lucide (when `lucide_download: true`)

### Pre-cache Lucide Icons

You can pre-cache Lucide icons:

```bash
uv run generator/scripts/cache_lucide_icons.py -- --icons circle square triangle
```

Cache all available icons:

```bash
uv run generator/scripts/cache_lucide_icons.py -- --all
```

If PNG conversion fails, install `cairosvg` or allow SVG fallback with:

```bash
uv run generator/scripts/cache_lucide_icons.py -- --allow-svg-fallback
```

### Lucide License

- Source: https://lucide.dev
- License: ISC
- Copyright: Lucide Contributors
- Local license note: `assets/lucide/LICENSE_LUCIDE.txt`

When redistributing generated assets that include Lucide icons, keep the
license attribution above.

## Replace or Customize Icons

### Use a custom icon list

Option 1: pass icons directly:

```bash
uv run generator/scripts/cache_lucide_icons.py -- --icons circle square triangle heart
```

Option 2: use a file:

```bash
uv run generator/scripts/cache_lucide_icons.py -- --icons-file ./my_icons.txt
```

`my_icons.txt` example:

```text
circle
square
triangle
heart
```

### Force a full replacement of local cached icons

If you want to replace the existing icon cache completely:

```bash
rm -f assets/lucide/*.png assets/lucide/*.svg
uv run generator/scripts/cache_lucide_icons.py -- --icons-file ./my_icons.txt
```

Notes:

- `lucide_download: false` means use local cache only.
- `lucide_download: true` allows downloading missing icons at runtime.
- If an icon with the same name exists in `assets/customize/`, it overrides Lucide.
- For best compatibility, store custom icons as PNG files.

## Testing

Pure Python tests:

```bash
pytest -q
```

Blender regression smoke test (all tasks, all difficulties):

```bash
blender --background --python generator/tests/test_regression.py -- \
  --output-root ./tmp/regression_full
```

Smaller run:

```bash
blender --background --python generator/tests/test_regression.py -- \
  --task 3d_projection \
  --difficulty easy \
  --num-questions 2 \
  --output-root ./tmp/regression_projection
```

## Troubleshooting

- `bpy not found`
  Run scripts with Blender (`blender --background --python ...`), not plain `python`.

- YAML config fails to load (`PyYAML` missing)
  Install dependencies into your environment (`uv sync`) and ensure Blender can access them.

- Folding/shape-finding has missing icon textures
  Run the icon cache script first, and verify files exist under `assets/lucide/`.

- Blender command not found
  Install Blender and add it to your shell `PATH`.

## Minimal Python API Example

```python
from generator.tasks import get_generator_class

Generator = get_generator_class("3d_rotation")
gen = Generator(
    output_dir="blender_dataset/3D_rotation_api_demo",
    config={
        "num_questions": 3,
        "image_resolution": (640, 480),
        "difficulty": "easy",
        "use_gpu": False,
    },
)
files, summary = gen.generate_dataset()
print(len(files), summary)
```

## Citation

If you find Spatial-DISE helpful, please cite:

```bibtex
@inproceedings{huang2025spatialdise,
  title = {Spatial-{{DISE}}: {{A Unified Benchmark}} for {{Evaluating Spatial Reasoning}} in {{Vision-Language Models}}},
  booktitle = {The {{Fourteenth International Conference}} on {{Learning Representations}}},
  author = {Huang, Xinmiao and He, Qisong and Huang, Zhenglin and Wang, Boxuan and Li, Zhuoyun and Cheng, Guangliang and Dong, Yi and Huang, Xiaowei},
  year = 2025
}
```
