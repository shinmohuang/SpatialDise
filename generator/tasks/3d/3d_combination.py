#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3D combination generator."""

import os
import json
import random
import sys
import math
from datetime import datetime

import bpy
import bmesh
import mathutils

from generator.core.base_generator import BaseGenerator


class CombinationGenerator(BaseGenerator):
    """3D shape assembly question generator"""

    def __init__(self, output_dir=None, config=None):
        """
        Initialize the generator with configuration parameters.

        Args:
            output_dir (str): Directory to save generated files. If None, a default is used.
            config (dict): Configuration dictionary. If None, default values are used.
        """
        if output_dir is None:
            output_dir = "blender_dataset/3D_combination"

        super().__init__("3D_combination", output_dir, config)

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
    # Segmented shape helpers
    # ------------------------------------------------------------------

    def _snapshot_block_states(self, master_obj):
        """Capture blocks and their original local/world positions for later restore."""
        blocks = list(master_obj.children)
        original_positions = []
        world_positions = []
        for block in blocks:
            original_positions.append((block.location.copy(), block.parent))
            world_positions.append(block.matrix_world.translation.copy())
        return blocks, original_positions, world_positions

    def _compute_segment_spacing(self, blocks, base_spacing=2.0):
        """Compute dynamic spacing between segmented components based on average block size."""
        total_blocks = len(blocks)
        if total_blocks == 0:
            return base_spacing

        avg_size_x = avg_size_y = avg_size_z = 0.0
        for block in blocks:
            if hasattr(block, "dimensions"):
                avg_size_x += block.dimensions.x
                avg_size_y += block.dimensions.y
                avg_size_z += block.dimensions.z

        avg_size_x /= total_blocks
        avg_size_y /= total_blocks
        avg_size_z /= total_blocks

 # :
 # - original, for
 # - keep
        spacing = max(1.5, avg_size_x * 1.4)
        return spacing

    def _instantiate_segment_wrappers(self, blocks, original_positions, world_positions):
        """Create segmented master and wrapper objects for each block, without layout."""
        segmented_master = bpy.data.objects.new("SegmentedMaster", None)
        bpy.context.scene.collection.objects.link(segmented_master)

        components = []
        for i, block in enumerate(blocks):
            # Detach from the original parent.
            block.parent = None

 # createobject()
            wrapper = bpy.data.objects.new(f"Component_{i}", None)
            bpy.context.scene.collection.objects.link(wrapper)

            components.append({
                "wrapper": wrapper,
                "block": block,
                "original_index": i,
                "original_position": original_positions[i],
                "original_world_pos": world_positions[i]
            })

 # setblock, and
            block.parent = wrapper
            block.matrix_world.translation = world_positions[i]

 # object
            wrapper.parent = segmented_master

            bpy.context.view_layer.update()

        return components, segmented_master

    def _layout_segment_components(self, components, spacing):
        """
        component,,.

        :
        - (y=0), .
        - x-z , ,
          fromin.
        """
        count = len(components)
        if count == 0:
            return

 # component, forset
        max_dim = 0.0
        for comp in components:
            block = comp["block"]
            dims = getattr(block, "dimensions", None)
            if dims is not None:
                max_dim = max(
                    max_dim,
                    float(dims.x),
                    float(dims.y),
                    float(dims.z),
                )

        # Fallback when dimensions could not be estimated.
        if max_dim <= 0.0:
            max_dim = 1.0

        # : x/z ,
 # .
        # x/z max_dim,
        # cell_size >= 1.3 * max_dim > max_dim,
 # component.
        cell_size = max(spacing, max_dim * 1.3)

 # ,
        cols = max(1, int(math.ceil(math.sqrt(count))))
        rows = int(math.ceil(count / cols))

 # in, andcamera
        offset_x = -(cols - 1) * cell_size * 0.5
        offset_z = (rows - 1) * cell_size * 0.5

        for idx, comp in enumerate(components):
            row = idx // cols
            col = idx % cols
            x = offset_x + col * cell_size
            z = offset_z - row * cell_size

 # in
            comp["wrapper"].location = (x, 0.0, z)
            bpy.context.view_layer.update()

 # andcomponent;, to
            # calculate_optimal_position .
            has_collision = False
            for j in range(idx):
                other_block = components[j]["block"]
                if self.check_collision(comp["block"], other_block):
                    has_collision = True
                    break

            if has_collision:
                optimal_pos = self.calculate_optimal_position(
                    components, idx, spacing
                )
                comp["wrapper"].location = optimal_pos
                bpy.context.view_layer.update()

    def create_segmented_shape(self, master_obj, spacing=2.0):
        """
        shapecomponent, and

        Args:
            master_obj:
            spacing:

        Returns:
            allcomponentlist
        """
        blocks, original_positions, world_positions = self._snapshot_block_states(
            master_obj)

        # Adjust spacing based on average component size.
        spacing = self._compute_segment_spacing(blocks, spacing)

 # create
        components, segmented_master = self._instantiate_segment_wrappers(
            blocks, original_positions, world_positions)

 # , avoid
        self._layout_segment_components(components, spacing)

        bpy.context.view_layer.update()

        return components, segmented_master, original_positions

    def restore_original_shape(self, components, original_positions):
        """
        componentrestoreoriginalshape

        Args:
            components:
            original_positions:
        """
        for comp, orig_pos in zip(components, original_positions):
            block = comp["block"]
            orig_location, orig_parent = orig_pos

 # restoreoriginal
            block.parent = orig_parent

 # restoreoriginal
            if orig_parent:
 # ifobject, set
                block.location = orig_location
            else:
 # ifobject, set
                block.matrix_world.translation = orig_location

 # sceneensure
        bpy.context.view_layer.update()

    # ------------------------------------------------------------------
    # Target shape & view helpers
    # ------------------------------------------------------------------

    def _build_target_shape(self, question_seed):
        """
        Create the base combination shape and collect its blocks.

        This mirrors the legacy behavior: use `create_combination_shape`
        with the same config fields and simple logging.
        """
        original_obj = self.create_combination_shape(
            use_rectangular=self.config.get("use_rectangular_prisms"),
            rect_prob=self.config.get("rectangular_prism_prob"),
            seed=question_seed,
        )

        cubes = [obj for obj in original_obj.children]
        if not cubes:
            print("Warning: No blocks were generated!")
        else:
            print(f"Generated {len(cubes)} blocks")
        return original_obj, cubes

    def _render_question_and_opposite_views(self, q_id, cam, cubes):
        """
        Render the main question view and its opposite view.

        Returns camera states and image paths so that `generate_question`
        can assemble metadata without duplicating rendering logic.
        """
 # camera, ensureto
        try:
            if hasattr(cam.data, "ortho_scale"):
                original_ortho_scale = cam.data.ortho_scale
 # 1.5, ensure
                cam.data.ortho_scale = 18 # andkeep
            else:
                original_ortho_scale = 18
        except Exception as e:
            print(f"Failed to adjust camera view scale: {e}")
            original_ortho_scale = 12

        # find_best_view
        question_view, visible_count = self.find_best_view(
            self.iso_views,
            cubes,
            cam,
            prefer_isometric=True,
            auto_generate=True,
            num_candidates=8,
        )
        print(f"Selected view: {question_view['name']} visible block count: {visible_count}")

        # question
        self.set_camera_to_view(cam, question_view, add_randomness=True)

 # shapein, andcamerain
        shape_center = self.get_shape_center(cubes)
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot_quat.to_euler()

        # ortho_scale question
        if hasattr(cam.data, "ortho_scale"):
            cam.data.ortho_scale = 8.0
        bpy.context.view_layer.update()

        question_location = cam.location.copy()
        question_rotation = cam.rotation_euler.copy()

 # (shape)
        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)

 # face
        opposite_view = question_view.copy()
        opposite_view["name"] = "opposite_" + question_view["name"]

        pos_x, pos_y, pos_z = question_view["pos"]
        opposite_view["pos"] = (-pos_x, -pos_y, -pos_z)

 # setcameratoface
        self.set_camera_to_view(cam, opposite_view, add_randomness=False)

 # camerashapein
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot_quat.to_euler()
        if hasattr(cam.data, "ortho_scale"):
            cam.data.ortho_scale = 8.0
        bpy.context.view_layer.update()

        opposite_location = cam.location.copy()
        opposite_rotation = cam.rotation_euler.copy()

 # face
        opposite_img = os.path.join(self.output_dir, f"{q_id}_Q_opposite.png")
        self.render_image(opposite_img)

 # afterrestoreto
        if hasattr(cam.data, "ortho_scale"):
            cam.data.ortho_scale = 18

        # question
        cam.location = question_location
        cam.rotation_euler = question_rotation
        bpy.context.view_layer.update()

        return (
            question_view,
            question_location,
            question_rotation,
            question_img,
            opposite_view,
            opposite_location,
            opposite_rotation,
            opposite_img,
            original_ortho_scale,
        )

    def create_distractor(self, original_component, master_obj, seed, highlight_distractor=False):
        """
        componentcreatedistractor

        Args:
            original_component:
            master_obj:
            seed:
            highlight_distractor: ()

        Returns:
            distractorcomponentobject
        """
 # setrandomensure
        random.seed(seed)

 # originalblock
        original_block = original_component["block"]
        wrapper = original_component["wrapper"]

 # originalshape
        orig_shape = None
        orig_dimensions = (1, 1, 1) # defaultcube
 # originalshape
        if hasattr(original_block, "dimensions"):
            dims = original_block.dimensions
            orig_dimensions = (dims.x, dims.y, dims.z)

            # type
            max_dim = max(orig_dimensions)
            min_dim = min(orig_dimensions)

            if max_dim / min_dim > 1.5:
                # Infer original block type from dimensions.
                if dims.x > dims.y and dims.x > dims.z:
                    orig_shape = self.shape_types[1]  # x_prism
                elif dims.y > dims.x and dims.y > dims.z:
                    orig_shape = self.shape_types[2]  # y_prism
                elif dims.z > dims.x and dims.z > dims.y:
                    orig_shape = self.shape_types[3]  # z_prism
            else:
                orig_shape = self.shape_types[0]  # cube

        if orig_shape is None:
            orig_shape = self.shape_types[0] # defaultcube
 # create
        # type
        available_shapes = [s for s in self.shape_types if s != orig_shape]
        if not available_shapes: # ensureavailableshape
            available_shapes = self.shape_types
        distractor_shape = random.choice(available_shapes)

 # create
        mesh = bpy.data.meshes.new(f"{distractor_shape['name']}Mesh")
        distractor = bpy.data.objects.new(distractor_shape['name'], mesh)
        bpy.context.scene.collection.objects.link(distractor)

        # bmesh
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)

 # shape
        dimensions = distractor_shape["dimensions"]
        for v in bm.verts:
            v.co.x *= dimensions[0]
            v.co.y *= dimensions[1]
            v.co.z *= dimensions[2]

        bm.to_mesh(mesh)
        bm.free()

 # set
        distractor.display_type = 'WIRE'

 # creatematerial -
        mat = bpy.data.materials.new(name="DistractorMaterial")
        mat.use_nodes = True

        # Access node-tree handles.
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

 # default
        for node in nodes:
            nodes.remove(node)

 # create()
        emission = nodes.new(type='ShaderNodeEmission')
        emission.inputs['Color'].default_value = (0.7, 0.7, 0.7, 1.0)  # Neutral gray emission color.
        emission.inputs['Strength'].default_value = 1.0  # Keep contrast stable across renders.
        emission.location = (0, 0)

 # create
        output = nodes.new(type='ShaderNodeOutputMaterial')
        output.location = (200, 0)

 # - to,
        links.new(emission.outputs['Emission'], output.inputs['Surface'])

 # material
        if distractor.data.materials:
            distractor.data.materials[0] = mat
        else:
            distractor.data.materials.append(mat)

 # ensurematerialin
        distractor.show_wire = True
        distractor.show_all_edges = True

 # set
        distractor.parent = wrapper

 # originalblock
        original_world_matrix = original_block.matrix_world.copy()

 # setdistractor(keepandoriginalblockrotation)
        distractor.matrix_world = original_world_matrix

 # originalblock(delete, afterrestore)
        original_block.hide_viewport = True
        original_block.hide_render = True

 # sceneensure
        bpy.context.view_layer.update()

        return {
            "wrapper": wrapper,
            "block": distractor,
            "replaced_block": original_block,
            "original_index": original_component["original_index"]
        }

    def restore_from_distractor(self, distractor_component):
        """
        restoredistractororiginalcomponent

        Args:
            distractor_component:
        """
 # originalblock
        original_block = distractor_component["replaced_block"]
        original_block.hide_viewport = False
        original_block.hide_render = False

 # deletedistractor
        distractor = distractor_component["block"]

 # deletedistractormaterial
        if distractor.data and distractor.data.materials:
            for i in range(len(distractor.data.materials)):
                mat = distractor.data.materials[i]
                if mat:
 # material
                    distractor.data.materials[i] = None
 # ifmaterial, delete
                    if mat.users == 0:
                        bpy.data.materials.remove(mat)

 # deletedistractorobject
        if distractor.data:
            mesh = distractor.data
            bpy.data.objects.remove(distractor, do_unlink=True)
 # delete
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        else:
            bpy.data.objects.remove(distractor, do_unlink=True)

 # sceneensure
        bpy.context.view_layer.update()

    def _render_combination_options(
        self,
        q_id,
        cam,
        original_obj,
        components,
        segmented_master,
        question_seed,
        original_ortho_scale,
        initial_cam_location,
        initial_cam_rot,
    ):
        """
        Render correct and distractor option images for the segmented shape view.

        This follows the legacy behavior: a single options view with all
        components visible, then per-component distractors created via
        `create_distractor`.
        """

        def _visible_blocks_from_components():
            """Return the currently()."""
            blocks = []
            for comp in components:
                wrapper = comp["wrapper"]
                visible = None
 # selectforobject
                for child in wrapper.children:
                    if not getattr(child, "hide_render", False):
                        visible = child
                        break
                if visible is None:
                    visible = comp["block"]
                blocks.append(visible)
            return blocks
        # as distractor()
        base_index = random.randint(0, len(components) - 1)

        options = []
        bpy.context.view_layer.update()

        components_count = len(components)
        # , type
        component_blocks = _visible_blocks_from_components()
        component_block_counts = self.count_block_types(component_blocks)

        # iso_front_top_left
        front_top_left_view = None
        for view in self.iso_views:
            if view["name"] == "iso_front_top_left":
                front_top_left_view = view.copy()
                break

        if front_top_left_view is None:
            print("Warning: iso_front_top_left ,")
            front_top_left_view = self.iso_views[0].copy()

        option_view = front_top_left_view
        option_view["name"] = "options_" + option_view["name"]

        # , look_at (0,0,0)
        option_view["look_at"] = (0, 0, 0)

        # , (view),
 # frombefore, shapeand.
        base_pos = mathutils.Vector(option_view["pos"])
 # ,,, in
        base_pos.x *= 0.8
        base_pos.z *= 0.7
        option_view["pos"] = (base_pos.x, base_pos.y, base_pos.z)

 # componentcountcamera()
        distance_scale = max(1.1, components_count / 8.0)
        orig_pos = mathutils.Vector(option_view["pos"])
        direction = orig_pos.normalized()
        new_distance = orig_pos.length * distance_scale
        new_pos = direction * new_distance
        option_view["pos"] = (new_pos.x, new_pos.y, new_pos.z)

 # setcamerato
        self.set_camera_to_view(cam, option_view, add_randomness=False)
        bpy.context.view_layer.update()

 # 1. correct answer(alloriginalcomponent)
        correct_img = os.path.join(self.output_dir, f"{q_id}_A0.png")
        self.render_image(correct_img)

        correct_option = {
            "image": correct_img,
            "label": "correct",
            "distractor_index": None,
            "camera_location": tuple(cam.location),
            "camera_rotation": tuple(cam.rotation_euler),
            "seed": question_seed,
            "block_count": components_count,
            "block_counts": component_block_counts,
        }
        options.append(correct_option)

 # 2. distractor,, avoid:
        # - (cube_count, rect_prism_count)
        num_distractors = self.config.get("num_distractors", 3)

        # (cube, rect_prism) ()
        used_pairs = {
            (
                correct_option["block_counts"].get("cube", 0),
                correct_option["block_counts"].get("rect_prism", 0),
            )
        }

        distractor_options = []

        for i in range(num_distractors):
            max_attempts = 6
            accepted_option = None

            for attempt in range(max_attempts):
                distractor_seed = question_seed + i * 1000 + attempt

 # distractorcomponentcount: difficulty
                # - easy: 2
                # - medium: 2 3 ()
                # - hard: ( 3 )
                difficulty_label = self.config.get("difficulty", "easy")
                components_count = len(components)
                if components_count <= 1:
                    replace_count = 1
                else:
                    min_allowed = 2
                    max_allowed = min(3, components_count)
                    if difficulty_label == "easy":
                        replace_count = min_allowed
                    elif difficulty_label == "medium":
                        if max_allowed == min_allowed:
                            replace_count = min_allowed
                        else:
                            replace_count = random.choice(
                                [min_allowed, max_allowed]
                            )
                    else:  # hard
                        replace_count = max_allowed

 # distractorselectcomponentindex
                available_indices = list(range(len(components)))
                random.shuffle(available_indices)
                replace_indices = available_indices[:replace_count]

                applied_distractors = []
 # incomponent
                for idx_offset, comp_idx in enumerate(replace_indices):
                    comp = components[comp_idx]
                    sub_seed = distractor_seed + idx_offset * 17
                    d = self.create_distractor(
                        comp,
                        original_obj,
                        sub_seed,
                        highlight_distractor=False,
                    )
                    applied_distractors.append(d)

                bpy.context.view_layer.update()

                # type()
                current_blocks = _visible_blocks_from_components()
                current_block_counts = self.count_block_types(current_blocks)
                pair = (
                    current_block_counts.get("cube", 0),
                    current_block_counts.get("rect_prism", 0),
                )

                # (cube, rect) , ,
                if pair in used_pairs and attempt < max_attempts - 1:
                    for d in applied_distractors:
                        self.restore_from_distractor(d)
                    continue

 # (after, )
                distractor_img = os.path.join(
                    self.output_dir, f"{q_id}_A{i+1}.png"
                )
                self.render_image(distractor_img)

                accepted_option = {
                    "image": distractor_img,
                    "label": f"distractor_{i+1}",
                    "distractor_index": replace_indices[0]
                    if replace_indices
                    else None,
                    "distractor_indices": replace_indices,
                    "distractor_seed": distractor_seed,
                    "camera_location": tuple(cam.location),
                    "camera_rotation": tuple(cam.rotation_euler),
                    "block_count": components_count,
                    "block_counts": current_block_counts,
                }

                used_pairs.add(pair)

 # restoreoriginalcomponent, distractor
                for d in applied_distractors:
                    self.restore_from_distractor(d)

                break

            if accepted_option is not None:
                distractor_options.append(accepted_option)

        options.extend(distractor_options)

 # restoreoriginalshape: object
        for component in components:
            block = component["block"]
            wrapper = component["wrapper"]
            block.parent = None
            bpy.data.objects.remove(wrapper, do_unlink=True)

        bpy.data.objects.remove(segmented_master, do_unlink=True)

 # restorecamera
        try:
            if hasattr(cam.data, "ortho_scale"):
                cam.data.ortho_scale = original_ortho_scale
        except Exception as e:
            print(f"Failed to restore camera view scale: {e}")

 # camerato
        cam.location = initial_cam_location
        cam.rotation_euler = initial_cam_rot
        bpy.context.view_layer.update()

        return option_view, options

    def generate_question(self, q_id):
        """3D"""
        print(f"Generating question {q_id}...")

 # Clear existing objects
        self.clear_question_objects()

        # ID,
 # difficultytoshape
        difficulty_label = self.config.get("difficulty", "easy")
        question_seed = hash((q_id, difficulty_label)) % 100000

 # 1. shape
        original_obj, cubes = self._build_target_shape(question_seed)
        if not cubes:
            return None
        original_block_count = len(cubes)
        original_block_counts = self.count_block_types(cubes)

 # camera
        cam = bpy.context.scene.camera
        initial_cam_location = cam.location.copy()
        initial_cam_rot = cam.rotation_euler.copy()

        # 2. view( + )
        (
            question_view,
            question_location,
            question_rotation,
            question_img,
            opposite_view,
            opposite_location,
            opposite_rotation,
            opposite_img,
            original_ortho_scale,
        ) = self._render_question_and_opposite_views(q_id, cam, cubes)

        # 3. view
        components, segmented_master, original_positions = self.create_segmented_shape(
            original_obj)
        if not components:
            print("Warning: No components were created!")
            return None
        print(f"Created {len(components)} separated components")

 # 4 & 5. generatedistractorand
        option_view, options = self._render_combination_options(
            q_id,
            cam,
            original_obj,
            components,
            segmented_master,
            question_seed,
            original_ortho_scale,
            initial_cam_location,
            initial_cam_rot,
        )

 # create
        meta = {
            "question_id": q_id,
            "question_image": question_img,
            "opposite_view_image": opposite_img, # face
            "seed": question_seed,
            "timestamp": datetime.now().isoformat(),
            "original_block_count": original_block_count,
            "original_block_counts": original_block_counts,
            "question_view": {
                "name": question_view["name"],
                "camera_location": tuple(question_location),
                "camera_rotation": tuple(question_rotation)
            },
            "opposite_view": { # face
            "name": opposite_view["name"],
                "camera_location": tuple(opposite_location),
                "camera_rotation": tuple(opposite_rotation)
            },
            "options_view": {
                "name": option_view["name"],
                "camera_location": tuple(option_view["pos"]),
                "look_at": tuple(option_view["look_at"]),
                "camera_rotation": tuple(cam.rotation_euler)
            },
            "options": options
        }

        # Write metadata file.
        meta_path = os.path.join(self.output_dir, f"{q_id}.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        return meta_path

    def calculate_optimal_position(self, components, new_component_index, spacing=2.0):
        """
        component, avoidandcomponent

        Args:
            components:
            new_component_index:
            spacing:

        Returns:
            (x, y, z):
        """
        if new_component_index == 0:
            return (0, 0, 0)

        new_wrapper = components[new_component_index]["wrapper"]
        new_block = components[new_component_index]["block"]

        existing_positions = []
        for i in range(new_component_index):
            comp = components[i]
            wrapper = comp["wrapper"]
            existing_positions.append(wrapper.location)

        if not existing_positions:
            return (0, 0, 0)

        avg_size = 0
        count = 0
        for i in range(min(new_component_index, len(components))):
            comp = components[i]
            block = comp["block"]
            if hasattr(block, "dimensions"):
                avg_size += max(block.dimensions.x, block.dimensions.y)
                count += 1

        if count > 0:
            avg_size /= count
        else:
            avg_size = 2.0

 # component,
        grid_spacing = max(spacing, avg_size * 2.0)
        max_search_distance = len(components) * grid_spacing * 0.5
        row = 0
        col = 0
        spiral_direction = 0 # 0:, 1:, 2:, 3:
        spiral_steps = 1
        steps_taken = 0
        direction_changes = 0

        while True:
            x = col * grid_spacing
            y = 0
            z = -row * grid_spacing
            test_pos = (x, y, z)
            new_wrapper.location = test_pos
            bpy.context.view_layer.update()

            collision = False
            for i in range(new_component_index):
                comp = components[i]
                if self.check_collision(new_block, comp["block"], threshold=spacing * 0.3):
                    collision = True
                    break

            if not collision:
                return test_pos

            steps_taken += 1
            if steps_taken == spiral_steps:
                steps_taken = 0
                spiral_direction = (spiral_direction + 1) % 4
                direction_changes += 1
                if direction_changes == 2:
                    direction_changes = 0
                    spiral_steps += 1

            if spiral_direction == 0:
                col += 1
            elif spiral_direction == 1:
                row += 1
            elif spiral_direction == 2:
                col -= 1
            elif spiral_direction == 3:
                row -= 1

            if abs(x) > max_search_distance or abs(z) > max_search_distance:
                print(f"Warning: {new_component_index} ,")
                return (x, y, z)


# Alias for registry
Combination3DGenerator = CombinationGenerator
