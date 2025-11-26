#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified CLI for SpatialDise generators."""

from __future__ import annotations

import argparse
import sys
from typing import Tuple

from generator.core import logging as log
from generator.core.paths import default_output_dir, ensure_dir
from generator.tasks import get_generator_class, normalize_task_name


def parse_arguments():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    choices = [
        "3d_rotation",
        "3d_folding",
        "3d_combination",
        "3d_projection",
        "3d_shape_finding",
        "rotation",
        "combination",
        "projection",
        "view_matching",
        "box_folding",
        "shape_finding",
    ]
    parser = argparse.ArgumentParser(description="SpatialDise generator CLI")
    parser.add_argument("--task", type=str, default="3d_rotation",
                        choices=choices,
                        help="Task name (3d_* or legacy alias)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (defaults by task)")
    parser.add_argument("--num-questions", type=int, default=10,
                        help="Questions to generate (default: 10)")
    parser.add_argument("--difficulty", type=float, default=0.7,
                        help="Difficulty scale for distractors (0.0-1.0)")
    parser.add_argument("--difficulty-level", type=str, choices=["easy", "medium", "hard"],
                        help="Discrete difficulty level for tasks that expect enums (folding/shape-finding)")
    parser.add_argument("--num-distractors", type=int, default=3,
                        help="Number of distractor options")
    parser.add_argument("--resolution", type=str, default="640x480",
                        help="Image resolution as WIDTHxHEIGHT (e.g., 640x480)")
    parser.add_argument("--min-cells", type=int, default=5,
                        help="Minimum cells in generated shapes")
    parser.add_argument("--max-cells", type=int, default=15,
                        help="Maximum cells in generated shapes")
    parser.add_argument("--rectangular-prob", type=float, default=0.3,
                        help="Probability of using rectangular prisms vs cubes")
    parser.add_argument("--camera-distance", type=float, default=1.0,
                        help="Camera distance factor (legacy compatibility)")
    parser.add_argument("--render-engine", type=str, default="CYCLES",
                        choices=["CYCLES", "BLENDER_EEVEE"],
                        help="Render engine")
    parser.add_argument("--ortho-scale", type=float, default=15.0,
                        help="Orthographic camera scale (legacy default 15)")
    parser.add_argument("--auto-generate-views", action="store_true",
                        help="Enable automatic view candidate generation")
    parser.add_argument("--num-view-candidates", type=int, default=8,
                        help="Number of view candidates when auto-generate is enabled")
    parser.add_argument("--wireframe-render", action="store_true",
                        help="Force enable Freestyle/line-art rendering (on by default)")
    parser.add_argument("--no-wireframe", action="store_true",
                        help="Disable Freestyle/line-art rendering")
    parser.add_argument("--use-gpu", action="store_true", default=True,
                        help="Prefer GPU rendering (default on for compatibility)")
    parser.add_argument("--disable-gpu", action="store_true",
                        help="Force CPU rendering")
    parser.add_argument("--preset", type=str, choices=["easy", "medium", "hard"],
                        help="Use legacy preset tuning for counts/difficulty")
    return parser.parse_args(argv)


def parse_resolution(res_str: str) -> Tuple[int, int]:
    try:
        width, height = map(int, res_str.lower().split("x"))
        return width, height
    except Exception:
        log.warn(f"Invalid resolution '{res_str}', falling back to 640x480")
        return 640, 480


def get_preset_config(preset: str, task: str):
    """Reapply legacy presets to keep old behavior compatible."""
    base_config = {}
    if preset == "easy":
        base_config = {
            "distractor_difficulty": 0.3,
            "num_distractors": 3,
            "num_cells_min": 5,
            "num_cells_max": 8,
            "rectangular_prism_prob": 0.3,
            "difficulty": "easy",
        }
    elif preset == "medium":
        base_config = {
            "distractor_difficulty": 0.6,
            "num_distractors": 3,
            "num_cells_min": 6,
            "num_cells_max": 10,
            "rectangular_prism_prob": 0.5,
            "difficulty": "medium",
        }
    elif preset == "hard":
        base_config = {
            "distractor_difficulty": 0.9,
            "num_distractors": 3,
            "num_cells_min": 8,
            "num_cells_max": 12,
            "rectangular_prism_prob": 0.7,
            "difficulty": "hard",
        }

    if task in ("3d_combination", "combination"):
        if preset == "easy":
            base_config["num_cells_min"] = 4
            base_config["num_cells_max"] = 6
        elif preset == "medium":
            base_config["num_cells_min"] = 5
            base_config["num_cells_max"] = 8
        elif preset == "hard":
            base_config["num_cells_min"] = 6
            base_config["num_cells_max"] = 10
    elif task in ("3d_projection", "view_matching", "projection"):
        if preset == "hard":
            base_config["num_cells_min"] = 7
    elif task in ("3d_folding", "box_folding"):
        base_config["difficulty"] = preset
    elif task in ("3d_shape_finding", "shape_finding"):
        base_config["num_distractors"] = 3
        base_config["ortho_scale"] = 5.0
        base_config["difficulty"] = preset
    return base_config


def main():
    args = parse_arguments()
    task_name = normalize_task_name(args.task)
    output_dir = args.output_dir or default_output_dir(task_name)
    ensure_dir(output_dir)

    width, height = parse_resolution(args.resolution)

    log.info(f"Task: {task_name}")
    log.info(f"Output: {output_dir}")
    generator_cls = get_generator_class(task_name)
    wireframe = True
    if args.no_wireframe:
        wireframe = False
    elif args.wireframe_render:
        wireframe = True

    cfg = {
        "num_questions": args.num_questions,
        "image_resolution": (width, height),
        "num_distractors": args.num_distractors,
        "distractor_difficulty": args.difficulty,
        "num_cells_min": args.min_cells,
        "num_cells_max": args.max_cells,
        "rectangular_prism_prob": args.rectangular_prob,
        "use_rectangular_prisms": args.rectangular_prob > 0,
        "camera_distance_factor": args.camera_distance,
        "render_engine": args.render_engine,
        "ortho_scale": args.ortho_scale,
        "auto_generate_views": args.auto_generate_views,
        "num_candidates": args.num_view_candidates,
        "wireframe_render": wireframe,
        "use_gpu": False if args.disable_gpu else args.use_gpu,
    }
    if args.difficulty_level:
        cfg["difficulty"] = args.difficulty_level
    if args.preset:
        preset_cfg = get_preset_config(args.preset, task_name)
        cfg.update(preset_cfg)
        log.info(f"Using preset={args.preset}")

    log.info("Configuration:")
    for k, v in sorted(cfg.items()):
        log.info(f"  {k}={v}")

    generator = generator_cls(output_dir=output_dir, config=cfg)
    files, summary = generator.generate_dataset()
    log.info(f"Generated {len(files)} questions; summary={summary}")


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
    except ImportError:
        from generator.core import logging as log
        log.warn("This script must be run from within Blender (bpy not found).")
        log.info("Usage: blender --background --python SpatialDise/generator/cli/generate.py -- [arguments]")
        sys.exit(1)

    main()
