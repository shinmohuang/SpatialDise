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
        # 更改默认目录名
        if output_dir is None:
            output_dir = "blender_dataset/combination"

        super().__init__("combination", output_dir, config)

        # 根据难度标签调整方块数量范围，以拉开题目复杂度
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

        # 根据平均尺寸调整间距：
        # - 比原始实现略大一些，用于减少遮挡
        # - 同时保持尽量紧凑的布局
        spacing = max(1.5, avg_size_x * 1.4)
        return spacing

    def _instantiate_segment_wrappers(self, blocks, original_positions, world_positions):
        """Create segmented master and wrapper objects for each block, without layout."""
        segmented_master = bpy.data.objects.new("SegmentedMaster", None)
        bpy.context.scene.collection.objects.link(segmented_master)

        components = []
        for i, block in enumerate(blocks):
            # 取消原来的父级关系
            block.parent = None

            # 创建新的父对象（包装器）
            wrapper = bpy.data.objects.new(f"Component_{i}", None)
            bpy.context.scene.collection.objects.link(wrapper)

            components.append({
                "wrapper": wrapper,
                "block": block,
                "original_index": i,
                "original_position": original_positions[i],
                "original_world_pos": world_positions[i]
            })

            # 设置方块为包装器的子级，并放回原世界位置
            block.parent = wrapper
            block.matrix_world.translation = world_positions[i]

            # 将包装器设为分离主对象的子级
            wrapper.parent = segmented_master

            bpy.context.view_layer.update()

        return components, segmented_master

    def _layout_segment_components(self, components, spacing):
        """
        将分离组件布局为规则网格，以获得尽量清晰、不遮挡的展示效果。

        布局策略：
        - 所有组件放在同一水平面 (y=0)，避免上下遮挡。
        - 在 x-z 平面上按行列均匀排布，单元格大小基于最大块尺寸放大数倍，
          从而在等轴视角下也有充分间距。
        """
        count = len(components)
        if count == 0:
            return

        # 估计组件的最大尺寸，用于设置网格单元大小
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

        # 兜底
        if max_dim <= 0.0:
            max_dim = 1.0

        # 单元格边长：保证相邻组件在 x/z 方向不会发生实际碰撞，
        # 但尽量压缩间距以获得更紧凑的展示。
        # 若每个组件在 x/z 方向的最大尺寸为 max_dim，
        # 则 cell_size >= 1.3 * max_dim 可以保证中心间距 > max_dim，
        # 这样两个组件的包围盒不会重叠。
        cell_size = max(spacing, max_dim * 1.3)

        # 计算合适的网格行列数，使得接近方形布局
        cols = max(1, int(math.ceil(math.sqrt(count))))
        rows = int(math.ceil(count / cols))

        # 使整个网格以原点为中心，方便与相机视角对齐
        offset_x = -(cols - 1) * cell_size * 0.5
        offset_z = (rows - 1) * cell_size * 0.5

        for idx, comp in enumerate(components):
            row = idx // cols
            col = idx % cols
            x = offset_x + col * cell_size
            z = offset_z - row * cell_size

            # 先放在规则网格位置
            comp["wrapper"].location = (x, 0.0, z)
            bpy.context.view_layer.update()

            # 与已放置组件做一次碰撞检测；如有碰撞，退回到带碰撞检测的
            # calculate_optimal_position 逻辑进一步调整位置。
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
        将完整形状分解为独立的组件，并排列展示

        Args:
            master_obj: 包含所有组件的主对象
            spacing: 组件之间的间距

        Returns:
            包含所有分离组件的列表
        """
        blocks, original_positions, world_positions = self._snapshot_block_states(
            master_obj)

        # 根据平均尺寸调整间距
        spacing = self._compute_segment_spacing(blocks, spacing)

        # 创建包装器但不布局
        components, segmented_master = self._instantiate_segment_wrappers(
            blocks, original_positions, world_positions)

        # 应用布局算法，避免重叠
        self._layout_segment_components(components, spacing)

        bpy.context.view_layer.update()

        return components, segmented_master, original_positions

    def restore_original_shape(self, components, original_positions):
        """
        将分离的组件恢复为原始形状

        Args:
            components: 组件列表
            original_positions: 原始位置列表
        """
        for comp, orig_pos in zip(components, original_positions):
            block = comp["block"]
            orig_location, orig_parent = orig_pos

            # 恢复原始父级关系
            block.parent = orig_parent

            # 恢复原始位置
            if orig_parent:
                # 如果有父对象，需要设置相对位置
                block.location = orig_location
            else:
                # 如果没有父对象，设置世界位置
                block.matrix_world.translation = orig_location

        # 更新场景以确保正确计算
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
            print("警告: 没有生成任何方块!")
        else:
            print(f"生成了 {len(cubes)} 个方块")
        return original_obj, cubes

    def _render_question_and_opposite_views(self, q_id, cam, cubes):
        """
        Render the main question view and its opposite view.

        Returns camera states and image paths so that `generate_question`
        can assemble metadata without duplicating rendering logic.
        """
        # 扩大相机视场，确保能够看到更多内容
        try:
            if hasattr(cam.data, "ortho_scale"):
                original_ortho_scale = cam.data.ortho_scale
                # 扩大为原来的1.5倍，确保视野足够宽
                cam.data.ortho_scale = 18  # 与旧实现保持一致
            else:
                original_ortho_scale = 18
        except Exception as e:
            print(f"调整相机视场失败: {e}")
            original_ortho_scale = 12

        # 使用 find_best_view 找到最佳视角
        question_view, visible_count = self.find_best_view(
            self.iso_views,
            cubes,
            cam,
            prefer_isometric=True,
            auto_generate=True,
            num_candidates=8,
        )
        print(f"选择视角: {question_view['name']} 可见方块数: {visible_count}")

        # 设置相机到问题视角
        self.set_camera_to_view(cam, question_view, add_randomness=True)

        # 计算形状的几何中心，并让相机对准中心
        shape_center = self.get_shape_center(cubes)
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot_quat.to_euler()

        # 缩小 ortho_scale 来放大 question 图片中的物体
        if hasattr(cam.data, "ortho_scale"):
            cam.data.ortho_scale = 8.0
        bpy.context.view_layer.update()

        question_location = cam.location.copy()
        question_rotation = cam.rotation_euler.copy()

        # 渲染题目图像 (完整形状)
        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)

        # 构建对面视角
        opposite_view = question_view.copy()
        opposite_view["name"] = "opposite_" + question_view["name"]

        pos_x, pos_y, pos_z = question_view["pos"]
        opposite_view["pos"] = (-pos_x, -pos_y, -pos_z)

        # 设置相机到对面视角
        self.set_camera_to_view(cam, opposite_view, add_randomness=False)

        # 同样让相机对准形状中心
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot_quat.to_euler()
        if hasattr(cam.data, "ortho_scale"):
            cam.data.ortho_scale = 8.0
        bpy.context.view_layer.update()

        opposite_location = cam.location.copy()
        opposite_rotation = cam.rotation_euler.copy()

        # 渲染对面视角图像
        opposite_img = os.path.join(self.output_dir, f"{q_id}_Q_opposite.png")
        self.render_image(opposite_img)

        # 为后续选项渲染恢复到较大的视场
        if hasattr(cam.data, "ortho_scale"):
            cam.data.ortho_scale = 18

        # 将相机设置回问题视角
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
        为指定组件创建干扰项

        Args:
            original_component: 要替换的原始组件
            master_obj: 原始形状的主对象
            seed: 随机种子
            highlight_distractor: 是否高亮显示干扰项（红色）

        Returns:
            干扰项组件对象
        """
        # 设置随机种子以确保可重现性
        random.seed(seed)

        # 获取原始方块
        original_block = original_component["block"]
        wrapper = original_component["wrapper"]

        # 确定原始形状
        orig_shape = None
        orig_dimensions = (1, 1, 1)  # 默认立方体

        # 尝试检测原始形状的尺寸
        if hasattr(original_block, "dimensions"):
            dims = original_block.dimensions
            orig_dimensions = (dims.x, dims.y, dims.z)

            # 根据维度比例判断形状类型
            max_dim = max(orig_dimensions)
            min_dim = min(orig_dimensions)

            if max_dim / min_dim > 1.5:
                # 找出哪个维度是长的
                if dims.x > dims.y and dims.x > dims.z:
                    orig_shape = self.shape_types[1]  # x_prism
                elif dims.y > dims.x and dims.y > dims.z:
                    orig_shape = self.shape_types[2]  # y_prism
                elif dims.z > dims.x and dims.z > dims.y:
                    orig_shape = self.shape_types[3]  # z_prism
            else:
                orig_shape = self.shape_types[0]  # cube

        if orig_shape is None:
            orig_shape = self.shape_types[0]  # 默认立方体

        # 创建新的分散项
        # 选择与原始形状不同的形状类型
        available_shapes = [s for s in self.shape_types if s != orig_shape]
        if not available_shapes:  # 确保有可用形状
            available_shapes = self.shape_types
        distractor_shape = random.choice(available_shapes)

        # 创建分散项的网格
        mesh = bpy.data.meshes.new(f"{distractor_shape['name']}Mesh")
        distractor = bpy.data.objects.new(distractor_shape['name'], mesh)
        bpy.context.scene.collection.objects.link(distractor)

        # 创建立方体使用bmesh
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)

        # 使用新形状的尺寸缩放
        dimensions = distractor_shape["dimensions"]
        for v in bm.verts:
            v.co.x *= dimensions[0]
            v.co.y *= dimensions[1]
            v.co.z *= dimensions[2]

        bm.to_mesh(mesh)
        bm.free()

        # 设置线框显示
        distractor.display_type = 'WIRE'

        # 创建材质 - 使用发射着色器消除反射
        mat = bpy.data.materials.new(name="DistractorMaterial")
        mat.use_nodes = True

        # 获取节点树
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # 清除默认节点
        for node in nodes:
            nodes.remove(node)

        # 创建发射着色器节点（无反射）
        emission = nodes.new(type='ShaderNodeEmission')
        emission.inputs['Color'].default_value = (0.7, 0.7, 0.7, 1.0)  # 深灰色
        emission.inputs['Strength'].default_value = 1.0  # 发射强度
        emission.location = (0, 0)

        # 创建输出节点
        output = nodes.new(type='ShaderNodeOutputMaterial')
        output.location = (200, 0)

        # 连接节点 - 发射着色器直接连接到输出，完全无反射
        links.new(emission.outputs['Emission'], output.inputs['Surface'])

        # 应用材质
        if distractor.data.materials:
            distractor.data.materials[0] = mat
        else:
            distractor.data.materials.append(mat)

        # 确保材质在线框模式下可见
        distractor.show_wire = True
        distractor.show_all_edges = True

        # 设置分散项为包装器的子级
        distractor.parent = wrapper

        # 获取原始方块的世界变换
        original_world_matrix = original_block.matrix_world.copy()

        # 设置干扰项的世界变换（保持与原始方块相同的位置和旋转）
        distractor.matrix_world = original_world_matrix

        # 临时隐藏原始方块（不删除，以便后续恢复）
        original_block.hide_viewport = True
        original_block.hide_render = True

        # 更新场景以确保正确计算
        bpy.context.view_layer.update()

        return {
            "wrapper": wrapper,
            "block": distractor,
            "replaced_block": original_block,
            "original_index": original_component["original_index"]
        }

    def restore_from_distractor(self, distractor_component):
        """
        恢复被干扰项替换的原始组件

        Args:
            distractor_component: 干扰项组件信息
        """
        # 显示原始方块
        original_block = distractor_component["replaced_block"]
        original_block.hide_viewport = False
        original_block.hide_render = False

        # 删除干扰项
        distractor = distractor_component["block"]

        # 删除干扰项的材质
        if distractor.data and distractor.data.materials:
            for i in range(len(distractor.data.materials)):
                mat = distractor.data.materials[i]
                if mat:
                    # 尝试移除材质
                    distractor.data.materials[i] = None
                    # 如果材质没有其他用户，删除它
                    if mat.users == 0:
                        bpy.data.materials.remove(mat)

        # 删除干扰项对象
        if distractor.data:
            mesh = distractor.data
            bpy.data.objects.remove(distractor, do_unlink=True)
            # 删除网格数据
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        else:
            bpy.data.objects.remove(distractor, do_unlink=True)

        # 更新场景以确保正确计算
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
            """Return the currently可见的块对象列表（每个组件选择一个未隐藏的子块）."""
            blocks = []
            for comp in components:
                wrapper = comp["wrapper"]
                visible = None
                # 优先选择未被隐藏用于渲染的子对象
                for child in wrapper.children:
                    if not getattr(child, "hide_render", False):
                        visible = child
                        break
                if visible is None:
                    visible = comp["block"]
                blocks.append(visible)
            return blocks
        # 选择一个随机组件作为干扰项基准（用于初始种子和索引选择）
        base_index = random.randint(0, len(components) - 1)

        options = []
        bpy.context.view_layer.update()

        components_count = len(components)
        # 初始情况下只有原始块，直接统计可见块类型
        component_blocks = _visible_blocks_from_components()
        component_block_counts = self.count_block_types(component_blocks)

        # 从预定义视角中选择 iso_front_top_left 作为选项视角
        front_top_left_view = None
        for view in self.iso_views:
            if view["name"] == "iso_front_top_left":
                front_top_left_view = view.copy()
                break

        if front_top_left_view is None:
            print("警告：找不到 iso_front_top_left 视角，使用默认视角")
            front_top_left_view = self.iso_views[0].copy()

        option_view = front_top_left_view
        option_view["name"] = "options_" + option_view["name"]

        # 组件排列在原点附近，look_at 指向 (0,0,0)
        option_view["look_at"] = (0, 0, 0)

        # 调整视角，使其俯仰角更低一些（更接近水平视图），
        # 但仍然从左前方略微俯视，兼顾形状关系与整体布局。
        base_pos = mathutils.Vector(option_view["pos"])
        # 稍微减小高度、略微减小左右偏移，使视角更平、更靠中
        base_pos.x *= 0.8
        base_pos.z *= 0.7
        option_view["pos"] = (base_pos.x, base_pos.y, base_pos.z)

        # 根据组件数量调整相机距离（基于新的方向向量）
        distance_scale = max(1.1, components_count / 8.0)
        orig_pos = mathutils.Vector(option_view["pos"])
        direction = orig_pos.normalized()
        new_distance = orig_pos.length * distance_scale
        new_pos = direction * new_distance
        option_view["pos"] = (new_pos.x, new_pos.y, new_pos.z)

        # 设置相机到选项视角
        self.set_camera_to_view(cam, option_view, add_randomness=False)
        bpy.context.view_layer.update()

        # 1. 渲染正确答案（所有原始组件）
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

        # 2. 渲染干扰项，带有单解性约束，但避免整组反复重试：
        #    - 同一题中 (cube_count, rect_prism_count) 组合不重复
        num_distractors = self.config.get("num_distractors", 3)

        # 记录已使用的 (cube, rect_prism) 组合（包含正确答案）
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

                # 本次干扰项要替换的组件数量：根据难度动态控制
                # - easy: 尽量只替换 2 个组件
                # - medium: 在 2 和 3 之间波动（如果组件数允许）
                # - hard: 尽量替换到上限（最多 3 个）
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
                    else:  # hard 及其他情况
                        replace_count = max_allowed

                # 为该干扰项选择需要替换的组件索引集合
                available_indices = list(range(len(components)))
                random.shuffle(available_indices)
                replace_indices = available_indices[:replace_count]

                applied_distractors = []
                # 对选中的多个组件依次应用替换
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

                # 使用当前可见块统计类型（其中多个组件已被干扰块替换）
                current_blocks = _visible_blocks_from_components()
                current_block_counts = self.count_block_types(current_blocks)
                pair = (
                    current_block_counts.get("cube", 0),
                    current_block_counts.get("rect_prism", 0),
                )

                # 如果该 (cube, rect) 组合已被使用，并且还有尝试机会，则撤销并重试
                if pair in used_pairs and attempt < max_attempts - 1:
                    for d in applied_distractors:
                        self.restore_from_distractor(d)
                    continue

                # 接受该候选（即使是最后一次尝试时重复，也会作为兜底）
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

                # 恢复原始组件，为下一个干扰项准备
                for d in applied_distractors:
                    self.restore_from_distractor(d)

                break

            if accepted_option is not None:
                distractor_options.append(accepted_option)

        options.extend(distractor_options)

        # 恢复原始形状：移除包装器和分段主对象
        for component in components:
            block = component["block"]
            wrapper = component["wrapper"]
            block.parent = None
            bpy.data.objects.remove(wrapper, do_unlink=True)

        bpy.data.objects.remove(segmented_master, do_unlink=True)

        # 恢复相机视场
        try:
            if hasattr(cam.data, "ortho_scale"):
                cam.data.ortho_scale = original_ortho_scale
        except Exception as e:
            print(f"恢复相机视场失败: {e}")

        # 重置相机到初始位置
        cam.location = initial_cam_location
        cam.rotation_euler = initial_cam_rot
        bpy.context.view_layer.update()

        return option_view, options

    def generate_question(self, q_id):
        """生成一个3D形状拼装题目"""
        print(f"生成题目 {q_id}...")

        # 清除现有对象
        self.clear_question_objects()

        # 基于题目ID和难度创建种子以确保可重现性，
        # 不同难度下同一题号会得到不同的形状
        difficulty_label = self.config.get("difficulty", "easy")
        question_seed = hash((q_id, difficulty_label)) % 100000

        # 1. 构建目标形状
        original_obj, cubes = self._build_target_shape(question_seed)
        if not cubes:
            return None
        original_block_count = len(cubes)
        original_block_counts = self.count_block_types(cubes)

        # 保存相机初始位置
        cam = bpy.context.scene.camera
        initial_cam_location = cam.location.copy()
        initial_cam_rot = cam.rotation_euler.copy()

        # 2. 渲染题干视图（完整形状 + 对面视角）
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

        # 3. 构建分段视图
        components, segmented_master, original_positions = self.create_segmented_shape(
            original_obj)
        if not components:
            print("警告: 没有创建任何组件!")
            return None
        print(f"创建了 {len(components)} 个分离组件")

        # 4 & 5. 生成组合干扰项并渲染选项图像
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

        # 创建元数据
        meta = {
            "question_id": q_id,
            "question_image": question_img,
            "opposite_view_image": opposite_img,  # 添加对面视角图像路径
            "seed": question_seed,
            "timestamp": datetime.now().isoformat(),
            "original_block_count": original_block_count,
            "original_block_counts": original_block_counts,
            "question_view": {
                "name": question_view["name"],
                "camera_location": tuple(question_location),
                "camera_rotation": tuple(question_rotation)
            },
            "opposite_view": {  # 添加对面视角信息
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

        # 写入元数据文件
        meta_path = os.path.join(self.output_dir, f"{q_id}.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        return meta_path

    def calculate_optimal_position(self, components, new_component_index, spacing=2.0):
        """
        计算新组件的最佳位置，避免与现有组件重叠

        Args:
            components: 现有组件列表
            new_component_index: 新组件的索引
            spacing: 组件之间的基础间距

        Returns:
            (x, y, z): 建议的位置坐标
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

        # 为了进一步减小组件之间的互相遮挡和碰撞风险，使用更大的网格间距
        grid_spacing = max(spacing, avg_size * 2.0)
        max_search_distance = len(components) * grid_spacing * 0.5
        row = 0
        col = 0
        spiral_direction = 0  # 0:右, 1:下, 2:左, 3:上
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
                print(f"警告: 对组件 {new_component_index} 找不到无碰撞位置，使用默认网格位置")
                return (x, y, z)


# Alias for registry
Combination3DGenerator = CombinationGenerator
