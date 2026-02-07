#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared base for SpatialDise generators backed by core modules."""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime

try:
    import bpy  # type: ignore
    import mathutils  # type: ignore
except ImportError:
    print("This script must be run inside Blender (bpy not found)")
    import sys
    sys.exit(1)

from generator.core import camera as camera_utils
from generator.core import geometry
from generator.core import render as render_utils
from generator.core import scene as scene_utils
from generator.core.logging import info
from generator.core.paths import default_output_dir, ensure_dir


class BaseGenerator:
    """Base class for spatial reasoning generators using shared core helpers."""

    def __init__(self, generator_name: str, output_dir: str | None = None, config: dict | None = None):
        # Default output stays repo-local (scripts folder)
        if output_dir is None:
            normalized = generator_name.lower() if generator_name else "generator"
            output_dir = default_output_dir(normalized)
        self.output_dir = ensure_dir(output_dir)

        self.default_config = {
            "num_questions": 10,
            "image_resolution": (640, 480),
            "num_distractors": 3,
            "distractor_difficulty": 1,
            "num_cells_min": 5,
            "num_cells_max": 15,
            "use_rectangular_prisms": True,
            "rectangular_prism_prob": 0.3,
            "camera_distance_factor": 1.0,
            "render_engine": "CYCLES",
            "material_style": "solid",
            "ortho_scale": 15.0,
            "collision_threshold": 0.05,
            "wireframe_render": True,  # Freestyle by default
            "use_gpu": True,
            "difficulty": "easy",
        }
        self.config = {**self.default_config, **(config or {})}

        self.grid_coords = [(x, y, z) for x in (-1, 0, 1)
                            for y in (-1, 0, 1)
                            for z in (-1, 0, 1)]
        self.shape_types = [
            {"name": "cube", "dimensions": (1.0, 1.0, 1.0)},
            {"name": "x_prism", "dimensions": (2.0, 1.0, 1.0)},
            {"name": "y_prism", "dimensions": (1.0, 2.0, 1.0)},
            {"name": "z_prism", "dimensions": (1.0, 1.0, 2.0)},
        ]
        self.iso_views = [
            {"name": "iso_front_top_right", "pos": (6.0, -4.0, 4.0), "look_at": (0, 0, 0)},
            {"name": "iso_back_top_right", "pos": (6.0, 4.0, 4.0), "look_at": (0.1, -0.1, 0)},
            {"name": "iso_front_top_left", "pos": (-6.0, -4.0, 4.0), "look_at": (0.1, 0.1, 0)},
            {"name": "iso_back_top_left", "pos": (-6.0, 4.0, 4.0), "look_at": (-0.1, -0.1, 0)},
        ]

    # Scene/camera/render helpers
    def evaluate_visibility(self, view, cubes, camera):
        return camera_utils.evaluate_visibility(view, cubes, camera)

    def clear_scene(self):
        scene_utils.clear_scene()

    def clear_question_objects(self):
        scene_utils.clear_question_objects()

    def setup_gpu_acceleration(self):
        return render_utils.setup_gpu_acceleration(self.config)

    def setup_scene(self):
        return scene_utils.setup_scene(self.config)

    def render_image(self, filepath):
        return render_utils.render_image(filepath)

    def set_camera_to_view(self, camera, view, add_randomness=True):
        return camera_utils.set_camera_to_view(camera, view, add_randomness=add_randomness)

    def find_best_view(self, views, cubes, camera, prefer_isometric=True, iso_bonus=2.0, auto_generate=False, num_candidates=12):
        return camera_utils.find_best_view(self, views, cubes, camera, prefer_isometric=prefer_isometric, iso_bonus=iso_bonus, auto_generate=auto_generate, num_candidates=num_candidates)

    def generate_view_candidates(self, shape_center, shape_extent, num_candidates=12, distance_factor=1.2):
        return camera_utils.generate_view_candidates(shape_center, shape_extent, num_candidates, distance_factor)

    # Geometry helpers
    def create_combination_shape(self, use_rectangular=None, rect_prob=None, seed=None,
                                 remove_blocks=0, growth_history=None):
        return geometry.create_combination_shape(
            self,
            use_rectangular=self.config["use_rectangular_prisms"] if use_rectangular is None else use_rectangular,
            rect_prob=self.config["rectangular_prism_prob"] if rect_prob is None else rect_prob,
            seed=seed,
            remove_blocks=remove_blocks,
            growth_history=growth_history,
        )

    def get_shape_center(self, blocks):
        return geometry.get_shape_center(blocks)

    def get_shape_extent(self, blocks):
        return geometry.get_shape_extent(blocks)

    def is_top_view_different(self, original_positions, distractor_blocks):
        return geometry.is_top_view_different(original_positions, distractor_blocks)

    def check_collision(self, obj1, obj2, threshold=None):
        threshold = self.config.get("collision_threshold", 0.05) if threshold is None else threshold
        return geometry.check_collision(obj1, obj2, threshold)

    def check_and_fix_overlaps(self, master_obj):
        """Resolve obvious overlaps via AABB checks; mirrors legacy behavior."""
        blocks = list(master_obj.children)
        if len(blocks) <= 1:
            return 0

        overlap_threshold = 0.001
        fixed_count = 0

        for i in range(len(blocks)):
            block_i = blocks[i]
            i_world = block_i.matrix_world
            i_bbox = [i_world @ mathutils.Vector(v) for v in block_i.bound_box]
            i_min = mathutils.Vector((min(v.x for v in i_bbox), min(v.y for v in i_bbox), min(v.z for v in i_bbox)))
            i_max = mathutils.Vector((max(v.x for v in i_bbox), max(v.y for v in i_bbox), max(v.z for v in i_bbox)))

            for j in range(i + 1, len(blocks)):
                block_j = blocks[j]
                j_world = block_j.matrix_world
                j_bbox = [j_world @ mathutils.Vector(v) for v in block_j.bound_box]
                j_min = mathutils.Vector((min(v.x for v in j_bbox), min(v.y for v in j_bbox), min(v.z for v in j_bbox)))
                j_max = mathutils.Vector((max(v.x for v in j_bbox), max(v.y for v in j_bbox), max(v.z for v in j_bbox)))

                overlap = not (i_max.x < j_min.x or i_min.x > j_max.x or
                               i_max.y < j_min.y or i_min.y > j_max.y or
                               i_max.z < j_min.z or i_min.z > j_max.z)
                if not overlap:
                    continue

                overlap_min = mathutils.Vector((max(i_min.x, j_min.x), max(i_min.y, j_min.y), max(i_min.z, j_min.z)))
                overlap_max = mathutils.Vector((min(i_max.x, j_max.x), min(i_max.y, j_max.y), min(i_max.z, j_max.z)))
                overlap_size = overlap_max - overlap_min
                overlap_volume = overlap_size.x * overlap_size.y * overlap_size.z
                if overlap_volume <= overlap_threshold:
                    continue

                i_center = (i_min + i_max) / 2
                j_center = (j_min + j_max) / 2
                dir_i = (i_center - overlap_min).normalized()
                dir_j = (j_center - overlap_min).normalized()

                i_is_cube = (abs(block_i.dimensions.x - block_i.dimensions.y) < 0.1 and
                             abs(block_i.dimensions.x - block_i.dimensions.z) < 0.1)
                j_is_cube = (abs(block_j.dimensions.x - block_j.dimensions.y) < 0.1 and
                             abs(block_j.dimensions.x - block_j.dimensions.z) < 0.1)

                if i_is_cube and not j_is_cube:
                    move_i = True
                elif j_is_cube and not i_is_cube:
                    move_i = False
                else:
                    i_volume = block_i.dimensions.x * block_i.dimensions.y * block_i.dimensions.z
                    j_volume = block_j.dimensions.x * block_j.dimensions.y * block_j.dimensions.z
                    move_i = i_volume <= j_volume

                move_dist = max(0.05, overlap_size.length * 0.6)
                if move_i:
                    block_i.location += dir_i * move_dist
                else:
                    block_j.location += dir_j * move_dist

                bpy.context.view_layer.update()
                fixed_count += 1

        if fixed_count > 0:
            info(f"Fixed {fixed_count} overlap issues")
        return fixed_count

    # Block classification helpers
    def classify_block_shape(self, block, tol: float = 0.05) -> str:
        """
        type:
        - 'cube'
        - 'rect_prism' ()
        - 'unknown'
        """
        dims = getattr(block, "dimensions", None)
        if dims is None:
            return "unknown"
        try:
            if (
                abs(dims.x - dims.y) < tol
                and abs(dims.x - dims.z) < tol
                and abs(dims.y - dims.z) < tol
            ):
                return "cube"
            return "rect_prism"
        except Exception:
            return "unknown"

    def count_block_types(self, blocks, tol: float = 0.05) -> dict:
        """
        type:
        - total:
        - cube:
        - rect_prism:
        - unknown:
        """
        counts = {"total": 0, "cube": 0, "rect_prism": 0, "unknown": 0}
        for block in blocks:
            counts["total"] += 1
            shape = self.classify_block_shape(block, tol)
            if shape in counts:
                counts[shape] += 1
            else:
                counts["unknown"] += 1
        return counts

    # Dataset helpers
    def generate_distractor(self, original_shape, growth_history=None, distractor_seed=None, difficulty=None):
        if difficulty is None:
            difficulty = self.config.get('distractor_difficulty', 0.5)

        if distractor_seed is not None:
            random.seed(distractor_seed)

        self.clear_question_objects()
        use_variant = random.random() < 0.5

        if use_variant and growth_history:
            num_blocks = len(growth_history)
            blocks_to_remove = int(num_blocks * (0.2 + difficulty * 0.3))
            blocks_to_remove = max(1, min(blocks_to_remove, num_blocks - 1))
            distractor_obj = self.create_combination_shape(
                use_rectangular=self.config.get('use_rectangular_prisms'),
                rect_prob=self.config.get('rectangular_prism_prob'),
                seed=distractor_seed,
                remove_blocks=blocks_to_remove,
                growth_history=growth_history
            )
        else:
            distractor_obj = self.create_combination_shape(
                use_rectangular=self.config.get('use_rectangular_prisms'),
                rect_prob=self.config.get('rectangular_prism_prob'),
                seed=distractor_seed
            )

        # Ensure the generated distractor shape is a single contiguous component,
        # avoiding visually isolated floating blocks.
        try:
            self._ensure_single_component(distractor_obj)
        except Exception as e:  # Safety guard: never fail generation due to post-check
            info(f"ensure_single_component failed: {e}")

        return distractor_obj

    def _ensure_single_component(self, master_obj):
        """
        Remove small disconnected components so that the shape looks contiguous.

        We treat blocks as connected when their bounding boxes are close enough
        according to `collision_threshold`, and keep only the largest component.
        """
        if master_obj is None:
            return

        blocks = [child for child in master_obj.children]
        if len(blocks) <= 1:
            return

        import mathutils

 # (for"");,
 # (face).
        connection_threshold = self.config.get("collision_threshold", 0.05)
        n = len(blocks)
        adjacency = [set() for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                try:
                    # blocks
                    mat1 = blocks[i].matrix_world
                    mat2 = blocks[j].matrix_world
                    bbox1 = [mat1 @ mathutils.Vector(v) for v in blocks[i].bound_box]
                    bbox2 = [mat2 @ mathutils.Vector(v) for v in blocks[j].bound_box]
                    min1 = mathutils.Vector(
                        (min(v.x for v in bbox1), min(v.y for v in bbox1), min(v.z for v in bbox1))
                    )
                    max1 = mathutils.Vector(
                        (max(v.x for v in bbox1), max(v.y for v in bbox1), max(v.z for v in bbox1))
                    )
                    min2 = mathutils.Vector(
                        (min(v.x for v in bbox2), min(v.y for v in bbox2), min(v.z for v in bbox2))
                    )
                    max2 = mathutils.Vector(
                        (max(v.x for v in bbox2), max(v.y for v in bbox2), max(v.z for v in bbox2))
                    )

 # 1) "": in()
                    overlap_x = not (max1.x <= min2.x or min1.x >= max2.x)
                    overlap_y = not (max1.y <= min2.y or min1.y >= max2.y)
                    overlap_z = not (max1.z <= min2.z or min1.z >= max2.z)
                    is_colliding = overlap_x and overlap_y and overlap_z
                    if is_colliding:
 # , or
                        continue

 # 2): face/or
                    min1_conn = min1 - mathutils.Vector(
                        (connection_threshold, connection_threshold, connection_threshold)
                    )
                    max1_conn = max1 + mathutils.Vector(
                        (connection_threshold, connection_threshold, connection_threshold)
                    )
 # < / >( <= / >=), ensure
                    separated = (
                        max1_conn.x < min2.x
                        or min1_conn.x > max2.x
                        or max1_conn.y < min2.y
                        or min1_conn.y > max2.y
                        or max1_conn.z < min2.z
                        or min1_conn.z > max2.z
                    )
                    if not separated:
                        adjacency[i].add(j)
                        adjacency[j].add(i)
                except Exception:
                    continue

        visited = set()
        components = []
        for i in range(n):
            if i in visited:
                continue
            stack = [i]
            comp = []
            visited.add(i)
            while stack:
                u = stack.pop()
                comp.append(u)
                for v in adjacency[u]:
                    if v not in visited:
                        visited.add(v)
                        stack.append(v)
            components.append(comp)

        if len(components) <= 1:
            return

        largest = max(components, key=len)
        keep_indices = set(largest)

        for idx, obj in enumerate(blocks):
            if idx not in keep_indices:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    continue

    def create_summary_file(self, meta_files):
        questions = []
        for meta_file in meta_files:
            if os.path.exists(meta_file):
                with open(meta_file, 'r') as f:
                    data = json.load(f)
                    questions.append(data)

        summary = {
            "dataset": self.__class__.__name__,
            "total_questions": len(questions),
            "generation_time": datetime.now().isoformat(),
            "config": self.config,
            "questions": questions
        }

        summary_path = os.path.join(self.output_dir, "dataset_summary.json")
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)

        return summary_path

    def generate_dataset(self):
        start_time = time.time()
        info(f"Starting dataset generation: {self.config['num_questions']} questions")

        try:
            self.clear_scene()
            camera = self.setup_scene()
            if camera is None:
                raise RuntimeError("Failed to initialize camera; rendering aborted")

            generated_files = []
            for i in range(self.config['num_questions']):
                q_id = f"question_{i:04d}"
                try:
                    meta_file = self.generate_question(q_id)
                    if meta_file:
                        generated_files.append(meta_file)
                except Exception as exc:  # pragma: no cover - Blender runtime diagnostics
                    print(f"Error generating question {q_id} error while processing: {exc}")
                    import traceback
                    traceback.print_exc()
                    continue

                if (i + 1) % 5 == 0 or i == self.config['num_questions'] - 1:
                    elapsed = time.time() - start_time
                    avg_time = elapsed / (i + 1)
                    remaining = avg_time * (self.config['num_questions'] - i - 1)
                    print(f"Progress: {i+1}/{self.config['num_questions']} questions "
                          f"({elapsed:.1f}s elapsed, ~{remaining:.1f}s remaining)")

            if generated_files:
                summary_file = self.create_summary_file(generated_files)
                total_time = time.time() - start_time
                info(f"Dataset generation complete in {total_time:.1f} seconds")
                info(f"Generated {len(generated_files)} questions")
                info(f"Summary file created: {summary_file}")
                return generated_files, summary_file

            print("Warning: No questions were generated successfully")
            return [], None

        except Exception as exc:  # pragma: no cover - Blender runtime diagnostics
            print(f"Error occurred during dataset generation: {exc}")
            import traceback
            traceback.print_exc()
            return [], None


# Backward-compatible alias
SpatialReasoningGeneratorBase = BaseGenerator
