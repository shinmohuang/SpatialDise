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
    """盒子折叠题目生成器"""

    def _build_cube_net_layouts(self):
        """
        构建立方体展开图布局和相关映射。

        返回:
            face_name_to_index: 面名 -> 索引
            face_index_to_name: 索引 -> 面名
            cube_net_layouts: 不同展开布局的 position/rotation 定义
            unfolding_patterns: 每种布局下，6 个面的平面坐标列表
            face_rotations: 每种布局下，6 个面的旋转角度列表
        """
        # 立方体面名称与索引映射
        face_name_to_index = {
            "front": 0,
            "top": 1,
            "back": 2,
            "bottom": 3,
            "right": 4,
            "left": 5,
        }
        face_index_to_name = {v: k for k, v in face_name_to_index.items()}

        # 展开图布局定义：可以在此处新增更多 net 模式
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
        初始化生成器及其配置参数

        Args:
            output_dir (str): 生成文件的保存目录。若为None，则使用默认目录。
            config (dict): 配置字典。若为None，则使用默认配置。
        """
        # 设置默认输出目录
        if output_dir is None:
            output_dir = "blender_dataset/box_folding"

        super().__init__("box_folding", output_dir, config)

        # 定义贴图缩放比例
        self.cube_texture_scale = 1     # 三维立方体的贴图比例
        self.unfolded_texture_scale = 1  # 二维展开图的贴图比例

        # 初始化展开图布局和相关映射，便于后续扩展不同 net 形状
        (
            self.face_name_to_index,
            self.face_index_to_name,
            self.cube_net_layouts,
            self.unfolding_patterns,
            self.face_rotations,
        ) = self._build_cube_net_layouts()

        # 每个面对应的材质颜色和标记
        self.face_materials = [
            {'name': 'red', 'color': (1.0, 0.0, 0.0, 1.0)},
            {'name': 'green', 'color': (0.0, 1.0, 0.0, 1.0)},
            {'name': 'blue', 'color': (0.0, 0.0, 1.0, 1.0)},
            {'name': 'yellow', 'color': (1.0, 1.0, 0.0, 1.0)},
            {'name': 'cyan', 'color': (0.0, 1.0, 1.0, 1.0)},
            {'name': 'magenta', 'color': (1.0, 0.0, 1.0, 1.0)},
        ]

        # 定义基础图案，无论是否加载图标都需要
        self.face_patterns = [
            'circle',
            'square',
            'triangle',
            'star',
            'cross',
            'diamond',
        ]

        # 获取图标文件路径列表
        from generator.core import logging as log
        try:
            self.icon_files = icon_utils.ensure_lucide_icons(
                self.config.get("lucide_icons", icon_utils.DEFAULT_LUCIDE_ICONS),
                download=self.config.get("lucide_download", False),
                allow_svg_fallback=True,
            )
            if self.icon_files:
                log.info(f"找到 {len(self.icon_files)} 个图标文件")
                test_icons = self.icon_files[:5]
                for icon in test_icons:
                    try:
                        bpy.data.images.load(icon, check_existing=True)
                        log.info(f"成功加载图像: {os.path.basename(icon)}")
                    except Exception as e:
                        log.warn(f"无法加载图像 {os.path.basename(icon)}: {e}")
            else:
                log.warn(f"未找到可用的图标文件，图标目录: {icon_utils.ASSETS_ROOT}")
        except Exception as e:
            log.warn(f"加载图标时出错: {e}")
            self.icon_files = []

        if not self.icon_files:
            log.info("未找到可用的图标文件，将使用几何图案作为备用")

    def create_cube_with_textures(self, cube_size=2.0, seed=None, texture_scale=None):
        """
        创建一个带有贴图的立方体

        Args:
            cube_size: 立方体的大小
            seed: 随机种子，用于确保可重现性
            texture_scale: 贴图缩放比例，若为None则使用self.cube_texture_scale

        Returns:
            cube: 创建的立方体对象
            face_assignments: 每个面的纹理分配信息
        """
        # 设置随机种子
        if seed is not None:
            random.seed(seed)

        # 使用默认贴图比例（如果未指定）
        if texture_scale is None:
            texture_scale = self.cube_texture_scale

        # 新实现：使用辅助函数创建立方体和材质，并完成面映射
        cube, mesh = self._create_cube_mesh(cube_size)
        face_assignments = self._assign_cube_face_materials(
            cube, texture_scale)
        self._map_faces_to_directions(mesh, face_assignments)
        return cube, face_assignments

    def _create_cube_mesh(self, cube_size=2.0):
        """创建立方体并设置UV与材质槽，仅负责几何和UV，不涉及材质内容。"""
        bpy.ops.mesh.primitive_cube_add(
            size=cube_size, enter_editmode=False, align='WORLD'
        )
        cube = bpy.context.active_object
        cube.name = "TexturedCube"

        mesh = cube.data

        # 确保有UV层
        if not mesh.uv_layers:
            mesh.uv_layers.new(name="UVMap")

        # 使用标准Cube Project生成UV
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.cube_project(
            cube_size=True, correct_aspect=True, clip_to_bounds=True
        )
        bpy.ops.object.mode_set(mode='OBJECT')

        # 确保材质槽足够
        while len(cube.material_slots) < 6:
            cube.data.materials.append(None)

        return cube, mesh

    def _assign_cube_face_materials(self, cube, texture_scale):
        """为立方体6个面创建材质并分配，返回face_assignments列表。"""
        face_assignments = []

        # 随机打乱材质颜色
        random_materials = self.face_materials.copy()
        random.shuffle(random_materials)

        # 决定是否使用图标或退化为纯色
        use_icons = False
        if hasattr(self, "icon_files") and len(self.icon_files) >= 6:
            try:
                test_icon = self.icon_files[0]
                if os.path.exists(test_icon):
                    bpy.data.images.load(test_icon, check_existing=True)
                    use_icons = True
                    print("将使用图标作为贴图")
            except Exception as e:
                print(f"测试图标加载失败，将使用纯色: {e}")
                use_icons = False

        if use_icons:
            selected_icons = self._select_cube_icons(self.icon_files, 6)
            for i, icon in enumerate(selected_icons):
                print(f"选择的图标 {i}: {os.path.basename(icon)}")
        else:
            print("未使用图标贴图，将使用纯色面")
            selected_icons = [None] * 6

        # 为每个面创建材质和纹理
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
                # 使用共享helper创建“白底 + 图标”材质
                face_name = self.face_index_to_name.get(i)
                material = icon_utils.create_icon_material_for_cube(
                    material_name,
                    icon_path,
                    color,
                    texture_scale=texture_scale,
                    face_name=face_name,
                )
            else:
                # 退化为纯色材质（不再生成几何图案）
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
        为单个立方体选择贴图图标，尽量避免同系列（如 arrow-left/right）出现在同一立方体上。

        规则：
        - 通过文件名的“第一个连字符前缀”自动分组，例如:
          arrow-left, arrow-right -> 系列前缀 arrow
          chevrons-left, chevrons-right -> 系列前缀 chevrons
        - 只有当前缀在图标集中出现次数>=2 时，才视为一个“系列”；否则按完整文件名当作独立系列。
        - 若可用图标不足以满足约束，会回退允许重复系列，以保证选足 count 个。
        """

        def series_key(path: str) -> str:
            name = os.path.splitext(os.path.basename(path))[0]
            parts = name.split("-", 1)
            return parts[0].lower() if len(parts) > 1 else name.lower()

        # 统计每个前缀出现次数，用于区分“系列”与单独图标
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
            # 仅当前缀对应多个图标时才启用“系列去重”，否则按独立图标处理
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
        """根据面中心位置识别front/back/top/bottom/left/right并设置材质索引。"""
        face_index_to_direction = {}

        # 计算每个面的中心点坐标
        face_centers = {}
        for poly in mesh.polygons:
            center = mathutils.Vector((0, 0, 0))
            for v_idx in poly.vertices:
                center += mesh.vertices[v_idx].co
            center /= len(poly.vertices)
            face_centers[poly.index] = center
            print(
                f"面 {poly.index}: 中心点 ({center.x:.4f}, {center.y:.4f}, {center.z:.4f})"
            )

        # 按X轴排序找出左面和右面
        x_sorted = sorted(face_centers.items(), key=lambda x: x[1].x)
        left_face = x_sorted[0][0]
        right_face = x_sorted[-1][0]
        face_index_to_direction[left_face] = "left"
        face_index_to_direction[right_face] = "right"
        print(
            f"识别面 {left_face} 为左面(left), 中心点X: {face_centers[left_face].x:.4f}"
        )
        print(
            f"识别面 {right_face} 为右面(right), 中心点X: {face_centers[right_face].x:.4f}"
        )

        # 按Y轴排序找出前面和后面
        y_sorted = sorted(face_centers.items(), key=lambda x: x[1].y)
        front_face = y_sorted[0][0]
        back_face = y_sorted[-1][0]
        face_index_to_direction[front_face] = "front"
        face_index_to_direction[back_face] = "back"
        print(
            f"识别面 {front_face} 为前面(front), 中心点Y: {face_centers[front_face].y:.4f}"
        )
        print(
            f"识别面 {back_face} 为后面(back), 中心点Y: {face_centers[back_face].y:.4f}"
        )

        # 按Z轴排序找出顶面和底面
        z_sorted = sorted(face_centers.items(), key=lambda x: x[1].z)
        bottom_face = z_sorted[0][0]
        top_face = z_sorted[-1][0]
        face_index_to_direction[bottom_face] = "bottom"
        face_index_to_direction[top_face] = "top"
        print(
            f"识别面 {bottom_face} 为底面(bottom), 中心点Z: {face_centers[bottom_face].z:.4f}"
        )
        print(
            f"识别面 {top_face} 为顶面(top), 中心点Z: {face_centers[top_face].z:.4f}"
        )

        identified_directions = set(face_index_to_direction.values())
        expected_directions = {"front", "back",
                               "top", "bottom", "right", "left"}

        if identified_directions != expected_directions:
            print("警告: 未能识别所有六个面! 识别到的面:", identified_directions)
            missing_directions = expected_directions - identified_directions
            if missing_directions:
                print("缺少的面:", missing_directions)

        face_name_to_index_map = {name: idx for idx,
                                  name in face_index_to_direction.items()}

        for face_name in expected_directions:
            if face_name not in face_name_to_index_map:
                print(f"错误: 未能找到面 {face_name}!")

        assigned_materials = set()
        for face_name, face_idx in face_name_to_index_map.items():
            material_idx = self.face_name_to_index[face_name]
            if material_idx < len(face_assignments):
                mesh.polygons[face_idx].material_index = material_idx
                assigned_materials.add(material_idx)
                print(
                    f"将材质 {material_idx} ({face_assignments[material_idx]['material']}) 分配给面 {face_name} (索引 {face_idx})"
                )

        # 若仍有面未分配材质（可能 left/back 未识别），按剩余材质补全
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
            print(f"警告: 只有 {len(assigned_materials)} 个材质被分配，应该是6个")

    def add_cube_icon_texture(self, material, icon_path, base_color, texture_scale=1.0, face_name=None):
        """
        为3D立方体添加图标贴图

        Args:
            material: 要添加纹理的材质
            icon_path: 图标文件路径
            base_color: 基础颜色
            texture_scale: 纹理缩放比例，值越大图标越小
            face_name: 面的名称，用于特殊处理某些面的贴图方向
        """
        # 为兼容旧调用保留该方法，但内部委托给共享helper构建完整材质。
        # 注意：该方法现在返回一个新的材质实例；调用方应优先改用
        # icon_utils.create_icon_material_for_cube。
        return icon_utils.create_icon_material_for_cube(
            material.name if material else "CubeIconMaterial",
            icon_path,
            base_color,
            texture_scale=texture_scale,
            face_name=face_name,
        )

    def add_unfolded_icon_texture(self, material, icon_path, base_color, texture_scale=1.0, rotation_angle=0):
        """
        为2D展开图添加图标贴图，并应用旋转角度。
        兼容旧接口的包装器，实际材质创建委托给共享helper。

        Args:
            material: 要添加纹理的材质（仅用于继承 name，如为空则使用默认名称）
            icon_path: 图标文件路径
            base_color: 基础颜色（目前主要用于回退时记录）
            texture_scale: 纹理缩放比例，值越大图标越小
            rotation_angle: 纹理旋转角度（度）
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
        创建立方体的展开图

        Args:
            cube: 原始立方体对象
            face_assignments: 面的贴图分配信息
            pattern_index: 使用的展开图模式索引，如果为None则随机选择
            texture_scale: 贴图缩放比例，若为None则使用self.unfolded_texture_scale

        Returns:
            unfolded_obj: 展开图对象
        """
        # 如果没有指定展开图模式，随机选择一个
        if pattern_index is None:
            pattern_index = random.randint(0, len(self.unfolding_patterns) - 1)

        # 使用默认贴图比例（如果未指定）
        if texture_scale is None:
            texture_scale = self.unfolded_texture_scale

        # 1) 仅负责根据 pattern/rotation 实例化展开平面
        unfolded_obj, planes = self._instantiate_unfolded_net(pattern_index)

        # 2) 为每个平面应用与立方体相匹配的材质
        self._apply_unfolded_materials(
            planes, face_assignments, pattern_index, texture_scale)

        return unfolded_obj

    def _instantiate_unfolded_net(self, pattern_index):
        """根据展开图模式创建平面，并应用旋转，只负责几何与父子关系。"""
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
        """为展开图平面应用与立方体对应面的材质/图标。"""
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
                # 如果没有找到纹理，复制原材质的基础色，保持旧行为
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
        根据难度级别创建干扰项

        Args:
            correct_cube: 正确答案的cube对象
            face_assignments: 面的贴图分配信息
            difficulty: 难度级别，可选值为 "easy", "medium", "hard"
            seed: 随机种子
            avoid_faces: 避免修改的面列表
            priority_faces: 优先修改的面列表（目前预留，未来策略可使用）

        Returns:
            distractor_cube: 干扰项cube对象
            changed_faces: 被修改的面列表
            change_type: 修改类型
        """

        if seed is not None:
            random.seed(seed)

        if avoid_faces is None:
            avoid_faces = []

        if priority_faces is None:
            priority_faces = []

        # 目前仅预留该变量，便于未来扩展更复杂的优先级策略
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
            # 默认按照中等难度处理
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
        """生成 easy 难度的干扰项，只做单面替换。"""
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
            # 不再生成几何图案，回退为纯色材质
            change_label = "solid_color"

        distractor_cube.material_slots[face_to_change].material = new_mat
        changed_faces = [face_to_change]
        change_type = f"easy_replaced_{change_label}"
        return distractor_cube, changed_faces, change_type

    def _make_medium_distractor(self, distractor_cube, face_assignments, visible_faces, avoid_faces, force_visible_face_change, seed):
        """生成 medium 难度的干扰项，支持多种策略组合。"""
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
        """生成 hard 难度的干扰项，使用多面交换和复杂旋转等策略。"""
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
        修改立方体纹理的方向

        Args:
            cube: 要修改的立方体对象
            face_assignments: 面的贴图分配信息
            seed: 随机种子
            texture_scale: 贴图缩放比例
            priority_faces: 优先修改的面列表
            flip_type: 指定翻转类型，可以是 "flip"（上下左右翻转）或 "rotate"（旋转）
            rotation_angle: 指定旋转角度
            subtle: 是否进行细微调整

        Returns:
            changed_faces: 被修改的面列表
            change_type: 修改类型
        """
        # 设置随机种子
        if seed is not None:
            random.seed(seed)

        # 使用默认贴图比例（如果未指定）
        if texture_scale is None:
            texture_scale = self.cube_texture_scale

        # 初始化已修改的面列表和修改类型
        changed_faces = []
        change_type = ""

        # 确定要修改的面
        if priority_faces:
            # 使用提供的优先面
            candidate_faces = priority_faces
        else:
            # 随机选择一个面进行修改
            candidate_faces = list(range(6))

        # 随机选择一个面
        face_idx = random.choice(candidate_faces)

        # 获取面的材质
        material = cube.material_slots[face_idx].material
        if not material:
            # 如果没有材质，跳过这个面
            return [], "no_material_changed"

        # 获取面的名称
        face_name = self.face_index_to_name.get(face_idx, "unknown")

        # 确保材质使用节点
        if not material.use_nodes:
            material.use_nodes = True

        # 获取当前材质的旋转信息（如果有）
        current_rotation = self.get_material_rotation(material)

        # 根据flip_type参数和subtle参数决定修改类型
        if subtle:
            # 细微调整：小角度旋转或微弱翻转
            if flip_type == "flip":
                # 细微翻转：使用微小的缩放或偏移
                change_type = "subtle_flip"
                # 实现：简单示例 - 轻微缩放
                for node in material.node_tree.nodes:
                    if node.type == 'MAPPING':
                        scale_factor = random.uniform(0.95, 1.05)
                        node.inputs['Scale'].default_value[0] *= scale_factor
                        node.inputs['Scale'].default_value[1] *= scale_factor
            else:  # 默认为旋转或随机选择
                # 细微旋转：使用小角度旋转
                change_type = "subtle_rotation"
                small_angle = random.choice([-15, 15, 30, -30])
                self.rotate_material_texture(material, small_angle)
        else:
            # 标准调整
            if flip_type == "flip":
                # 执行翻转（上下或左右翻转）
                flip_type = random.choice(["horizontal", "vertical"])
                if flip_type == "horizontal":
                    # 左右翻转
                    change_type = "horizontal_flip"
                    # 查找映射节点并翻转X轴
                    for node in material.node_tree.nodes:
                        if node.type == 'MAPPING':
                            node.inputs['Scale'].default_value[0] *= -1
                else:
                    # 上下翻转
                    change_type = "vertical_flip"
                    # 查找映射节点并翻转Y轴
                    for node in material.node_tree.nodes:
                        if node.type == 'MAPPING':
                            node.inputs['Scale'].default_value[1] *= -1
            elif flip_type == "rotate":
                # 执行旋转（90°、180°或270°）
                if rotation_angle is not None:
                    angle = rotation_angle
                else:
                    angle = random.choice([90, 180, 270])
                change_type = f"rotation_{angle}"
                self.rotate_material_texture(material, angle)
            else:
                # 默认：随机选择翻转或旋转
                modification = random.choice(["flip", "rotate"])
                if modification == "flip":
                    # 执行翻转
                    flip_type = random.choice(["horizontal", "vertical"])
                    if flip_type == "horizontal":
                        # 左右翻转
                        change_type = "horizontal_flip"
                        # 查找映射节点并翻转X轴
                        for node in material.node_tree.nodes:
                            if node.type == 'MAPPING':
                                node.inputs['Scale'].default_value[0] *= -1
                    else:
                        # 上下翻转
                        change_type = "vertical_flip"
                        # 查找映射节点并翻转Y轴
                        for node in material.node_tree.nodes:
                            if node.type == 'MAPPING':
                                node.inputs['Scale'].default_value[1] *= -1
                else:
                    # 执行旋转
                    angle = random.choice([90, 180, 270])
                    change_type = f"rotation_{angle}"
                    self.rotate_material_texture(material, angle)

        # 记录修改的面
        changed_faces.append(face_idx)

        # 返回修改的面列表和修改类型
        return changed_faces, change_type

    def duplicate_cube(self, original_cube):
        """复制立方体对象"""
        try:
            # 确保没有选中的对象
            bpy.ops.object.select_all(action='DESELECT')

            # 选中原始立方体
            original_cube.select_set(True)
            bpy.context.view_layer.objects.active = original_cube
            # 复制对象
            bpy.ops.object.duplicate()

            # 获取新创建的对象
            distractor_cube = bpy.context.active_object

            # 如果没有获取到复制的对象，尝试其他方法
            if distractor_cube is None or distractor_cube == original_cube:
                selected_objects = bpy.context.selected_objects
                for obj in selected_objects:
                    if obj != original_cube:
                        distractor_cube = obj
                        break

            # 如果仍然没有找到，创建一个新的立方体
            if distractor_cube is None or distractor_cube == original_cube:
                print("警告: 无法通过复制获取对象，创建新立方体作为替代")
                bpy.ops.mesh.primitive_cube_add(
                    size=2.0, enter_editmode=False, align='WORLD')
                distractor_cube = bpy.context.active_object

            # 设置名称
            if distractor_cube:
                distractor_cube.name = "DistractorCube"

            return distractor_cube

        except Exception as e:
            print(f"复制立方体时出错: {e}")
            return None

    def modify_cube_textures(self, cube, face_assignments, faces_to_change, seed=None, texture_scale=None):
        """
        修改立方体的贴图

        Args:
            cube: 要修改的立方体对象
            face_assignments: 面的贴图分配信息
            faces_to_change: 要修改的面数量或面索引列表
            seed: 随机种子
            texture_scale: 贴图缩放比例

        Returns:
            changed_faces: 被改变的面的索引列表
            change_type: 变化类型描述
        """
        # 使用默认贴图比例（如果未指定）
        if texture_scale is None:
            texture_scale = self.cube_texture_scale

        # 首先复制所有材质
        try:
            for i in range(len(face_assignments)):
                if i < len(cube.material_slots):
                    original_material = face_assignments[i]['material_obj']
                    cube.material_slots[i].material = original_material
        except Exception as e:
            print(f"复制材质时出错: {e}")

        # 确定要修改的面
        face_indices = list(range(6))
        if isinstance(faces_to_change, list):
            # 如果传入的是面索引列表，直接使用
            faces_to_modify = faces_to_change
        else:
            # 如果传入的是数量，随机选择
            num_faces = min(faces_to_change, 6)
            random.shuffle(face_indices)
            faces_to_modify = face_indices[:num_faces]

        # 记录原始分配，方便日志记录
        original_assignments = {}
        for i, assignment in enumerate(face_assignments):
            if 'material' in assignment:
                original_assignments[i] = assignment['material']

        # record new material names for change_type
        change_descriptors = []

        # 变更选中面的材质
        for face_idx in faces_to_modify:
            try:
                # 确保face_idx在范围内
                if face_idx >= len(cube.material_slots):
                    print(f"警告: 索引 {face_idx} 超出材质槽范围，跳过")
                    continue

                # 获取原始材质
                original_material = face_assignments[face_idx].get('material')

                # 找出未使用的材质
                available_materials = [m for m in self.face_materials
                                       if m['name'] != original_material]

                # 随机选择新材质
                if available_materials:
                    new_material_data = random.choice(available_materials)
                    # record new material for change_type signature
                    change_descriptors.append(new_material_data['name'])

                    # 创建新材质
                    material_name = f"DistractorMaterial_{new_material_data['name']}"
                    material = bpy.data.materials.new(name=material_name)
                    material.use_nodes = True

                    # 设置材质基础颜色
                    color = new_material_data['color']

                    # 使用节点系统设置材质
                    nodes = material.node_tree.nodes
                    links = material.node_tree.links

                    # 清除默认节点
                    for node in nodes:
                        nodes.remove(node)

                    # 创建基本节点
                    output = nodes.new('ShaderNodeOutputMaterial')
                    output.location = (300, 0)

                    principled = nodes.new('ShaderNodeBsdfPrincipled')
                    principled.location = (0, 0)
                    principled.inputs['Base Color'].default_value = color

                    links.new(
                        principled.outputs['BSDF'], output.inputs['Surface'])

                    # 添加贴图
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
                        # 不再生成几何图案，保持原基础颜色
                        pass

                    # 添加材质到立方体
                    cube.material_slots[face_idx].material = material

            except Exception as e:
                print(f"更改材质 {face_idx} 时出错: {e}")

        # 返回带有新材质名称的 change_type 以保证唯一性
        if change_descriptors:
            change_type_str = f"texture_replaced_{'_'.join(change_descriptors)}"
        else:
            change_type_str = "texture_replaced"
        return faces_to_modify, change_type_str

    def get_material_rotation(self, material):
        """获取材质中的纹理旋转角度（Z轴）"""
        if not material or not material.use_nodes:
            return None

        for node in material.node_tree.nodes:
            if node.type == 'MAPPING':
                # 尝试获取Z轴旋转（第三个元素）
                try:
                    return node.inputs['Rotation'].default_value[2]
                except (IndexError, KeyError, AttributeError):
                    pass
        return None

    def copy_material_nodes(self, source_material, target_material):
        """复制材质节点设置"""
        if not source_material.use_nodes or not target_material.use_nodes:
            return

        # 清除目标材质的所有节点
        for node in target_material.node_tree.nodes:
            target_material.node_tree.nodes.remove(node)

        # 基础色和不透明度
        color = (1, 1, 1, 1)

        # 寻找源材质中的颜色和纹理
        source_nodes = source_material.node_tree.nodes
        source_links = source_material.node_tree.links

        # 创建基本节点
        output = target_material.node_tree.nodes.new(
            'ShaderNodeOutputMaterial')
        output.location = (300, 0)

        principled = target_material.node_tree.nodes.new(
            'ShaderNodeBsdfPrincipled')
        principled.location = (0, 0)

        # 连接BSDF到输出
        target_material.node_tree.links.new(
            principled.outputs['BSDF'], output.inputs['Surface'])

        # 查找纹理和颜色
        texture_image = None
        for node in source_nodes:
            if node.type == 'BSDF_PRINCIPLED':
                # 获取颜色
                if node.inputs['Base Color'].is_linked:
                    color = (1, 1, 1, 1)  # 有连接到颜色，使用白色作为基础
                else:
                    color = node.inputs['Base Color'].default_value

            elif node.type == 'TEX_IMAGE' and node.image:
                # 找到纹理
                texture_image = node.image

        # 设置基础色
        principled.inputs['Base Color'].default_value = color

        # 如果找到纹理，添加到新材质
        if texture_image:
            # 创建纹理节点
            tex_node = target_material.node_tree.nodes.new(
                'ShaderNodeTexImage')
            tex_node.location = (-300, 0)
            tex_node.image = texture_image

            # 添加坐标和映射节点
            coord_node = target_material.node_tree.nodes.new(
                'ShaderNodeTexCoord')
            coord_node.location = (-600, 0)

            mapping_node = target_material.node_tree.nodes.new(
                'ShaderNodeMapping')
            mapping_node.location = (-450, 0)

            # 连接节点
            target_material.node_tree.links.new(
                coord_node.outputs['UV'], mapping_node.inputs['Vector'])
            target_material.node_tree.links.new(
                mapping_node.outputs['Vector'], tex_node.inputs['Vector'])
            target_material.node_tree.links.new(
                tex_node.outputs['Color'], principled.inputs['Base Color'])

    def rotate_material_texture(self, material, angle_degrees):
        """旋转材质中的纹理"""
        if not material.use_nodes:
            return

        nodes = material.node_tree.nodes

        # 寻找映射节点
        mapping_node = None
        for node in nodes:
            if node.type == 'MAPPING':
                mapping_node = node
                break

        # 如果没有找到映射节点，尝试创建一个
        if not mapping_node:
            # 查找纹理节点和坐标节点
            tex_node = None
            coord_node = None

            for node in nodes:
                if node.type == 'TEX_IMAGE':
                    tex_node = node
                elif node.type == 'TEX_COORD':
                    coord_node = node

            # 如果找到纹理节点但没有坐标节点，创建一个
            if tex_node and not coord_node:
                coord_node = nodes.new('ShaderNodeTexCoord')
                coord_node.location = (
                    tex_node.location.x - 300, tex_node.location.y)

            # 如果有纹理节点和坐标节点，创建映射节点
            if tex_node and coord_node:
                # 断开现有连接
                for link in material.node_tree.links:
                    if link.to_node == tex_node and link.to_socket.name == 'Vector':
                        material.node_tree.links.remove(link)

                # 创建映射节点
                mapping_node = nodes.new('ShaderNodeMapping')
                mapping_node.location = (
                    coord_node.location.x + 150, coord_node.location.y)

                # 连接节点
                material.node_tree.links.new(
                    coord_node.outputs['UV'], mapping_node.inputs['Vector'])
                material.node_tree.links.new(
                    mapping_node.outputs['Vector'], tex_node.inputs['Vector'])

        # 应用旋转
        if mapping_node:
            # 转换为弧度
            angle_rad = math.radians(angle_degrees)
            # 设置旋转 - 只旋转Z轴
            mapping_node.inputs['Rotation'].default_value = (
                0.0, 0.0, angle_rad)

    def get_visible_faces(self, view):
        """
        根据相机视角确定可见的立方体面

        Args:
            view: 视角信息，包含名称

        Returns:
            visible_faces: 可见面的索引列表
        """
        # 不同视角可见的面
        view_to_faces = {
            "iso_front_top_right": [0, 1, 4],  # 前面、顶面、右面
            "iso_back_top_right": [2, 1, 4],   # 后面、顶面、右面
            "iso_front_top_left": [0, 1, 5],   # 前面、顶面、左面
            "iso_back_top_left": [2, 1, 5],    # 后面、顶面、左面
            "iso_front_bottom_right": [0, 3, 4],  # 前面、底面、右面
            "iso_back_bottom_right": [2, 3, 4],  # 后面、底面、右面
            "iso_front_bottom_left": [0, 3, 5],  # 前面、底面、左面
            "iso_back_bottom_left": [2, 3, 5],   # 后面、底面、左面
            "front": [0],                      # 前面
            "back": [2],                       # 后面
            "left": [5],                       # 左面
            "right": [4],                      # 右面
            "top": [1],                        # 顶面
            "bottom": [3]                      # 底面
        }

        # 获取视角名称
        view_name = view.get("name", "") if isinstance(view, dict) else view

        # 返回对应的可见面
        return view_to_faces.get(view_name, [0, 1, 4])  # 默认返回前顶右三个面

    def generate_question(self, q_id):
        """生成一个盒子折叠题目"""
        print(f"Generating box folding question {q_id}...")

        # 更彻底地清除场景中的现有物体
        self.clear_question_objects()

        # 创建随机种子
        question_seed = hash(f"box_folding_{q_id}") % 10000
        random.seed(question_seed)

        # 当前难度
        difficulty = self.config.get("difficulty", "medium")

        # 创建立方体与面分配（用于展开图与元数据）
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

        # 清理场景，删除所有对象
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
        """创建展开图并渲染题目图像（Q 图）。"""
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
            f"展开图边界: 宽度={width:.2f}, 高度={height:.2f}, 中心=({center_x:.2f}, {center_y:.2f})"
        )
        print(f"设置相机正交视场大小: {ortho_scale:.2f}")

        if cube:
            cube.hide_render = True
        if unfolded_cube:
            unfolded_cube.hide_render = False

        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)
        return question_img

    def _render_correct_answer(self, q_id, question_seed, original_materials):
        """渲染立方体正确答案视图，并返回视角信息和选项描述。"""
        # 清除场景，为渲染正确答案做准备
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
        """生成干扰项选项列表。"""
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
            print(f"警告: 无法创建正确答案立方体的参考副本: {e}")

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
                print(f"警告: 创建干扰项 {i+1} 的原始立方体时出错: {e}")
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
                            f"警告: 干扰项 {i+1} 尝试 {attempts}: 生成的干扰立方体无效"
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
                            reason.append("与已有干扰项重复")
                        if not has_visible_difference:
                            reason.append("在可见面上没有明显差异")
                        print(
                            f"干扰项 {i+1} 尝试 {attempts}: {', '.join(reason)}，重试..."
                        )

                        if attempts >= max_attempts // 2 and not valid_visual_difference:
                            if distractor_signature not in used_change_types:
                                print(
                                    f"警告: 干扰项 {i+1} 在可见面上差异不明显，但已尝试多次，接受当前结果"
                                )
                                unique_distractor = True
                                valid_visual_difference = True
                                used_change_types.append(distractor_signature)
                                used_face_changes.extend(
                                    [f for f in changed_faces if f in visible_faces]
                                )
                except Exception as e:
                    print(f"创建干扰项时出错 (尝试 {attempts}): {e}")
                    attempts += 1
                    import traceback

                    traceback.print_exc()
                    continue

            if not unique_distractor or not valid_visual_difference:
                print(
                    f"警告: 无法为干扰项 {i+1} 创建有效的变化，使用最后一次尝试的结果"
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
                print(f"错误: 干扰项 {i+1} 无效，跳过")
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
                print(f"渲染干扰项 {i+1} 时出错: {e}")
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
        """组装并保存题目元数据，返回元数据文件路径。"""
        metadata = {
            "question_id": q_id,
            "question_type": "box_folding",
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
        """生成完整的盒子折叠数据集"""
        print(
            f"Generating box folding dataset with {self.config['num_questions']} questions...")

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)

        # 设置基本的场景
        self.setup_scene()

        # 生成每个问题
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

        # 创建数据集摘要文件
        summary_file = self.create_summary_file(meta_files)
        print(
            f"Box folding dataset generation complete, saved to {self.output_dir}")

        # 返回生成的元数据文件列表和摘要文件路径
        return meta_files, summary_file

    def clear_scene_except(self, objects_to_keep):
        """清除场景中除指定对象外的所有物体"""
        # 过滤掉None对象
        objects_to_keep = [obj for obj in objects_to_keep if obj is not None]

        # 确保保留的对象仍有效（未被删除）
        valid_objects_to_keep = []
        for obj in objects_to_keep:
            try:
                # 测试对象是否有效
                _ = obj.name
                valid_objects_to_keep.append(obj)
            except ReferenceError:
                print(f"警告: 要保留的对象已被删除")
            except Exception as e:
                print(f"检查对象时出错: {e}")

        objects_to_keep = valid_objects_to_keep

        try:
            # 删除不在保留列表中的对象
            objects_to_delete = []
            for obj in list(bpy.context.scene.objects):
                if obj not in objects_to_keep and obj.type not in {'CAMERA', 'LIGHT'}:
                    objects_to_delete.append(obj)

            # 单独循环删除对象，防止在迭代过程中修改集合
            for obj in objects_to_delete:
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception as e:
                    print(
                        f"删除对象 {obj.name if hasattr(obj, 'name') else 'unknown'} 时出错: {e}")

            # 更新场景
            bpy.context.view_layer.update()
        except Exception as e:
            print(f"清理场景时出错: {e}")
            import traceback
            traceback.print_exc()

    def get_less_visible_faces(self, view):
        """
        根据相机视角返回不可见的立方体面索引列表
        """
        # 获取可见面列表
        visible = self.get_visible_faces(view)
        # 所有面索引
        all_faces = list(range(6))
        # 返回不可见的面
        return [f for f in all_faces if f not in visible]

    def swap_cube_textures(self, cube, faces_to_swap):
        """
        交换立方体面之间的贴图，不从贴图库中替换

        Args:
            cube: 要修改的立方体对象
            faces_to_swap: 要交换的面对列表，如[(0,1), (2,3)]表示交换0和1面、2和3面的贴图

        Returns:
            changed_faces: 被改变的面的索引列表
            change_type: 变化类型描述
        """
        if not faces_to_swap or len(cube.material_slots) < 2:
            return [], "no_swap"

        # 记录改变的面
        changed_faces = []

        # 执行交换
        for face1, face2 in faces_to_swap:
            try:
                # 确保索引在范围内
                if face1 >= len(cube.material_slots) or face2 >= len(cube.material_slots):
                    print(f"警告: 面索引 {face1} 或 {face2} 超出材质槽范围，跳过")
                    continue

                # 获取面的材质
                material1 = cube.material_slots[face1].material
                material2 = cube.material_slots[face2].material

                # 交换材质
                cube.material_slots[face1].material = material2
                cube.material_slots[face2].material = material1

                # 记录已改变的面
                changed_faces.extend([face1, face2])

                print(f"交换了面 {face1} 和面 {face2} 的贴图")
            except Exception as e:
                print(f"交换材质时出错: {e}")

        return changed_faces, f"swapped_{len(changed_faces)//2}_pairs"

    def validate_visual_difference(self, distractor_cube, correct_cube, visible_faces):
        """
        验证干扰项与正确答案在可见面上是否有足够的视觉差异

        Args:
            distractor_cube: 干扰项立方体
            correct_cube: 正确答案立方体
            visible_faces: 当前视角下可见的面的索引列表

        Returns:
            bool: 是否有足够的视觉差异
            list: 有视觉差异的面的索引列表
        """
        # 检查对象是否有效
        try:
            # 尝试访问一个属性来检查对象是否有效
            if not distractor_cube or not correct_cube:
                return False, []

            # 检查对象是否已被删除
            if not hasattr(distractor_cube, 'material_slots') or not hasattr(correct_cube, 'material_slots'):
                return False, []

            # 检查material_slots是否可访问
            _ = len(distractor_cube.material_slots)
            _ = len(correct_cube.material_slots)
        except ReferenceError:
            # 对象已被删除，返回安全值
            print("警告: 检测到对象已被删除，跳过视觉差异验证")
            return False, []
        except Exception as e:
            # 其他错误，记录并返回安全值
            print(f"验证视觉差异时出错: {e}")
            return False, []

        # 检查可见面中是否至少有一个面的材质不同
        different_faces = []

        for face_idx in visible_faces:
            try:
                # 检查材质槽是否存在
                if (face_idx >= len(distractor_cube.material_slots) or
                        face_idx >= len(correct_cube.material_slots)):
                    continue

                # 获取两个立方体对应面的材质
                dist_mat = distractor_cube.material_slots[face_idx].material
                corr_mat = correct_cube.material_slots[face_idx].material

                # 如果材质对象不同，认为有视觉差异
                if dist_mat != corr_mat:
                    different_faces.append(face_idx)
                    continue

                # 即使材质对象相同，检查节点树是否有差异（例如旋转、翻转）
                if dist_mat and corr_mat and dist_mat.use_nodes and corr_mat.use_nodes:
                    # 检查纹理旋转
                    dist_rotation = self.get_material_rotation(dist_mat)
                    corr_rotation = self.get_material_rotation(corr_mat)

                    if dist_rotation is not None and corr_rotation is not None:
                        # 如果旋转角度不同，认为有视觉差异
                        if abs(dist_rotation - corr_rotation) > 0.01:  # 允许一点点浮点误差
                            different_faces.append(face_idx)
                            continue

                    # 检查映射节点的缩放（用于翻转检测）
                    has_flip_difference = False
                    for dist_node in dist_mat.node_tree.nodes:
                        if dist_node.type == 'MAPPING':
                            for corr_node in corr_mat.node_tree.nodes:
                                if corr_node.type == 'MAPPING':
                                    # 检查X/Y缩放是否有翻转（正负号不同）
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
                # 对象在迭代过程中可能被删除
                print(f"警告: 检查面 {face_idx} 时对象已被删除")
                continue
            except Exception as e:
                print(f"检查面 {face_idx} 时出错: {e}")
                continue

        # 如果有可见面存在差异，返回True
        return len(different_faces) > 0, different_faces

    def setup_scene(self):
        """设置渲染场景，继承父类设置并添加特定配置"""
        # 首先调用父类的setup_scene方法设置基本场景
        super().setup_scene()

        # 可以在这里添加box_folding特有的场景设置
        print("Box folding场景设置完成")


# Backward-compatible alias
Folding3DGenerator = BoxFoldingGenerator
