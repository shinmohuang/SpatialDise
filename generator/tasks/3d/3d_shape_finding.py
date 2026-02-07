#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3D shape finding generator implemented directly (no legacy import wrappers)."""

from __future__ import annotations

import importlib.util
import math
import os
import random
from pathlib import Path

import bpy
import mathutils

from generator.core import icons as icon_utils


def _load_folding_base():
    """Load Folding3DGenerator from sibling 3d_folding.py without importing via invalid module name."""
    module_path = Path(__file__).with_name("3d_folding.py")
    spec = importlib.util.spec_from_file_location(
        "generator.tasks.dynamic_3d_folding_base",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load 3d_folding.py from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return getattr(module, "Folding3DGenerator")


FoldingBase = _load_folding_base()


class ShapeFinding3DGenerator(FoldingBase):
    """3D Shape Finding Generator

    This generator creates a cube with six different textures. It captures three
    views of this cube. Before taking the third view, one randomly chosen
    visible face is replaced with a blue texture. Four option images are then
    produced – each a straight-on orthographic view of a single cube face. One
    of these options corresponds to the face that was turned blue (showing its
    *original* texture) and is therefore the correct answer.
    """

    def __init__(self, output_dir=None, config=None):
        # set default config for this task then merge user config
        default = {
            "num_questions": 10,
            "image_resolution": (640, 480),
            "difficulty": "medium",  # medium
            "ortho_scale": 5.0  # V0-V2, 15.08.0
            }
        if config is None:
            config = {}
        merged = {**default, **config}
        if output_dir is None:
            output_dir = "blender_dataset/3D_shape_finding"
        super().__init__(output_dir=output_dir, config=merged)

 # scene, avoidset
        self._scene_initialized = False

 # face
        self.face_index_to_name = {
            0: "front",
            1: "top",
            2: "back",
            3: "bottom",
            4: "right",
            5: "left"
        }

    def setup_scene_once(self):
        """setscene, in, avoidcreate"""
        if not self._scene_initialized:
            super().setup_scene()
            self._scene_initialized = True
            print("Scene initialized for shape finding generator")
        else:
 # set, create
            scene = bpy.context.scene
            scene.render.resolution_x = self.config["image_resolution"][0]
            scene.render.resolution_y = self.config["image_resolution"][1]
            bpy.context.view_layer.update()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    _FACE_NORMALS = {
        0: mathutils.Vector((0, -1, 0)),  # front  –Y
        1: mathutils.Vector((0, 0, 1)),   # top    +Z
        2: mathutils.Vector((0, 1, 0)),   # back   +Y
        3: mathutils.Vector((0, 0, -1)),  # bottom –Z
        4: mathutils.Vector((1, 0, 0)),   # right  +X
        5: mathutils.Vector((-1, 0, 0)),  # left   –X
    }

    def _create_blue_material(self):
        """Return a simple blue principled material."""
        mat = bpy.data.materials.new(name="BlueFaceMaterial")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs['Base Color'].default_value = (0.0, 0.0, 1.0, 1.0)
        links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        return mat

    def _set_camera_for_face(self, camera, cube, face_idx, distance=4.0):
        """Position *camera* so that it looks orthogonally at *face_idx*.

        Args:
            camera: bpy.types.Object (camera)
            cube  : cube object
            face_idx: index 0..5 mapping of faces
            distance: multiplier for camera offset
        """
        normal_local = self._FACE_NORMALS[face_idx]
        normal_world = cube.matrix_world.to_3x3() @ normal_local
        center_world = cube.matrix_world.translation
        cam_loc = center_world + normal_world.normalized() * distance
        camera.location = cam_loc
        # Aim camera at cube center
        direction = center_world - cam_loc
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()
        # Orthographic settings -
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = 3.0  # 3.0, O0-O3
        bpy.context.view_layer.update()

    # ------------------------------------------------------------------
    # View selection and rendering helpers
    # ------------------------------------------------------------------

    def _choose_views_by_difficulty(self, difficulty: str, seed: int | None = None):
        """, seed ."""
        rng = random.Random(seed)
        if difficulty == "easy":
            views = []
            base_view_idx = rng.randint(0, 3)
            views.append(self.iso_views[base_view_idx])
            second_view_options = [(base_view_idx + i) % 4 for i in [1, 3]]
            views.append(self.iso_views[rng.choice(second_view_options)])
            third_options = [(base_view_idx + 2) % 4]
            if rng.random() < 0.5:
                unused_adjacent = [
                    i for i in second_view_options if self.iso_views[i] not in views
                ][0]
                third_options.append(unused_adjacent)
            views.append(self.iso_views[rng.choice(third_options)])
            return views
        if difficulty == "medium":
            views = rng.sample(self.iso_views, 3)
            if rng.random() < 0.7:
                for i in range(len(self.iso_views)):
                    if (
                        self.iso_views[i] in views
                        and self.iso_views[(i + 1) % 4] in views
                    ):
                        idx1 = views.index(self.iso_views[i])
                        idx2 = views.index(self.iso_views[(i + 1) % 4])
                        if abs(idx1 - idx2) != 1 and idx2 != 0:
                            views[idx2], views[idx1 + 1] = (
                                views[idx1 + 1],
                                views[idx2],
                            )
                        break
            return views
        # hard
        views = rng.sample(self.iso_views, 3)
        rng.shuffle(views)
        return views

    def _render_initial_views(self, q_id, cam, views, difficulty: str):
        """view V0/V1 ."""
        view_images = []
        for i, view in enumerate(views[:2]):
            self.set_camera_to_view(cam, view, add_randomness=False)
            cam.data.ortho_scale = self.config.get("ortho_scale", 5.0)
            if difficulty == "medium":
                yaw = random.uniform(-math.pi / 6, math.pi / 6)
                cam.rotation_euler.rotate_axis("Z", yaw)
            elif difficulty == "hard":
                yaw = random.uniform(0, 2 * math.pi)
                cam.rotation_euler.rotate_axis("Z", yaw)
            bpy.context.view_layer.update()
            img_path = os.path.join(self.output_dir, f"{q_id}_V{i}.png")
            self.render_image(img_path)
            view_images.append(img_path)
        return view_images

    # ------------------------------------------------------------------
    # Blue-face selection, third view, and options
    # ------------------------------------------------------------------

    def _select_replaced_face(self, views, third_view, difficulty: str, seed: int | None):
        """difficultyselectface index."""
        rng = random.Random(seed)
        visible_faces_third = self.get_visible_faces(third_view)

        if difficulty == "easy":
            previously_visible_faces = set()
            for v in views[:2]:
                previously_visible_faces.update(self.get_visible_faces(v))
            common_visible_faces = previously_visible_faces.intersection(
                visible_faces_third
            )
            if 1 in common_visible_faces and len(common_visible_faces) > 1:
                common_visible_faces.remove(1)
            if common_visible_faces:
                face_appearances = {face: 0 for face in common_visible_faces}
                for v in views[:2]:
                    visible = self.get_visible_faces(v)
                    for face in common_visible_faces:
                        if face in visible:
                            face_appearances[face] += 1
                if rng.random() < 0.8:
                    min_appearances = min(face_appearances.values())
                    candidates = [
                        face
                        for face, count in face_appearances.items()
                        if count == min_appearances
                    ]
                    return rng.choice(candidates)
                return rng.choice(list(common_visible_faces))
            non_top_visible_faces = [f for f in visible_faces_third if f != 1]
            if non_top_visible_faces:
                return rng.choice(non_top_visible_faces)
            return 1

        if difficulty == "medium":
            previously_visible = {face: 0 for face in range(6)}
            for v in views[:2]:
                for face in self.get_visible_faces(v):
                    previously_visible[face] += 1
            candidates = {}
            for face in visible_faces_third:
                weight = 1.0
                if face == 1:
                    weight *= 0.5
                prev_count = previously_visible[face]
                if prev_count == 1:
                    weight *= 1.5
                elif prev_count == 0:
                    weight *= 0.8
                candidates[face] = weight
            total_weight = sum(candidates.values())
            rand_val = rng.uniform(0, total_weight)
            cumulative = 0
            for face, weight in candidates.items():
                cumulative += weight
                if rand_val <= cumulative:
                    return face

        else:  # hard
            previously_visible = {face: 0 for face in range(6)}
            for v in views[:2]:
                visible = self.get_visible_faces(v)
                for face in visible:
                    previously_visible[face] += 1
            candidates = {}
            for face in visible_faces_third:
                if previously_visible[face] == 0:
                    candidates[face] = 3.0
                elif previously_visible[face] == 1:
                    candidates[face] = 2.0
                else:
                    candidates[face] = 1.0
            total_weight = sum(candidates.values())
            rand_val = rng.uniform(0, total_weight)
            cumulative = 0
            for face, weight in candidates.items():
                cumulative += weight
                if rand_val <= cumulative:
                    return face

        # fallback
        return random.choice(visible_faces_third)

    def _render_third_view_with_blue_face(
        self, q_id, cam, cube, third_view, replaced_face_idx, difficulty: str
    ):
        """view V2, ."""
        original_material = cube.material_slots[replaced_face_idx].material
        cube.material_slots[replaced_face_idx].material = self._create_blue_material()

        self.set_camera_to_view(cam, third_view, add_randomness=False)
        cam.data.ortho_scale = self.config.get("ortho_scale", 5.0)
        if difficulty == "medium":
            yaw = random.uniform(-math.pi / 6, math.pi / 6)
            cam.rotation_euler.rotate_axis("Z", yaw)
        elif difficulty == "hard":
            yaw = random.uniform(0, 2 * math.pi)
            cam.rotation_euler.rotate_axis("Z", yaw)
        bpy.context.view_layer.update()
        img_path = os.path.join(self.output_dir, f"{q_id}_V2.png")
        self.render_image(img_path)

        cube.material_slots[replaced_face_idx].material = original_material
        return img_path, original_material

    def _build_option_faces(
        self, difficulty: str, views, replaced_face_idx: int, seed: int | None
    ):
        """, (option_faces, correct_index)."""
        rng = random.Random(seed)
        if difficulty == "easy":
            union_visible_faces = set()
            for v in views:
                union_visible_faces.update(self.get_visible_faces(v))
            if replaced_face_idx not in union_visible_faces:
                union_visible_faces.add(replaced_face_idx)
            while len(union_visible_faces) < 4:
                union_visible_faces.add(rng.randint(0, 5))
            if len(union_visible_faces) > 4:
                option_faces = [replaced_face_idx]
                union_visible_faces.remove(replaced_face_idx)
                face_frequency = {face: 0 for face in union_visible_faces}
                for v in views:
                    visible = self.get_visible_faces(v)
                    for face in union_visible_faces:
                        if face in visible:
                            face_frequency[face] += 1
                remaining_faces = sorted(
                    list(union_visible_faces),
                    key=lambda f: face_frequency[f],
                    reverse=True,
                )
                option_faces.extend(remaining_faces[:3])
            else:
                option_faces = list(union_visible_faces)
        elif difficulty == "medium":
            union_visible_faces = set()
            for v in views:
                union_visible_faces.update(self.get_visible_faces(v))
            face_visibility = {face: 0 for face in range(6)}
            for v in views:
                for face in self.get_visible_faces(v):
                    face_visibility[face] += 1
            must_include = [replaced_face_idx]
            candidate_faces = [f for f in range(6) if f not in must_include]
            weights = [0.5 + face_visibility[f] for f in candidate_faces]
            distractor_faces = []
            for _ in range(3):
                if not candidate_faces:
                    break
                total = sum(weights)
                r = rng.uniform(0, total)
                cumulative = 0
                for i, (face, weight) in enumerate(zip(candidate_faces, weights)):
                    cumulative += weight
                    if r <= cumulative:
                        distractor_faces.append(face)
                        candidate_faces.pop(i)
                        weights.pop(i)
                        break
            option_faces = must_include + distractor_faces
        else:
            candidates = [replaced_face_idx]
            all_faces = list(range(6))
            all_faces.remove(replaced_face_idx)
            rng.shuffle(all_faces)
            candidates.extend(all_faces[:3])
            option_faces = candidates

        rng.shuffle(option_faces)
        correct_index = option_faces.index(replaced_face_idx)
        return option_faces, correct_index

    def _render_option_images(
        self,
        q_id,
        cam,
        cube,
        option_faces,
        replaced_face_idx,
        sun,
        original_sun_location,
        original_sun_rotation,
    ):
        """option_faces , ."""
        option_images = []
        for opt_idx, face_idx in enumerate(option_faces):
            self._set_camera_for_face(cam, cube, face_idx)
            if sun:
                sun.location = cam.location
                sun.rotation_euler = cam.rotation_euler
            img_path = os.path.join(self.output_dir, f"{q_id}_O{opt_idx}.png")
            self.render_image(img_path)
            label = "correct" if face_idx == replaced_face_idx else f"distractor_{opt_idx}"
            face_name_map = {
                0: "front",
                1: "top",
                2: "back",
                3: "bottom",
                4: "right",
                5: "left",
            }
            option_images.append(
                {
                    "image": img_path,
                    "face_index": face_idx,
                    "label": label,
                    "view_name": face_name_map.get(face_idx, "unknown"),
                }
            )

        if sun and original_sun_location is not None and original_sun_rotation is not None:
            sun.location = original_sun_location
            sun.rotation_euler = original_sun_rotation

        return option_images

    # ------------------------------------------------------------------
    # Main generation
    # ------------------------------------------------------------------
    def generate_question(self, q_id):
        """Generate one shape-finding question."""
        print(f"Generating shape-finding question {q_id}…")
        # clear scene but keep camera/lights
        self.clear_question_objects()
        self.setup_scene_once()

        # random seed for reproducibility
        seed = hash(f"shape_question_{q_id}") % 10000
        random.seed(seed)
        self.icon_files = icon_utils.resolve_task_icons(
            self.config.get("lucide_icons"),
            download=self.config.get("lucide_download", True),
            prefer_png=True,
            allow_svg_fallback=False,
        )

        # , medium
        difficulty = self.config.get("difficulty", "medium")

        cube, face_assignments = self.create_cube_with_textures(seed=seed)

        # keep original materials list for restoration
        original_materials = [slot.material for slot in cube.material_slots]

        cam = bpy.context.scene.camera

 # set, avoidingeneratein
        sun = bpy.data.objects.get("Sun")
        original_sun_location = None
        original_sun_rotation = None
        if sun:
            original_sun_location = sun.location.copy()
            original_sun_rotation = sun.rotation_euler.copy()

        # Choose views based on difficulty and capture first two views
        views = self._choose_views_by_difficulty(difficulty, seed)
        view_images = self._render_initial_views(q_id, cam, views, difficulty)

        # Prepare blue replacement before third view
        third_view = views[2]
        replaced_face_idx = self._select_replaced_face(
            views, third_view, difficulty, seed
        )

        # Render third question view with blue face and restore material
        third_img_path, original_material_of_replaced = (
            self._render_third_view_with_blue_face(
                q_id, cam, cube, third_view, replaced_face_idx, difficulty
            )
        )
        view_images.append(third_img_path)

        # Generate option faces and render option images
        option_faces, correct_option_index = self._build_option_faces(
            difficulty, views, replaced_face_idx, seed
        )
        option_images = self._render_option_images(
            q_id,
            cam,
            cube,
            option_faces,
            replaced_face_idx,
            sun,
            original_sun_location,
            original_sun_rotation,
        )

        # ------------------------------------------------------------------
        # Save metadata
        # ------------------------------------------------------------------
        metadata = {
            "question_id": q_id,
            "question_type": "3d_shape_finding",
            # use third view as main question image
            "question_image": view_images[-1],
            "views": view_images,
            "options": option_images,
            "correct_answer": correct_option_index,
            "replaced_face": replaced_face_idx,
            "third_view": third_view["name"],
            "difficulty": difficulty,
            "seed": seed,
            "icons_used": [fa.get("icon") for fa in (face_assignments or []) if fa.get("icon")],
        }
        meta_path = os.path.join(
            self.output_dir, f"{q_id}_meta.json")
        with open(meta_path, 'w') as f:
            import json
            json.dump(metadata, f, indent=2)
        print(
            f"Generated question {q_id}. Correct answer index: {correct_option_index}")
        return meta_path

    def generate_dataset(self):
        """Generate full dataset of shape-finding questions."""
        print(
            f"Generating shape-finding dataset with {self.config['num_questions']} questions…")
        os.makedirs(self.output_dir, exist_ok=True)
        self.setup_scene_once()
        meta_files = []
        question_files = []
        for q in range(self.config['num_questions']):
            try:
                meta = self.generate_question(q)
                meta_files.append(meta)
                # meta , question json
                question_files.append(meta)
            except Exception as e:
                import traceback
                print(f"Error generating question {q}: {e}")
                traceback.print_exc()
        summary = self.create_summary_file(meta_files)
        print(
            f"Shape finding dataset generation complete. Saved to {self.output_dir}")
        return question_files, summary


# Alias for legacy references
ShapeFindingGenerator = ShapeFinding3DGenerator
