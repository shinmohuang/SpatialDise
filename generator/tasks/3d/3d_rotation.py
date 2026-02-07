#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3D rotation matching generator."""

import os
import json
import random
from datetime import datetime

import bpy
import mathutils

from generator.core.base_generator import BaseGenerator


class RotationMatchingGenerator(BaseGenerator):
    """3D rotation matching question generator"""

    def __init__(self, output_dir=None, config=None):
        """
        Initialize the generator with configuration parameters.

        Args:
            output_dir (str): Directory to save generated files. If None, a default is used.
            config (dict): Configuration dictionary. If None, default values are used.
        """
        super().__init__("3D_rotation", output_dir, config)
        # top_view
        self._has_top_view = False  # view
 # difficultyblockcount,
        difficulty_label = self.config.get("difficulty", "easy")
        if difficulty_label == "easy":
            self.config["num_cells_min"] = 3
            self.config["num_cells_max"] = 5
        elif difficulty_label == "medium":
            self.config["num_cells_min"] = 5
            self.config["num_cells_max"] = 8
        elif difficulty_label == "hard":
            self.config["num_cells_min"] = 8
            self.config["num_cells_max"] = 12

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _create_original_shape(self, question_seed):
        """Create the base 3D shape and return (original_obj, growth_history, cubes)."""
        original_obj = self.create_combination_shape(
            use_rectangular=self.config.get("use_rectangular_prisms"),
            rect_prob=self.config.get("rectangular_prism_prob"),
            seed=question_seed,
        )

 # Ensure the original shape is a single connected component to avoid floating blocks
        try:
            self._ensure_single_component(original_obj)
        except Exception:
            pass

        growth_history_str = original_obj.get("growth_history", "[]")
        growth_history = eval(growth_history_str)

        cubes = [obj for obj in original_obj.children]
        return original_obj, growth_history, cubes

    def _render_question_view(self, q_id, cam, cubes):
        """
        Find best question view via find_best_view, set camera, and render Q image.

        Returns:
            question_view, question_location, question_rotation, question_img
        """
        question_view, visible_count = self.find_best_view(
            self.iso_views,
            cubes,
            cam,
            prefer_isometric=True,
            iso_bonus=2.0,
            auto_generate=True,
            num_candidates=8,
        )
        print(
            f"Selected view: {question_view['name']} with {visible_count} visible blocks"
        )

        self.set_camera_to_view(cam, question_view, add_randomness=True)

        shape_center = self.get_shape_center(cubes)
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot_quat.to_euler()

        original_ortho_scale = cam.data.ortho_scale
        cam.data.ortho_scale = 8.0

        bpy.context.view_layer.update()

        question_location = cam.location.copy()
        question_rotation = cam.rotation_euler.copy()

        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)

        return question_view, question_location, question_rotation, question_img

    def _render_correct_option(self, q_id, cam, cubes, question_seed, used_views):
        """
        Render the correct answer option (same shape, different view).

        Returns:
            correct_option dict, correct_view, correct_location, correct_rotation
        """
        remaining_views = [
            v for v in self.iso_views if v["name"] not in used_views
        ]
        if not remaining_views:
            remaining_views = self.iso_views

        correct_view = random.choice(remaining_views)
        used_views.add(correct_view["name"])

        self.set_camera_to_view(cam, correct_view, add_randomness=True)

        shape_center = self.get_shape_center(cubes)
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot_quat.to_euler()
        bpy.context.view_layer.update()

        correct_location = cam.location.copy()
        correct_rotation = cam.rotation_euler.copy()

        correct_img = os.path.join(self.output_dir, f"{q_id}_A0.png")
        self.render_image(correct_img)

        block_counts = self.count_block_types(cubes)

        option = {
            "image": correct_img,
            "label": "correct",
            "view_name": correct_view["name"],
            "camera_location": tuple(correct_location),
            "camera_rotation": tuple(correct_rotation),
            "seed": question_seed,
            "block_count": len(cubes),
            "block_counts": block_counts,
        }
        return option, correct_view, correct_location, correct_rotation

    def _render_distractor_options(
        self,
        q_id,
        cam,
        original_obj,
        growth_history,
        question_seed,
        correct_view,
    ):
        """Generate and render distractor options, returning a list of option dicts.

        :
        - block ().
        -, distractoravoidshape.
        """
        options = []

        # Original shape signature: + , /
        original_blocks = [child for child in original_obj.children]
        original_signature = self._block_signature(original_blocks)
        used_signatures = {original_signature}

        # Map high-level difficulty label to numeric distractor_difficulty
        difficulty_label = self.config.get("difficulty", "easy")
        difficulty_map = {
            "easy": 0.2,
            "medium": 0.5,
            "hard": 0.8,
        }
        distractor_diff = difficulty_map.get(
            difficulty_label, self.config.get("distractor_difficulty", 0.5)
        )

        for i in range(self.config["num_distractors"]):
            best_candidate = None
            max_attempts = 10
            attempt = 0

            while attempt < max_attempts:
                attempt += 1
                self.clear_question_objects()

                distractor_seed = question_seed + i + 1000 + attempt

                distractor_obj = self.generate_distractor(
                    original_shape=original_obj,
                    growth_history=growth_history,
                    distractor_seed=distractor_seed,
                    difficulty=distractor_diff,
                )

                distractor_cubes = [obj for obj in distractor_obj.children]
                signature = self._block_signature(distractor_cubes)

                # Ensure distractor shapes are unique versus the original and previous distractors.
                if signature in used_signatures:
                    best_candidate = distractor_obj  # Keep a fallback candidate from the last attempt.
                    continue

                used_signatures.add(signature)
                best_candidate = distractor_obj
                break

            if best_candidate is None:
                # Fallback: skip this distractor if no valid candidate was found.
                continue

            distractor_obj = best_candidate

            distractor_view = random.choice(self.iso_views)
            self.set_camera_to_view(cam, distractor_view, add_randomness=True)

            distractor_cubes = [obj for obj in distractor_obj.children]
            if distractor_cubes:
                distractor_center = self.get_shape_center(distractor_cubes)
                direction = mathutils.Vector(distractor_center) - cam.location
                rot_quat = direction.to_track_quat("-Z", "Y")
                cam.rotation_euler = rot_quat.to_euler()
                bpy.context.view_layer.update()

            distractor_location = cam.location.copy()
            distractor_rotation = cam.rotation_euler.copy()

            block_count = len(distractor_cubes)
            block_counts = self.count_block_types(distractor_cubes)

            distractor_img = os.path.join(
                self.output_dir, f"{q_id}_A{i+1}.png"
            )
            self.render_image(distractor_img)

            options.append(
                {
                    "image": distractor_img,
                    "label": f"distractor_{i+1}",
                    "view_name": distractor_view["name"],
                    "distractor_type": "different_view"
                    if distractor_view["name"] != correct_view["name"]
                    else "correct_view",
                    "camera_location": tuple(distractor_location),
                    "camera_rotation": tuple(distractor_rotation),
                    "seed": distractor_seed,
                    "block_count": block_count,
                    "block_counts": block_counts,
                }
            )

            self.clear_question_objects()

        return options

    def _block_signature(self, blocks, precision: int = 3):
        """
        Build a hashable signature of a shape based on block positions + dimensions.

        :
        - block , rotation .
        """
        sig = []
        for b in blocks:
            try:
                loc = b.location
                if hasattr(b, "dimensions"):
                    dims = b.dimensions
                    sig.append(
                        (
                            round(loc.x, precision),
                            round(loc.y, precision),
                            round(loc.z, precision),
                            round(dims.x, 2),
                            round(dims.y, 2),
                            round(dims.z, 2),
                        )
                    )
                else:
                    sig.append(
                        (
                            round(loc.x, precision),
                            round(loc.y, precision),
                            round(loc.z, precision),
                        )
                    )
            except Exception:
                continue
        return frozenset(sig)

    def generate_question(self, q_id):
        """Generate a single 3D rotation matching question"""
        print(f"Generating question {q_id}...")

        # Clear any existing objects
        self.clear_question_objects()

        # Create seed based on question ID and difficulty for reproducibility
        difficulty_label = self.config.get("difficulty", "easy")
        question_seed = hash((q_id, difficulty_label)) % 100000

        # Create the 3D shape and gather helpers
        original_obj, growth_history, cubes = self._create_original_shape(
            question_seed
        )
        original_block_count = len(cubes)
        original_block_counts = self.count_block_types(cubes)

        # Save camera's initial position
        cam = bpy.context.scene.camera
        initial_cam_location = cam.location.copy()
        initial_cam_rot = cam.rotation_euler.copy()

        # Question view (Q image)
        (
            question_view,
            question_location,
            question_rotation,
            question_img,
        ) = self._render_question_view(q_id, cam, cubes)

        # Prepare options list
        options = []
        used_views = set()  # Track used views to avoid duplicates
        used_views.add(question_view["name"])  # question
        # Correct answer option
        correct_option, correct_view, correct_location, correct_rotation = (
            self._render_correct_option(
                q_id, cam, cubes, question_seed, used_views
            )
        )
        options.append(correct_option)

        # Distractor options
        distractor_options = self._render_distractor_options(
            q_id,
            cam,
            original_obj,
            growth_history,
            question_seed,
            correct_view,
        )
        options.extend(distractor_options)

        # Reset camera
        cam.location = initial_cam_location
        cam.rotation_euler = initial_cam_rot

        # Create metadata
        meta = {
            "question_id": q_id,
            "question_image": question_img,
            "seed": question_seed,
            "timestamp": datetime.now().isoformat(),
            "original_block_count": original_block_count,
            "original_block_counts": original_block_counts,
            "question_view": {
                "name": question_view["name"],
                "camera_location": tuple(question_location),
                "camera_rotation": tuple(question_rotation)
            },
            "options": options
        }

        # Write metadata file
        meta_path = os.path.join(self.output_dir, f"{q_id}.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        return meta_path

# Alias for registry
Rotation3DGenerator = RotationMatchingGenerator
