#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Small-batch regression smoke test for SpatialDise generators.

Run inside Blender:
  conda run -n blender blender --background --python SpatialDise/generator/tests/test_regression.py -- --task 3d_rotation --difficulty easy
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime
import json
import random

try:
    import bpy  # noqa: F401
    BLENDER_AVAILABLE = True
except Exception:
    BLENDER_AVAILABLE = False

GENERATOR_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_ROOT = os.path.dirname(GENERATOR_ROOT)  # SpatialDise/
# repo root containing SpatialDise/
TOP_ROOT = os.path.dirname(PACKAGE_ROOT)
for path in (GENERATOR_ROOT, PACKAGE_ROOT, TOP_ROOT):
    if path not in sys.path:
        sys.path.append(path)

from SpatialDise.generator.tasks import get_generator_class, normalize_task_name  # noqa: E402


TASKS = ["3d_rotation", "3d_folding", "3d_combination",
         "3d_projection", "3d_shape_finding"]
DIFFICULTIES = ["easy", "medium", "hard"]


def parse_args():
    # Blender prepends its own flags; only parse args after the first "--" if present.
    raw_argv = sys.argv
    if "--" in raw_argv:
        raw_argv = raw_argv[raw_argv.index("--") + 1:]
    else:
        raw_argv = raw_argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument("--task", action="append", choices=TASKS + ["rotation", "projection", "view_matching", "combination", "box_folding", "shape_finding"],
                        help="Tasks to run (default: 3d_rotation only)")
    parser.add_argument("--difficulty", action="append",
                        choices=DIFFICULTIES, help="Difficulties to run (default: easy)")
    parser.add_argument("--num-questions", type=int, default=1,
                        help="Questions per task/difficulty")
    parser.add_argument("--resolution", type=str,
                        default="640x480", help="Resolution WxH")
    parser.add_argument("--output-root", type=str, default=None,
                        help="Optional directory to keep rendered outputs (default: temp dir is removed)")
    parser.add_argument("--wireframe-render", action="store_true",
                        help="Enable line-art (Freestyle) rendering for higher contrast")
    args = parser.parse_args(raw_argv)
    return args


def _load_image_size(path: str):
    """Return (width, height) using Blender's image loader to avoid extra deps."""
    img = bpy.data.images.load(path)
    size = (img.size[0], img.size[1])
    bpy.data.images.remove(img)
    return size


def _verify_metadata(meta_path: str, expected_res: tuple[int, int]):
    if not os.path.exists(meta_path):
        raise RuntimeError(f"Metadata file missing: {meta_path}")
    with open(meta_path, "r") as f:
        meta = json.load(f)
    required_keys = ["question_id", "question_image", "options"]
    for key in required_keys:
        if key not in meta:
            raise RuntimeError(f"Metadata missing key '{key}' in {meta_path}")
    if not isinstance(meta["options"], list) or not meta["options"]:
        raise RuntimeError(f"No options found in metadata {meta_path}")
    if "seed" not in meta:
        raise RuntimeError(f"Seed not recorded in metadata {meta_path}")
    if meta.get("question_type") in ("box_folding", "shape_finding"):
        icons_used = meta.get("icons_used", [])
        if icons_used is not None and len(icons_used) == 0:
            log_msg = f"Warning: icons_used empty in {meta_path}"
            print(log_msg)

    # Files must exist and match expected resolution
    images = [meta["question_image"]]
    for opt in meta["options"]:
        img_path = opt.get("image")
        if img_path:
            images.append(img_path)
    for img_path in images:
        if not os.path.exists(img_path):
            raise RuntimeError(f"Missing rendered image: {img_path}")
        w, h = _load_image_size(img_path)
        if (w, h) != expected_res:
            raise RuntimeError(
                f"Image {img_path} has resolution {(w, h)}; expected {expected_res}")


def main():
    if not BLENDER_AVAILABLE:
        print("This test must run inside Blender (bpy missing).")
        sys.exit(1)

    args = parse_args()
    tasks = [normalize_task_name(t) for t in (args.task or TASKS)]
    difficulties = args.difficulty or DIFFICULTIES

    try:
        width, height = map(int, args.resolution.lower().split("x"))
    except Exception:
        width, height = 160, 120

    if args.output_root:
        tmpdir = os.path.abspath(args.output_root)
        os.makedirs(tmpdir, exist_ok=True)
        keep = True
    else:
        # default to repo-local output folder to avoid /var tmp
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = os.path.join(TOP_ROOT, "spatialdise_regression_outputs")
        tmpdir = os.path.join(root, stamp)
        os.makedirs(tmpdir, exist_ok=True)
        keep = True
    print(f"[regression] output dir: {tmpdir}")

    random.seed(12345)
    for task in tasks:
        for diff in difficulties:
            print(f"[regression] task={task} difficulty={diff}")
            out_dir = os.path.join(tmpdir, f"{task}_{diff}")
            cfg = {
                "num_questions": args.num_questions,
                "image_resolution": (width, height),
                "num_distractors": 2,
                "distractor_difficulty": 0.3,
                "num_cells_min": 3,
                "num_cells_max": 5,
                "rectangular_prism_prob": 0.3,
                "use_rectangular_prisms": True,
                "ortho_scale": 10.0,
                "use_gpu": False,
                "difficulty": diff,
            }
            generator_cls = get_generator_class(task)
            gen = generator_cls(output_dir=out_dir, config=cfg)
            files, summary = gen.generate_dataset()
            if not files:
                raise RuntimeError(f"No files generated for {task}/{diff}")
            if summary and not os.path.exists(summary):
                raise RuntimeError(f"Summary missing for {task}/{diff}")
            for meta_path in files:
                _verify_metadata(meta_path, (width, height))
            print(
                f"[regression] generated {len(files)} files; summary={summary}")

    print("[regression] SUCCESS")
    if keep:
        print(f"[regression] kept outputs at {tmpdir}")


if __name__ == "__main__":
    main()
