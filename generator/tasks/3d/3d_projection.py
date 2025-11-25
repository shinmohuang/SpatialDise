#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3D projection/view matching generator."""

import os
import json
import random
import math
from datetime import datetime

import bpy
import mathutils

from SpatialDise.generator.core.base_generator import BaseGenerator
from SpatialDise.generator.core import projection as projection_utils


class ViewMatchingGenerator(BaseGenerator):
    """3D View Matching Generator"""

    def __init__(self, output_dir=None, config=None):
        """Initialize the generator with configuration parameters"""
        # 更改默认目录名
        if output_dir is None:
            output_dir = "blender_dataset/view_matching"

        super().__init__("view_matching", output_dir, config)

        # 根据难度标签调整方块数量范围和干扰项难度，
        # 以拉开 easy / medium / hard 之间的题目复杂度。
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

        # 定义多种正交视图
        self.orthographic_views = [
            {"name": "top_view", "pos": (0, 0, 10.0), "look_at": (0, 0, 0)},
            {"name": "front_view", "pos": (0, -10.0, 0), "look_at": (0, 0, 0)},
            {"name": "right_view", "pos": (10.0, 0, 0), "look_at": (0, 0, 0)},
            {"name": "back_view", "pos": (0, 10.0, 0), "look_at": (0, 0, 0)},
            {"name": "left_view", "pos": (-10.0, 0, 0), "look_at": (0, 0, 0)},
            # 不包含底视图 bottom_view
        ]

        # 定义对向视图映射关系
        self.opposite_views = {
            "front_view": "back_view",
            "back_view": "front_view",
            "left_view": "right_view",
            "right_view": "left_view",
            "top_view": None,  # top_view没有明确的对向视图
        }

    def get_opposite_view(self, view_name):
        """
        获取给定视图的对向视图名称

        Args:
            view_name: 视图名称

        Returns:
            对向视图名称，如果不存在则返回None
        """
        return self.opposite_views.get(view_name)

    def get_projected_positions(self, blocks, view_name):
        """
        根据视图名称获取块的投影位置集合

        Args:
            blocks: 块对象列表
            view_name: 视图名称

        Returns:
            投影位置的集合
        """
        return projection_utils.project_block_positions(blocks, view_name)

    def is_view_different(self, original_positions, distractor_blocks, view_name, min_difference=0.3):
        """
        检查两个形状在给定视图下的投影是否有明显区别

        Args:
            original_positions: 原始形状在指定视图下的投影位置集合
            distractor_blocks: 干扰项形状的方块列表
            view_name: 视图名称
            min_difference: 最小差异阈值，默认0.3

        Returns:
            Boolean: 如果两个形状明显不同返回True，否则返回False
        """
        distractor_positions = self.get_projected_positions(
            distractor_blocks, view_name)

        diff_coords = original_positions.symmetric_difference(
            distractor_positions)
        total_coords = original_positions.union(distractor_positions)

        if not total_coords:
            return False  # 避免除以零

        difference_ratio = len(diff_coords) / len(total_coords)
        print(f"视图 {view_name} 的投影差异率: {difference_ratio:.2f}")
        return difference_ratio >= min_difference

    def create_view_indicator(
        self,
        view_name,
        scene_center=(0, 0, 0),
        scale=0.7,
        color=(0, 0.5, 1, 1),
        distance=None,
    ):
        """创建视图方向指示器（单个锥体）"""
        indicator = bpy.data.objects.new("ViewIndicator", None)
        bpy.context.scene.collection.objects.link(indicator)

        cx, cy, cz = scene_center
        # 从中心到指示器的距离；如果未指定，则使用默认值
        if distance is None:
            distance = 2.0  # 略大于默认网格边界

        if "top" in view_name:
            cone_pos = (cx, cy, cz + distance)
            cone_dir = (0, 0, 1)
        elif "front" in view_name:
            cone_pos = (cx, cy - distance, cz)
            cone_dir = (0, -1, 0)
        elif "back" in view_name:
            cone_pos = (cx, cy + distance, cz)
            cone_dir = (0, 1, 0)
        elif "right" in view_name:
            cone_pos = (cx + distance, cy, cz)
            cone_dir = (1, 0, 0)
        elif "left" in view_name:
            cone_pos = (cx - distance, cy, cz)
            cone_dir = (-1, 0, 0)
        else:
            cone_pos = (cx, cy, cz + distance)
            cone_dir = (0, 0, 1)

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
            principled.inputs["Base Color"].default_value = color
            principled.inputs["Specular"].default_value = 0.2
            principled.inputs["Metallic"].default_value = 0.8
            principled.inputs["Emission"].default_value = (
                color[0], color[1], color[2], 1.0)
            principled.inputs["Emission Strength"].default_value = 1.0

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
        return indicator

    def generate_question(self, q_id):
        """Generate a single 3D view matching question"""
        print(f"Generating question {q_id}...")

        # Clear any existing objects
        self.clear_question_objects()

        # Create seed based on question ID and difficulty for reproducibility.
        # 不同难度下同一题号会得到不同的形状与视图组合。
        difficulty_label = self.config.get("difficulty", "easy")
        question_seed = hash((q_id, difficulty_label)) % 100000

        # Create the 3D shape
        original_obj = self.create_combination_shape(
            use_rectangular=self.config.get('use_rectangular_prisms'),
            rect_prob=self.config.get('rectangular_prism_prob'),
            seed=question_seed
        )

        # Ensure base shape is a single connected component，避免悬浮方块
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
            print("警告: 没有生成任何方块!")
            return None

        # 预先计算每个正交视图下的投影，用于选择具有唯一截面的正确答案视图
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

        # 使用find_best_view找到最佳视角，启用自动生成视角功能
        question_view, visible_count = self.find_best_view(
            self.iso_views, cubes, cam,
            prefer_isometric=True, iso_bonus=2.0,
            auto_generate=True, num_candidates=8)
        print(
            f"Selected view: {question_view['name']} with {visible_count} visible blocks")

        # 设置问题视图为选出的最佳视图
        self.set_camera_to_view(cam, question_view, add_randomness=True)

        # 缩小视角来放大物体，同时确保物体在视角中心
        # 计算形状的几何中心
        shape_center = self.get_shape_center(cubes)

        # 调整相机的look_at点指向形状中心，确保物体居中
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam.rotation_euler = rot_quat.to_euler()

        # 缩小ortho_scale来放大question图片中的物体
        original_ortho_scale = cam.data.ortho_scale
        cam.data.ortho_scale = 8.0  # 缩小视角来放大物体显示

        # 更新场景以应用相机设置
        bpy.context.view_layer.update()

        question_location = cam.location.copy()
        question_rotation = cam.rotation_euler.copy()

        # 随机选择一个正交视图作为正确答案，优先选取截面模式在所有视图中唯一的视图
        candidate_views = unique_views if unique_views else self.orthographic_views
        correct_view = random.choice(candidate_views)

        # 创建视图指示器（在渲染问题图像前）
        # 使用形状的中心位置和整体尺寸，确保指示器既不被遮挡，也尽量处于相机视野内
        shape_center = self.get_shape_center(cubes)
        shape_extent = self.get_shape_extent(cubes)
        ex, ey, ez = shape_extent if shape_extent else (1.0, 1.0, 1.0)

        # 基于组合体整体尺寸预估需要的视场大小
        max_extent_xyz = max(ex, ey, ez)
        base_radius = max_extent_xyz / 2.0

        # 在设置 indicator 之前，先确保正交相机的视场足够容纳组合体本身
        # 和之后要添加的视图指示器。
        safety_margin = 1.2
        target_scale = max(8.0, (max_extent_xyz + safety_margin * 2.0))
        try:
            cam.data.ortho_scale = max(cam.data.ortho_scale, target_scale)
            # 将相机视场整体外扩 20%，为指示器和组合体预留更多边缘空间
            cam.data.ortho_scale *= 1.2
        except Exception:
            pass

        # 初始创建 indicator（其朝向仍由 view_name 决定），
        # 仅沿对应视图方向在包围盒外推一点距离。
        indicator_distance = base_radius + 0.3
        view_indicator = self.create_view_indicator(
            correct_view["name"],
            scene_center=shape_center,
            distance=indicator_distance,
        )

        # Render question image (3D view)
        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)

        # 移除视图指示器（渲染后立即删除，以免影响后续渲染）
        if view_indicator:
            # 保存所有子对象的列表副本，避免在遍历时修改列表
            children = list(view_indicator.children)
            # 删除指示器的所有子物体
            for child in children:
                bpy.data.objects.remove(child, do_unlink=True)
            # 删除指示器本身
            bpy.data.objects.remove(view_indicator, do_unlink=True)

            # 清理所有未使用的材质
            for material in bpy.data.materials[:]:  # 使用列表副本避免修改迭代中的集合
                if material.name.startswith("ArrowMaterial") and material.users == 0:
                    bpy.data.materials.remove(material)

        # Prepare options list
        options = []
        distractor_positions_list = []  # 存储所有干扰项的位置信息（用于差异度计算）
        used_view_names = set()  # 记录已使用的视图名称，避免重复

        used_view_names.add(correct_view["name"])

        # 计算原始形状在正确答案视图中的投影位置
        original_projected_positions = self.get_projected_positions(
            cubes, correct_view["name"])
        # 记录题内已使用的截面模式（投影集合），用于保证选项之间不重复
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

        # 获取剩余可用的正交视图（除了正确答案使用的视图）
        remaining_views = [view for view in self.orthographic_views
                           if view["name"] != correct_view["name"]]

        # 获取正确答案的对向视图名称
        opposite_view_name = self.get_opposite_view(correct_view["name"])

        # 从可用视图中过滤掉对向视图
        if opposite_view_name:
            remaining_views = [view for view in remaining_views
                               if view["name"] != opposite_view_name]
            print(f"已排除对向视图 {opposite_view_name} 作为干扰项")

        # Generate distractors
        for i in range(self.config['num_distractors']):
            # Clear existing objects
            self.clear_question_objects()

            # 决定干扰项的类型 - 70%的概率使用原始形状的不同视图，30%的概率使用修改后的形状
            use_original_with_different_view = random.random() < 0.3

            # 跟踪已使用的视图和种子，避免重复
            used_distractor_views = set()
            used_distractor_seeds = set()

            # 从已生成的干扰项中收集已使用的视图和种子
            for option in options:
                if option.get("label", "").startswith("distractor_"):
                    used_distractor_views.add(option.get("view_name", ""))
                    used_distractor_seeds.add(option.get("seed", None))

            if use_original_with_different_view and remaining_views:
                # ===== 干扰项类型1: 使用原始形状但选择不同的视图 =====
                # 获取可用视图 - 排除已被其他干扰项使用的视图
                available_views = [view for view in remaining_views
                                   if view["name"] not in used_distractor_views]

                # 如果没有可用视图，切换到策略2
                if not available_views:
                    use_original_with_different_view = False
                    print(f"没有可用视图，切换到修改形状策略")
                else:
                    # 从剩余视图中随机选择一个（已排除正确答案的对向视图和已使用的视图）
                    distractor_view = random.choice(available_views)

                    # 重新创建原始形状
                    distractor_obj = self.create_combination_shape(
                        seed=question_seed)
                    distractor_blocks = [
                        obj for obj in distractor_obj.children]

                    # 设置相机到所选视图
                    self.set_camera_to_view(
                        cam, distractor_view, add_randomness=False)

                    # 为原始形状的不同视图干扰项保持正交视图特性，不调整相机朝向

                    # 检查这个视图的投影是否与正确答案有足够差异，
                    # 且不会与题内已有选项的截面模式重复
                    distractor_positions = self.get_projected_positions(
                        distractor_blocks, distractor_view["name"])
                    proj_key = frozenset(distractor_positions)

                    # 如果与正确答案或已有选项的投影差异不够，或模式完全重复，
                    # 则尝试使用修改形状策略。
                    if (proj_key in used_projection_sets) or not self.is_view_different(
                            original_projected_positions, distractor_blocks, distractor_view["name"]):
                        # 如果差异不够，切换到修改形状的方法
                        use_original_with_different_view = False
                        print(
                            f"视图 {distractor_view['name']} 的投影差异不足，切换到修改形状策略")
                    else:
                        # 记录干扰项使用的视图与截面模式
                        used_view_name = distractor_view["name"]
                        used_projection_sets.add(proj_key)

            # 如果不使用原始形状的不同视图，或者没有剩余视图可用，则使用修改后的形状
            if not use_original_with_different_view:
                # ===== 干扰项类型2: 使用修改后的形状 =====
                # 确保干扰项从指定视角看与原始形状有明显区别
                max_attempts = 15  # 增加尝试次数以提高成功率
                is_different = False
                attempt = 0

                while not is_different and attempt < max_attempts:
                    attempt += 1

                    # 清除现有对象
                    self.clear_question_objects()

                    # 创建基于难度设置的干扰项
                    # 确保种子不重复
                    while True:
                        distractor_seed = question_seed + i + \
                            1000 + attempt + random.randint(0, 1000)
                        if distractor_seed not in used_distractor_seeds:
                            break
                        attempt += 1  # 增加尝试次数以获取不同种子

                    # 使用基类的干扰项生成方法
                    distractor_obj = self.generate_distractor(
                        original_shape=original_obj,
                        growth_history=growth_history,
                        distractor_seed=distractor_seed,
                        # 降低难度参数以产生更明显的差异
                        difficulty=max(
                            0.1, self.config['distractor_difficulty'] - 0.2)
                    )

                    # 检查干扰项是否与原始形状有足够差异
                    distractor_blocks = [
                        obj for obj in distractor_obj.children]
                    is_different = self.is_view_different(
                        original_projected_positions, distractor_blocks, correct_view["name"],
                        min_difference=0.35)  # 增加差异阈值

                    # 进一步要求：截面模式不能与题内已有选项完全相同
                    distractor_positions = self.get_projected_positions(
                        distractor_blocks, correct_view["name"])
                    proj_key = frozenset(distractor_positions)

                    is_unique_pattern = proj_key not in used_projection_sets

                    # 只有两个条件都满足才接受这个干扰项
                    is_acceptable = is_different and is_unique_pattern

                    if is_acceptable or attempt == max_attempts:
                        # 如果接受，记录这个干扰项的位置
                        if is_acceptable:
                            distractor_positions_list.append(
                                distractor_positions)
                            used_distractor_seeds.add(distractor_seed)
                            used_projection_sets.add(proj_key)
                        break

                # 使用与正确答案相同的视图
                self.set_camera_to_view(
                    cam, correct_view, add_randomness=False)

                # 为修改后形状的干扰项保持正交视图特性，不调整相机朝向

                used_view_name = correct_view["name"]

            # 保存相机位置信息
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

            # 输出干扰项信息用于调试
            print(
                f"干扰项 {i+1}: 类型={options[-1]['distractor_type']}, 视图={options[-1]['view_name']}, 种子={options[-1]['seed']}")

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
