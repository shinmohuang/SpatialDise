#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spatial Reasoning Question Generator
====================================
A module for generating 3D rotation matching questions using Blender.
This generator creates questions that test the ability to visualize 3D objects
from different perspectives.
"""

# 确保脚本在 Blender 内运行
try:
    import mathutils
    import bpy
except ImportError:
    print("This script must be run inside Blender")
    import sys
    sys.exit(1)

import os
import json
import math
import random
import bmesh
import time
from datetime import datetime


class SpatialReasoningGeneratorBase:
    """Base class for spatial reasoning question generators"""

    def __init__(self, generator_name, output_dir=None, config=None):
        """
        Initialize the generator with configuration parameters.

        Args:
            generator_name (str): Name of the generator
            output_dir (str): Directory to save generated files. If None, a default is used.
            config (dict): Configuration dictionary. If None, default values are used.
        """
        # Set default output directory
        if output_dir is None:
            self.output_dir = f"blender_dataset/{generator_name}"
        else:
            self.output_dir = output_dir

        # Default configuration
        self.default_config = {
            "num_questions": 10,        # Number of questions to generate
            "image_resolution": (640, 480),  # Resolution of rendered images
            "num_distractors": 3,       # Number of distractor options per question
            "distractor_difficulty": 1,  # Distractor difficulty (0.0-1.0)
            "num_cells_min": 5,         # Minimum number of cells in the shape
            "num_cells_max": 15,        # Maximum number of cells in the shape
            "use_rectangular_prisms": True,  # Use rectangular prisms or just cubes
            "rectangular_prism_prob": 0.3,   # Probability of a rectangular prism vs cube
            "camera_distance_factor": 1.0,   # 相机距离因子，用于调整视角
            "render_engine": "CYCLES",  # 渲染引擎，可选CYCLES或Blender支持的其他引擎
            "material_style": "solid",   # 材质风格：solid, wireframe, or textured
            "ortho_scale": 15.0,   # 正交相机视野大小，值越大视野越宽
            "collision_threshold": 0.05,  # 碰撞检测阈值，较小的值检测更精确
        }

        # Override defaults with provided config
        if config is not None:
            self.config = {**self.default_config, **config}
        else:
            self.config = self.default_config

        # Grid coordinates: 3x3x3 grid centered at origin, each cell size 1
        self.grid_coords = [(x, y, z) for x in (-1, 0, 1)
                            for y in (-1, 0, 1)
                            for z in (-1, 0, 1)]

        # Predefined shape types
        self.shape_types = [
            {"name": "cube", "dimensions": (1.0, 1.0, 1.0)},  # Cube
            {"name": "x_prism", "dimensions": (2.0, 1.0, 1.0)},  # X-axis prism
            {"name": "y_prism", "dimensions": (1.0, 2.0, 1.0)},  # Y-axis prism
            {"name": "z_prism", "dimensions": (1.0, 1.0, 2.0)},  # Z-axis prism
        ]

        # 预定义的等轴测视角，所有子类共用
        self.iso_views = [
            {"name": "iso_front_top_right", "pos": (
                6.0, -4.0, 4.0), "look_at": (0, 0, 0)},
            {"name": "iso_back_top_right", "pos": (
                6.0, 4.0, 4.0), "look_at": (0.1, -0.1, 0)},
            {"name": "iso_front_top_left",
                "pos": (-6.0, -4.0, 4.0), "look_at": (0.1, 0.1, 0)},
            {"name": "iso_back_top_left",
                "pos": (-6.0, 4.0, 4.0), "look_at": (-0.1, -0.1, 0)},
        ]

        # Ensure the output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

    def evaluate_visibility(self, view, cubes, camera):
        """Evaluate how many cubes are visible from a specific view"""
        # Save current camera state
        temp_loc = camera.location.copy()
        temp_rot = camera.rotation_euler.copy()

        # Set camera to view position (without random offsets for consistent evaluation)
        pos = view["pos"]
        camera.location = mathutils.Vector((pos[0], pos[1], pos[2]))

        # Point camera at look-at point
        look_at = view["look_at"]
        direction = mathutils.Vector(look_at) - camera.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()

        # Update scene to ensure correct calculations
        bpy.context.view_layer.update()

        # Get camera direction
        from mathutils import Vector
        cam_direction = Vector((0, 0, -1))
        cam_direction.rotate(camera.rotation_euler)

        # Count visible cubes (simplistic approach not accounting for occlusion)
        visible_count = 0
        visible_areas = 0  # 新增：考虑可见表面积
        for cube in cubes:
            # Vector from camera to cube
            to_cube = cube.matrix_world.translation - camera.location
            distance = to_cube.length

            # Check if cube is in front of camera
            angle = to_cube.normalized().dot(cam_direction.normalized())

            if angle > 0:  # Cube is in camera's forward direction
                # 基础可见性检测
                visible_count += 1

                # 考虑距离因素——距离近的方块贡献更多
                distance_factor = 1.0 / max(1.0, distance * 0.2)

                # 考虑方块大小
                if hasattr(cube, "dimensions"):
                    size = max(cube.dimensions.x,
                               cube.dimensions.y, cube.dimensions.z)
                    visible_areas += size * distance_factor
                else:
                    visible_areas += distance_factor

        # Restore camera
        camera.location = temp_loc
        camera.rotation_euler = temp_rot

        return visible_count, visible_areas

    def clear_scene(self):
        """Clear all objects from the scene"""
        for collection in bpy.data.collections:
            bpy.data.collections.remove(collection)

        for obj in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)

        for mesh in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)

    def clear_question_objects(self):
        """Remove all objects except camera and lights"""
        for obj in bpy.context.scene.objects:
            if obj.type not in {'CAMERA', 'LIGHT'}:
                bpy.data.objects.remove(obj, do_unlink=True)

    def setup_gpu_acceleration(self):
        """
        配置GPU加速渲染 (支持CUDA, OpenCL, Metal等)
        自动检测可用的GPU设备并启用最佳配置
        """
        try:
            # 确保使用Cycles渲染引擎(支持GPU加速)
            if bpy.context.scene.render.engine != 'CYCLES':
                print("GPU加速需要Cycles渲染引擎，当前引擎不支持")
                return False

            # 配置为GPU渲染
            bpy.context.scene.cycles.device = 'GPU'
            print("已设置渲染设备为GPU")

            # 查找Cycles插件偏好设置
            if 'cycles' in bpy.context.preferences.addons:
                cycles_prefs = bpy.context.preferences.addons['cycles'].preferences

                # 自动检测并设置最佳计算设备类型
                available_devices = []
                device_type_set = False

                # 检测可用的计算设备类型
                if hasattr(cycles_prefs, 'compute_device_type'):
                    # 尝试不同的设备类型，按优先级排序
                    device_types = ['METAL', 'CUDA', 'OPENCL', 'CPU']

                    for device_type in device_types:
                        try:
                            # 临时设置设备类型来测试是否可用
                            old_type = cycles_prefs.compute_device_type
                            cycles_prefs.compute_device_type = device_type

                            # 刷新设备列表
                            cycles_prefs.get_devices()

                            # 检查是否有可用的GPU设备
                            gpu_devices = [
                                d for d in cycles_prefs.devices if d.type == 'GPU' or d.type == 'METAL' or device_type in d.name.upper()]

                            if gpu_devices:
                                print(
                                    f"检测到 {device_type} 设备: {len(gpu_devices)} 个GPU")
                                device_type_set = True
                                break
                            else:
                                # 恢复原设置
                                cycles_prefs.compute_device_type = old_type
                        except Exception as e:
                            print(f"测试 {device_type} 设备类型时出错: {e}")
                            try:
                                cycles_prefs.compute_device_type = old_type
                            except:
                                pass

                    if device_type_set:
                        print(
                            f"已设置 {cycles_prefs.compute_device_type} 作为计算设备类型")
                    else:
                        print("未找到可用的GPU设备类型，将使用CPU")

                # 启用所有可用的GPU设备
                if hasattr(cycles_prefs, 'devices'):
                    # 刷新设备列表
                    cycles_prefs.get_devices()

                    print("可用渲染设备:")
                    gpu_count = 0
                    for i, device in enumerate(cycles_prefs.devices):
                        print(f"  {i}: {device.name} (类型: {device.type})")

                        # 启用所有GPU设备
                        if device.type == 'GPU' or device.type == 'METAL':
                            try:
                                device.use = True
                                gpu_count += 1
                                print(f"    ✓ 已启用GPU设备: {device.name}")
                            except Exception as e:
                                print(f"    ✗ 无法启用设备: {device.name} - {e}")
                        elif device.type == 'CPU':
                            # 如果没有GPU可用，保留CPU作为备选
                            if gpu_count == 0:
                                try:
                                    device.use = True
                                    print(f"    ✓ 已启用CPU设备: {device.name}")
                                except:
                                    pass

                    if gpu_count > 0:
                        print(f"成功启用 {gpu_count} 个GPU设备")
                    else:
                        print("未找到可用GPU设备，将使用CPU渲染")

            # 优化GPU渲染性能设置
            if bpy.context.scene.cycles.device == 'GPU':
                # 适合GPU的采样设置
                bpy.context.scene.cycles.samples = 128  # GPU可以处理更多采样
                bpy.context.scene.cycles.max_bounces = 8  # 限制光线弹射次数
                bpy.context.scene.cycles.use_denoising = True  # 启用降噪

                # GPU特定的优化
                if hasattr(bpy.context.scene.cycles, 'tile_size'):
                    # 较大的瓦片大小适合GPU
                    bpy.context.scene.cycles.tile_size = 256

                print("已应用GPU优化设置")

            # 验证GPU配置
            if hasattr(bpy.context.scene.cycles, 'device'):
                print(f"当前渲染设备: {bpy.context.scene.cycles.device}")

            if 'cycles' in bpy.context.preferences.addons:
                cycles_prefs = bpy.context.preferences.addons['cycles'].preferences
                if hasattr(cycles_prefs, 'compute_device_type'):
                    print(f"计算设备类型: {cycles_prefs.compute_device_type}")

            print("GPU加速配置完成")
            return True

        except Exception as e:
            print(f"配置GPU加速时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def setup_scene(self):
        """Set up scene with camera, lights, and render settings"""
        scene = bpy.context.scene

        # Set render resolution
        scene.render.resolution_x = self.config["image_resolution"][0]
        scene.render.resolution_y = self.config["image_resolution"][1]
        scene.render.resolution_percentage = 100

        # 设置渲染引擎
        render_engine = self.config.get("render_engine", "CYCLES")

        # 检查渲染引擎是否可用
        available_engines = {'CYCLES', 'BLENDER_WORKBENCH'}

        # 尝试检测当前Blender版本支持的EEVEE引擎名称
        if hasattr(bpy.context.scene.render, 'engine'):
            possible_eevee_values = [
                'BLENDER_EEVEE',
                'BLENDER_EEVEE_NEXT'
            ]
            for value in possible_eevee_values:
                try:
                    temp_value = scene.render.engine
                    scene.render.engine = value
                    available_engines.add(value)
                    scene.render.engine = temp_value
                    break
                except (TypeError, ValueError):
                    continue

        # 选择一个可用的渲染引擎
        if render_engine not in available_engines:
            print(f"警告: 渲染引擎 '{render_engine}' 不可用，将使用 'CYCLES'")
            render_engine = 'CYCLES'

        # 设置渲染引擎
        try:
            scene.render.engine = render_engine
            print(f"使用渲染引擎: {render_engine}")
        except Exception as e:
            print(f"设置渲染引擎失败: {e}，尝试使用CYCLES")
            try:
                scene.render.engine = 'CYCLES'
            except Exception as e2:
                print(f"设置CYCLES引擎也失败: {e2}")

        # 配置GPU加速 (仅在使用CYCLES时)
        if scene.render.engine == 'CYCLES':
            gpu_enabled = self.config.get("use_gpu", True)  # 默认启用GPU
            if gpu_enabled:
                print("正在配置GPU加速...")
                self.setup_gpu_acceleration()
            else:
                print("GPU加速已禁用")

        # 调整渲染质量设置
        try:
            if 'EEVEE' in render_engine:
                # 适用于所有EEVEE变体
                try:
                    scene.eevee.taa_render_samples = 64  # 更高质量的抗锯齿
                    scene.eevee.use_soft_shadows = True
                    scene.eevee.use_bloom = True
                    scene.eevee.bloom_intensity = 0.05
                    scene.eevee.use_ssr = True  # 屏幕空间反射
                except AttributeError as e:
                    print(f"警告: 无法设置EEVEE参数: {e}")
            elif render_engine == "CYCLES":
                try:
                    # 如果没有启用GPU，使用CPU优化设置
                    if not self.config.get("use_gpu", True) or bpy.context.scene.cycles.device != 'GPU':
                        scene.cycles.samples = 64  # CPU使用较少采样
                    # GPU设置在setup_gpu_acceleration中已配置
                    scene.cycles.use_denoising = True
                except AttributeError as e:
                    print(f"警告: 无法设置CYCLES参数: {e}")
        except Exception as e:
            print(f"设置渲染质量参数失败: {e}")

        # Set white background - Enhanced version with stronger enforcement
        try:
            # 确保场景有世界材质
            if not scene.world:
                scene.world = bpy.data.worlds.new("World")

            # 强制启用节点
            scene.world.use_nodes = True
            nodes = scene.world.node_tree.nodes
            links = scene.world.node_tree.links

            # 清理现有节点
            for node in nodes:
                nodes.remove(node)

            # 创建背景节点
            background = nodes.new(type='ShaderNodeBackground')
            # 设置纯白色背景 (FFFFFF) - 降低强度避免过度照亮物体
            background.inputs['Color'].default_value = (
                1.0, 1.0, 1.0, 1.0)  # 纯白色背景
            background.inputs['Strength'].default_value = 1.0  # 降低强度到1.0避免物体变白
            background.location = (0, 0)

            # 创建输出节点
            output = nodes.new(type='ShaderNodeOutputWorld')
            output.location = (200, 0)

            # 连接节点
            links.new(background.outputs['Background'],
                      output.inputs['Surface'])

            # 强制更新世界材质
            scene.world.node_tree.update_tag()
            bpy.context.view_layer.update()

            print("✓ 成功设置纯白色背景 (强度1.0)")

        except Exception as e:
            print(f"✗ 设置背景时出错: {e}")

        # 设置film属性确保背景不透明 - 增强版本
        try:
            render = scene.render
            # 确保背景不透明
            render.film_transparent = False

            # 设置背景颜色为白色（作为备用）
            scene.world.color = (1.0, 1.0, 1.0)

            # 强制设置视图变换为Raw，避免颜色空间转换影响
            if hasattr(scene.view_settings, 'view_transform'):
                scene.view_settings.view_transform = 'Raw'
            if hasattr(scene.view_settings, 'look'):
                scene.view_settings.look = 'None'

            # 设置颜色管理
            if hasattr(scene.display_settings, 'display_device'):
                scene.display_settings.display_device = 'sRGB'

            print("✓ 成功设置film属性为不透明，并配置颜色管理为Raw")
        except Exception as e:
            print(f"✗ 设置film属性时出错: {e}")

        # 设置渲染引擎和采样 - 增强版本
        try:
            render = scene.render
            render.engine = self.config.get("render_engine", "CYCLES")

            # 设置采样数
            if hasattr(scene, 'cycles') and render.engine == 'CYCLES':
                # 检查GPU配置
                gpu_enabled = self.config.get("use_gpu", True)
                if gpu_enabled and hasattr(bpy.context.scene.cycles, 'device') and bpy.context.scene.cycles.device == 'GPU':
                    scene.cycles.samples = 128  # GPU使用更高采样
                else:
                    scene.cycles.samples = 64   # CPU使用较低采样

                # 设置降噪
                scene.cycles.use_denoising = True
                if hasattr(scene.cycles, 'denoiser'):
                    scene.cycles.denoiser = 'OPENIMAGEDENOISE'

                # 优化光线弹射设置，减少环境光影响但保持质量
                scene.cycles.max_bounces = 2  # 从6减少到2，大幅减少总弹射次数
                scene.cycles.diffuse_bounces = 1  # 从3减少到1，减少漫反射
                scene.cycles.glossy_bounces = 1  # 从3减少到1，减少镜面反射
                scene.cycles.transmission_bounces = 1  # 从3减少到1，减少透射
                scene.cycles.volume_bounces = 0
                scene.cycles.transparent_max_bounces = 2  # 从8减少到2，减少透明度弹射

                print(f"✓ 设置Cycles采样数: {scene.cycles.samples}")

        except Exception as e:
            print(f"✗ 设置渲染引擎时出错: {e}")

        # Add orthographic camera
        try:
            cam_data = bpy.data.cameras.new("Camera")
            cam_data.type = 'ORTHO'
            # 使用配置中的视野大小设置，如果没有则使用默认值15
            cam_data.ortho_scale = self.config.get("ortho_scale", 15.0)

            cam = bpy.data.objects.new("Camera", cam_data)
            scene.collection.objects.link(cam)

            # Position camera
            cam.location = mathutils.Vector((5.0, -5.0, 5.0))
            cam.rotation_euler = mathutils.Euler(
                (math.radians(62), math.radians(2), math.radians(43)), 'XYZ')
            scene.camera = cam
        except Exception as e:
            print(f"设置相机失败: {e}")
            # 如果已有相机，尝试使用现有相机
            for obj in scene.objects:
                if obj.type == 'CAMERA':
                    scene.camera = obj
                    cam = obj
                    break
            else:
                print("找不到可用相机，渲染可能会失败")
                return None

        # Add sun light
        try:
            light_data = bpy.data.lights.new(name="Sun", type='SUN')
            light_data.energy = 2.0  # 增加光照强度
            if hasattr(light_data, 'angle'):
                light_data.angle = 0.1  # 较小的角度产生更锐利的阴影
            light = bpy.data.objects.new(name="Sun", object_data=light_data)
            scene.collection.objects.link(light)
            light.location = (20, 0, 15)
            light.rotation_euler = mathutils.Euler(
                (math.radians(45), 0, math.radians(90)), 'XYZ')
        except Exception as e:
            print(f"设置太阳光失败: {e}")

        # Add ambient light
        try:
            ambient_light = bpy.data.lights.new(name="Ambient", type='AREA')
            ambient_light.energy = 1.5  # 增加环境光强度
            if hasattr(ambient_light, 'size'):
                ambient_light.size = 5.0  # 更大的面光源
            ambient_obj = bpy.data.objects.new(
                name="AmbientLight", object_data=ambient_light)
            scene.collection.objects.link(ambient_obj)
            ambient_obj.location = (0, 0, 10)
        except Exception as e:
            print(f"设置环境光失败: {e}")

        # 添加背面补光
        try:
            back_light = bpy.data.lights.new(name="BackLight", type='AREA')
            back_light.energy = 0.8
            if hasattr(back_light, 'size'):
                back_light.size = 5.0
            back_light_obj = bpy.data.objects.new(
                name="BackLight", object_data=back_light)
            scene.collection.objects.link(back_light_obj)
            back_light_obj.location = (-10, 10, 8)
            back_light_obj.rotation_euler = mathutils.Euler(
                (math.radians(45), math.radians(-45), 0), 'XYZ')
        except Exception as e:
            print(f"设置背面补光失败: {e}")

        # Enable Freestyle for line drawing
        try:
            scene.render.use_freestyle = True
            freestyle = bpy.context.view_layer.freestyle_settings

            # Clear existing line sets
            while freestyle.linesets:
                freestyle.linesets.remove(freestyle.linesets[0])

            # Create line set
            lineset = freestyle.linesets.new("LineSet")
            lineset.select_silhouette = True
            lineset.select_border = True
            lineset.select_crease = True
            lineset.linestyle.color = (0, 0, 0)  # Black
            lineset.linestyle.thickness = 1.5
        except Exception as e:
            print(f"设置Freestyle失败: {e}")

        # 设置阴影样式
        try:
            if hasattr(bpy.context.scene, 'display') and hasattr(bpy.context.scene.display, 'shading'):
                bpy.context.scene.display.shading.light = 'STUDIO'
                bpy.context.scene.display.shading.show_object_outline = True
        except Exception as e:
            print(f"设置阴影样式失败: {e}")

        # 更新场景以应用所有更改
        try:
            bpy.context.view_layer.update()
        except Exception as e:
            print(f"更新视图层失败: {e}")

        return cam

    def render_image(self, filepath):
        """Render the current scene to an image file"""
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Set render path and render
        bpy.context.view_layer.update()
        bpy.context.scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)

        return filepath

    def set_camera_to_view(self, camera, view, add_randomness=True):
        """Set camera position and orientation for a specific view"""
        # Add small random offset for natural look (if enabled)
        def add_small_offset(value):
            return value + random.uniform(-0.15, 0.15) if add_randomness else value

        # Set camera position with offset (if enabled)
        pos = view["pos"]
        pos_with_offset = (add_small_offset(pos[0]),
                           add_small_offset(pos[1]),
                           add_small_offset(pos[2]))
        camera.location = mathutils.Vector(pos_with_offset)

        # Set camera look-at target with offset (if enabled)
        look_at = view["look_at"]
        look_at_with_offset = (add_small_offset(look_at[0]),
                               add_small_offset(look_at[1]),
                               add_small_offset(look_at[2]))
        direction = mathutils.Vector(look_at_with_offset) - camera.location
        rot_quat = direction.to_track_quat('-Z', 'Y')

        # Add slight random rotation for variety (if enabled)
        euler = rot_quat.to_euler()
        if add_randomness:
            euler.x += math.radians(random.uniform(-2, 2))
            euler.y += math.radians(random.uniform(-2, 2))
            euler.z += math.radians(random.uniform(-2, 2))
        camera.rotation_euler = euler

        return camera

    def create_combination_shape(self, use_rectangular=None, rect_prob=None, seed=None,
                                 remove_blocks=0, growth_history=None):
        """
        Create a random combination of connected cubes or rectangular prisms

        Args:
            use_rectangular: Whether to use rectangular prisms (None = use config value)
            rect_prob: Probability of rectangular prism vs cube (None = use config value)
            seed: Random seed for reproducibility
            remove_blocks: Number of blocks to remove from end of growth history
            growth_history: Predefined growth history to recreate a shape

        Returns:
            Master object containing the generated shape
        """
        # Use config values if parameters not specified
        if use_rectangular is None:
            use_rectangular = self.config["use_rectangular_prisms"]
        if rect_prob is None:
            rect_prob = self.config["rectangular_prism_prob"]

        # Set random seed if provided
        if seed is not None:
            random.seed(seed)

        # Create empty master object
        master_obj = bpy.data.objects.new("Master", None)
        bpy.context.scene.collection.objects.link(master_obj)

        # Determine number of cells
        num_cells = random.randint(
            self.config["num_cells_min"], self.config["num_cells_max"])

        # Initialize tracking variables
        added_positions = set()
        candidate_positions = set()
        position_shapes = {}
        growth_directions = {}
        position_offsets = {}
        growth_order = []
        created_objects = []  # 用于碰撞检测的已创建对象列表

        # Define helper functions
        def get_neighbors(pos):
            """Get neighboring grid positions and directions"""
            x, y, z = pos
            neighbors = []
            directions = [
                (1, 0, 0), (-1, 0, 0),  # X axis
                (0, 1, 0), (0, -1, 0),  # Y axis
                (0, 0, 1), (0, 0, -1)   # Z axis
            ]
            for dx, dy, dz in directions:
                new_pos = (x+dx, y+dy, z+dz)
                # 扩大网格边界，从[-1,1]到[-2,2]
                if all(-2 <= c <= 2 for c in new_pos):
                    neighbors.append((new_pos, (dx, dy, dz)))
            return neighbors

        def select_shape_by_direction(direction, position):
            """选择形状类型基于生长方向，优化长方体选择"""
            if not use_rectangular or random.random() >= rect_prob:
                return self.shape_types[0], (0, 0, 0)  # Cube, no offset

            # 提取坐标和方向分量
            dx, dy, dz = direction
            x, y, z = position

            # 扩大网格边界
            grid_min, grid_max = -2, 2

            # 放宽边缘判断，只有在绝对值为2时才认为是边缘
            is_near_x_edge = abs(x) >= 2
            is_near_y_edge = abs(y) >= 2
            is_near_z_edge = abs(z) >= 2

            # 创建方向优先级列表，优先考虑与生长方向一致的长方体
            priority_shapes = []

            # 首先添加与生长方向一致的形状
            if dx != 0:  # X方向
                shape = self.shape_types[1]  # x_prism
                offset_x = (shape["dimensions"][0] - 1.0) / 2 * dx
                priority_shapes.append((1, (offset_x, 0, 0)))
            elif dy != 0:  # Y方向
                shape = self.shape_types[2]  # y_prism
                offset_y = (shape["dimensions"][1] - 1.0) / 2 * dy
                priority_shapes.append((2, (0, offset_y, 0)))
            elif dz != 0:  # Z方向
                shape = self.shape_types[3]  # z_prism
                offset_z = (shape["dimensions"][2] - 1.0) / 2 * dz
                priority_shapes.append((3, (0, 0, offset_z)))

            # 然后添加其他方向作为备选
            for shape_idx in [1, 2, 3]:
                # 跳过已添加的方向
                if (shape_idx == 1 and dx != 0) or \
                   (shape_idx == 2 and dy != 0) or \
                   (shape_idx == 3 and dz != 0):
                    continue

                # 根据形状计算偏移量
                shape = self.shape_types[shape_idx]
                if shape_idx == 1:  # x方向
                    offset = ((shape["dimensions"][0] - 1.0) / 2, 0, 0)
                elif shape_idx == 2:  # y方向
                    offset = (0, (shape["dimensions"][1] - 1.0) / 2, 0)
                else:  # z方向
                    offset = (0, 0, (shape["dimensions"][2] - 1.0) / 2)

                priority_shapes.append((shape_idx, offset))

            # 按优先级尝试每个形状
            for shape_idx, offset in priority_shapes:
                shape = self.shape_types[shape_idx]
                offset_x, offset_y, offset_z = offset
                dimensions = shape["dimensions"]

                # 计算放置后的最终位置
                final_x = x + offset_x
                final_y = y + offset_y
                final_z = z + offset_z

                # 检查是否会超出网格边界
                if (final_x - dimensions[0]/2 < grid_min or final_x + dimensions[0]/2 > grid_max or
                    final_y - dimensions[1]/2 < grid_min or final_y + dimensions[1]/2 > grid_max or
                        final_z - dimensions[2]/2 < grid_min or final_z + dimensions[2]/2 > grid_max):
                    continue  # 这个方向不合适，尝试下一个

                # 边缘检查
                if (shape_idx == 1 and is_near_x_edge) or \
                   (shape_idx == 2 and is_near_y_edge) or \
                   (shape_idx == 3 and is_near_z_edge):
                    continue  # 边缘不适合对应方向的长方体

                return shape, offset

            # 如果所有长方体都不合适，使用立方体
            return self.shape_types[0], (0, 0, 0)

        def would_collide(new_pos, new_shape, new_offset):
            """Check if a new block would collide with existing blocks"""
            # 创建临时块以检查碰撞
            dimensions = new_shape["dimensions"]

            # 检查是否会超出网格边界（额外检查）
            grid_min, grid_max = -2, 2  # 扩大网格边界
            offset_x, offset_y, offset_z = new_offset
            x, y, z = new_pos

            # 计算方块在偏移后各个方向的最大最小坐标
            x_min = x + offset_x - dimensions[0]/2
            x_max = x + offset_x + dimensions[0]/2
            y_min = y + offset_y - dimensions[1]/2
            y_max = y + offset_y + dimensions[1]/2
            z_min = z + offset_z - dimensions[2]/2
            z_max = z + offset_z + dimensions[2]/2

            # 如果任何一个方向超出网格，返回碰撞=True
            if (x_min < grid_min or x_max > grid_max or
                y_min < grid_min or y_max > grid_max or
                    z_min < grid_min or z_max > grid_max):
                return True

            # 创建临时网格进行碰撞测试
            temp_mesh = bpy.data.meshes.new("TempCollisionMesh")
            temp_obj = bpy.data.objects.new("TempCollision", temp_mesh)
            bpy.context.scene.collection.objects.link(temp_obj)

            # 创建立方体网格
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)

            # 按形状尺寸缩放
            for v in bm.verts:
                v.co.x *= dimensions[0]
                v.co.y *= dimensions[1]
                v.co.z *= dimensions[2]

            bm.to_mesh(temp_mesh)
            bm.free()

            # 设置位置（带偏移）
            temp_obj.location = (
                new_pos[0] + offset_x, new_pos[1] + offset_y, new_pos[2] + offset_z)

            # 更新场景以确保对象的世界矩阵正确
            bpy.context.view_layer.update()

            # 根据形状类型和难度级别动态设置碰撞阈值
            is_rectangular = new_shape != self.shape_types[0]

            # 根据difficulty参数调整阈值 - 难度越高阈值越小(检测更严格)
            difficulty = self.config.get('distractor_difficulty', 0.5)

            # 方块越多，阈值越小(检测更严格)
            block_count_factor = min(1.0, len(created_objects) / 10.0)

            # 长方体需要更严格的碰撞检测
            base_threshold = 0.005 if is_rectangular else 0.01  # 从0.01降低到0.005

            # 最终阈值: 基础阈值 * (1 - 难度系数) * (1 - 方块数量因子)
            # 这样在简单难度和方块少时阈值大，在困难难度和方块多时阈值小
            adjusted_threshold = base_threshold * \
                (1 - difficulty * 0.5) * (1 - block_count_factor * 0.5)

            # 检查与现有对象的碰撞
            collision = False
            for existing_obj in created_objects:
                if self.check_collision(temp_obj, existing_obj, threshold=adjusted_threshold):
                    collision = True
                    break

            # 移除临时对象
            bpy.data.objects.remove(temp_obj, do_unlink=True)
            if temp_mesh.users == 0:
                bpy.data.meshes.remove(temp_mesh)

            return collision

        # 评估候选位置的函数，计算其适合放置长方体的程度
        def evaluate_candidate_position(pos, direction):
            """评估候选位置对长方体的适用性"""
            if not use_rectangular:
                return 0  # 如果不使用长方体，所有位置评分相同

            dx, dy, dz = direction
            x, y, z = pos

            # 初始分数
            score = 0

            # 检查是否在边缘
            is_edge = abs(x) >= 2 or abs(y) >= 2 or abs(z) >= 2
            if is_edge:
                return 0  # 边缘位置不适合放置长方体

            # 增加与生长方向匹配的长方体分数
            if dx != 0:  # X方向
                shape = self.shape_types[1]  # x_prism
                offset_x = (shape["dimensions"][0] - 1.0) / 2 * dx
                offset = (offset_x, 0, 0)
                if not would_collide(pos, shape, offset):
                    score += 3  # 优先选择沿生长方向的长方体
            elif dy != 0:  # Y方向
                shape = self.shape_types[2]  # y_prism
                offset_y = (shape["dimensions"][1] - 1.0) / 2 * dy
                offset = (0, offset_y, 0)
                if not would_collide(pos, shape, offset):
                    score += 3
            elif dz != 0:  # Z方向
                shape = self.shape_types[3]  # z_prism
                offset_z = (shape["dimensions"][2] - 1.0) / 2 * dz
                offset = (0, 0, offset_z)
                if not would_collide(pos, shape, offset):
                    score += 3

            # 检查其他方向的长方体可能性
            for shape_idx in [1, 2, 3]:
                # 跳过与生长方向相同的情况（已检查）
                if (shape_idx == 1 and dx != 0) or \
                   (shape_idx == 2 and dy != 0) or \
                   (shape_idx == 3 and dz != 0):
                    continue

                shape = self.shape_types[shape_idx]
                if shape_idx == 1:  # x方向
                    offset_val = (shape["dimensions"][0] - 1.0) / 2
                    offset = (offset_val, 0, 0)
                elif shape_idx == 2:  # y方向
                    offset_val = (shape["dimensions"][1] - 1.0) / 2
                    offset = (0, offset_val, 0)
                else:  # z方向
                    offset_val = (shape["dimensions"][2] - 1.0) / 2
                    offset = (0, 0, offset_val)

                if not would_collide(pos, shape, offset):
                    score += 1  # 其他方向可以放置长方体也加分，但权重较低

            return score

        # Use provided growth history or create new one
        if growth_history:
            # Recreate shape from history, optionally removing some blocks from end
            for step in growth_history[:-remove_blocks if remove_blocks > 0 else None]:
                pos = step["position"]
                added_positions.add(pos)
                position_shapes[pos] = step["shape"]
                position_offsets[pos] = step["offset"]
                growth_order.append(pos)
        else:
            # Start with a random position
            start_pos = random.choice(
                [(x, y, z) for x in range(-2, 3) for y in range(-2, 3) for z in range(-2, 3)])
            added_positions.add(start_pos)
            # Start with a cube
            position_shapes[start_pos] = self.shape_types[0]
            position_offsets[start_pos] = (0, 0, 0)  # No offset
            growth_order.append(start_pos)

            # Add initial candidates
            for neighbor, direction in get_neighbors(start_pos):
                if neighbor not in added_positions:
                    candidate_positions.add(neighbor)
                    growth_directions[neighbor] = direction

            # 当前长方体比例
            current_rect_prob = rect_prob

            # Grow shape by adding blocks
            while len(added_positions) < num_cells and candidate_positions:
                # 评估所有候选位置
                candidate_scores = []
                for pos in candidate_positions:
                    direction = growth_directions.get(pos, (0, 0, 0))
                    score = evaluate_candidate_position(pos, direction)
                    candidate_scores.append((pos, score))

                # 根据分数排序候选位置
                candidate_scores.sort(key=lambda x: x[1], reverse=True)

                # 选择策略: 80%概率选择高分候选，20%概率随机选择（避免形状过于规则）
                if candidate_scores and random.random() < 0.8 and candidate_scores[0][1] > 0:
                    # 从前30%的高分候选中选择
                    top_candidates = candidate_scores[:max(
                        1, len(candidate_scores)//3)]
                    next_pos, _ = random.choice(top_candidates)
                else:
                    # 随机选择
                    next_pos = random.choice(list(candidate_positions))

                candidate_positions.remove(next_pos)

                # Get growth direction
                direction = growth_directions.get(next_pos, (0, 0, 0))

                # 动态调整长方体概率
                # 计算当前长方体数量
                rect_count = sum(
                    1 for pos in position_shapes if position_shapes[pos] != self.shape_types[0])
                if len(added_positions) > 0:
                    rect_ratio = rect_count / len(added_positions)
                    # 如果长方体比例低于目标，增加概率
                    if rect_ratio < rect_prob * 0.8:
                        current_rect_prob = min(0.95, rect_prob * 1.5)
                    else:
                        current_rect_prob = rect_prob

                # Select shape type and offset with adaptive probability
                use_rect_this_time = use_rectangular and random.random() < current_rect_prob
                if use_rect_this_time:
                    shape, offset = select_shape_by_direction(
                        direction, next_pos)
                else:
                    shape, offset = self.shape_types[0], (0, 0, 0)  # 使用立方体

                # Check for collisions with existing blocks
                if created_objects and would_collide(next_pos, shape, offset):
                    # 直接跳过位置，不尝试缩小
                    continue

                # Add to shape
                added_positions.add(next_pos)
                growth_order.append(next_pos)
                position_shapes[next_pos] = shape
                position_offsets[next_pos] = offset

                # Update candidates
                for neighbor, new_direction in get_neighbors(next_pos):
                    if neighbor not in added_positions and neighbor not in candidate_positions:
                        candidate_positions.add(neighbor)
                        growth_directions[neighbor] = new_direction

        # Create blocks
        created_blocks = []
        for pos in growth_order:
            # Get shape and offset
            shape = position_shapes[pos]
            offset = position_offsets[pos]
            dimensions = shape["dimensions"]

            # Create mesh
            mesh = bpy.data.meshes.new(f"{shape['name']}Mesh")
            obj = bpy.data.objects.new(shape['name'], mesh)
            bpy.context.scene.collection.objects.link(obj)

            # Create cube using bmesh
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)

            # Scale to shape dimensions
            for v in bm.verts:
                v.co.x *= dimensions[0]
                v.co.y *= dimensions[1]
                v.co.z *= dimensions[2]

            bm.to_mesh(mesh)
            bm.free()

            # Position with offset
            offset_x, offset_y, offset_z = offset
            obj.location = (pos[0] + offset_x, pos[1] +
                            offset_y, pos[2] + offset_z)

            # Update the scene to ensure world matrix is correct for collision detection
            bpy.context.view_layer.update()

            # Check for collisions with existing objects (secondary check for safety)
            has_collision = False
            for existing_obj in created_objects:
                if self.check_collision(obj, existing_obj):
                    has_collision = True
                    print(f"警告: 检测到在位置 {pos} 的方块与现有方块碰撞")
                    break

            # Add to list of created objects for future collision checks
            created_objects.append(obj)

            # Set wireframe display
            obj.display_type = 'WIRE'

            # Create material with dark color for contrast against white background - 无反射材质
            mat = bpy.data.materials.new(name="SimpleMaterial")
            mat.use_nodes = True  # 启用节点以便更精确控制

            # 清除默认节点
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            for node in nodes:
                nodes.remove(node)

            # 创建发射着色器节点（无反射）
            emission = nodes.new(type='ShaderNodeEmission')
            emission.inputs['Color'].default_value = (
                0.7, 0.7, 0.7, 1.0)  # 深灰色
            emission.inputs['Strength'].default_value = 1.0  # 发射强度
            emission.location = (0, 0)

            # 创建输出节点
            output = nodes.new(type='ShaderNodeOutputMaterial')
            output.location = (200, 0)

            # 连接节点 - 发射着色器直接连接到输出，完全无反射
            links.new(emission.outputs['Emission'], output.inputs['Surface'])

            # Apply material
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

            # Parent to master object
            obj.parent = master_obj

            # Record block info
            created_blocks.append({
                "object": obj,
                "position": pos,
                "shape": shape,
                "offset": offset
            })

        # 应用后处理检查来修复任何可能的重叠
        fixed_count = self.check_and_fix_overlaps(master_obj)
        if fixed_count > 0:
            # 如果进行了修复，再次检查一遍以处理级联重叠
            self.check_and_fix_overlaps(master_obj)

        # Record growth history
        generation_history = []
        for pos in growth_order:
            generation_history.append({
                "position": pos,
                "shape": position_shapes[pos],
                "offset": position_offsets[pos]
            })

        # Store history as object property
        master_obj["growth_history"] = str(generation_history)
        master_obj["seed"] = seed

        return master_obj

    def check_and_fix_overlaps(self, master_obj):
        """
        检查并修复形状中重叠的方块

        Args:
            master_obj: 包含所有方块的主对象

        Returns:
            修复的重叠数量
        """
        blocks = list(master_obj.children)
        if len(blocks) <= 1:
            return 0  # 没有或只有一个方块，不需要检查

        # 设置一个更小的阈值来检测重叠
        overlap_threshold = 0.001

        # 跟踪已修复的重叠数量
        fixed_count = 0

        # 对每对方块进行检查
        for i in range(len(blocks)):
            block_i = blocks[i]

            # 获取方块i的世界坐标框
            i_world_matrix = block_i.matrix_world
            i_bound_box = [i_world_matrix @
                           mathutils.Vector(v) for v in block_i.bound_box]
            i_min = mathutils.Vector((min(v.x for v in i_bound_box),
                                     min(v.y for v in i_bound_box),
                                     min(v.z for v in i_bound_box)))
            i_max = mathutils.Vector((max(v.x for v in i_bound_box),
                                     max(v.y for v in i_bound_box),
                                     max(v.z for v in i_bound_box)))

            for j in range(i+1, len(blocks)):
                block_j = blocks[j]

                # 获取方块j的世界坐标框
                j_world_matrix = block_j.matrix_world
                j_bound_box = [j_world_matrix @
                               mathutils.Vector(v) for v in block_j.bound_box]
                j_min = mathutils.Vector((min(v.x for v in j_bound_box),
                                         min(v.y for v in j_bound_box),
                                         min(v.z for v in j_bound_box)))
                j_max = mathutils.Vector((max(v.x for v in j_bound_box),
                                         max(v.y for v in j_bound_box),
                                         max(v.z for v in j_bound_box)))

                # 检查边界框是否重叠(AABB碰撞检测)
                overlap = not (i_max.x < j_min.x or i_min.x > j_max.x or
                               i_max.y < j_min.y or i_min.y > j_max.y or
                               i_max.z < j_min.z or i_min.z > j_max.z)

                # 如果有重叠，尝试修复
                if overlap:
                    # 计算重叠区域的中心
                    overlap_min = mathutils.Vector((max(i_min.x, j_min.x),
                                                    max(i_min.y, j_min.y),
                                                    max(i_min.z, j_min.z)))
                    overlap_max = mathutils.Vector((min(i_max.x, j_max.x),
                                                    min(i_max.y, j_max.y),
                                                    min(i_max.z, j_max.z)))
                    overlap_center = (overlap_min + overlap_max) / 2

                    # 计算重叠程度
                    overlap_size = overlap_max - overlap_min
                    overlap_volume = overlap_size.x * overlap_size.y * overlap_size.z

                    # 判断重叠是否显著(避免微小重叠导致不必要的调整)
                    if overlap_volume > overlap_threshold:
                        # 获取两个方块的中心
                        i_center = (i_min + i_max) / 2
                        j_center = (j_min + j_max) / 2

                        # 计算从重叠中心到每个方块中心的方向向量
                        dir_i = (i_center - overlap_center).normalized()
                        dir_j = (j_center - overlap_center).normalized()

                        # 确定哪个方块更容易移动(选择立方体而不是长方体)
                        i_is_cube = (abs(block_i.dimensions.x - block_i.dimensions.y) < 0.1 and
                                     abs(block_i.dimensions.x - block_i.dimensions.z) < 0.1)
                        j_is_cube = (abs(block_j.dimensions.x - block_j.dimensions.y) < 0.1 and
                                     abs(block_j.dimensions.x - block_j.dimensions.z) < 0.1)

                        # 如果一个是立方体另一个是长方体，移动立方体；否则移动较小的一个
                        move_i = False
                        if i_is_cube and not j_is_cube:
                            move_i = True
                        elif not i_is_cube and j_is_cube:
                            move_i = False
                        else:
                            # 两个都是立方体或都是长方体，移动体积较小的
                            i_volume = block_i.dimensions.x * block_i.dimensions.y * block_i.dimensions.z
                            j_volume = block_j.dimensions.x * block_j.dimensions.y * block_j.dimensions.z
                            move_i = i_volume <= j_volume

                        # 计算移动距离(基于重叠程度，但最小为0.05)
                        move_dist = max(0.05, overlap_size.length * 0.6)

                        # 执行移动
                        if move_i:
                            # 移动方块i
                            block_i.location += dir_i * move_dist
                        else:
                            # 移动方块j
                            block_j.location += dir_j * move_dist

                        # 更新场景以确保修改生效
                        bpy.context.view_layer.update()
                        fixed_count += 1

                        # 如果需要，重新计算方块i的边界框(如果它被移动了)
                        if move_i:
                            i_world_matrix = block_i.matrix_world
                            i_bound_box = [
                                i_world_matrix @ mathutils.Vector(v) for v in block_i.bound_box]
                            i_min = mathutils.Vector((min(v.x for v in i_bound_box),
                                                      min(v.y for v in i_bound_box),
                                                      min(v.z for v in i_bound_box)))
                            i_max = mathutils.Vector((max(v.x for v in i_bound_box),
                                                      max(v.y for v in i_bound_box),
                                                      max(v.z for v in i_bound_box)))

        if fixed_count > 0:
            print(f"已修复 {fixed_count} 个重叠问题")

        return fixed_count

    def create_summary_file(self, meta_files):
        """Create a summary file with info about all generated questions"""
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
        """Generate a complete dataset of questions"""
        start_time = time.time()
        print(
            f"Starting dataset generation: {self.config['num_questions']} questions")

        try:
            # Initialize scene
            self.clear_scene()
            camera = self.setup_scene()

            # Generate each question
            generated_files = []
            for i in range(self.config['num_questions']):
                try:
                    q_id = f"question_{i:04d}"
                    meta_file = self.generate_question(q_id)

                    if meta_file:  # 只有在成功生成时才添加
                        generated_files.append(meta_file)
                    else:
                        print(f"警告: 问题 {q_id} 生成失败，跳过")

                    # Progress report
                    if (i+1) % 5 == 0 or i == self.config['num_questions'] - 1:
                        elapsed = time.time() - start_time
                        avg_time = elapsed / (i+1)
                        remaining = avg_time * \
                            (self.config['num_questions'] - i - 1)
                        print(f"Progress: {i+1}/{self.config['num_questions']} questions " +
                              f"({elapsed:.1f}s elapsed, ~{remaining:.1f}s remaining)")
                except Exception as e:
                    print(f"生成问题 {q_id} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            # Generate a summary file
            if generated_files:
                summary_file = self.create_summary_file(generated_files)
                total_time = time.time() - start_time
                print(
                    f"Dataset generation complete in {total_time:.1f} seconds")
                print(f"Generated {len(generated_files)} questions")
                print(f"Summary file created: {summary_file}")
                return generated_files, summary_file
            else:
                print("警告: 没有成功生成任何问题")
                return [], None

        except Exception as e:
            print(f"数据集生成过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return [], None

    def find_best_view(self, views, cubes, camera, prefer_isometric=True, iso_bonus=2.0, auto_generate=False, num_candidates=12):
        """
        找到最佳视角，智能评估形状结构特征和视角质量

        Args:
            views: 可选的视角列表
            cubes: 要显示的方块列表
            camera: 相机对象
            prefer_isometric: 是否优先考虑等轴测视角(True)还是纯粹按可见方块数(False)
            iso_bonus: 等轴测视角的加分倍数，默认为2.0(加倍)
            auto_generate: 是否自动生成额外的视角候选
            num_candidates: 自动生成多少个视角候选

        Returns:
            最佳视角和可见方块数量
        """
        if not cubes:
            # 如果没有方块，返回第一个视角或None
            return (views[0], 0) if views else (None, 0)

        # 获取形状特征
        shape_center = self.get_shape_center(cubes)
        shape_extent = self.get_shape_extent(cubes)

        # 如果开启自动生成，创建额外的视角候选
        candidate_views = list(views)  # 从原有视角开始
        if auto_generate and len(cubes) > 0:
            # 生成多样化的视角候选
            additional_views = self.generate_view_candidates(
                shape_center,
                shape_extent,
                num_candidates=num_candidates
            )
            candidate_views.extend(additional_views)

        # 缓存视角评分
        view_cache = {}

        # 评估每个视角的可见度
        view_scores = []
        for view in candidate_views:
            # 检查缓存
            cache_key = str(view["pos"]) + str(view["look_at"])
            if cache_key in view_cache:
                visible_count, visible_areas = view_cache[cache_key]
            else:
                # 获取可见性信息
                visible_count, visible_areas = self.evaluate_visibility(
                    view, cubes, camera)
                view_cache[cache_key] = (visible_count, visible_areas)

            # 基础分数是可见方块数量
            base_score = visible_count

            # 计算总方块量权重 - 如果可见的方块占总数比例大，增加得分
            total_blocks = len(cubes)
            visibility_ratio = visible_count / total_blocks if total_blocks > 0 else 0

            # 计算形状中心到相机方向与形状主轴的夹角
            view_pos = mathutils.Vector(view["pos"])
            view_direction = (
                view_pos - mathutils.Vector(shape_center)).normalized()

            # 相机位置沿不同轴分量平衡性加分
            # 在所有三个轴上都有明显分量的视角能更好地展示3D结构
            axis_balance = min(abs(view_direction.x), abs(
                view_direction.y), abs(view_direction.z))
            axis_balance_score = axis_balance * 5.0  # 平衡视角加分

            # 考虑形状的主要延展方向
            extent_max = max(shape_extent)
            extent_min = min(shape_extent)
            if extent_max > 0:
                shape_elongation = (extent_max - extent_min) / extent_max
            else:
                shape_elongation = 0

            # 对细长形状，尝试找到能看到延展方向的视角
            elongation_score = 0
            if shape_elongation > 0.3:  # 如果形状明显沿某个方向延展
                # 找出最长轴
                if shape_extent[0] == extent_max:  # X轴最长
                    elongation_score = abs(
                        view_direction.y) + abs(view_direction.z)
                elif shape_extent[1] == extent_max:  # Y轴最长
                    elongation_score = abs(
                        view_direction.x) + abs(view_direction.z)
                else:  # Z轴最长
                    elongation_score = abs(
                        view_direction.x) + abs(view_direction.y)
                elongation_score *= 3.0 * shape_elongation  # 延展方向可见性加分

            # 综合评分
            final_score = (
                base_score * 1.0 +                # 基础可见方块数
                visible_areas * 1 +             # 可见表面积
                visibility_ratio * 10.0 +         # 可见比例
                axis_balance_score +              # 视角平衡性
                elongation_score                  # 展示形状延展方向
            )

            # 等轴测视角加分
            is_iso = "iso" in view.get("name", "").lower()
            if prefer_isometric and is_iso:
                final_score *= iso_bonus

            view_scores.append((view, final_score, visible_count))

        # 按最终分数排序
        view_scores.sort(key=lambda x: x[1], reverse=True)

        if not view_scores:
            return None, 0

        # 返回最佳视角和其实际可见方块数
        best_view, _, actual_visible = view_scores[0]

        return best_view, actual_visible

    def generate_view_candidates(self, shape_center, shape_extent, num_candidates=12, distance_factor=1.2):
        """生成多样化的视角候选

        Args:
            shape_center: 形状的几何中心坐标 (x, y, z)
            shape_extent: 形状在三个坐标轴上的延展范围 (x_extent, y_extent, z_extent)
            num_candidates: 要生成的视角候选数量
            distance_factor: 相机距离因子，控制相机离形状中心的距离

        Returns:
            视角候选列表，每个视角包含 name, pos, look_at
        """
        views = []

        # 计算相机距离基于形状尺寸
        max_extent = max(shape_extent)
        if max_extent <= 0:
            max_extent = 5.0  # 默认值

        # 基础相机距离，考虑形状大小
        base_distance = max_extent * 4.0 * distance_factor

        # 1. 生成黄金螺旋分布的视角 - 在球面上均匀分布点
        phi = math.pi * (3. - math.sqrt(5.))  # 黄金角
        for i in range(num_candidates):
            y = 1 - (i / float(num_candidates - 1)) * \
                2 if num_candidates > 1 else 0  # y从1到-1
            radius = math.sqrt(1 - y * y)  # 半径在xz平面

            theta = phi * i  # 黄金角旋转

            # 计算球面坐标
            x = math.cos(theta) * radius
            z = math.sin(theta) * radius

            # 缩放到合适的距离
            camera_pos = (
                shape_center[0] + x * base_distance,
                shape_center[1] + y * base_distance,
                shape_center[2] + z * base_distance
            )

            # 创建视角
            view = {
                "name": f"auto_view_{i}",
                "pos": camera_pos,
                "look_at": shape_center
            }
            views.append(view)

        # 2. 额外添加几个沿主轴分布的视角
        # 主轴的重要性顺序基于形状延展
        axes_priority = sorted(
            [(0, shape_extent[0]), (1, shape_extent[1]), (2, shape_extent[2])],
            key=lambda x: x[1],
            reverse=True
        )

        # 根据主轴的延展度，添加更多该轴的视角
        for axis_index, extent in axes_priority:
            # 计算轴的权重 - 延展度越大权重越高
            axis_weight = extent / max_extent if max_extent > 0 else 1/3
            # 该轴分配的视角数量
            axis_views = min(
                3, max(1, round(num_candidates * axis_weight / 3)))

            for i in range(axis_views):
                # 计算在该轴上的角度
                angle = math.pi * (i+1) / (axis_views+1)  # 将角度均匀分布

                # 根据不同轴生成不同的视角位置
                if axis_index == 0:  # X轴
                    x = math.cos(angle) * base_distance
                    y = math.sin(angle) * base_distance * 0.8
                    z = math.sin(angle + math.pi/4) * base_distance * 0.6
                    camera_pos = (
                        shape_center[0] + x, shape_center[1] + y, shape_center[2] + z)
                elif axis_index == 1:  # Y轴
                    x = math.sin(angle) * base_distance * 0.8
                    y = math.cos(angle) * base_distance
                    z = math.sin(angle + math.pi/4) * base_distance * 0.6
                    camera_pos = (
                        shape_center[0] + x, shape_center[1] + y, shape_center[2] + z)
                else:  # Z轴
                    x = math.sin(angle) * base_distance * 0.8
                    y = math.sin(angle + math.pi/4) * base_distance * 0.6
                    z = math.cos(angle) * base_distance
                    camera_pos = (
                        shape_center[0] + x, shape_center[1] + y, shape_center[2] + z)

                # 添加视角
                view = {
                    "name": f"axis_{axis_index}_view_{i}",
                    "pos": camera_pos,
                    "look_at": shape_center
                }
                views.append(view)

        # 3. 特殊添加几个近似等轴测视角
        isometric_directions = [
            (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
            (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)
        ]
        for i, direction in enumerate(isometric_directions):
            # 标准化方向向量
            norm = math.sqrt(direction[0]**2 +
                             direction[1]**2 + direction[2]**2)
            if norm > 0:
                normalized = tuple(d/norm for d in direction)

                # 计算相机位置
                camera_pos = (
                    shape_center[0] + normalized[0] * base_distance,
                    shape_center[1] + normalized[1] * base_distance,
                    shape_center[2] + normalized[2] * base_distance
                )

                # 创建视角
                view = {
                    "name": f"auto_iso_view_{i}",
                    "pos": camera_pos,
                    "look_at": shape_center
                }
                views.append(view)

        return views

    def get_shape_center(self, blocks):
        """计算一组方块的几何中心

        Args:
            blocks: 块对象列表

        Returns:
            (x, y, z) 形式的中心点坐标
        """
        if not blocks:
            return (0, 0, 0)

        # 计算所有块的平均位置
        sum_x, sum_y, sum_z = 0, 0, 0
        for block in blocks:
            pos = block.location
            sum_x += pos.x
            sum_y += pos.y
            sum_z += pos.z

        count = len(blocks)
        return (sum_x / count, sum_y / count, sum_z / count)

    def get_shape_extent(self, blocks):
        """计算形状在三个主轴方向上的延展范围

        Args:
            blocks: 块对象列表

        Returns:
            (x_extent, y_extent, z_extent) 沿三个轴的延展大小
        """
        if not blocks:
            return (0, 0, 0)

        # 初始化最小最大值
        min_x = max_x = blocks[0].location.x
        min_y = max_y = blocks[0].location.y
        min_z = max_z = blocks[0].location.z

        # 找出各轴的最大最小值
        for block in blocks:
            x, y, z = block.location

            # 考虑方块尺寸
            if hasattr(block, "dimensions"):
                half_x = block.dimensions.x / 2
                half_y = block.dimensions.y / 2
                half_z = block.dimensions.z / 2
            else:
                half_x = half_y = half_z = 0.5  # 默认尺寸

            min_x = min(min_x, x - half_x)
            max_x = max(max_x, x + half_x)
            min_y = min(min_y, y - half_y)
            max_y = max(max_y, y + half_y)
            min_z = min(min_z, z - half_z)
            max_z = max(max_z, z + half_z)

        # 返回三个轴的延展范围
        return (max_x - min_x, max_y - min_y, max_z - min_z)

    def is_top_view_different(self, original_positions, distractor_blocks):
        """
        检查两个形状在俯视图中是否有明显区别
        返回True表示明显不同，False表示相似

        Args:
            original_positions: 存储的原始块位置集合 (x,y) 元组
            distractor_blocks: 干扰项的块对象列表
        """
        # 原始形状的位置已经是预先存储的集合
        original_top_visible = original_positions

        # 获取干扰项中从顶部可见的块位置
        distractor_top_visible = set()
        for block in distractor_blocks:
            pos = block.location
            x, y = round(pos.x), round(pos.y)
            distractor_top_visible.add((x, y))

        # 计算差异度: 不同的坐标数量除以总坐标数量
        diff_coords = original_top_visible.symmetric_difference(
            distractor_top_visible)
        total_coords = original_top_visible.union(distractor_top_visible)

        if not total_coords:
            return False  # 避免除以零

        difference_ratio = len(diff_coords) / len(total_coords)

        # 差异率至少要0.3才算明显不同
        return difference_ratio >= 0.3

    def check_collision(self, obj1, obj2, threshold=None):
        """
        检查两个对象之间是否有碰撞

        Args:
            obj1: 第一个对象
            obj2: 第二个对象
            threshold: 两个对象之间的最小距离阈值，如果为None则使用配置中的值

        Returns:
            Boolean: 如果碰撞返回True，否则返回False
        """
        if threshold is None:
            threshold = self.config.get("collision_threshold", 0.05)

        if not hasattr(obj1, "bound_box") or not hasattr(obj2, "bound_box"):
            return False

        # 获取对象的世界矩阵
        mat1 = obj1.matrix_world
        mat2 = obj2.matrix_world

        # 获取边界框的顶点（8个顶点）
        bbox1 = [mat1 @ mathutils.Vector(v) for v in obj1.bound_box]
        bbox2 = [mat2 @ mathutils.Vector(v) for v in obj2.bound_box]

        # 计算边界框的最小/最大值
        min1 = mathutils.Vector((min(v.x for v in bbox1), min(
            v.y for v in bbox1), min(v.z for v in bbox1)))
        max1 = mathutils.Vector((max(v.x for v in bbox1), max(
            v.y for v in bbox1), max(v.z for v in bbox1)))
        min2 = mathutils.Vector((min(v.x for v in bbox2), min(
            v.y for v in bbox2), min(v.z for v in bbox2)))
        max2 = mathutils.Vector((max(v.x for v in bbox2), max(
            v.y for v in bbox2), max(v.z for v in bbox2)))

        # 应用阈值扩展边界框
        min1 -= mathutils.Vector((threshold, threshold, threshold))
        max1 += mathutils.Vector((threshold, threshold, threshold))

        # 执行AABB（轴对齐边界框）碰撞检测
        # 如果一个边界框的最小值大于另一个的最大值，或者最大值小于另一个的最小值，则没有碰撞
        if (max1.x < min2.x or min1.x > max2.x or
            max1.y < min2.y or min1.y > max2.y or
                max1.z < min2.z or min1.z > max2.z):
            return False

        return True

    def generate_distractor(self, original_shape, growth_history=None, distractor_seed=None, difficulty=None):
        """生成一个干扰项形状，可以是原始形状的变体或完全不同的形状

        Args:
            original_shape: 原始形状对象
            growth_history: 原始形状的生长历史
            distractor_seed: 用于随机数生成的种子
            difficulty: 难度参数(0.0-1.0)，越高生成的干扰项越难区分

        Returns:
            干扰项主对象
        """
        if difficulty is None:
            difficulty = self.config.get('distractor_difficulty', 0.5)

        # 使用不同的种子创建干扰项
        if distractor_seed is not None:
            random.seed(distractor_seed)

        # 清除现有对象
        self.clear_question_objects()

        # 50%的概率使用变体，50%的概率使用全新形状
        use_variant = random.random() < 0.5

        if use_variant and growth_history:
            # 创建形状的变体版本
            # 移除一些块并重新生长
            num_blocks = len(growth_history)
            blocks_to_remove = int(
                num_blocks * (0.2 + difficulty * 0.3))  # 移除20%-50%的块
            blocks_to_remove = max(
                1, min(blocks_to_remove, num_blocks - 1))  # 至少保留一个块

            # 创建变体
            distractor_obj = self.create_combination_shape(
                use_rectangular=self.config.get('use_rectangular_prisms'),
                rect_prob=self.config.get('rectangular_prism_prob'),
                seed=distractor_seed,
                remove_blocks=blocks_to_remove,
                growth_history=growth_history
            )
        else:
            # 创建全新的形状
            distractor_obj = self.create_combination_shape(
                use_rectangular=self.config.get('use_rectangular_prisms'),
                rect_prob=self.config.get('rectangular_prism_prob'),
                seed=distractor_seed
            )

        return distractor_obj


class RotationMatchingGenerator(SpatialReasoningGeneratorBase):
    """3D rotation matching question generator"""

    def __init__(self, output_dir=None, config=None):
        """
        Initialize the generator with configuration parameters.

        Args:
            output_dir (str): Directory to save generated files. If None, a default is used.
            config (dict): Configuration dictionary. If None, default values are used.
        """
        super().__init__("3D_rotation", output_dir, config)
        # 确保没有top_view属性
        self._has_top_view = False  # 添加标记以确认没有俯视图

    def generate_question(self, q_id):
        """Generate a single 3D rotation matching question"""
        print(f"Generating question {q_id}...")

        # Clear any existing objects
        self.clear_question_objects()

        # Create seed based on question ID for reproducibility
        question_seed = hash(q_id) % 10000

        # Create the 3D shape
        original_obj = self.create_combination_shape(
            use_rectangular=self.config.get('use_rectangular_prisms'),
            rect_prob=self.config.get('rectangular_prism_prob'),
            seed=question_seed
        )

        # Get growth history for creating distractors
        growth_history_str = original_obj.get("growth_history", "[]")
        growth_history = eval(growth_history_str)

        # Get all children (cubes) in the shape
        cubes = [obj for obj in original_obj.children]

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

        # 设置相机到问题视角
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

        # Render question image
        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)

        # Prepare options list
        options = []
        used_views = set()  # Track used views to avoid duplicates
        used_views.add(question_view["name"])  # 避免答案视角与问题视角相同

        # ===== 正确答案：相同形状，不同视角 =====
        # 从剩余视角中选择一个用于正确答案
        remaining_views = [
            v for v in self.iso_views if v["name"] not in used_views]
        if not remaining_views:
            # 如果没有剩余视角，重用任意等轴测视角
            remaining_views = self.iso_views

        correct_view = random.choice(remaining_views)
        used_views.add(correct_view["name"])

        # 设置相机到正确答案视角（有随机偏移）
        self.set_camera_to_view(cam, correct_view, add_randomness=True)

        # 为正确答案也应用视角调整：确保物体居中
        shape_center = self.get_shape_center(cubes)
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam.rotation_euler = rot_quat.to_euler()
        bpy.context.view_layer.update()

        correct_location = cam.location.copy()
        correct_rotation = cam.rotation_euler.copy()

        # 渲染正确答案图像
        correct_img = os.path.join(self.output_dir, f"{q_id}_A0.png")
        self.render_image(correct_img)

        # 添加正确答案到选项列表
        options.append({
            "image": correct_img,
            "label": "correct",
            "view_name": correct_view["name"],
            "camera_location": tuple(correct_location),
            "camera_rotation": tuple(correct_rotation),
            "seed": question_seed  # 正确答案使用和问题相同的种子
        })

        # ===== 干扰项：不同形状或修改过的形状 =====
        for i in range(self.config['num_distractors']):
            # 清空当前对象
            self.clear_question_objects()

            # 生成干扰项种子（确保与问题种子不同）
            distractor_seed = question_seed + i + 1000

            # 使用基类的干扰项生成方法
            distractor_obj = self.generate_distractor(
                original_shape=original_obj,
                growth_history=growth_history,
                distractor_seed=distractor_seed
            )

            # 干扰项可以使用任意等轴测视角，不需要避开已使用的视角
            distractor_view = random.choice(self.iso_views)

            # 设置相机到干扰项视角
            self.set_camera_to_view(cam, distractor_view, add_randomness=True)

            # 为干扰项也应用视角调整：确保物体居中
            # 获取干扰项的形状中心
            distractor_cubes = [obj for obj in distractor_obj.children]
            if distractor_cubes:
                distractor_center = self.get_shape_center(distractor_cubes)
                direction = mathutils.Vector(distractor_center) - cam.location
                rot_quat = direction.to_track_quat('-Z', 'Y')
                cam.rotation_euler = rot_quat.to_euler()
                bpy.context.view_layer.update()

            distractor_location = cam.location.copy()
            distractor_rotation = cam.rotation_euler.copy()

            # 渲染干扰项图像
            distractor_img = os.path.join(
                self.output_dir, f"{q_id}_A{i+1}.png")
            self.render_image(distractor_img)

            # 添加干扰项到选项列表
            options.append({
                "image": distractor_img,
                "label": f"distractor_{i+1}",
                "view_name": distractor_view["name"],
                "distractor_type": "different_view" if distractor_view["name"] != correct_view["name"] else "correct_view",
                "camera_location": tuple(distractor_location),
                "camera_rotation": tuple(distractor_rotation),
                "seed": distractor_seed  # 干扰项使用不同的种子
            })

            # 清理对象，准备下一个干扰项
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
            "options": options
        }

        # Write metadata file
        meta_path = os.path.join(self.output_dir, f"{q_id}.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        return meta_path


class ViewMatchingGenerator(SpatialReasoningGeneratorBase):
    """3D View Matching Generator"""

    def __init__(self, output_dir=None, config=None):
        """Initialize the generator with configuration parameters"""
        # 更改默认目录名
        if output_dir is None:
            output_dir = "blender_dataset/view_matching"

        super().__init__("view_matching", output_dir, config)

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

    def generate_question(self, q_id):
        """Generate a single 3D view matching question"""
        print(f"Generating question {q_id}...")

        # Clear any existing objects
        self.clear_question_objects()

        # Create seed based on question ID for reproducibility
        question_seed = hash(q_id) % 10000

        # Create the 3D shape
        original_obj = self.create_combination_shape(
            use_rectangular=self.config.get('use_rectangular_prisms'),
            rect_prob=self.config.get('rectangular_prism_prob'),
            seed=question_seed
        )

        # Get growth history for creating distractors
        growth_history_str = original_obj.get("growth_history", "[]")
        growth_history = eval(growth_history_str)

        # Get all children (cubes) in the shape
        cubes = [obj for obj in original_obj.children]

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

        # 随机选择一个正交视图作为正确答案
        correct_view = random.choice(self.orthographic_views)

        # 创建视图指示器（在渲染问题图像前）
        # 使用形状的中心位置创建指示器
        shape_center = self.get_shape_center(cubes)
        view_indicator = self.create_view_indicator(
            correct_view["name"], scene_center=shape_center)

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
        distractor_positions_list = []  # 存储所有干扰项的位置信息
        used_view_names = set()  # 记录已使用的视图名称，避免重复

        used_view_names.add(correct_view["name"])

        # 计算原始形状在正确答案视图中的投影位置
        original_projected_positions = self.get_projected_positions(
            cubes, correct_view["name"])

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

                    # 检查这个视图的投影是否与正确答案有足够差异
                    distractor_positions = self.get_projected_positions(
                        distractor_blocks, distractor_view["name"])

                    # 如果与正确答案的投影差异不够，则尝试使用其他方法生成干扰项
                    if not self.is_view_different(
                            original_projected_positions, distractor_blocks, distractor_view["name"]):
                        # 如果差异不够，切换到修改形状的方法
                        use_original_with_different_view = False
                        print(
                            f"视图 {distractor_view['name']} 的投影差异不足，切换到修改形状策略")
                    else:
                        # 记录干扰项使用的视图
                        used_view_name = distractor_view["name"]

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

                    # 检查与已有干扰项的差异
                    distractor_positions = self.get_projected_positions(
                        distractor_blocks, correct_view["name"])

                    is_different_from_existing = True
                    for existing_positions in distractor_positions_list:
                        diff_coords = distractor_positions.symmetric_difference(
                            existing_positions)
                        total_coords = distractor_positions.union(
                            existing_positions)
                        if not total_coords:
                            is_different_from_existing = False
                            break
                        difference_ratio = len(diff_coords) / len(total_coords)
                        if difference_ratio < 0.35:  # 增加差异阈值
                            is_different_from_existing = False
                            break

                    # 只有两个条件都满足才接受这个干扰项
                    is_acceptable = is_different and is_different_from_existing

                    if is_acceptable or attempt == max_attempts:
                        # 如果接受，记录这个干扰项的位置
                        if is_acceptable:
                            distractor_positions_list.append(
                                distractor_positions)
                            used_distractor_seeds.add(distractor_seed)
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

    def get_projected_positions(self, blocks, view_name):
        """
        根据视图名称获取块的投影位置集合

        Args:
            blocks: 块对象列表
            view_name: 视图名称

        Returns:
            投影位置的集合
        """
        positions = set()
        for block in blocks:
            pos = block.location

            # 根据视图类型确定投影平面
            if "top" in view_name:
                # 顶视图: 保留x和y坐标
                projection = (round(pos.x), round(pos.y))
            elif "front" in view_name:
                # 前视图: 保留x和z坐标
                projection = (round(pos.x), round(pos.z))
            elif "back" in view_name:
                # 后视图: 保留x和z坐标，但x轴镜像
                projection = (-round(pos.x), round(pos.z))
            elif "right" in view_name:
                # 右视图: 保留y和z坐标
                projection = (round(pos.y), round(pos.z))
            elif "left" in view_name:
                # 左视图: 保留y和z坐标，但y轴镜像
                projection = (-round(pos.y), round(pos.z))
            else:
                # 其他视图默认使用xy平面
                projection = (round(pos.x), round(pos.y))

            positions.add(projection)

        return positions

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
        # 获取干扰项形状在指定视图下的投影位置
        distractor_positions = self.get_projected_positions(
            distractor_blocks, view_name)

        # 计算差异度: 不同的坐标数量除以总坐标数量
        diff_coords = original_positions.symmetric_difference(
            distractor_positions)
        total_coords = original_positions.union(distractor_positions)

        if not total_coords:
            return False  # 避免除以零

        difference_ratio = len(diff_coords) / len(total_coords)

        # 输出差异率，用于调试
        print(f"视图 {view_name} 的投影差异率: {difference_ratio:.2f}")

        # 差异率至少要达到指定阈值才算明显不同
        return difference_ratio >= min_difference

    def create_view_indicator(self, view_name, scene_center=(0, 0, 0), scale=0.7, color=(0, 0.5, 1, 1)):
        """创建视图方向指示器（单个锥体）

        Args:
            view_name: 视图名称，如 "top_view"
            scene_center: 场景中心点
            scale: 指示器的大小比例
            color: 指示器的颜色 (RGBA)

        Returns:
            创建的指示器对象
        """
        # 创建一个空物体作为指示器的父对象
        indicator = bpy.data.objects.new("ViewIndicator", None)
        bpy.context.scene.collection.objects.link(indicator)

        # 设置指示器位置在场景外围但在相机视野内
        cx, cy, cz = scene_center

        # 根据网格边界(-2到2)调整视角指示器位置
        distance = 2.0  # 从中心到指示器的距离，略大于网格边界

        # 根据视图名称确定锥体位置
        if "top" in view_name:
            # 顶视图 - 从上方指向物体
            cone_pos = (cx, cy, cz + distance)
            cone_dir = (0, 0, 1)
        elif "front" in view_name:
            # 前视图 - 从前方指向物体
            cone_pos = (cx, cy - distance, cz)
            cone_dir = (0, -1, 0)
        elif "back" in view_name:
            # 后视图 - 从后方指向物体
            cone_pos = (cx, cy + distance, cz)
            cone_dir = (0, 1, 0)
        elif "right" in view_name:
            # 右视图 - 从右侧指向物体
            cone_pos = (cx + distance, cy, cz)
            cone_dir = (1, 0, 0)
        elif "left" in view_name:
            # 左视图 - 从左侧指向物体
            cone_pos = (cx - distance, cy, cz)
            cone_dir = (-1, 0, 0)
        else:
            # 默认位置
            cone_pos = (cx, cy, cz + distance)
            cone_dir = (0, 0, 1)

        indicator.location = cone_pos

        # 创建锥体（高锥度）- 锥体的尖头指向物体中心
        cone_height = 1 * scale
        cone_radius = 0.2 * scale

        # 创建锥体，锥体base在远离物体的一侧，尖头指向物体
        bpy.ops.mesh.primitive_cone_add(
            vertices=32,
            radius1=cone_radius,
            radius2=0,
            depth=cone_height,
            location=cone_pos
        )
        cone = bpy.context.active_object
        cone.name = "ViewDirectionCone"

        # 创建锥体材质
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

        # 应用材质到锥体
        cone.data.materials.append(arrow_mat)

        # 设置锥体不投射和不接收阴影
        # 通过调整材质节点来禁用阴影
        nodes = arrow_mat.node_tree.nodes
        principled = nodes.get("Principled BSDF")
        if principled:
            # 将Alpha设置为低值使其半透明但可见
            principled.inputs["Alpha"].default_value = 1.0
            # 将Transmission设置为0，防止投射阴影
            if "Transmission" in principled.inputs:
                principled.inputs["Transmission"].default_value = 0.0

        # 设置物体的可见性选项
        cone.hide_render = False  # 确保在渲染中可见
        cone.display_type = 'TEXTURED'  # 确保在视图中显示为纹理

        # 设置物体不可被选中
        cone.hide_select = True

        # 使用方向向量计算旋转
        # 锥体默认方向是z轴正方向，需要旋转使其指向目标
        from mathutils import Vector
        direction = Vector(cone_dir)

        # 使用to_track_quat使锥体的尖端指向物体中心
        # "Z"表示锥体的前向轴(尖端方向)，"Y"表示锥体的上方轴
        rot_quat = direction.to_track_quat('Z', 'Y')

        # 由于锥体默认尖端朝+Z方向，我们需要额外旋转180度使尖端朝向物体
        from mathutils import Matrix
        rot_mat = rot_quat.to_matrix().to_4x4()

        # 创建绕X轴旋转180度的矩阵
        rot_x = Matrix.Rotation(math.radians(180), 4, 'X')

        # 组合两个旋转
        final_rot = (rot_mat @ rot_x).to_euler()

        # 应用旋转
        cone.rotation_euler = final_rot

        # 将锥体设为指示器的子对象
        cone.parent = indicator

        return indicator


class CombinationGenerator(SpatialReasoningGeneratorBase):
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

    def create_segmented_shape(self, master_obj, spacing=2.0):
        """
        将完整形状分解为独立的组件，并排列展示

        Args:
            master_obj: 包含所有组件的主对象
            spacing: 组件之间的间距

        Returns:
            包含所有分离组件的列表
        """
        components = []

        # 获取所有子对象
        blocks = list(master_obj.children)

        # 记录原始位置以便后续恢复
        original_positions = []
        for block in blocks:
            original_positions.append((block.location.copy(), block.parent))

        # 创建新的空对象作为分离组件的父对象
        segmented_master = bpy.data.objects.new("SegmentedMaster", None)
        bpy.context.scene.collection.objects.link(segmented_master)

        # 获取组件数量
        total_blocks = len(blocks)

        # 计算每个组件的平均尺寸，用于动态调整间距
        avg_size_x = 0
        avg_size_y = 0
        avg_size_z = 0

        for block in blocks:
            if hasattr(block, "dimensions"):
                avg_size_x += block.dimensions.x
                avg_size_y += block.dimensions.y
                avg_size_z += block.dimensions.z

        if total_blocks > 0:
            avg_size_x /= total_blocks
            avg_size_y /= total_blocks
            avg_size_z /= total_blocks

            # 根据平均尺寸调整间距，确保间距至少是平均尺寸的1.5倍
            spacing = max(2.0, avg_size_x * 1.5)

        # 为每个组件设置位置
        for i, block in enumerate(blocks):
            # 取消原来的父级关系
            original_parent = block.parent
            block.parent = None

            # 创建新的父对象（包装器）
            wrapper = bpy.data.objects.new(f"Component_{i}", None)
            bpy.context.scene.collection.objects.link(wrapper)

            # 记录组件信息（暂时不设置位置）
            components.append({
                "wrapper": wrapper,
                "block": block,
                "original_index": i,
                "original_position": original_positions[i],
                "original_world_pos": block.matrix_world.translation.copy()
            })

            # 设置方块为包装器的子级
            block.parent = wrapper

            # 确保方块在包装器中心
            block.matrix_world.translation = components[i]["original_world_pos"]

            # 将包装器设为分离主对象的子级
            wrapper.parent = segmented_master

            # 更新场景以确保正确计算
            bpy.context.view_layer.update()

            # 计算最佳位置（避免重叠）
            optimal_pos = self.calculate_optimal_position(
                components, i, spacing)

            # 应用计算出的最佳位置
            wrapper.location = optimal_pos

            # 再次更新场景以应用新位置
            bpy.context.view_layer.update()

        # 最终更新场景以确保正确计算
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

    def generate_question(self, q_id):
        """生成一个3D形状拼装题目"""
        print(f"生成题目 {q_id}...")

        # 清除现有对象
        self.clear_question_objects()

        # 基于题目ID创建种子以确保可重现性
        question_seed = hash(q_id) % 10000

        # 创建初始形状 (使用生长算法)
        original_obj = self.create_combination_shape(
            use_rectangular=self.config.get('use_rectangular_prisms'),
            rect_prob=self.config.get('rectangular_prism_prob'),
            seed=question_seed
        )

        # 获取所有方块
        cubes = [obj for obj in original_obj.children]
        if not cubes:
            print("警告: 没有生成任何方块!")
            return None

        print(f"生成了 {len(cubes)} 个方块")

        # 保存相机初始位置
        cam = bpy.context.scene.camera
        initial_cam_location = cam.location.copy()
        initial_cam_rot = cam.rotation_euler.copy()

        # 扩大相机视场，确保能够看到更多内容
        try:
            if hasattr(cam.data, 'ortho_scale'):
                original_ortho_scale = cam.data.ortho_scale
                # 扩大为原来的1.5倍，确保视野足够宽
                cam.data.ortho_scale = 18  # 原来是12
        except Exception as e:
            print(f"调整相机视场失败: {e}")
            original_ortho_scale = 12

        # 使用find_best_view找到最佳视角，启用自动生成视角功能
        question_view, visible_count = self.find_best_view(
            self.iso_views, cubes, cam,
            prefer_isometric=True, auto_generate=True, num_candidates=8)
        print(f"选择视角: {question_view['name']} 可见方块数: {visible_count}")

        # 设置相机到问题视角
        self.set_camera_to_view(cam, question_view, add_randomness=True)

        # 缩小视角来放大物体，同时确保物体在视角中心
        # 计算形状的几何中心
        shape_center = self.get_shape_center(cubes)

        # 调整相机的look_at点指向形状中心，确保物体居中
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam.rotation_euler = rot_quat.to_euler()

        # 缩小ortho_scale来放大question图片中的物体
        cam.data.ortho_scale = 8.0  # 从原来的18缩小到8，放大物体显示

        # 更新场景以应用相机设置
        bpy.context.view_layer.update()

        question_location = cam.location.copy()
        question_rotation = cam.rotation_euler.copy()

        # 渲染题目图像 (完整形状)
        question_img = os.path.join(self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)

        # 添加对面视角的渲染
        # 计算对面视角 - 在等轴测视图中，对面视角是通过反转位置向量获得的
        opposite_view = question_view.copy()
        opposite_view["name"] = "opposite_" + question_view["name"]

        # 反转位置向量以获得对面视角
        pos_x, pos_y, pos_z = question_view["pos"]
        opposite_view["pos"] = (-pos_x, -pos_y, -pos_z)

        # 设置相机到对面视角
        self.set_camera_to_view(cam, opposite_view, add_randomness=False)

        # 同样调整对面视角的相机设置
        direction = mathutils.Vector(shape_center) - cam.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam.rotation_euler = rot_quat.to_euler()
        cam.data.ortho_scale = 8.0  # 保持与question图片相同的视角大小
        bpy.context.view_layer.update()

        opposite_location = cam.location.copy()
        opposite_rotation = cam.rotation_euler.copy()

        # 渲染对面视角图像
        opposite_img = os.path.join(self.output_dir, f"{q_id}_Q_opposite.png")
        self.render_image(opposite_img)

        # 恢复相机的ortho_scale设置，为后续选项图片渲染做准备
        cam.data.ortho_scale = 18  # 恢复到选项渲染所需的大视角

        # 将相机设置回问题视角
        cam.location = question_location
        cam.rotation_euler = question_rotation
        bpy.context.view_layer.update()

        # 将形状拆分为单个组件并排列展示
        components, segmented_master, original_positions = self.create_segmented_shape(
            original_obj)

        if not components:
            print("警告: 没有创建任何组件!")
            return None

        print(f"创建了 {len(components)} 个分离组件")

        # 选择一个随机组件作为干扰项
        distractor_index = random.randint(0, len(components) - 1)
        correct_component = components[distractor_index]

        # 备份组件列表，用于选项生成
        options = []

        # 确保场景更新以反映所有变化
        bpy.context.view_layer.update()

        # 创建一个基于问题视角的选项视角
        # 使用iso_front_top_left作为选项视角
        components_count = len(components)

        # 从预定义的视角列表中找到我们想用的视角
        front_top_left_view = None
        for view in self.iso_views:
            if view["name"] == "iso_front_top_right":
                front_top_left_view = view.copy()  # 复制一份，避免修改原始定义
                break

        if front_top_left_view is None:
            print("警告：找不到iso_front_top_left视角，使用默认视角")
            front_top_left_view = self.iso_views[0].copy()

        # 定义选项视角
        option_view = front_top_left_view
        option_view["name"] = "options_" + option_view["name"]  # 添加前缀以区分

        # 确定组件排列的中心点
        center_x = 0  # 组件排列是水平居中的
        center_y = 0
        center_z = 0

        # 修改look_at点以确保相机对准组件中心
        option_view["look_at"] = (center_x, center_y, center_z)

        # 根据组件数量调整相机距离
        distance_scale = max(1.2, components_count / 7.0)  # 组件越多，距离越远

        # 获取原始位置向量
        orig_pos = mathutils.Vector(option_view["pos"])

        # 计算从原点到相机的方向向量
        direction = orig_pos.normalized()

        # 调整距离
        new_distance = orig_pos.length * distance_scale

        # 设置新的相机位置
        new_pos = direction * new_distance
        option_view["pos"] = (new_pos.x, new_pos.y, new_pos.z)

        # 设置相机到选项视角
        self.set_camera_to_view(cam, option_view, add_randomness=False)

        # 更新场景以确保正确计算
        bpy.context.view_layer.update()

        # 1. 生成正确答案(所有原始组件)
        # 渲染正确答案图像
        correct_img = os.path.join(self.output_dir, f"{q_id}_A0.png")
        self.render_image(correct_img)

        # 添加正确答案到选项列表
        options.append({
            "image": correct_img,
            "label": "correct",
            "distractor_index": None,
            "camera_location": tuple(cam.location),
            "camera_rotation": tuple(cam.rotation_euler),
            "seed": question_seed
        })

        # 生成干扰项
        for i in range(self.config['num_distractors']):
            # 为当前干扰项计算一个不同的种子
            distractor_seed = question_seed + i + 1000

            # 创建干扰项 (替换一个组件) - 生成图像时不高亮显示干扰项
            distractor = self.create_distractor(
                correct_component, original_obj, distractor_seed, highlight_distractor=False)

            # 确保场景更新以反映所有变化
            bpy.context.view_layer.update()

            # 渲染干扰项图像 - 使用相同的视角
            distractor_img = os.path.join(
                self.output_dir, f"{q_id}_A{i+1}.png")
            self.render_image(distractor_img)

            # 添加干扰项到选项列表
            options.append({
                "image": distractor_img,
                "label": f"distractor_{i+1}",
                "distractor_index": distractor["original_index"],
                "distractor_seed": distractor_seed,
                "camera_location": tuple(cam.location),
                "camera_rotation": tuple(cam.rotation_euler)
            })

            # 恢复原始组件
            self.restore_from_distractor(distractor)

            # 如果需要生成更多干扰项，可以选择不同的组件
            if i < self.config['num_distractors'] - 1:
                # 在剩余组件中选择一个不同的组件
                remaining_indices = [j for j in range(len(components))
                                     if j != distractor_index]
                if remaining_indices:  # 确保有可选的组件
                    distractor_index = random.choice(remaining_indices)
                    correct_component = components[distractor_index]

        # 恢复原始形状
        for component in components:
            block = component["block"]
            wrapper = component["wrapper"]

            # 将方块父级关系重置
            block.parent = None

            # 删除包装器
            bpy.data.objects.remove(wrapper, do_unlink=True)

        # 删除分段主对象
        bpy.data.objects.remove(segmented_master, do_unlink=True)

        # 恢复相机视场
        try:
            if hasattr(cam.data, 'ortho_scale'):
                cam.data.ortho_scale = original_ortho_scale
        except Exception as e:
            print(f"恢复相机视场失败: {e}")

        # 重置相机
        cam.location = initial_cam_location
        cam.rotation_euler = initial_cam_rot

        # 创建元数据
        meta = {
            "question_id": q_id,
            "question_image": question_img,
            "opposite_view_image": opposite_img,  # 添加对面视角图像路径
            "seed": question_seed,
            "timestamp": datetime.now().isoformat(),
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
            # 第一个组件放在中心
            return (0, 0, 0)

        new_wrapper = components[new_component_index]["wrapper"]
        new_block = components[new_component_index]["block"]

        # 获取现有组件位置的边界
        existing_positions = []
        for i in range(new_component_index):
            comp = components[i]
            wrapper = comp["wrapper"]
            existing_positions.append(wrapper.location)

        # 如果没有现有组件，返回中心位置
        if not existing_positions:
            return (0, 0, 0)

        # 计算组件的平均尺寸
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
            avg_size = 2.0  # 默认值

        # 设置基础网格间距
        grid_spacing = max(spacing, avg_size * 1.5)

        # 定义搜索范围
        max_search_distance = len(components) * grid_spacing * 0.5

        # 初始尝试行列
        row = 0
        col = 0
        spiral_direction = 0  # 0:右, 1:下, 2:左, 3:上
        spiral_steps = 1
        steps_taken = 0
        direction_changes = 0

        while True:
            # 计算位置
            x = col * grid_spacing
            y = 0  # 保持y=0，在xz平面上排列
            z = -row * grid_spacing

            # 设置新位置
            test_pos = (x, y, z)

            # 检查是否有碰撞
            new_wrapper.location = test_pos

            # 更新场景以应用位置更改
            bpy.context.view_layer.update()

            # 检查与其他组件的碰撞
            collision = False
            for i in range(new_component_index):
                comp = components[i]
                if self.check_collision(new_block, comp["block"], threshold=spacing*0.3):
                    collision = True
                    break

            if not collision:
                return test_pos

            # 移动到下一个位置（螺旋模式）
            steps_taken += 1
            if steps_taken == spiral_steps:
                steps_taken = 0
                spiral_direction = (spiral_direction + 1) % 4
                direction_changes += 1
                if direction_changes == 2:
                    direction_changes = 0
                    spiral_steps += 1

            # 根据当前方向移动
            if spiral_direction == 0:  # 右
                col += 1
            elif spiral_direction == 1:  # 下
                row += 1
            elif spiral_direction == 2:  # 左
                col -= 1
            elif spiral_direction == 3:  # 上
                row -= 1

            # 防止无限循环
            if abs(x) > max_search_distance or abs(z) > max_search_distance:
                print(f"警告: 对组件 {new_component_index} 找不到无碰撞位置，使用默认网格位置")
                return (x, y, z)  # 返回当前尝试的位置


def main():
    """Example usage"""
    try:
        # Configuration
        config = {
            "num_questions": 5,
            'distractor_difficulty': 0.3,
            'num_distractors': 3,
            'num_cells_min': 5,
            'num_cells_max': 10,
            'rectangular_prism_prob': 0.5,
            'render_engine': 'CYCLES',  # 明确指定渲染引擎为CYCLES
            'ortho_scale': 18.0  # 指定正交相机视野大小
        }

        # rotation_matching_generator = RotationMatchingGenerator(
        #     output_dir="blender_dataset/3D_rotation",
        #     config=config
        # )

        # rotation_matching_generator.generate_dataset()

        # view_matching_generator = ViewMatchingGenerator(
        #     output_dir="blender_dataset/view_matching",
        #     config=config
        # )

        # view_matching_generator.generate_dataset()

        # # 使用组合生成器生成3D组装题目
        # combination_generator = CombinationGenerator(
        #     output_dir="blender_dataset/combination",
        #     config=config
        # )

        # combination_generator.generate_dataset()

        # 导入盒子折叠生成器
        import os
        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.append(current_dir)
        from box_folding_generator import BoxFoldingGenerator

        # 使用盒子折叠生成器生成题目
        box_folding_generator = BoxFoldingGenerator(
            output_dir="blender_dataset/box_folding",
            config=config
        )

        box_folding_generator.generate_dataset()

        print("Generation complete!")
    except Exception as e:
        print(f"执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
