import os
import bpy
import math
import json
import random
import mathutils
import bmesh
import glob

from generator.core.base_generator import SpatialReasoningGeneratorBase
from generator.core import icons as icon_utils


class BoxFoldingGenerator(SpatialReasoningGeneratorBase):
    """generate"""

    def _build_cube_net_layouts(self):
        """
        cubeunfolded net.

        return:
            face_name_to_index: ->
            face_index_to_name: ->
            cube_net_layouts: position/rotation
            unfolding_patterns: , 6
            face_rotations: , 6
        """
 # cubefaceandindex
        face_name_to_index = {
            "front": 0,
            "top": 1,
            "back": 2,
            "bottom": 3,
            "right": 4,
            "left": 5,
        }
        face_index_to_name = {v: k for k, v in face_name_to_index.items()}

        # : net
        cube_net_layouts = {
            "cross": {
                "front": {"position": (1, 1), "rotation": 0},
                "back": {"position": (1, 3), "rotation": 180},
                "left": {"position": (0, 1), "rotation": 180},
                "right": {"position": (2, 1), "rotation": 270},
                "top": {"position": (1, 2), "rotation": 0},
                "bottom": {"position": (1, 0), "rotation": 0},
            },
            "T": {
                "front": {"position": (1, 0), "rotation": 0},
                "back": {"position": (1, 2), "rotation": 180},
                "left": {"position": (0, 0), "rotation": 90},
                "right": {"position": (2, 0), "rotation": 270},
                "top": {"position": (1, 1), "rotation": 0},
                "bottom": {"position": (1, 3), "rotation": 0},
            },
        }

        unfolding_patterns = []
        face_rotations = []

        for layout_name in ("cross", "T"):
            pattern = []
            rotations = []
            layout_def = cube_net_layouts[layout_name]
            for i in range(6):
                face_name = face_index_to_name[i]
                face_info = layout_def[face_name]
                pos = face_info["position"]
                rot = face_info["rotation"]
                pattern.append((pos[0], pos[1], 0))
                rotations.append(rot)
            unfolding_patterns.append(pattern)
            face_rotations.append(rotations)

        return (
            face_name_to_index,
            face_index_to_name,
            cube_net_layouts,
            unfolding_patterns,
            face_rotations,
        )

    def __init__(self, output_dir=None, config=None):
        """
        generate

        Args:
            output_dir (str): . None, .
            config (dict): . None, .
        """
 # setdefault
        if output_dir is None:
            output_dir = "blender_dataset/3D_folding"

        super().__init__("3D_folding", output_dir, config)

 # texture
        self.cube_texture_scale = 1 # cubetexture
        self.unfolded_texture_scale = 1 # unfolded nettexture
        # , net
        (
            self.face_name_to_index,
            self.face_index_to_name,
            self.cube_net_layouts,
            self.unfolding_patterns,
            self.face_rotations,
        ) = self._build_cube_net_layouts()

 # eachfacematerial
        self.face_materials = [
            {'name': 'red', 'color': (1.0, 0.0, 0.0, 1.0)},
            {'name': 'green', 'color': (0.0, 1.0, 0.0, 1.0)},
            {'name': 'blue', 'color': (0.0, 0.0, 1.0, 1.0)},
            {'name': 'yellow', 'color': (1.0, 1.0, 0.0, 1.0)},
            {'name': 'cyan', 'color': (0.0, 1.0, 1.0, 1.0)},
            {'name': 'magenta', 'color': (1.0, 0.0, 1.0, 1.0)},
        ]

 # ,
        self.face_patterns = [
            'circle',
            'square',
            'triangle',
            'star',
            'cross',
            'diamond',
        ]

 # list
        from generator.core import logging as log
        try:
            self.icon_files = icon_utils.resolve_task_icons(
                self.config.get("lucide_icons"),
                download=self.config.get("lucide_download", False),
                prefer_png=True,
                allow_svg_fallback=True,
            )
            if self.icon_files:
                log.info(f"{len(self.icon_files)}")
                test_icons = self.icon_files[:5]
                for icon in test_icons:
                    try:
                        bpy.data.images.load(icon, check_existing=True)
                        log.info(f": {os.path.basename(icon)}")
                    except Exception as e:
                        log.warn(f"{os.path.basename(icon)}: {e}")
            else:
                log.warn(f", : {icon_utils.ASSETS_ROOT}")
        except Exception as e:
            log.warn(f"error while processing: {e}")
            self.icon_files = []

        if not self.icon_files:
            log.info(", will use")

    def create_cube_with_textures(self, cube_size=2.0, seed=None, texture_scale=None):
        """
        createtexturecube

        Args:
            cube_size:
            seed: ,
            texture_scale: , Noneself.cube_texture_scale

        Returns:
            cube:
            face_assignments:
        """
 # setrandom
        if seed is not None:
            random.seed(seed)

 # defaulttexture(if)
        if texture_scale is None:
            texture_scale = self.cube_texture_scale

 # : createcubematerial, andface
        cube, mesh = self._create_cube_mesh(cube_size)
        face_assignments = self._assign_cube_face_materials(
            cube, texture_scale)
        self._map_faces_to_directions(mesh, face_assignments)
        return cube, face_assignments

    def _create_cube_mesh(self, cube_size=2.0):
        """UV, UV, ."""
        bpy.ops.mesh.primitive_cube_add(
            size=cube_size, enter_editmode=False, align='WORLD'
        )
        cube = bpy.context.active_object
        cube.name = "TexturedCube"

        mesh = cube.data

        # UV
        if not mesh.uv_layers:
            mesh.uv_layers.new(name="UVMap")

        # Cube ProjectUV
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.cube_project(
            cube_size=True, correct_aspect=True, clip_to_bounds=True
        )
        bpy.ops.object.mode_set(mode='OBJECT')

 # ensurematerial
        while len(cube.material_slots) < 6:
            cube.data.materials.append(None)

        return cube, mesh

    def _assign_cube_face_materials(self, cube, texture_scale):
        """6, face_assignments."""
        face_assignments = []

 # randommaterial
        random_materials = self.face_materials.copy()
        random.shuffle(random_materials)

 # or
        use_icons = False
        if hasattr(self, "icon_files") and len(self.icon_files) >= 6:
            try:
                test_icon = self.icon_files[0]
                if os.path.exists(test_icon):
                    bpy.data.images.load(test_icon, check_existing=True)
                    use_icons = True
                    print("will use")
            except Exception as e:
                print(f"Testing, will use: {e}")
                use_icons = False

        if use_icons:
            selected_icons = self._select_cube_icons(self.icon_files, 6)
            for i, icon in enumerate(selected_icons):
                print(f"{i}: {os.path.basename(icon)}")
        else:
            print(", will use")
            selected_icons = [None] * 6

 # eachfacecreatematerial
        for i in range(6):
            material_data = random_materials[i]
            color = material_data["color"]

            icon_path = selected_icons[i] if use_icons else None
            icon_name = (
                os.path.basename(icon_path).split(
                    ".")[0] if icon_path else f"pattern_{i}"
            )
            material_name = f"CubeMaterial_{material_data['name']}_{icon_name}"

            if use_icons and icon_path:
                # helper" + "
                face_name = self.face_index_to_name.get(i)
                material = icon_utils.create_icon_material_for_cube(
                    material_name,
                    icon_path,
                    color,
                    texture_scale=texture_scale,
                    face_name=face_name,
                )
            else:
 # material(generate)
                material = bpy.data.materials.new(name=material_name)
                material.use_nodes = True
                nodes = material.node_tree.nodes
                links = material.node_tree.links
                nodes.clear()

                output_node = nodes.new("ShaderNodeOutputMaterial")
                output_node.location = (300, 0)

                bsdf_node = nodes.new("ShaderNodeBsdfPrincipled")
                bsdf_node.location = (0, 0)
                bsdf_node.inputs["Base Color"].default_value = color

                links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])

            cube.material_slots[i].material = material
            face_assignments.append(
                {
                    "material": material_data["name"],
                    "icon": icon_name if icon_path else selected_icons[i],
                    "material_obj": material,
                }
            )

        return face_assignments

    def _select_cube_icons(self, icon_files, count):
        """
        , ( arrow-left/right).

        :
        - "before",:
          arrow-left, arrow-right -> arrow
          chevrons-left, chevrons-right -> chevrons
        - currentinin>=2, ""; else.
        - , , count .
        """

        def series_key(path: str) -> str:
            name = os.path.splitext(os.path.basename(path))[0]
            parts = name.split("-", 1)
            return parts[0].lower() if len(parts) > 1 else name.lower()

 # eachbefore, for""and
        prefix_counts = {}
        for path in icon_files:
            key = series_key(path)
            prefix_counts[key] = prefix_counts.get(key, 0) + 1

        shuffled = icon_files.copy()
        random.shuffle(shuffled)

        selected = []
        used_series = set()

        for icon in shuffled:
            key = series_key(icon)
 # current"", else
            effective_key = key if prefix_counts.get(key, 0) >= 2 else os.path.splitext(os.path.basename(icon))[0].lower()

            if key in used_series:
                continue
            selected.append(icon)
            used_series.add(effective_key)
            if len(selected) >= count:
                break

        if len(selected) < count:
            remaining = [i for i in shuffled if i not in selected]
            for icon in remaining:
                selected.append(icon)
                if len(selected) >= count:
                    break

        if len(selected) < count:
            selected.extend(icon_files[: count - len(selected)])

        return selected[:count]

    def _map_faces_to_directions(self, mesh, face_assignments):
        """front/back/top/bottom/left/right."""
        face_index_to_direction = {}

 # eachfacein
        face_centers = {}
        for poly in mesh.polygons:
            center = mathutils.Vector((0, 0, 0))
            for v_idx in poly.vertices:
                center += mesh.vertices[v_idx].co
            center /= len(poly.vertices)
            face_centers[poly.index] = center
            print(
                f"{poly.index}: ({center.x:.4f}, {center.y:.4f}, {center.z:.4f})"
            )

        # X
        x_sorted = sorted(face_centers.items(), key=lambda x: x[1].x)
        left_face = x_sorted[0][0]
        right_face = x_sorted[-1][0]
        face_index_to_direction[left_face] = "left"
        face_index_to_direction[right_face] = "right"
        print(
            f"{left_face} (left), X: {face_centers[left_face].x:.4f}"
        )
        print(
            f"{right_face} (right), X: {face_centers[right_face].x:.4f}"
        )

        # Y
        y_sorted = sorted(face_centers.items(), key=lambda x: x[1].y)
        front_face = y_sorted[0][0]
        back_face = y_sorted[-1][0]
        face_index_to_direction[front_face] = "front"
        face_index_to_direction[back_face] = "back"
        print(
            f"{front_face} (front), Y: {face_centers[front_face].y:.4f}"
        )
        print(
            f"{back_face} (back), Y: {face_centers[back_face].y:.4f}"
        )

        # Z
        z_sorted = sorted(face_centers.items(), key=lambda x: x[1].z)
        bottom_face = z_sorted[0][0]
        top_face = z_sorted[-1][0]
        face_index_to_direction[bottom_face] = "bottom"
        face_index_to_direction[top_face] = "top"
        print(
            f"{bottom_face} (bottom), Z: {face_centers[bottom_face].z:.4f}"
        )
        print(
            f"{top_face} (top), Z: {face_centers[top_face].z:.4f}"
        )

        identified_directions = set(face_index_to_direction.values())
        expected_directions = {"front", "back",
                               "top", "bottom", "right", "left"}

        if identified_directions != expected_directions:
            print("Warning: ! :", identified_directions)
            missing_directions = expected_directions - identified_directions
            if missing_directions:
                print("face:", missing_directions)

        face_name_to_index_map = {name: idx for idx,
                                  name in face_index_to_direction.items()}

        for face_name in expected_directions:
            if face_name not in face_name_to_index_map:
                print(f"Error: {face_name}!")

        assigned_materials = set()
        for face_name, face_idx in face_name_to_index_map.items():
            material_idx = self.face_name_to_index[face_name]
            if material_idx < len(face_assignments):
                mesh.polygons[face_idx].material_index = material_idx
                assigned_materials.add(material_idx)
                print(
                    f"{material_idx} ({face_assignments[material_idx]['material']}) {face_name} ( {face_idx})"
                )

        # ( left/back ),
        if len(assigned_materials) != 6:
            remaining_mat = [
                i for i in range(len(face_assignments)) if i not in assigned_materials
            ]
            remaining_faces = [
                poly.index
                for poly in mesh.polygons
                if poly.index not in face_name_to_index_map.values()
            ]
            for mat_idx, face_idx in zip(remaining_mat, remaining_faces):
                mesh.polygons[face_idx].material_index = mat_idx
                assigned_materials.add(mat_idx)

        if len(assigned_materials) != 6:
            print(f"Warning: {len(assigned_materials)} , 6")

    def add_cube_icon_texture(self, material, icon_path, base_color, texture_scale=1.0, face_name=None):
        """
        3D

        Args:
            material:
            icon_path:
            base_color:
            texture_scale: ,
            face_name: ,
        """
        # , helper.
 # : inreturnmaterial;
        # icon_utils.create_icon_material_for_cube.
        return icon_utils.create_icon_material_for_cube(
            material.name if material else "CubeIconMaterial",
            icon_path,
            base_color,
            texture_scale=texture_scale,
            face_name=face_name,
        )

    def add_unfolded_icon_texture(self, material, icon_path, base_color, texture_scale=1.0, rotation_angle=0):
        """
        2D, .
        , helper.

        Args:
            material: ( name, )
            icon_path:
            base_color: ()
            texture_scale: ,
            rotation_angle: ()
        """
        name = material.name if material else "UnfoldedIconMaterial"
        return icon_utils.create_icon_material_for_unfolded(
            name,
            icon_path,
            base_color,
            texture_scale=texture_scale,
            rotation_angle=rotation_angle,
        )

    def create_unfolded_cube(self, cube, face_assignments, pattern_index=None, texture_scale=None):
        """
        createcubeunfolded net

        Args:
            cube:
            face_assignments:
            pattern_index: , None
            texture_scale: , Noneself.unfolded_texture_scale

        Returns:
            unfolded_obj:
        """
 # ifunfolded net, randomselect
        if pattern_index is None:
            pattern_index = random.randint(0, len(self.unfolding_patterns) - 1)

 # defaulttexture(if)
        if texture_scale is None:
            texture_scale = self.unfolded_texture_scale

        # 1) pattern/rotation
        unfolded_obj, planes = self._instantiate_unfolded_net(pattern_index)

 # 2) eachfaceandcubematerial
        self._apply_unfolded_materials(
            planes, face_assignments, pattern_index, texture_scale)

        return unfolded_obj

    def _instantiate_unfolded_net(self, pattern_index):
        """unfolded netcreateface, androtation, and."""
        pattern = self.unfolding_patterns[pattern_index]
        face_rotations = self.face_rotations[pattern_index]

        unfolded_obj = bpy.data.objects.new("UnfoldedCube", None)
        bpy.context.scene.collection.objects.link(unfolded_obj)

        # front, top, back, bottom, right, left
        face_indices = [0, 1, 2, 3, 4, 5]
        face_to_position = {
            0: pattern[0],
            1: pattern[1],
            2: pattern[2],
            3: pattern[3],
            4: pattern[4],
            5: pattern[5],
        }

        face_size = 2.0
        planes = {}

        for face_idx in face_indices:
            bpy.ops.mesh.primitive_plane_add(
                size=face_size,
                enter_editmode=False,
                align='WORLD',
                location=(
                    face_to_position[face_idx][0] * face_size,
                    face_to_position[face_idx][1] * face_size,
                    face_to_position[face_idx][2] * face_size,
                ),
            )

            plane = bpy.context.active_object
            plane.name = f"Face_{face_idx}"

            rotation_angle = face_rotations[face_idx]
            if rotation_angle != 0:
                rotation_rad = math.radians(rotation_angle)
                plane.rotation_euler = (0, 0, rotation_rad)

            plane.parent = unfolded_obj
            planes[face_idx] = plane

        return unfolded_obj, planes

    def _apply_unfolded_materials(self, planes, face_assignments, pattern_index, texture_scale):
        """unfolded netfaceandcubefacematerial/."""
        pattern = self.unfolding_patterns[pattern_index]
        face_rotations = self.face_rotations[pattern_index]

        for face_idx, plane in planes.items():
            if face_idx >= len(face_assignments):
                continue

            orig_material = face_assignments[face_idx]["material_obj"]
            icon_name = face_assignments[face_idx]["icon"]
            material_name = f"UnfoldedMaterial_{orig_material.name}"

            material = bpy.data.materials.new(name=material_name)
            material.use_nodes = True

            icon_path = None
            base_color = (1, 1, 1, 1)

            for node in orig_material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image:
                    icon_path = node.image.filepath
                elif node.type == "BSDF_PRINCIPLED":
                    base_color = node.inputs["Base Color"].default_value

            rotation_angle = face_rotations[face_idx]

            if icon_path and os.path.exists(icon_path):
                material = icon_utils.create_icon_material_for_unfolded(
                    material_name,
                    icon_path,
                    base_color,
                    texture_scale=texture_scale,
                    rotation_angle=rotation_angle,
                )
            else:
 # ifto, material, keep
                nodes = material.node_tree.nodes
                links = material.node_tree.links
                for n in nodes:
                    nodes.remove(n)

                output = nodes.new("ShaderNodeOutputMaterial")
                output.location = (300, 0)

                principled = nodes.new("ShaderNodeBsdfPrincipled")
                principled.location = (0, 0)
                principled.inputs["Base Color"].default_value = base_color

                links.new(principled.outputs["BSDF"], output.inputs["Surface"])

            while len(plane.material_slots) > 0:
                bpy.ops.object.material_slot_remove({"object": plane})

            plane.data.materials.append(material)

    def create_distractor_by_difficulty(self, correct_cube, face_assignments, difficulty="medium", seed=None, avoid_faces=None, priority_faces=None):
        """
        difficultycreatedistractor

        Args:
            correct_cube: cube
            face_assignments:
            difficulty: , "easy", "medium", "hard"
            seed:
            avoid_faces:
            priority_faces: (, )

        Returns:
            distractor_cube: cube
            changed_faces:
            change_type: type
        """

        if seed is not None:
            random.seed(seed)

        if avoid_faces is None:
            avoid_faces = []

        if priority_faces is None:
            priority_faces = []

 # before,
        available_priority_faces = [
            face for face in priority_faces if face not in avoid_faces]

        distractor_cube = self.duplicate_cube(correct_cube)

        visible_faces = self.get_visible_faces(self.current_view)
        force_visible_face_change = True

        if difficulty == "easy":
            distractor_cube, changed_faces, change_type = self._make_easy_distractor(
                distractor_cube,
                face_assignments,
                visible_faces,
                avoid_faces,
                force_visible_face_change,
            )
        elif difficulty == "hard":
            distractor_cube, changed_faces, change_type = self._make_hard_distractor(
                distractor_cube,
                face_assignments,
                visible_faces,
                avoid_faces,
                force_visible_face_change,
                seed,
            )
        else:
 # defaultindifficulty
            distractor_cube, changed_faces, change_type = self._make_medium_distractor(
                distractor_cube,
                face_assignments,
                visible_faces,
                avoid_faces,
                force_visible_face_change,
                seed,
            )

        has_visible_difference, _ = self.validate_visual_difference(
            distractor_cube, correct_cube, visible_faces)

        if not has_visible_difference and force_visible_face_change:
            face_to_change = random.choice(visible_faces)
            original_changed_faces = changed_faces.copy() if changed_faces else []
            additional_changed, additional_type = self.modify_cube_textures(
                distractor_cube,
                face_assignments,
                [face_to_change],
                seed=seed + 100 if seed else None,
            )
            if face_to_change not in changed_faces:
                changed_faces = original_changed_faces + additional_changed
            change_type = f"{change_type}_forced_{additional_type}"

        return distractor_cube, changed_faces, change_type

    def _make_easy_distractor(self, distractor_cube, face_assignments, visible_faces, avoid_faces, force_visible_face_change):
        """easy , ."""
        candidates = [f for f in visible_faces if f not in avoid_faces]
        if not candidates and force_visible_face_change:
            candidates = visible_faces
        elif not candidates:
            candidates = [f for f in range(6) if f not in avoid_faces] or list(
                range(6)
            )

        face_to_change = random.choice(candidates)

        orig_mat = distractor_cube.material_slots[face_to_change].material
        base_color = None
        for node in orig_mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                base_color = node.inputs["Base Color"].default_value
                break

        new_mat = bpy.data.materials.new(
            name=f"EasyDistractor_Mat_{face_to_change}"
        )
        new_mat.use_nodes = True
        nodes = new_mat.node_tree.nodes
        links = new_mat.node_tree.links
        nodes.clear()

        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (300, 0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        bsdf.inputs["Base Color"].default_value = base_color
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        if hasattr(self, "icon_files") and len(self.icon_files) > 1:
            orig_icon = face_assignments[face_to_change].get("icon")
            icon_choices = [
                i
                for i in self.icon_files
                if os.path.basename(i).split(".")[0] != orig_icon
            ]
            if not icon_choices:
                icon_choices = list(self.icon_files)
            choice_icon = random.choice(icon_choices)
            new_mat = icon_utils.create_icon_material_for_cube(
                f"EasyDistractor_Mat_{face_to_change}",
                choice_icon,
                base_color,
                texture_scale=self.cube_texture_scale,
                face_name=self.face_index_to_name.get(face_to_change),
            )
            change_label = os.path.splitext(os.path.basename(choice_icon))[0]
        else:
 # generate, material
            change_label = "solid_color"

        distractor_cube.material_slots[face_to_change].material = new_mat
        changed_faces = [face_to_change]
        change_type = f"easy_replaced_{change_label}"
        return distractor_cube, changed_faces, change_type

    def _make_medium_distractor(self, distractor_cube, face_assignments, visible_faces, avoid_faces, force_visible_face_change, seed):
        """medium , ."""
        modification_types = [
            "flip_texture",
            "rotate_texture",
            "change_texture",
            "combined_modification",
        ]

        if len(avoid_faces) > 2:
            weights = [0.15, 0.15, 0.2, 0.5]
        else:
            weights = [0.25, 0.25, 0.25, 0.25]

        total_weight = sum(weights)
        r = random.uniform(0, total_weight)
        cumulative = 0
        modification_type = modification_types[-1]
        for i, weight in enumerate(weights):
            cumulative += weight
            if r <= cumulative:
                modification_type = modification_types[i]
                break

        less_visible_faces = self.get_less_visible_faces(self.current_view)

        available_visible_faces = [
            face for face in visible_faces if face not in avoid_faces
        ]
        available_less_visible = [
            face for face in less_visible_faces if face not in avoid_faces
        ]

        if force_visible_face_change and not available_visible_faces:
            available_visible_faces = visible_faces

        usable_faces = []
        if available_visible_faces:
            if random.random() < 0.8 or force_visible_face_change:
                usable_faces = available_visible_faces
            elif available_less_visible:
                usable_faces = available_less_visible
            else:
                usable_faces = [f for f in range(6) if f not in avoid_faces]
                if not usable_faces:
                    usable_faces = list(range(6))
        elif available_less_visible:
            usable_faces = available_less_visible
        else:
            usable_faces = [f for f in range(6) if f not in avoid_faces]
            if not usable_faces:
                usable_faces = list(range(6))

        if modification_type == "flip_texture":
            face_to_flip = random.choice(usable_faces)
            changed_faces, change_type = self.modify_texture_directions(
                distractor_cube,
                face_assignments,
                seed,
                priority_faces=[face_to_flip],
                flip_type="flip",
            )
        elif modification_type == "rotate_texture":
            face_to_rotate = random.choice(usable_faces)
            directional_faces = []
            for face in usable_faces:
                mat = distractor_cube.material_slots[face].material
                if any(node.type == "TEX_IMAGE" for node in mat.node_tree.nodes):
                    directional_faces.append(face)
            if directional_faces:
                face_to_rotate = random.choice(directional_faces)

            changed_faces, change_type = self.modify_texture_directions(
                distractor_cube,
                face_assignments,
                seed,
                priority_faces=[face_to_rotate],
                flip_type="rotate",
            )
        elif modification_type == "change_texture":
            face_to_change = random.choice(usable_faces)
            changed_faces, change_type = self.modify_cube_textures(
                distractor_cube, face_assignments, [face_to_change], seed
            )
        else:
            if len(usable_faces) >= 2:
                modification_faces = random.sample(usable_faces, 2)

                first_changed, first_change_type = self.modify_texture_directions(
                    distractor_cube,
                    face_assignments,
                    seed,
                    priority_faces=[modification_faces[0]],
                    subtle=True,
                )

                second_changed, second_change_type = self.modify_cube_textures(
                    distractor_cube,
                    face_assignments,
                    [modification_faces[1]],
                    seed=seed + 1 if seed else None,
                )

                changed_faces = first_changed + second_changed
                change_type = (
                    f"combined_{first_change_type}_{second_change_type}"
                )
            else:
                face_to_change = random.choice(usable_faces)
                changed_faces, change_type = self.modify_cube_textures(
                    distractor_cube, face_assignments, [face_to_change], seed
                )
                change_type = "fallback_" + change_type

        return distractor_cube, changed_faces, change_type

    def _make_hard_distractor(self, distractor_cube, face_assignments, visible_faces, avoid_faces, force_visible_face_change, seed):
        """hard , ."""
        all_faces = list(range(6))
        available_faces = [f for f in all_faces if f not in avoid_faces]

        available_visible_faces = [
            f for f in visible_faces if f not in avoid_faces
        ]
        if force_visible_face_change and not available_visible_faces:
            available_visible_faces = visible_faces

        distractor_strategies = [
            "swap_and_flip",
            "multi_face_change",
            "complex_rotation",
            "pattern_swap",
        ]
        strategy = random.choice(distractor_strategies)

        if strategy == "swap_and_flip":
            if len(available_visible_faces) >= 2:
                swap_pair = random.sample(available_visible_faces, 2)
            elif available_visible_faces and available_faces:
                visible_face = random.choice(available_visible_faces)
                other_faces = [
                    f for f in available_faces if f not in available_visible_faces
                ]
                if other_faces:
                    other_face = random.choice(other_faces)
                    swap_pair = [visible_face, other_face]
                else:
                    swap_pair = [
                        visible_face,
                        random.choice(
                            [f for f in all_faces if f != visible_face]
                        ),
                    ]
            else:
                swap_pair = random.sample(all_faces, 2)

            texture_changed_faces, texture_change_type = self.swap_cube_textures(
                distractor_cube, [tuple(swap_pair)]
            )
            remaining_faces = [
                f
                for f in all_faces
                if f not in texture_changed_faces and f not in avoid_faces
            ] or all_faces

            flip_candidates = [
                f for f in remaining_faces if f in visible_faces
            ]
            if not flip_candidates:
                flip_candidates = remaining_faces

            face_to_flip = random.choice(flip_candidates)
            flip_changed_faces, flip_change_type = self.modify_texture_directions(
                distractor_cube,
                face_assignments,
                seed=seed,
                priority_faces=[face_to_flip],
                flip_type="flip",
            )
            changed_faces = texture_changed_faces + flip_changed_faces
            change_type = f"swap_{texture_change_type}_and_{flip_change_type}"

        elif strategy == "multi_face_change":
            available_visible_faces = [
                f for f in visible_faces if f not in avoid_faces
            ]
            if available_visible_faces:
                visible_face = random.choice(available_visible_faces)
                remaining_candidates = [
                    f for f in available_faces if f != visible_face
                ]
                num_faces_to_change = min(3, len(remaining_candidates) + 1)
                if num_faces_to_change > 1 and remaining_candidates:
                    additional_faces = random.sample(
                        remaining_candidates, num_faces_to_change - 1
                    )
                    faces_to_change = [visible_face] + additional_faces
                else:
                    faces_to_change = [visible_face]
            else:
                num_faces_to_change = min(3, len(available_faces)) or 1
                faces_to_change = random.sample(
                    available_faces or all_faces, num_faces_to_change
                )

            all_changed_faces = []
            change_types = []
            for i, face in enumerate(faces_to_change):
                mod_type = random.choice(["texture", "direction", "both"])
                face_seed = seed + i if seed else None

                if mod_type in ("texture", "both"):
                    face_changed, face_change = self.modify_cube_textures(
                        distractor_cube, face_assignments, [face], face_seed
                    )
                    all_changed_faces.extend(face_changed)
                    change_types.append(face_change)

                if mod_type in ("direction", "both"):
                    dir_changed, dir_change = self.modify_texture_directions(
                        distractor_cube,
                        face_assignments,
                        face_seed,
                        priority_faces=[face],
                    )
                    all_changed_faces.extend(
                        [f for f in dir_changed if f not in all_changed_faces]
                    )
                    change_types.append(dir_change)

            changed_faces = all_changed_faces
            change_type = f"multi_face_{'_'.join(change_types)}"

        elif strategy == "complex_rotation":
            rotation_candidates = available_faces or all_faces
            visible_candidates = [
                f for f in rotation_candidates if f in visible_faces
            ]
            if visible_candidates:
                rotation_candidates = visible_candidates

            num_faces_to_rotate = random.randint(
                1, min(3, len(rotation_candidates))
            )
            faces_to_rotate = random.sample(
                rotation_candidates, num_faces_to_rotate
            )

            all_rotated_faces = []
            rotation_types = []
            for i, face in enumerate(faces_to_rotate):
                face_seed = seed + i if seed else None
                angle = random.choice([90, 180, 270])

                rotated_faces, rotation_type = self.modify_texture_directions(
                    distractor_cube,
                    face_assignments,
                    face_seed,
                    priority_faces=[face],
                    flip_type="rotate",
                    rotation_angle=angle,
                )

                all_rotated_faces.extend(rotated_faces)
                rotation_types.append(rotation_type)

            changed_faces = all_rotated_faces
            change_type = f"complex_rotation_{'_'.join(rotation_types)}"

        elif strategy == "pattern_swap":
            if available_visible_faces:
                visible_face = random.choice(available_visible_faces)
                other_faces = [
                    f
                    for f in all_faces
                    if f != visible_face and f not in avoid_faces
                ]
                if not other_faces:
                    other_faces = [
                        f for f in all_faces if f != visible_face
                    ]
                other_face = random.choice(other_faces)
                swap_pairs = [(visible_face, other_face)]
                remaining_faces = [
                    f
                    for f in all_faces
                    if f not in [visible_face, other_face]
                    and f not in avoid_faces
                ]
                if len(remaining_faces) >= 2 and random.random() < 0.5:
                    second_pair = random.sample(remaining_faces, 2)
                    swap_pairs.append(tuple(second_pair))
            else:
                available_for_swap = available_faces or all_faces
                if len(available_for_swap) >= 2:
                    swap_pairs = [
                        tuple(random.sample(available_for_swap, 2))
                    ]
                    remaining_faces = [
                        f
                        for f in available_for_swap
                        if f not in swap_pairs[0]
                    ]
                    if len(remaining_faces) >= 2 and random.random() < 0.5:
                        second_pair = random.sample(remaining_faces, 2)
                        swap_pairs.append(tuple(second_pair))
                else:
                    face_to_change = random.choice(all_faces)
                    changed_faces, change_type = self.modify_cube_textures(
                        distractor_cube,
                        face_assignments,
                        [face_to_change],
                        seed,
                    )
                    return (
                        distractor_cube,
                        changed_faces,
                        f"fallback_{change_type}",
                    )

            changed_faces, change_type = self.swap_cube_textures(
                distractor_cube, swap_pairs
            )
        else:
            face_to_change = random.choice(
                visible_faces) if visible_faces else random.choice(all_faces)
            changed_faces, change_type = self.modify_cube_textures(
                distractor_cube, face_assignments, [face_to_change], seed
            )
            change_type = "fallback_" + change_type

        return distractor_cube, changed_faces, change_type

    def modify_texture_directions(self, cube, face_assignments, seed=None, texture_scale=None, priority_faces=None, flip_type=None, rotation_angle=None, subtle=False):
        """
        cube

        Args:
            cube:
            face_assignments:
            seed:
            texture_scale:
            priority_faces:
            flip_type: type, "flip"() "rotate"()
            rotation_angle:
            subtle:

        Returns:
            changed_faces:
            change_type: type
        """
 # setrandom
        if seed is not None:
            random.seed(seed)

 # defaulttexture(if)
        if texture_scale is None:
            texture_scale = self.cube_texture_scale

        # type
        changed_faces = []
        change_type = ""

 # face
        if priority_faces:
 # face
            candidate_faces = priority_faces
        else:
 # randomselectface
            candidate_faces = list(range(6))

 # randomselectface
        face_idx = random.choice(candidate_faces)

 # Get face materials
        material = cube.material_slots[face_idx].material
        if not material:
 # ifmaterial, face
            return [], "no_material_changed"

 # face
        face_name = self.face_index_to_name.get(face_idx, "unknown")

 # ensurematerial
        if not material.use_nodes:
            material.use_nodes = True

 # currentmaterialrotation(if)
        current_rotation = self.get_material_rotation(material)

        # flip_typesubtletype
        if subtle:
 # : rotationorflip
            if flip_type == "flip":
 # flip: or
                change_type = "subtle_flip"
 # : -
                for node in material.node_tree.nodes:
                    if node.type == 'MAPPING':
                        scale_factor = random.uniform(0.95, 1.05)
                        node.inputs['Scale'].default_value[0] *= scale_factor
                        node.inputs['Scale'].default_value[1] *= scale_factor
            else: # defaultrotationorrandomselect # defaultrotationorrandomselect
                change_type = "subtle_rotation"
                small_angle = random.choice([-15, 15, 30, -30])
                self.rotate_material_texture(material, small_angle)
        else:
            # Standard adjustment path.
            if flip_type == "flip":
 # flip(orflip)
                flip_type = random.choice(["horizontal", "vertical"])
                if flip_type == "horizontal":
 # flip
                    change_type = "horizontal_flip"
                    # X
                    for node in material.node_tree.nodes:
                        if node.type == 'MAPPING':
                            node.inputs['Scale'].default_value[0] *= -1
                else:
 # flip
                    change_type = "vertical_flip"
                    # Y
                    for node in material.node_tree.nodes:
                        if node.type == 'MAPPING':
                            node.inputs['Scale'].default_value[1] *= -1
            elif flip_type == "rotate":
 # rotation(90°, 180°or270°)
                if rotation_angle is not None:
                    angle = rotation_angle
                else:
                    angle = random.choice([90, 180, 270])
                change_type = f"rotation_{angle}"
                self.rotate_material_texture(material, angle)
            else:
 # default: randomselectfliporrotation
                modification = random.choice(["flip", "rotate"])
                if modification == "flip":
 # flip
                    flip_type = random.choice(["horizontal", "vertical"])
                    if flip_type == "horizontal":
 # flip
                        change_type = "horizontal_flip"
                        # X
                        for node in material.node_tree.nodes:
                            if node.type == 'MAPPING':
                                node.inputs['Scale'].default_value[0] *= -1
                    else:
 # flip
                        change_type = "vertical_flip"
                        # Y
                        for node in material.node_tree.nodes:
                            if node.type == 'MAPPING':
                                node.inputs['Scale'].default_value[1] *= -1
                else:
 # rotation
                    angle = random.choice([90, 180, 270])
                    change_type = f"rotation_{angle}"
                    self.rotate_material_texture(material, angle)

 # face
        changed_faces.append(face_idx)

        # type
        return changed_faces, change_type

    def duplicate_cube(self, original_cube):
        """cubeobject"""
        try:
 # ensureinobject
            bpy.ops.object.select_all(action='DESELECT')

 # inoriginalcube
            original_cube.select_set(True)
            bpy.context.view_layer.objects.active = original_cube
 # object
            bpy.ops.object.duplicate()

 # createobject
            distractor_cube = bpy.context.active_object

 # iftoobject,
            if distractor_cube is None or distractor_cube == original_cube:
                selected_objects = bpy.context.selected_objects
                for obj in selected_objects:
                    if obj != original_cube:
                        distractor_cube = obj
                        break

 # ifto, createcube
            if distractor_cube is None or distractor_cube == original_cube:
                print("Warning: ,")
                bpy.ops.mesh.primitive_cube_add(
                    size=2.0, enter_editmode=False, align='WORLD')
                distractor_cube = bpy.context.active_object

 # set
            if distractor_cube:
                distractor_cube.name = "DistractorCube"

            return distractor_cube

        except Exception as e:
            print(f"error while processing: {e}")
            return None

    def modify_cube_textures(self, cube, face_assignments, faces_to_change, seed=None, texture_scale=None):
        """
        cubetexture

        Args:
            cube:
            face_assignments:
            faces_to_change:
            seed:
            texture_scale:

        Returns:
            changed_faces:
            change_type: type
        """
 # defaulttexture(if)
        if texture_scale is None:
            texture_scale = self.cube_texture_scale

 # allmaterial
        try:
            for i in range(len(face_assignments)):
                if i < len(cube.material_slots):
                    original_material = face_assignments[i]['material_obj']
                    cube.material_slots[i].material = original_material
        except Exception as e:
            print(f"error while processing: {e}")

 # face
        face_indices = list(range(6))
        if isinstance(faces_to_change, list):
 # ifface indexlist,
            faces_to_modify = faces_to_change
        else:
 # ifcount, randomselect
            num_faces = min(faces_to_change, 6)
            random.shuffle(face_indices)
            faces_to_modify = face_indices[:num_faces]

 # original,
        original_assignments = {}
        for i, assignment in enumerate(face_assignments):
            if 'material' in assignment:
                original_assignments[i] = assignment['material']

        # record new material names for change_type
        change_descriptors = []

 # infacematerial
        for face_idx in faces_to_modify:
            try:
                # face_idx
                if face_idx >= len(cube.material_slots):
                    print(f"Warning: {face_idx} ,")
                    continue

 # originalmaterial
                original_material = face_assignments[face_idx].get('material')

 # material
                available_materials = [m for m in self.face_materials
                                       if m['name'] != original_material]

 # randomselectmaterial
                if available_materials:
                    new_material_data = random.choice(available_materials)
                    # record new material for change_type signature
                    change_descriptors.append(new_material_data['name'])

 # creatematerial
                    material_name = f"DistractorMaterial_{new_material_data['name']}"
                    material = bpy.data.materials.new(name=material_name)
                    material.use_nodes = True

 # setmaterial
                    color = new_material_data['color']

 # setmaterial
                    nodes = material.node_tree.nodes
                    links = material.node_tree.links

 # default
                    for node in nodes:
                        nodes.remove(node)

 # create
                    output = nodes.new('ShaderNodeOutputMaterial')
                    output.location = (300, 0)

                    principled = nodes.new('ShaderNodeBsdfPrincipled')
                    principled.location = (0, 0)
                    principled.inputs['Base Color'].default_value = color

                    links.new(
                        principled.outputs['BSDF'], output.inputs['Surface'])

 # texture
                    face_name = self.face_index_to_name.get(face_idx)
                    if hasattr(self, 'icon_files') and len(self.icon_files) > 0:
                        # Exclude the original icon
                        original_icon = face_assignments[face_idx]['icon']
                        available_icons = [icon for icon in self.icon_files
                                           if os.path.basename(icon).split('.')[0] != original_icon]
                        if not available_icons:
                            available_icons = self.icon_files
                        random_icon = random.choice(available_icons)
                        material = icon_utils.create_icon_material_for_cube(
                            material_name,
                            random_icon,
                            color,
                            texture_scale=texture_scale,
                            face_name=face_name,
                        )
                    else:
 # generate, keep
                        pass

 # materialtocube
                    cube.material_slots[face_idx].material = material

            except Exception as e:
                print(f"{face_idx} error while processing: {e}")

        # change_type
        if change_descriptors:
            change_type_str = f"texture_replaced_{'_'.join(change_descriptors)}"
        else:
            change_type_str = "texture_replaced"
        return faces_to_modify, change_type_str

    def get_material_rotation(self, material):
        """(Z)"""
        if not material or not material.use_nodes:
            return None

        for node in material.node_tree.nodes:
            if node.type == 'MAPPING':
                # Z()
                try:
                    return node.inputs['Rotation'].default_value[2]
                except (IndexError, KeyError, AttributeError):
                    pass
        return None

    def copy_material_nodes(self, source_material, target_material):
        """materialset"""
        if not source_material.use_nodes or not target_material.use_nodes:
            return

 # materialall
        for node in target_material.node_tree.nodes:
            target_material.node_tree.nodes.remove(node)

        # Base color and opacity defaults.
        color = (1, 1, 1, 1)

 # materialin
        source_nodes = source_material.node_tree.nodes
        source_links = source_material.node_tree.links

 # create
        output = target_material.node_tree.nodes.new(
            'ShaderNodeOutputMaterial')
        output.location = (300, 0)

        principled = target_material.node_tree.nodes.new(
            'ShaderNodeBsdfPrincipled')
        principled.location = (0, 0)

        # BSDF
        target_material.node_tree.links.new(
            principled.outputs['BSDF'], output.inputs['Surface'])

        # Find color and texture information from the source material.
        texture_image = None
        for node in source_nodes:
            if node.type == 'BSDF_PRINCIPLED':
                # Read the base color from the Principled BSDF node.
                if node.inputs['Base Color'].is_linked:
                    color = (1, 1, 1, 1) # to,
                else:
                    color = node.inputs['Base Color'].default_value

            elif node.type == 'TEX_IMAGE' and node.image:
 # to
                texture_image = node.image

 # set
        principled.inputs['Base Color'].default_value = color

 # ifto, tomaterial
        if texture_image:
 # create
            tex_node = target_material.node_tree.nodes.new(
                'ShaderNodeTexImage')
            tex_node.location = (-300, 0)
            tex_node.image = texture_image

            # Add UV and Mapping nodes.
            coord_node = target_material.node_tree.nodes.new(
                'ShaderNodeTexCoord')
            coord_node.location = (-600, 0)

            mapping_node = target_material.node_tree.nodes.new(
                'ShaderNodeMapping')
            mapping_node.location = (-450, 0)

            # Connect nodes.
            target_material.node_tree.links.new(
                coord_node.outputs['UV'], mapping_node.inputs['Vector'])
            target_material.node_tree.links.new(
                mapping_node.outputs['Vector'], tex_node.inputs['Vector'])
            target_material.node_tree.links.new(
                tex_node.outputs['Color'], principled.inputs['Base Color'])

    def rotate_material_texture(self, material, angle_degrees):
        """rotationmaterialin"""
        if not material.use_nodes:
            return

        nodes = material.node_tree.nodes

        # Find an existing mapping node.
        mapping_node = None
        for node in nodes:
            if node.type == 'MAPPING':
                mapping_node = node
                break

 # ifto, create
        if not mapping_node:
            # If no mapping node exists, try to construct one.
            tex_node = None
            coord_node = None

            for node in nodes:
                if node.type == 'TEX_IMAGE':
                    tex_node = node
                elif node.type == 'TEX_COORD':
                    coord_node = node

 # ifto, create
            if tex_node and not coord_node:
                coord_node = nodes.new('ShaderNodeTexCoord')
                coord_node.location = (
                    tex_node.location.x - 300, tex_node.location.y)

 # if, create
            if tex_node and coord_node:
                # Remove the old vector link to the image texture.
                for link in material.node_tree.links:
                    if link.to_node == tex_node and link.to_socket.name == 'Vector':
                        material.node_tree.links.remove(link)

 # create
                mapping_node = nodes.new('ShaderNodeMapping')
                mapping_node.location = (
                    coord_node.location.x + 150, coord_node.location.y)

                # Reconnect nodes through the Mapping node.
                material.node_tree.links.new(
                    coord_node.outputs['UV'], mapping_node.inputs['Vector'])
                material.node_tree.links.new(
                    mapping_node.outputs['Vector'], tex_node.inputs['Vector'])

 # rotation
        if mapping_node:
            # Apply rotation in radians.
            angle_rad = math.radians(angle_degrees)
            # - Z
            mapping_node.inputs['Rotation'].default_value = (
                0.0, 0.0, angle_rad)

    def get_visible_faces(self, view):
        """
        cameracubeface

        Args:
            view: ,

        Returns:
            visible_faces:
        """
 # face
        view_to_faces = {
            "iso_front_top_right": [0, 1, 4], # beforeface, face, face
            "iso_back_top_right": [2, 1, 4], # afterface, face, face
            "iso_front_top_left": [0, 1, 5], # beforeface, face, face
            "iso_back_top_left": [2, 1, 5], # afterface, face, face
            "iso_front_bottom_right": [0, 3, 4], # beforeface, face, face
            "iso_back_bottom_right": [2, 3, 4], # afterface, face, face
            "iso_front_bottom_left": [0, 3, 5], # beforeface, face, face
            "iso_back_bottom_left": [2, 3, 5], # afterface, face, face
            "front": [0], # beforeface
            "back": [2], # afterface
            "left": [5], # face
            "right": [4], # face
            "top": [1], # face
            "bottom": [3] # face
            }

        # Resolve view name from dict/string input.
        view_name = view.get("name", "") if isinstance(view, dict) else view

 # returnvisible faces
        return view_to_faces.get(view_name, [0, 1, 4]) # defaultreturnbeforeface
    def generate_question(self, q_id):
        """generate"""
        print(f"Generating box folding question {q_id}...")

 # Clear existing scene objects more thoroughly
        self.clear_question_objects()

 # Create a random seed
        question_seed = hash(f"3d_folding_{q_id}") % 10000
        random.seed(question_seed)

 # Current difficulty
        difficulty = self.config.get("difficulty", "medium")

 # Create the cube and face assignments for unfolded view and metadata
        cube, base_face_assignments = self.create_cube_with_textures(
            seed=question_seed, texture_scale=self.cube_texture_scale
        )

        original_materials = []
        for slot in cube.material_slots:
            if slot.material:
                original_materials.append(slot.material)

        pattern_index = random.randint(0, 1)
        question_img = self._render_unfolded_question_image(
            q_id, cube, base_face_assignments, pattern_index
        )

        (
            correct_cube,
            correct_img,
            view,
            view_info,
            correct_option,
        ) = self._render_correct_answer(q_id, question_seed, original_materials)

        options = [correct_option]

        distractor_options = self._generate_distractor_options(
            q_id,
            question_seed,
            difficulty,
            correct_cube,
            original_materials,
            view,
            view_info,
        )
        options.extend(distractor_options)

 # Clean the scene by deleting all objects
        self.clear_question_objects()

        metadata_file = self._build_and_save_metadata(
            q_id,
            question_img,
            pattern_index,
            question_seed,
            base_face_assignments,
            options,
        )
        return metadata_file

    def _render_unfolded_question_image(self, q_id, cube, face_assignments, pattern_index):
        """(Q )."""
        unfolded_cube = self.create_unfolded_cube(
            cube,
            face_assignments,
            pattern_index,
            texture_scale=self.unfolded_texture_scale,
        )

        cam = bpy.context.scene.camera
        cam.data.type = "ORTHO"

        min_x = float("inf")
        max_x = float("-inf")
        min_y = float("inf")
        max_y = float("-inf")

        for child in unfolded_cube.children:
            for corner in child.bound_box:
                world_corner = child.matrix_world @ mathutils.Vector(corner)
                min_x = min(min_x, world_corner.x)
                max_x = max(max_x, world_corner.x)
                min_y = min(min_y, world_corner.y)
                max_y = max(max_y, world_corner.y)

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2

        width = max_x - min_x
        height = max_y - min_y

        cam.location = (center_x, center_y, 10)
        cam.rotation_euler = (0, 0, 0)

        margin_factor = 1.6
        ortho_scale = max(width, height) * margin_factor
        min_scale = 8.0
        max_scale = 20.0
        ortho_scale = max(min_scale, min(ortho_scale, max_scale))
        cam.data.ortho_scale = ortho_scale

        print(
            f": ={width:.2f}, ={height:.2f}, =({center_x:.2f}, {center_y:.2f})"
        )
        print(f": {ortho_scale:.2f}")

        if cube:
            cube.hide_render = True
        if unfolded_cube:
            unfolded_cube.hide_render = False

        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)
        return question_img

    def _render_correct_answer(self, q_id, question_seed, original_materials):
        """view, ."""
 # scene, correct answer
        self.clear_question_objects()

        correct_cube, _ = self.create_cube_with_textures(
            seed=question_seed, texture_scale=self.cube_texture_scale
        )

        if len(original_materials) == 6 and len(correct_cube.material_slots) >= 6:
            for i in range(6):
                correct_cube.material_slots[i].material = original_materials[i]

        cam = bpy.context.scene.camera
        cam.data.type = "PERSP"

        view = random.choice(self.iso_views)
        self.current_view = view
        self.set_camera_to_view(cam, view, add_randomness=True)

        view_info = {
            "name": view["name"],
            "position": [float(round(coord, 3)) for coord in cam.location],
            "rotation": [float(round(angle, 3)) for angle in cam.rotation_euler],
            "look_at": view["look_at"],
        }

        if correct_cube:
            correct_cube.hide_render = False

        correct_img = os.path.join(self.output_dir, f"{q_id}_A0.png")
        self.render_image(correct_img)

        option = {
            "image": correct_img,
            "label": "correct",
            "cube_seed": question_seed,
            "view_name": view["name"],
            "view_info": view_info,
        }
        return correct_cube, correct_img, view, view_info, option

    def _generate_distractor_options(
        self,
        q_id,
        question_seed,
        difficulty,
        correct_cube,
        original_materials,
        view,
        view_info,
    ):
        """Generate distractor option list."""
        options = []

        used_change_types = []
        used_face_changes = []
        visible_faces = self.get_visible_faces(self.current_view)

        reference_correct_cube = None
        try:
            reference_correct_cube = self.duplicate_cube(correct_cube)
            if reference_correct_cube:
                reference_correct_cube.hide_render = True
                reference_correct_cube.hide_viewport = True
        except Exception as e:
            print(f"Warning: : {e}")

        cam = bpy.context.scene.camera

        for i in range(self.config["num_distractors"]):
            objects_to_keep = [
                reference_correct_cube] if reference_correct_cube else []
            self.clear_scene_except(objects_to_keep + [cam])

            distractor_seed = hash(f"distractor_{q_id}_{i}") % 10000

            try:
                original_cube, face_assignments = self.create_cube_with_textures(
                    seed=question_seed, texture_scale=self.cube_texture_scale
                )

                if len(original_materials) == 6 and len(
                    original_cube.material_slots
                ) >= 6:
                    for j in range(6):
                        original_cube.material_slots[j].material = original_materials[j]
            except Exception as e:
                print(f"Warning: {i+1} error while processing: {e}")
                continue

            max_attempts = 15
            attempts = 0
            distractor_cube = None
            changed_faces = []
            change_type = ""
            unique_distractor = False
            valid_visual_difference = False
            different_visible_faces = []
            has_visible_difference = False

            while (
                (not unique_distractor or not valid_visual_difference)
                and attempts < max_attempts
            ):
                try:
                    distractor_cube, changed_faces, change_type = (
                        self.create_distractor_by_difficulty(
                            original_cube,
                            face_assignments,
                            difficulty,
                            seed=distractor_seed + attempts,
                            avoid_faces=used_face_changes
                            if attempts < max_attempts // 2
                            else [],
                            priority_faces=visible_faces,
                        )
                    )

                    distractor_signature = (
                        str(change_type),
                        str(sorted(changed_faces)),
                    )

                    if not distractor_cube or not hasattr(
                        distractor_cube, "material_slots"
                    ):
                        print(
                            f"Warning: {i+1} {attempts}:"
                        )
                        attempts += 1
                        continue

                    compare_cube = (
                        reference_correct_cube if reference_correct_cube else correct_cube
                    )
                    has_visible_difference, different_visible_faces = (
                        self.validate_visual_difference(
                            distractor_cube, compare_cube, visible_faces
                        )
                    )

                    if (
                        distractor_signature not in used_change_types
                        and has_visible_difference
                    ):
                        unique_distractor = True
                        valid_visual_difference = True
                        used_change_types.append(distractor_signature)
                        used_face_changes.extend(
                            [f for f in changed_faces if f in visible_faces]
                        )
                    else:
                        attempts += 1
                        reason = []
                        if distractor_signature in used_change_types:
                            reason.append("duplicate with existing distractors")
                        if not has_visible_difference:
                            reason.append("no obvious difference on visible faces")
                        print(
                            f"Distractor {i+1} attempt {attempts}: {', '.join(reason)}, retrying..."
                        )

                        if attempts >= max_attempts // 2 and not valid_visual_difference:
                            if distractor_signature not in used_change_types:
                                print(
                                    f"Warning: {i+1} , ,"
                                )
                                unique_distractor = True
                                valid_visual_difference = True
                                used_change_types.append(distractor_signature)
                                used_face_changes.extend(
                                    [f for f in changed_faces if f in visible_faces]
                                )
                except Exception as e:
                    print(f"error while processing ( {attempts}): {e}")
                    attempts += 1
                    import traceback

                    traceback.print_exc()
                    continue

            if not unique_distractor or not valid_visual_difference:
                print(
                    f"Warning: {i+1} ,"
                )
                distractor_signature = (
                    str(change_type),
                    str(sorted(changed_faces)),
                )
                used_change_types.append(distractor_signature)
                used_face_changes.extend(
                    [f for f in changed_faces if f in visible_faces]
                )

            if not distractor_cube or not hasattr(
                distractor_cube, "material_slots"
            ):
                print(f"Error: {i+1} ,")
                continue

            try:
                if original_cube and hasattr(original_cube, "hide_render"):
                    original_cube.hide_render = True
                if reference_correct_cube and hasattr(
                    reference_correct_cube, "hide_render"
                ):
                    reference_correct_cube.hide_render = True
                distractor_cube.hide_render = False

                self.set_camera_to_view(cam, view, add_randomness=False)

                distractor_img = os.path.join(
                    self.output_dir, f"{q_id}_A{i+1}.png"
                )
                self.render_image(distractor_img)

                options.append(
                    {
                        "image": distractor_img,
                        "label": f"distractor_{i+1}",
                        "cube_seed": distractor_seed,
                        "view_name": view["name"],
                        "view_info": view_info,
                        "changed_faces": changed_faces,
                        "change_type": change_type,
                        "visible_difference": valid_visual_difference,
                        "different_visible_faces": different_visible_faces
                        if has_visible_difference
                        else [],
                    }
                )
            except Exception as e:
                print(f"{i+1} error while processing: {e}")
                import traceback

                traceback.print_exc()

        return options

    def _build_and_save_metadata(
        self,
        q_id,
        question_img,
        pattern_index,
        question_seed,
        face_assignments,
        options,
    ):
        """Assemble and save question metadata, then return metadata path."""
        metadata = {
            "question_id": q_id,
            "question_type": "3d_folding",
            "question_image": question_img,
            "options": options,
            "pattern_index": pattern_index,
            "correct_answer": 0,
            "seed": question_seed,
            "icons_used": [
                fa.get("icon")
                for fa in (face_assignments or [])
                if fa.get("icon")
            ],
        }

        metadata_file = os.path.join(self.output_dir, f"{q_id}_meta.json")
        with open(metadata_file, "w") as f:
            json.dump(
                metadata,
                f,
                indent=2,
                default=lambda x: str(x)
                if isinstance(
                    x, (mathutils.Vector, mathutils.Euler, mathutils.Matrix)
                )
                else None,
            )

        return metadata_file

    def generate_dataset(self):
        """Generate the complete box-folding dataset"""
        print(
            f"Generating box folding dataset with {self.config['num_questions']} questions...")

 # Ensure the output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

 # Set up the base scene
        self.setup_scene()

        # question
        meta_files = []
        for q_id in range(self.config['num_questions']):
            try:
                metadata_file = self.generate_question(q_id)
                meta_files.append(metadata_file)
                print(f"Generated question {q_id}")
            except Exception as e:
                print(f"Error generating question {q_id}: {e}")
                import traceback
                traceback.print_exc()

 # Create dataset summary file
        summary_file = self.create_summary_file(meta_files)
        print(
            f"Box folding dataset generation complete, saved to {self.output_dir}")

 # Return generated metadata files and summary path
        return meta_files, summary_file

    def clear_scene_except(self, objects_to_keep):
        """Remove all scene objects except the specified ones"""
        # None
        objects_to_keep = [obj for obj in objects_to_keep if obj is not None]

 # Ensure preserved objects are still valid (not deleted)
        valid_objects_to_keep = []
        for obj in objects_to_keep:
            try:
                # Testing
                _ = obj.name
                valid_objects_to_keep.append(obj)
            except ReferenceError:
                print(f"Warning:")
            except Exception as e:
                print(f"error while processing: {e}")

        objects_to_keep = valid_objects_to_keep

        try:
 # Delete objects not in the keep list
            objects_to_delete = []
            for obj in list(bpy.context.scene.objects):
                if obj not in objects_to_keep and obj.type not in {'CAMERA', 'LIGHT'}:
                    objects_to_delete.append(obj)

 # Delete objects in a separate loop to avoid mutating during iteration
            for obj in objects_to_delete:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception as e:
                    print(
                        f"{obj.name if hasattr(obj, 'name') else 'unknown'} error while processing: {e}")

 # scene
            bpy.context.view_layer.update()
        except Exception as e:
            print(f"error while processing: {e}")
            import traceback
            traceback.print_exc()

    def get_less_visible_faces(self, view):
        """
        Return invisible cube-face indices for the current camera view
        """
 # Get visible face list
        visible = self.get_visible_faces(view)
 # All face indices
        all_faces = list(range(6))
 # Return invisible faces
        return [f for f in all_faces if f not in visible]

    def swap_cube_textures(self, cube, faces_to_swap):
        """
        Swap textures between cube faces without pulling new textures from the library

        Args:
            cube:
            faces_to_swap: , [(0,1), (2,3)]01, 23

        Returns:
            changed_faces:
            change_type: type
        """
        if not faces_to_swap or len(cube.material_slots) < 2:
            return [], "no_swap"

 # Record changed faces
        changed_faces = []

 # Perform swaps
        for face1, face2 in faces_to_swap:
            try:
 # Ensure indices are in range
                if face1 >= len(cube.material_slots) or face2 >= len(cube.material_slots):
                    print(f"Warning: {face1} {face2} ,")
                    continue

 # Get face materials
                material1 = cube.material_slots[face1].material
                material2 = cube.material_slots[face2].material

 # Swap materials
                cube.material_slots[face1].material = material2
                cube.material_slots[face2].material = material1

 # Record changed faces
                changed_faces.extend([face1, face2])

                print(f"{face1} {face2}")
            except Exception as e:
                print(f"error while processing: {e}")

        return changed_faces, f"swapped_{len(changed_faces)//2}_pairs"

    def validate_visual_difference(self, distractor_cube, correct_cube, visible_faces):
        """
        Validate whether distractor and correct answer differ enough on visible faces

        Args:
            distractor_cube:
            correct_cube:
            visible_faces:

        Returns:
            bool:
            list:
        """
 # Check whether objects are valid
        try:
 # Try accessing an attribute to verify object validity
            if not distractor_cube or not correct_cube:
                return False, []

 # Check whether objects have been deleted
            if not hasattr(distractor_cube, 'material_slots') or not hasattr(correct_cube, 'material_slots'):
                return False, []

            # material_slots
            _ = len(distractor_cube.material_slots)
            _ = len(correct_cube.material_slots)
        except ReferenceError:
 # Object has been deleted; return a safe fallback value
            print("Warning: Detected,")
            return False, []
        except Exception as e:
            # Error,
            print(f"error while processing: {e}")
            return False, []

 # Check whether at least one visible face has a different material
        different_faces = []

        for face_idx in visible_faces:
            try:
 # Check whether material slots exist
                if (face_idx >= len(distractor_cube.material_slots) or
                        face_idx >= len(correct_cube.material_slots)):
                    continue

 # Get materials for corresponding faces on both cubes
                dist_mat = distractor_cube.material_slots[face_idx].material
                corr_mat = correct_cube.material_slots[face_idx].material

 # If material objects differ, treat as a visual difference
                if dist_mat != corr_mat:
                    different_faces.append(face_idx)
                    continue

 # Even if material objects match, check node-tree differences (e.g., rotation/flip)
                if dist_mat and corr_mat and dist_mat.use_nodes and corr_mat.use_nodes:
 # Check texture rotation
                    dist_rotation = self.get_material_rotation(dist_mat)
                    corr_rotation = self.get_material_rotation(corr_mat)

                    if dist_rotation is not None and corr_rotation is not None:
 # If rotation differs, treat as a visual difference
                        if abs(dist_rotation - corr_rotation) > 0.01: # Allow a small floating-point tolerance
                            different_faces.append(face_idx)
                            continue

 # Check mapping-node scale values (for flip detection)
                    has_flip_difference = False
                    for dist_node in dist_mat.node_tree.nodes:
                        if dist_node.type == 'MAPPING':
                            for corr_node in corr_mat.node_tree.nodes:
                                if corr_node.type == 'MAPPING':
                                    # X/Y()
                                    try:
                                        if (dist_node.inputs['Scale'].default_value[0] *
                                            corr_node.inputs['Scale'].default_value[0] < 0 or
                                            dist_node.inputs['Scale'].default_value[1] *
                                                corr_node.inputs['Scale'].default_value[1] < 0):
                                            has_flip_difference = True
                                            break
                                    except (IndexError, KeyError, AttributeError):
                                        pass
                            if has_flip_difference:
                                different_faces.append(face_idx)
                                break
            except ReferenceError:
 # Objects may be deleted while iterating
                print(f"Warning: {face_idx}")
                continue
            except Exception as e:
                print(f"{face_idx} error while processing: {e}")
                continue

        # , True
        return len(different_faces) > 0, different_faces

    def setup_scene(self):
        """Set up render scene by inheriting base setup and adding task-specific configuration"""
        # setup_scene
        super().setup_scene()

        # box_folding
        print("Box folding")


# Backward-compatible alias
Folding3DGenerator = BoxFoldingGenerator
