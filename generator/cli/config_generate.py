#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run one or more SpatialDise generators from a YAML/JSON config file.

Usage (inside Blender):

  blender --background --python generator/cli/config_generate.py -- \\
    --config path/to/config.yaml

Config format (YAML example, single difficulty field):

  defaults:
    image_resolution: [640, 480]
    num_questions: 50
    use_gpu: true

  tasks:
    - task: 3d_folding
      output_dir: blender_dataset/box_folding
      difficulty: medium
    - task: 3d_rotation
      output_dir: blender_dataset/3d_rotation
      num_questions: 100
      difficulty: hard
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

# Ensure repo root is importable when running directly via Blender
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

def _maybe_add_local_venv() -> None:
    """Try to reuse the project's .venv site-packages when Blender ships its own Python."""
    venv_dir = REPO_ROOT / ".venv"
    if not venv_dir.exists():
        return

    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for base in ("lib", "lib64"):
        site_dir = venv_dir / base / py_ver / "site-packages"
        if site_dir.exists():
            site_dir_str = str(site_dir)
            if site_dir_str not in sys.path:
                sys.path.insert(0, site_dir_str)

_maybe_add_local_venv()

from generator.core import logging as log
from generator.core.paths import default_output_dir, ensure_dir
from generator.tasks import get_generator_class, normalize_task_name


def _parse_argv() -> argparse.Namespace:
    """Parse CLI arguments, respecting Blender's `--` separator."""
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Run SpatialDise generators from a YAML/JSON config file"
    )
    parser.add_argument(
        "--config",
        "-c",
        required=True,
        help="Path to YAML/JSON config file describing generation jobs",
    )
    parser.add_argument(
        "--task",
        action="append",
        dest="only_tasks",
        help="Optional: only run the specified task(s) (normalized name, e.g. 3d_folding)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned jobs without actually running generators",
    )
    return parser.parse_args(argv)


def _load_config_file(path: str) -> Dict[str, Any]:
    """Load a YAML or JSON config file.

    - .yaml / .yml → YAML (requires PyYAML)
    - .json        → JSON
    - others       → try YAML first, then JSON
    """
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    suffix = cfg_path.suffix.lower()
    text = cfg_path.read_text(encoding="utf-8")

    def _try_yaml() -> Dict[str, Any]:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "PyYAML is required to load .yaml/.yml config files. "
                "Install it into the Blender Python environment or use JSON instead."
            ) from exc
        data = yaml.safe_load(text)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError("Config root must be a mapping (YAML object).")
        return data

    def _try_json() -> Dict[str, Any]:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Config root must be a JSON object.")
        return data

    if suffix in {".yaml", ".yml"}:
        return _try_yaml()
    if suffix == ".json":
        return _try_json()

    # Fallback: try YAML, then JSON
    try:
        return _try_yaml()
    except Exception:
        return _try_json()


def _iter_jobs(raw_cfg: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Yield per-task job configs, merging with defaults if present.

    Supports two shapes:
      1) Multi-task:
           defaults: {...}
           tasks:
             - task: 3d_folding
               ...
             - task: 3d_rotation
               ...
      2) Single-task:
           task: 3d_folding
           num_questions: 10
           ...
    """
    defaults = raw_cfg.get("defaults") or {}
    tasks = raw_cfg.get("tasks")

    if tasks is None:
        # Treat the whole mapping as a single task config
        tasks = [raw_cfg]

    for item in tasks:
        if not isinstance(item, dict):
            log.warn(f"Skipping non-mapping task entry: {item!r}")
            continue
        merged = {**defaults, **item}
        yield merged


def _normalize_resolution(cfg: Dict[str, Any]) -> None:
    """Normalize image_resolution into a (width, height) tuple if specified."""
    if "image_resolution" not in cfg:
        return
    val = cfg["image_resolution"]
    if isinstance(val, (list, tuple)) and len(val) == 2:
        try:
            cfg["image_resolution"] = (int(val[0]), int(val[1]))
        except Exception:
            log.warn(f"Invalid image_resolution value {val!r}; leaving as-is")


def _prepare_generator_config(task_cfg: Dict[str, Any], task_name: str) -> Dict[str, Any]:
    """Strip non-generator keys and normalize values."""
    cfg = dict(task_cfg)
    for key in ("task", "name", "generator", "output_dir"):
        cfg.pop(key, None)

    # Ignore deprecated preset field for config-based runs; prefer difficulty only.
    preset = cfg.pop("preset", None)
    if preset:
        log.warn(
            f"[config] 'preset' is deprecated for config_generate; "
            f"preset={preset!r} for task={task_name} will be ignored. "
            "Use 'difficulty' and explicit numeric fields instead."
        )

    _normalize_resolution(cfg)
    return cfg


def main() -> None:
    args = _parse_argv()
    raw_cfg = _load_config_file(args.config)
    only_tasks: List[str] = [
        normalize_task_name(t) for t in (args.only_tasks or [])
    ]

    jobs = list(_iter_jobs(raw_cfg))
    if not jobs:
        log.warn("No tasks found in config; nothing to do.")
        return

    log.info(f"[config] Loaded {len(jobs)} job(s) from {args.config}")

    for job in jobs:
        raw_task_name = job.get("task") or job.get("name") or job.get("generator")
        if not raw_task_name:
            log.warn(f"[config] Skipping job without 'task'/'name'/'generator': {job!r}")
            continue

        task_name = normalize_task_name(str(raw_task_name))
        if only_tasks and task_name not in only_tasks:
            log.info(f"[config] Skipping task={task_name} (filtered by --task)")
            continue

        output_dir = job.get("output_dir")
        if not output_dir:
            output_root = job.get("output_root")
            base_dir = default_output_dir(task_name, root=output_root) if output_root else default_output_dir(task_name)
            difficulty = job.get("difficulty") or job.get("difficulty_level")
            if isinstance(difficulty, str) and difficulty.strip():
                output_dir = Path(base_dir) / difficulty.strip()
            else:
                output_dir = base_dir
        output_dir = ensure_dir(str(output_dir))

        gen_cfg = _prepare_generator_config(job, task_name)

        log.info(f"[config] Task={task_name}")
        log.info(f"[config] Output={output_dir}")
        log.info(f"[config] Generator config:")
        for k in sorted(gen_cfg.keys()):
            log.info(f"  {k}={gen_cfg[k]!r}")

        if args.dry_run:
            log.info(f"[config] Dry run: not executing generator for {task_name}")
            continue

        generator_cls = get_generator_class(task_name)
        generator = generator_cls(output_dir=output_dir, config=gen_cfg)
        files, summary = generator.generate_dataset()
        count = len(files) if isinstance(files, list) else 0
        log.info(f"[config] Generated {count} questions for {task_name}; summary={summary}")


if __name__ == "__main__":
    try:
        import bpy  # type: ignore  # noqa: F401
    except ImportError:
        from generator.core import logging as log
        log.warn("This script must be run from within Blender (bpy not found).")
        log.info("Usage: blender --background --python SpatialDise/generator/cli/config_generate.py -- --config path/to/config.yaml")
        sys.exit(1)

    main()
