#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3D projection generator."""

import os
import json
import random
import math
from datetime import datetime

import bpy
import mathutils

from generator.core.base_generator import BaseGenerator
from generator.core import projection as projection_utils


class ViewMatchingGenerator(BaseGenerator):
    """3D View Matching Generator"""

    def __init__(self, output_dir=None, config=None):
        """Initialize the generator with configuration parameters"""
        if output_dir is None:
            output_dir = "blender_dataset/3D_projection"

        super().__init__("3D_projection", output_dir, config)

        # Adjust block count range and distractor difficulty by difficulty label,
        # to separate complexity across easy / medium / hard.
        difficulty_label = self.config.get("difficulty", "easy")
        if difficulty_label == "easy":
            self.config["num_cells_min"] = 3
            self.config["num_cells_max"] = 5
            self.config["distractor_difficulty"] = 0.2
        elif difficulty_label == "medium":
            self.config["num_cells_min"] = 5
            self.config["num_cells_max"] = 8
            self.config["distractor_difficulty"] = 0.5
        elif difficulty_label == "hard":
            self.config["num_cells_min"] = 8
            self.config["num_cells_max"] = 12
            self.config["distractor_difficulty"] = 0.8

        # view
        self.orthographic_views = [
            {"name": "top_view", "pos": (0, 0, 10.0), "look_at": (0, 0, 0)},
            {"name": "front_view", "pos": (0, -10.0, 0), "look_at": (0, 0, 0)},
            {"name": "right_view", "pos": (10.0, 0, 0), "look_at": (0, 0, 0)},
            {"name": "back_view", "pos": (0, 10.0, 0), "look_at": (0, 0, 0)},
            {"name": "left_view", "pos": (-10.0, 0, 0), "look_at": (0, 0, 0)},
            # view bottom_view
        ]

        # view
        self.opposite_views = {
            "front_view": "back_view",
            "back_view": "front_view",
            "left_view": "right_view",
            "right_view": "left_view",
            "top_view": None,  # top_viewview
            }

    def get_opposite_view(self, view_name):
        """
        viewview

        Args:
            view_name: view

        Returns:
            view, None
        """
        return self.opposite_views.get(view_name)

    def get_projected_positions(self, blocks, view_name):
        """
        view

        Args:
            blocks:
            view_name: view

        Returns:
            Set of projected 2D positions.
        """
        return projection_utils.project_block_positions(blocks, view_name)

    def is_view_different(self, original_positions, distractor_blocks, view_name, min_difference=0.3):
        """
        view

        Args:
            original_positions: view
            distractor_blocks:
            view_name: view
            min_difference: , 0.3

        Returns:
            Boolean: True, False
        """
        distractor_positions = self.get_projected_positions(
            distractor_blocks, view_name)

        diff_coords = original_positions.symmetric_difference(
            distractor_positions)
        total_coords = original_positions.union(distractor_positions)

        if not total_coords:
            return False # avoid
        difference_ratio = len(diff_coords) / len(total_coords)
        from generator.core import logging as log
        log.info(f"view {view_name} projection difference ratio: {difference_ratio:.2f}")
        return difference_ratio >= min_difference

    def create_view_indicator(
        self,
        view_name,
        scene_center=(0, 0, 0),
        scale=0.7,
        color=(0, 0.5, 1, 1),
        distance=None,
        position=None,
    ):
        """view()"""
        indicator = bpy.data.objects.new("ViewIndicator", None)
        bpy.context.scene.collection.objects.link(indicator)

        cx, cy, cz = scene_center
 # frominto; if, default
        if distance is None:
            distance = 2.0 # default
        cone_dir = self._view_direction_vector(view_name)
        if position is not None:
            cone_pos = tuple(position)
        elif "top" in view_name:
            cone_pos = (cx, cy, cz + distance)
        elif "front" in view_name:
            cone_pos = (cx, cy - distance, cz)
        elif "back" in view_name:
            cone_pos = (cx, cy + distance, cz)
        elif "right" in view_name:
            cone_pos = (cx + distance, cy, cz)
        elif "left" in view_name:
            cone_pos = (cx - distance, cy, cz)
        else:
            cone_pos = (cx, cy, cz + distance)

        indicator.location = cone_pos

        cone_height = 1 * scale
        cone_radius = 0.2 * scale
        bpy.ops.mesh.primitive_cone_add(
            vertices=32,
            radius1=cone_radius,
            radius2=0,
            depth=cone_height,
            location=cone_pos
        )
        cone = bpy.context.active_object
        cone.name = "ViewDirectionCone"

        arrow_mat = bpy.data.materials.new(name="ArrowMaterial")
        arrow_mat.use_nodes = True
        nodes = arrow_mat.node_tree.nodes
        principled = nodes.get("Principled BSDF")
        if principled:
            base_color = principled.inputs.get("Base Color")
            if base_color:
                base_color.default_value = color

            specular = (
                principled.inputs.get("Specular")
                or principled.inputs.get("Specular IOR Level")
            )
            if specular:
                specular.default_value = 0.2

            metallic = principled.inputs.get("Metallic")
            if metallic:
                metallic.default_value = 0.8

            emission = principled.inputs.get("Emission")
            if emission:
                emission.default_value = (color[0], color[1], color[2], 1.0)

            emission_strength = principled.inputs.get("Emission Strength")
            if emission_strength:
                emission_strength.default_value = 1.0

        cone.data.materials.append(arrow_mat)

        nodes = arrow_mat.node_tree.nodes
        principled = nodes.get("Principled BSDF")
        if principled:
            principled.inputs["Alpha"].default_value = 1.0
            if "Transmission" in principled.inputs:
                principled.inputs["Transmission"].default_value = 0.0

        cone.hide_render = False
        cone.display_type = 'TEXTURED'
        cone.hide_select = True

        from mathutils import Vector, Matrix
        direction = Vector(cone_dir)
        rot_quat = direction.to_track_quat('Z', 'Y')
        rot_mat = rot_quat.to_matrix().to_4x4()
        rot_x = Matrix.Rotation(math.radians(180), 4, 'X')
        final_rot = (rot_mat @ rot_x).to_euler()
        cone.rotation_euler = final_rot
        cone.parent = indicator
        # Keep cone world transform after parenting (avoid double offset).
        cone.matrix_parent_inverse = indicator.matrix_world.inverted()
        return indicator

    def _view_direction_vector(self, view_name):
        """Map orthographic view name to a world-space direction vector."""
        if "top" in view_name:
            return mathutils.Vector((0.0, 0.0, 1.0))
        elif "front" in view_name:
            return mathutils.Vector((0.0, -1.0, 0.0))
        elif "back" in view_name:
            return mathutils.Vector((0.0, 1.0, 0.0))
        elif "right" in view_name:
            return mathutils.Vector((1.0, 0.0, 0.0))
        elif "left" in view_name:
            return mathutils.Vector((-1.0, 0.0, 0.0))
        return mathutils.Vector((0.0, 0.0, 1.0))

    def _compute_indicator_position(self, cam, cubes, shape_center, view_name, indicator_scale=0.7):
        """Place indicator in camera plane with margin from object and viewport edges."""
        scene = bpy.context.scene
        cam_inv = cam.matrix_world.inverted()
        shape_center_world = mathutils.Vector(shape_center)
        shape_center_cam = cam_inv @ shape_center_world

        # Sample shape bounding-box corners in camera-local coordinates.
        cam_points = []
        for cube in cubes:
            for corner in cube.bound_box:
                p_world = cube.matrix_world @ mathutils.Vector(corner)
                cam_points.append(cam_inv @ p_world)

        if not cam_points:
            return shape_center_world

        # "view",
        view_dir_world = self._view_direction_vector(view_name)
        view_dir_cam = cam.matrix_world.to_quaternion().inverted() @ view_dir_world
        dir_2d = mathutils.Vector((view_dir_cam.x, view_dir_cam.y))
        if dir_2d.length < 1e-6:
            dir_2d = mathutils.Vector((1.0, 0.0))
        dir_2d.normalize()

        supports = [p.x * dir_2d.x + p.y * dir_2d.y for p in cam_points]
        center_support = shape_center_cam.x * dir_2d.x + shape_center_cam.y * dir_2d.y
        shape_outer = max(0.4, max(supports) - center_support)

        cone_half = max(0.25, 0.45 * indicator_scale)
        gap = max(0.45, 0.7 * indicator_scale)
        offset = shape_outer + gap + cone_half

        target_xy = mathutils.Vector((
            shape_center_cam.x + dir_2d.x * offset,
            shape_center_cam.y + dir_2d.y * offset,
        ))

        xs = [p.x for p in cam_points]
        ys = [p.y for p in cam_points]

        res_x = max(1, int(scene.render.resolution_x * scene.render.resolution_percentage / 100))
        res_y = max(1, int(scene.render.resolution_y * scene.render.resolution_percentage / 100))
        aspect = res_x / res_y
        safe_margin = max(0.5, 0.08 * cam.data.ortho_scale)

        # Expand orthographic scale when needed to fit shape + indicator + margin.
        req_half_w = max(max(abs(x) for x in xs), abs(target_xy.x)) + safe_margin
        req_half_h = max(max(abs(y) for y in ys), abs(target_xy.y)) + safe_margin
        needed_half_h = max(req_half_h, req_half_w / aspect)
        cam.data.ortho_scale = max(cam.data.ortho_scale, needed_half_h * 2.0)

        # Recompute bounds after scaling and clamp into the safe region.
        safe_margin = max(0.5, 0.08 * cam.data.ortho_scale)
        half_h = cam.data.ortho_scale / 2.0
        half_w = half_h * aspect
        target_xy.x = min(max(target_xy.x, -half_w + safe_margin), half_w - safe_margin)
        target_xy.y = min(max(target_xy.y, -half_h + safe_margin), half_h - safe_margin)

        # Put indicator slightly in front of the shape to avoid occlusion.
        front_z = max(p.z for p in cam_points) + 0.15
        target_cam = mathutils.Vector((target_xy.x, target_xy.y, front_z))
        return cam.matrix_world @ target_cam

    def generate_question(self, q_id):
        """Generate a single 3D view matching question"""
        from generator.core import logging as log
        log.info(f"Generating question {q_id}...")

        # Clear any existing objects
        self.clear_question_objects()

        # Create seed based on question ID and difficulty for reproducibility.
        # view.
        difficulty_label = self.config.get("difficulty", "easy")
        question_seed = hash((q_id, difficulty_label)) % 100000

        # Create the 3D shape
        original_obj = self.create_combination_shape(
            use_rectangular=self.config.get('use_rectangular_prisms'),
            rect_prob=self.config.get('rectangular_prism_prob'),
            seed=question_seed
        )

        # Ensure base shape is a single connected component,
        try:
            self._ensure_single_component(original_obj)
        except Exception:
            pass

        # Get growth history for creating distractors
        growth_history_str = original_obj.get("growth_history", "[]")
        growth_history = eval(growth_history_str)

        # Get all children (cubes) in the shape
        cubes = [obj for obj in original_obj.children]
        if not cubes:
            log.warn("Warning: No blocks were generated!")
            return None

        # view, view
        view_projections = {
            view["name"]: self.get_projected_positions(cubes, view["name"])
            for view in self.orthographic_views
        }
        unique_views = []
        for view in self.orthographic_views:
            name = view["name"]
            proj = view_projections.get(name)
            if not proj:
                continue
            if all(
                proj != other_proj
                for other_name, other_proj in view_projections.items()
                if other_name != name
            ):
                unique_views.append(view)

        # Save camera's initial position
        cam = bpy.context.scene.camera
        initial_cam_location = cam.location.copy()
        initial_cam_rot = cam.rotation_euler.copy()

        # find_best_view,
        question_view, visible_count = self.find_best_view(
            self.iso_views, cubes, cam,
            prefer_isometric=True, iso_bonus=2.0,
            auto_generate=True, num_candidates=8)
        print(
            f"Selected view: {question_view['name']} with {visible_count} visible blocks")

        # questionviewview
        self.set_camera_to_view(cam, question_view, add_randomness=True)

 # , ensureinin
 # shapein
        shape_center = self.get_shape_center(cubes)

        # look_at,
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam.rotation_euler = rot_quat.to_euler()

        # ortho_scalequestion
        cam.data.ortho_scale = 8.0  # Zoom in on the object in the question image.
        # Update the scene so camera settings take effect.
        bpy.context.view_layer.update()

        question_location = cam.location.copy()
        question_rotation = cam.rotation_euler.copy()

        # view, viewview
        candidate_views = unique_views if unique_views else self.orthographic_views
        correct_view = random.choice(candidate_views)

        # view(question)
        shape_center = self.get_shape_center(cubes)
        indicator_pos = self._compute_indicator_position(
            cam=cam,
            cubes=cubes,
            shape_center=shape_center,
            view_name=correct_view["name"],
            indicator_scale=0.7,
        )
        bpy.context.view_layer.update()
        view_indicator = self.create_view_indicator(
            correct_view["name"],
            scene_center=shape_center,
            scale=0.85,
            position=indicator_pos,
        )

        # Render question image (3D view)
        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)

        # view(, )
        if view_indicator:
 # Save a copy of child objects to avoid mutating the list while iterating
            children = list(view_indicator.children)
 # Delete all child objects of the indicator
            for child in children:
                bpy.data.objects.remove(child, do_unlink=True)
 # Delete the indicator object itself
            bpy.data.objects.remove(view_indicator, do_unlink=True)

 # Clean up all unused materials
            for material in bpy.data.materials[:]: # listavoidin
                if material.name.startswith("ArrowMaterial") and material.users == 0:
                    bpy.data.materials.remove(material)

        # Prepare options list
        options = []
        distractor_positions_list = [] # alldistractor(fordifference)
        used_view_names = set()  # view,
        used_view_names.add(correct_view["name"])

        # view
        original_projected_positions = self.get_projected_positions(
            cubes, correct_view["name"])
 # Track projection patterns used in this question to avoid duplicate options
        used_projection_sets = {frozenset(original_projected_positions)}

        # Set camera to correct view for answer
        self.set_camera_to_view(cam, correct_view, add_randomness=False)

        correct_location = cam.location.copy()
        correct_rotation = cam.rotation_euler.copy()

        # Render correct answer image
        correct_img = os.path.join(self.output_dir, f"{q_id}_A0.png")
        self.render_image(correct_img)

        # Add correct answer to options list
        options.append({
            "image": correct_img,
            "label": "correct",
            "view_name": correct_view["name"],
            "camera_location": tuple(correct_location),
            "camera_rotation": tuple(correct_rotation),
            "seed": question_seed
        })

        # view(view)
        remaining_views = [view for view in self.orthographic_views
                           if view["name"] != correct_view["name"]]

        # view
        opposite_view_name = self.get_opposite_view(correct_view["name"])

        # viewview
        if opposite_view_name:
            remaining_views = [view for view in remaining_views
                               if view["name"] != opposite_view_name]
            print(f"Excluded opposite view {opposite_view_name} as distractor")

        # Generate distractors
        for i in range(self.config['num_distractors']):
            # Clear existing objects
            self.clear_question_objects()

            # type - 70%view, 30%
            use_original_with_different_view = random.random() < 0.3

            # view,
            used_distractor_views = set()
            used_distractor_seeds = set()

            # view
            for option in options:
                if option.get("label", "").startswith("distractor_"):
                    used_distractor_views.add(option.get("view_name", ""))
                    used_distractor_seeds.add(option.get("seed", None))

            if use_original_with_different_view and remaining_views:
                # ===== type1: view =====
                # view - view
                available_views = [view for view in remaining_views
                                   if view["name"] not in used_distractor_views]

                # view, 2
                if not available_views:
                    use_original_with_different_view = False
                    print(f"No available views; switching to modified-shape strategy")
                else:
                    # view(viewview)
                    distractor_view = random.choice(available_views)

 # Recreate the original shape
                    distractor_obj = self.create_combination_shape(
                        seed=question_seed)
                    distractor_blocks = [
                        obj for obj in distractor_obj.children]

                    # view
                    self.set_camera_to_view(
                        cam, distractor_view, add_randomness=False)

                    # viewview,

                    # view,
 # andface
                    distractor_positions = self.get_projected_positions(
                        distractor_blocks, distractor_view["name"])
                    proj_key = frozenset(distractor_positions)

 # ifandcorrect answerordifference, or,
 # shape.
                    if (proj_key in used_projection_sets) or not self.is_view_different(
                            original_projected_positions, distractor_blocks, distractor_view["name"]):
 # If the difference is insufficient, switch to the modified-shape strategy
                        use_original_with_different_view = False
                        print(
                            f"view {distractor_view['name']} ,")
                    else:
                        # view
                        used_view_name = distractor_view["name"]
                        used_projection_sets.add(proj_key)

            # view, view,
            if not use_original_with_different_view:
                # ===== type2: =====
 # Ensure distractors are visibly different from the original from the target view
                max_attempts = 15 # Increase attempts to improve success rate
                is_different = False
                attempt = 0

                while not is_different and attempt < max_attempts:
                    attempt += 1

 # Clear existing objects
                    self.clear_question_objects()

 # Create distractors based on difficulty settings
 # Ensure seed values are not repeated
                    while True:
                        distractor_seed = question_seed + i + \
                            1000 + attempt + random.randint(0, 1000)
                        if distractor_seed not in used_distractor_seeds:
                            break
                        attempt += 1  # Increase attempts to avoid seed collisions.
                    # Use the base-class helper to generate distractors.
                    distractor_obj = self.generate_distractor(
                        original_shape=original_obj,
                        growth_history=growth_history,
                        distractor_seed=distractor_seed,
 # Lower difficulty slightly to create clearer differences
                        difficulty=max(
                            0.1, self.config['distractor_difficulty'] - 0.2)
                    )

 # Check whether the distractor differs enough from the original
                    distractor_blocks = [
                        obj for obj in distractor_obj.children]
                    is_different = self.is_view_different(
                        original_projected_positions, distractor_blocks, correct_view["name"],
                        min_difference=0.35) # Increase the difference threshold
 # Additionally require projection patterns to be unique within the question
                    distractor_positions = self.get_projected_positions(
                        distractor_blocks, correct_view["name"])
                    proj_key = frozenset(distractor_positions)

                    is_unique_pattern = proj_key not in used_projection_sets

 # Accept the distractor only if both conditions are satisfied
                    is_acceptable = is_different and is_unique_pattern

                    if is_acceptable or attempt == max_attempts:
 # If accepted, record this distractor projection
                        if is_acceptable:
                            distractor_positions_list.append(
                                distractor_positions)
                            used_distractor_seeds.add(distractor_seed)
                            used_projection_sets.add(proj_key)
                        break

                # view
                self.set_camera_to_view(
                    cam, correct_view, add_randomness=False)

                # view,

                used_view_name = correct_view["name"]

 # Save camera transform information
            distractor_location = cam.location.copy()
            distractor_rotation = cam.rotation_euler.copy()

            # Render distractor image
            distractor_img = os.path.join(
                self.output_dir, f"{q_id}_A{i+1}.png")
            self.render_image(distractor_img)

            # Add distractor to options list
            options.append({
                "image": distractor_img,
                "label": f"distractor_{i+1}",
                "view_name": used_view_name,
                "distractor_type": "different_view" if use_original_with_different_view else "modified_shape",
                "camera_location": tuple(distractor_location),
                "camera_rotation": tuple(distractor_rotation),
                "seed": question_seed if use_original_with_different_view else distractor_seed
            })

 # Print distractor information for debugging
            print(
                f"{i+1}: type={options[-1]['distractor_type']}, view={options[-1]['view_name']}, ={options[-1]['seed']}")

            # Clean up
            self.clear_question_objects()

        # Reset camera
        cam.location = initial_cam_location
        cam.rotation_euler = initial_cam_rot

        # Create metadata
        meta = {
            "question_id": q_id,
            "question_image": question_img,
            "seed": question_seed,
            "timestamp": datetime.now().isoformat(),
            "question_view": {
                "name": question_view["name"],
                "camera_location": tuple(question_location),
                "camera_rotation": tuple(question_rotation)
            },
            "answer_view": {
                "name": correct_view["name"],
                "camera_location": tuple(correct_location),
                "camera_rotation": tuple(correct_rotation)
            },
            "options": options
        }

        # Write metadata file
        meta_path = os.path.join(self.output_dir, f"{q_id}.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        return meta_path


# Alias for registry
Projection3DGenerator = ViewMatchingGenerator
