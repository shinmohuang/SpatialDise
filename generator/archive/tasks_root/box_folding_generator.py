import os
import bpy
import math
import json
import random
import mathutils
import bmesh
import glob

from SpatialDise.generator.core.base_generator import BaseGenerator


class BoxFoldingGenerator(BaseGenerator):
    """盒子折叠题目生成器"""

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

        # 定义立方体各面的邻接关系 (边编号: 0=上边, 1=右边, 2=下边, 3=左边)
        self.cube_face_relations = {
            'front': {
                0: ('top', 2),     # 前面的上边连接顶面的下边
                1: ('right', 3),   # 前面的右边连接右面的左边
                2: ('bottom', 0),  # 前面的下边连接底面的上边
                3: ('left', 1)     # 前面的左边连接左面的右边
            },
            'back': {
                0: ('top', 0),     # 后面的上边连接顶面的上边
                1: ('left', 3),    # 后面的右边连接左面的左边
                2: ('bottom', 2),  # 后面的下边连接底面的下边
                3: ('right', 1)    # 后面的左边连接右面的右边
            },
            'left': {
                0: ('top', 3),     # 左面的上边连接顶面的左边
                1: ('front', 3),   # 左面的右边连接前面的左边
                2: ('bottom', 3),  # 左面的下边连接底面的左边
                3: ('back', 1)     # 左面的左边连接后面的右边
            },
            'right': {
                0: ('top', 1),     # 右面的上边连接顶面的右边
                1: ('back', 3),    # 右面的右边连接后面的左边
                2: ('bottom', 1),  # 右面的下边连接底面的右边
                3: ('front', 1)    # 右面的左边连接前面的右边
            },
            'top': {
                0: ('back', 0),    # 顶面的上边连接后面的上边
                1: ('right', 0),   # 顶面的右边连接右面的上边
                2: ('front', 0),   # 顶面的下边连接前面的上边
                3: ('left', 0)     # 顶面的左边连接左面的上边
            },
            'bottom': {
                0: ('front', 2),   # 底面的上边连接前面的下边
                1: ('right', 2),   # 底面的右边连接右面的下边
                2: ('back', 2),    # 底面的下边连接后面的下边
                3: ('left', 2)     # 底面的左边连接左面的下边
            }
        }

        # 定义展开图布局
        # 使用两种常见的展开图模式：十字形和T型
        # 对每个面添加rotation信息，表示在折叠回立方体时的额外旋转角度
        self.cube_net_layouts = {
            'cross': {  # 十字形展开布局
                'front': {'position': (1, 1), 'rotation': 0},    # 前面无需旋转
                'back':  {'position': (1, 3), 'rotation': 180},  # 后面旋转180°
                'left':  {'position': (0, 1), 'rotation': 180},  # 左面旋转180°
                'right': {'position': (2, 1), 'rotation': 270},  # 右面旋转270°
                'top':   {'position': (1, 2), 'rotation': 0},    # 顶面保持正常
                'bottom': {'position': (1, 0), 'rotation': 0}    # 底面保持正常
            },
            'T': {      # T型展开布局
                'front': {'position': (1, 0), 'rotation': 0},    # 前面无需旋转
                'back':  {'position': (1, 2), 'rotation': 180},  # 后面旋转180°
                'left':  {'position': (0, 0), 'rotation': 90},   # 左面旋转90°
                'right': {'position': (2, 0), 'rotation': 270},  # 右面旋转270°
                'top':   {'position': (1, 1), 'rotation': 0},   # 顶面保持正常
                'bottom': {'position': (1, 3), 'rotation': 0}    # 底面保持正常
            }
        }

        # 定义立方体面的名称到索引的映射
        self.face_name_to_index = {
            'front': 0,
            'top': 1,
            'back': 2,
            'bottom': 3,
            'right': 4,
            'left': 5
        }

        # 定义索引到立方体面名称的映射
        self.face_index_to_name = {v: k for k,
                                   v in self.face_name_to_index.items()}

        # 基于上述结构，创建展开图模式
        self.unfolding_patterns = []
        self.face_rotations = []  # 存储每个面的旋转角度

        # 创建十字形展开模式
        cross_pattern = []
        cross_rotations = []
        for i in range(6):  # 遍历6个面
            face_name = self.face_index_to_name[i]
            face_info = self.cube_net_layouts['cross'][face_name]
            position = face_info['position']
            rotation = face_info['rotation']
            # 转换为三维坐标 (x, y, z)，z始终为0
            cross_pattern.append((position[0], position[1], 0))
            cross_rotations.append(rotation)
        self.unfolding_patterns.append(cross_pattern)
        self.face_rotations.append(cross_rotations)

        # 创建T型展开模式
        t_pattern = []
        t_rotations = []
        for i in range(6):  # 遍历6个面
            face_name = self.face_index_to_name[i]
            face_info = self.cube_net_layouts['T'][face_name]
            position = face_info['position']
            rotation = face_info['rotation']
            # 转换为三维坐标 (x, y, z)，z始终为0
            t_pattern.append((position[0], position[1], 0))
            t_rotations.append(rotation)
        self.unfolding_patterns.append(t_pattern)
        self.face_rotations.append(t_rotations)

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
        try:
            icons_path = "/Users/hxm/Downloads/Compressed/Favorites/withbg"
            if os.path.exists(icons_path):
                self.icon_files = [os.path.join(icons_path, f) for f in os.listdir(icons_path)
                                   if f.lower().endswith('.png')]
                print(f"找到 {len(self.icon_files)} 个图标文件")

                # 测试加载前5个图像，验证它们是否可用
                test_icons = self.icon_files[:5] if len(
                    self.icon_files) > 5 else self.icon_files
                for icon in test_icons:
                    try:
                        if not os.path.exists(icon):
                            print(f"图标文件不存在: {icon}")
                            continue

                        # 尝试加载图像
                        bpy.data.images.load(icon, check_existing=True)
                        print(f"成功加载图像: {os.path.basename(icon)}")
                    except Exception as e:
                        print(f"无法加载图像 {os.path.basename(icon)}: {e}")
            else:
                print(f"图标目录不存在: {icons_path}")
                self.icon_files = []
        except Exception as e:
            print(f"加载图标时出错: {e}")
            self.icon_files = []

        if not self.icon_files:
            print("未找到可用的图标文件，将使用几何图案作为备用")

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

        # 创建立方体
        bpy.ops.mesh.primitive_cube_add(
            size=cube_size, enter_editmode=False, align='WORLD')
        cube = bpy.context.active_object
        cube.name = "TexturedCube"

        # 获取立方体的网格
        mesh = cube.data

        # 确保每个面都有正确的UV坐标
        if not mesh.uv_layers:  # 如果没有UV层，创建一个
            mesh.uv_layers.new(name="UVMap")

        # 进入编辑模式设置UV
        bpy.ops.object.mode_set(mode='EDIT')

        # 使用Blender的标准Cube Project操作来生成立方体的UV映射
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.cube_project(
            cube_size=True, correct_aspect=True, clip_to_bounds=True)

        # 返回对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

        # 确保材质插槽足够
        while len(cube.material_slots) < 6:
            cube.data.materials.append(None)

        # 记录每个面的材质和贴图分配
        face_assignments = []

        # 随机打乱材质和贴图顺序
        random_materials = self.face_materials.copy()
        random.shuffle(random_materials)

        # 决定是否使用图标或几何图案
        use_icons = False
        if hasattr(self, 'icon_files') and len(self.icon_files) >= 6:
            # 测试第一个图标是否可加载
            try:
                test_icon = self.icon_files[0]
                if os.path.exists(test_icon):
                    bpy.data.images.load(test_icon, check_existing=True)
                    use_icons = True
                    print("将使用图标作为贴图")
            except Exception as e:
                print(f"测试图标加载失败，将使用几何图案: {e}")
                use_icons = False

        if use_icons:
            selected_icons = random.sample(self.icon_files, 6)
            for i, icon in enumerate(selected_icons):
                print(f"选择的图标 {i}: {os.path.basename(icon)}")
        else:
            print("使用几何图案作为贴图")
            selected_icons = ['circle', 'square',
                              'triangle', 'star', 'cross', 'diamond']

        # 为每个面创建材质和纹理
        for i in range(6):
            # 创建新材质
            material_data = random_materials[i]
            icon_path = selected_icons[i] if use_icons else None
            icon_name = os.path.basename(icon_path).split(
                '.')[0] if icon_path else f"pattern_{i}"

            material_name = f"CubeMaterial_{material_data['name']}_{icon_name}"
            material = bpy.data.materials.new(name=material_name)
            material.use_nodes = True

            # 获取节点树和主节点
            nodes = material.node_tree.nodes
            links = material.node_tree.links

            # 清除默认节点
            for node in nodes:
                nodes.remove(node)

            # 创建输出节点
            output_node = nodes.new('ShaderNodeOutputMaterial')
            output_node.location = (300, 0)

            # 创建主着色器节点
            bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf_node.location = (0, 0)

            # 设置基础颜色
            color = material_data['color']
            bsdf_node.inputs['Base Color'].default_value = color

            # 连接着色器到输出
            links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

            # 添加图标贴图或纹理
            if use_icons and icon_path:
                # 获取当前面的名称
                face_name = self.face_index_to_name.get(i)
                # 使用指定的texture_scale参数
                self.add_cube_icon_texture(
                    material, icon_path, color, texture_scale=texture_scale, face_name=face_name)
            else:
                self.add_pattern_texture(material, selected_icons[i], color)

            # 添加材质到立方体
            cube.material_slots[i].material = material

            # 记录面的分配信息
            face_assignments.append({
                'material': material_data['name'],
                'icon': icon_name if icon_path else selected_icons[i],
                'material_obj': material
            })

        # 确定立方体各个面的方向并应用正确的材质
        # 直接使用位置法识别所有面，而不是依赖于法线点积
        face_index_to_direction = {}

        # 计算每个面的中心点坐标
        face_centers = {}
        for poly in mesh.polygons:
            # 计算面的中心点
            center = mathutils.Vector((0, 0, 0))
            for v_idx in poly.vertices:
                center += mesh.vertices[v_idx].co
            center /= len(poly.vertices)
            face_centers[poly.index] = center
            print(
                f"面 {poly.index}: 中心点 ({center.x:.4f}, {center.y:.4f}, {center.z:.4f})")

        # 按坐标轴排序识别面
        # 按X轴排序找出左面和右面
        x_sorted = sorted(face_centers.items(), key=lambda x: x[1].x)
        left_face = x_sorted[0][0]
        right_face = x_sorted[-1][0]
        face_index_to_direction[left_face] = 'left'
        face_index_to_direction[right_face] = 'right'
        print(
            f"识别面 {left_face} 为左面(left), 中心点X: {face_centers[left_face].x:.4f}")
        print(
            f"识别面 {right_face} 为右面(right), 中心点X: {face_centers[right_face].x:.4f}")

        # 按Y轴排序找出前面和后面
        y_sorted = sorted(face_centers.items(), key=lambda x: x[1].y)
        front_face = y_sorted[0][0]
        back_face = y_sorted[-1][0]
        face_index_to_direction[front_face] = 'front'
        face_index_to_direction[back_face] = 'back'
        print(
            f"识别面 {front_face} 为前面(front), 中心点Y: {face_centers[front_face].y:.4f}")
        print(
            f"识别面 {back_face} 为后面(back), 中心点Y: {face_centers[back_face].y:.4f}")

        # 按Z轴排序找出顶面和底面
        z_sorted = sorted(face_centers.items(), key=lambda x: x[1].z)
        bottom_face = z_sorted[0][0]
        top_face = z_sorted[-1][0]
        face_index_to_direction[bottom_face] = 'bottom'
        face_index_to_direction[top_face] = 'top'
        print(
            f"识别面 {bottom_face} 为底面(bottom), 中心点Z: {face_centers[bottom_face].z:.4f}")
        print(f"识别面 {top_face} 为顶面(top), 中心点Z: {face_centers[top_face].z:.4f}")

        # 验证是否所有6个面都被正确识别
        identified_directions = set(face_index_to_direction.values())
        expected_directions = set(
            ['front', 'back', 'top', 'bottom', 'right', 'left'])

        if identified_directions != expected_directions:
            print("警告: 未能识别所有六个面! 识别到的面:", identified_directions)
            missing_directions = expected_directions - identified_directions
            if missing_directions:
                print("缺少的面:", missing_directions)

        # 创建面名称到索引的映射
        face_name_to_index_map = {
            name: idx for idx, name in face_index_to_direction.items()
        }

        # 确保所有面都被识别
        for face_name in expected_directions:
            if face_name not in face_name_to_index_map:
                print(f"错误: 未能找到面 {face_name}!")

        # 重新分配材质，确保正确的面对应正确的材质
        assigned_materials = set()
        for face_name, face_idx in face_name_to_index_map.items():
            material_idx = self.face_name_to_index[face_name]
            if material_idx < len(face_assignments):
                mesh.polygons[face_idx].material_index = material_idx
                assigned_materials.add(material_idx)
                print(
                    f"将材质 {material_idx} ({face_assignments[material_idx]['material']}) 分配给面 {face_name} (索引 {face_idx})")

        # 检查是否所有材质都被分配
        if len(assigned_materials) != 6:
            print(f"警告: 只有 {len(assigned_materials)} 个材质被分配，应该是6个")

        return cube, face_assignments

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
        # 获取节点树
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # 清除所有现有节点
        for node in list(nodes):
            nodes.remove(node)

        # 创建新的输出节点
        output_node = nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (300, 0)

        # 创建主着色器节点
        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_node.location = (100, 0)

        # 确保材质不透明
        material.blend_method = 'OPAQUE'
        bsdf_node.inputs['Alpha'].default_value = 1.0

        try:
            # 检查文件是否存在
            if not os.path.exists(icon_path):
                print(f"图标文件不存在: {icon_path}")
                bsdf_node.inputs['Base Color'].default_value = base_color
                links.new(bsdf_node.outputs['BSDF'],
                          output_node.inputs['Surface'])
                return

            # 加载图像
            image_name = os.path.basename(icon_path)
            img = bpy.data.images.get(image_name)
            if img is None:
                img = bpy.data.images.load(icon_path, check_existing=True)

            # 创建图像纹理节点
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.location = (-100, 0)
            tex_node.image = img
            tex_node.extension = 'REPEAT'  # 改为REPEAT以确保填充整个空间

            # 创建纹理坐标节点 - 使用UV坐标
            coord_node = nodes.new('ShaderNodeTexCoord')
            coord_node.location = (-400, 0)

            # 添加映射节点来控制纹理大小
            mapping_node = nodes.new('ShaderNodeMapping')
            mapping_node.location = (-250, 0)

            # 设置缩放 - 确保纹理覆盖整个面，而不是仅仅一部分
            # 值小于1会放大纹理，确保覆盖整个面
            adjusted_scale = 1.0 / texture_scale

            # 对左面和后面进行特殊处理，修复贴图方向问题
            if face_name == 'left':
                # 水平翻转贴图以修复镜像问题
                mapping_node.inputs['Scale'].default_value = (
                    -adjusted_scale, adjusted_scale, 1.0)
                print(f"应用左面特殊处理：水平翻转贴图")
            elif face_name == 'back':
                # 垂直翻转贴图以修复上下颠倒问题
                mapping_node.inputs['Scale'].default_value = (
                    adjusted_scale, -adjusted_scale, 1.0)
                print(f"应用后面特殊处理：垂直翻转贴图")
            else:
                mapping_node.inputs['Scale'].default_value = (
                    adjusted_scale, adjusted_scale, 1.0)

            # 调整纹理在面上的位置，确保纹理居中显示
            mapping_node.inputs['Location'].default_value = (0.0, 0.0, 0.0)

            # 连接纹理坐标到映射节点，再连接到纹理节点
            links.new(coord_node.outputs['UV'],
                      mapping_node.inputs['Vector'])
            links.new(mapping_node.outputs['Vector'],
                      tex_node.inputs['Vector'])

            # 将纹理直接连接到BSDF的颜色输入
            links.new(tex_node.outputs['Color'],
                      bsdf_node.inputs['Base Color'])

            # 连接BSDF到输出
            links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

            print(
                f"成功为3D立方体材质 {material.name} 添加图标 {image_name}，缩放比例: {adjusted_scale}" +
                (", 并应用左面特殊处理" if face_name == 'left' else "") +
                (", 并应用后面特殊处理" if face_name == 'back' else ""))

        except Exception as e:
            print(f"创建图标纹理时出错: {e}，将使用纯色")
            # 出错时使用纯色
            bsdf_node.inputs['Base Color'].default_value = base_color
            links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

    def add_unfolded_icon_texture(self, material, icon_path, base_color, texture_scale=1.0, rotation_angle=0):
        """
        为2D展开图添加图标贴图，并应用旋转角度

        Args:
            material: 要添加纹理的材质
            icon_path: 图标文件路径
            base_color: 基础颜色
            texture_scale: 纹理缩放比例，值越大图标越小
            rotation_angle: 纹理旋转角度（度）
        """
        # 获取节点树
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # 清除所有现有节点
        for node in list(nodes):
            nodes.remove(node)

        # 创建新的输出节点
        output_node = nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (300, 0)

        # 创建主着色器节点
        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_node.location = (100, 0)

        # 确保材质不透明
        material.blend_method = 'OPAQUE'
        bsdf_node.inputs['Alpha'].default_value = 1.0

        try:
            # 检查文件是否存在
            if not os.path.exists(icon_path):
                print(f"图标文件不存在: {icon_path}")
                bsdf_node.inputs['Base Color'].default_value = base_color
                links.new(bsdf_node.outputs['BSDF'],
                          output_node.inputs['Surface'])
                return

            # 加载图像
            image_name = os.path.basename(icon_path)
            img = bpy.data.images.get(image_name)
            if img is None:
                img = bpy.data.images.load(icon_path, check_existing=True)

            # 创建图像纹理节点
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.location = (-100, 0)
            tex_node.image = img
            tex_node.extension = 'REPEAT'  # 改为REPEAT以确保填充整个空间

            # 创建纹理坐标节点
            coord_node = nodes.new('ShaderNodeTexCoord')
            coord_node.location = (-400, 0)

            # 添加映射节点来控制纹理大小和旋转
            mapping_node = nodes.new('ShaderNodeMapping')
            mapping_node.location = (-250, 0)

            # 设置缩放 - 确保纹理覆盖整个面
            adjusted_scale = 1.0 / texture_scale
            mapping_node.inputs['Scale'].default_value = (
                adjusted_scale, adjusted_scale, 1.0)

            # 设置旋转 - 应用旋转角度
            if rotation_angle != 0:
                # 转换为弧度
                rotation_rad = math.radians(rotation_angle)
                # 设置Z轴旋转
                mapping_node.inputs['Rotation'].default_value = (
                    0.0, 0.0, rotation_rad)

            # 调整纹理在面上的位置，确保纹理居中显示
            mapping_node.inputs['Location'].default_value = (0.0, 0.0, 0.0)

            # 连接纹理坐标到映射节点，再连接到纹理节点
            links.new(coord_node.outputs['UV'],
                      mapping_node.inputs['Vector'])
            links.new(mapping_node.outputs['Vector'],
                      tex_node.inputs['Vector'])

            # 将纹理直接连接到BSDF的颜色输入
            links.new(tex_node.outputs['Color'],
                      bsdf_node.inputs['Base Color'])

            # 连接BSDF到输出
            links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

            print(
                f"成功为2D展开图材质 {material.name} 添加图标 {image_name}，缩放比例: {adjusted_scale}，旋转角度: {rotation_angle}°")

        except Exception as e:
            print(f"创建图标纹理时出错: {e}，将使用纯色")
            # 出错时使用纯色
            bsdf_node.inputs['Base Color'].default_value = base_color
            links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

    def add_pattern_texture(self, material, pattern_name, base_color):
        """
        根据图案名称添加纹理到材质（备用方法）

        Args:
            material: 要添加纹理的材质
            pattern_name: 图案名称
            base_color: 基础颜色
        """
        # 获取节点树
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # 找到主BSDF节点和输出节点
        bsdf_node = None
        for node in nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf_node = node
                break

        if not bsdf_node:
            return

        # 创建简单的纹理 - 使用更通用的方法，避免版本特定的节点属性
        try:
            # 使用噪声纹理作为基础，它在各个Blender版本中都很稳定
            tex_node = nodes.new('ShaderNodeTexNoise')
            tex_node.location = (-300, 0)

            # 根据不同模式设置参数
            if pattern_name == 'circle':
                tex_node.inputs['Scale'].default_value = 5.0
                tex_node.inputs['Detail'].default_value = 2.0
                tex_node.inputs['Distortion'].default_value = 1.0
            elif pattern_name == 'square':
                tex_node.inputs['Scale'].default_value = 4.0
                tex_node.inputs['Detail'].default_value = 0.0
                tex_node.inputs['Distortion'].default_value = 0.0
            elif pattern_name == 'triangle':
                tex_node.inputs['Scale'].default_value = 8.0
                tex_node.inputs['Detail'].default_value = 0.0
                tex_node.inputs['Distortion'].default_value = 0.5
            elif pattern_name == 'star':
                tex_node.inputs['Scale'].default_value = 12.0
                tex_node.inputs['Detail'].default_value = 10.0
                tex_node.inputs['Distortion'].default_value = 2.0
            elif pattern_name == 'cross':
                tex_node.inputs['Scale'].default_value = 3.0
                tex_node.inputs['Detail'].default_value = 0.0
                tex_node.inputs['Distortion'].default_value = 0.0
            elif pattern_name == 'diamond':
                tex_node.inputs['Scale'].default_value = 6.0
                tex_node.inputs['Detail'].default_value = 0.0
                tex_node.inputs['Distortion'].default_value = 0.3
            else:
                # 默认设置
                tex_node.inputs['Scale'].default_value = 5.0
                tex_node.inputs['Detail'].default_value = 2.0

            # 创建颜色渐变节点
            color_ramp = nodes.new('ShaderNodeValToRGB')
            color_ramp.location = (-50, 0)

            # 根据不同图案设置颜色渐变
            if pattern_name == 'circle':
                # 保留两个默认控制点并调整
                color_ramp.color_ramp.elements[0].position = 0.3
                color_ramp.color_ramp.elements[0].color = (1, 1, 1, 1)  # 白色
                color_ramp.color_ramp.elements[1].position = 0.7
                color_ramp.color_ramp.elements[1].color = base_color
            elif pattern_name == 'square':
                # 更明显的方块效果
                color_ramp.color_ramp.elements[0].position = 0.49
                color_ramp.color_ramp.elements[0].color = (1, 1, 1, 1)  # 白色
                color_ramp.color_ramp.elements[1].position = 0.51
                color_ramp.color_ramp.elements[1].color = base_color
            else:
                # 其他图案的默认设置
                color_ramp.color_ramp.elements[0].position = 0.4
                color_ramp.color_ramp.elements[0].color = (1, 1, 1, 1)  # 白色
                color_ramp.color_ramp.elements[1].position = 0.6
                color_ramp.color_ramp.elements[1].color = base_color

            # 连接节点
            links.new(tex_node.outputs['Fac'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'],
                      bsdf_node.inputs['Base Color'])

        except Exception as e:
            print(f"创建纹理时出错: {e}，将使用纯色")
            # 出错时使用纯色
            bsdf_node.inputs['Base Color'].default_value = base_color

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

        pattern = self.unfolding_patterns[pattern_index]
        # 获取对应展开图的面旋转信息
        face_rotations = self.face_rotations[pattern_index]

        # 创建一个空物体作为展开图的父对象
        unfolded_obj = bpy.data.objects.new("UnfoldedCube", None)
        bpy.context.scene.collection.objects.link(unfolded_obj)

        # 立方体的每个面
        # 顺序：前(0), 上(1), 后(2), 下(3), 右(4), 左(5)
        face_indices = [0, 1, 2, 3, 4, 5]

        # 网格面到展开图位置的映射 - 直接使用pattern中对应的位置
        # 在pattern中已经按照立方体面的顺序排列好了坐标
        face_to_position = {
            0: pattern[0],  # 前面 - pattern中的第一个位置
            1: pattern[1],  # 上面 - pattern中的第二个位置
            2: pattern[2],  # 后面 - pattern中的第三个位置
            3: pattern[3],  # 下面 - pattern中的第四个位置
            4: pattern[4],  # 右面 - pattern中的第五个位置
            5: pattern[5],  # 左面 - pattern中的第六个位置
        }

        # 面的大小
        face_size = 2.0

        # 创建展开的面
        for i, face_idx in enumerate(face_indices):
            # 创建平面
            bpy.ops.mesh.primitive_plane_add(
                size=face_size,
                enter_editmode=False,
                align='WORLD',
                location=(
                    face_to_position[face_idx][0] * face_size,
                    face_to_position[face_idx][1] * face_size,
                    face_to_position[face_idx][2] * face_size
                )
            )

            # 获取创建的平面
            plane = bpy.context.active_object
            plane.name = f"Face_{face_idx}"

            # 应用旋转 - 根据展开图中的旋转信息
            rotation_angle = face_rotations[face_idx]  # 获取当前面的旋转角度
            if rotation_angle != 0:
                # 转换为弧度
                rotation_rad = math.radians(rotation_angle)
                # 绕Z轴旋转平面
                plane.rotation_euler = (0, 0, rotation_rad)

            # 应用与原始立方体面相同的材质
            if face_idx < len(face_assignments):
                # 获取原始材质信息
                orig_material = face_assignments[face_idx]['material_obj']
                icon_name = face_assignments[face_idx]['icon']
                material_name = f"UnfoldedMaterial_{orig_material.name}"

                # 创建新材质
                material = bpy.data.materials.new(name=material_name)
                material.use_nodes = True

                # 查找原始材质中的图像纹理节点，获取图像
                icon_path = None
                base_color = (1, 1, 1, 1)  # 默认白色

                for node in orig_material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        icon_path = node.image.filepath
                    elif node.type == 'BSDF_PRINCIPLED':
                        base_color = node.inputs['Base Color'].default_value

                # 添加适用于展开图的贴图
                if icon_path and os.path.exists(icon_path):
                    self.add_unfolded_icon_texture(
                        material, icon_path, base_color, texture_scale, rotation_angle)
                else:
                    # 如果没有找到纹理，复制原材质的其他属性
                    for node in orig_material.node_tree.nodes:
                        if node.type == 'BSDF_PRINCIPLED':
                            # 获取主节点树
                            nodes = material.node_tree.nodes
                            links = material.node_tree.links

                            # 清除默认节点
                            for n in nodes:
                                nodes.remove(n)

                            # 创建基本节点
                            output = nodes.new('ShaderNodeOutputMaterial')
                            output.location = (300, 0)

                            principled = nodes.new('ShaderNodeBsdfPrincipled')
                            principled.location = (0, 0)
                            principled.inputs['Base Color'].default_value = base_color

                            links.new(
                                principled.outputs['BSDF'], output.inputs['Surface'])

                # 清除现有材质插槽
                while len(plane.material_slots) > 0:
                    bpy.ops.object.material_slot_remove({'object': plane})

                # 添加材质
                plane.data.materials.append(material)

            # 将平面设为展开图的子对象
            plane.parent = unfolded_obj

        return unfolded_obj

    def create_distractor_by_difficulty(self, correct_cube, face_assignments, difficulty="medium", seed=None, avoid_faces=None, priority_faces=None):
        """
        根据难度级别创建干扰项

        Args:
            correct_cube: 正确答案的cube对象
            face_assignments: 面的贴图分配信息
            difficulty: 难度级别，可选值为 "easy", "medium", "hard"
            seed: 随机种子
            avoid_faces: 避免修改的面列表
            priority_faces: 优先修改的面列表

        Returns:
            distractor_cube: 干扰项cube对象
            changed_faces: 被修改的面列表
            change_type: 修改类型
        """

        # 设置随机种子
        if seed is not None:
            random.seed(seed)

        # 初始化避免修改的面和优先修改的面
        if avoid_faces is None:
            avoid_faces = []

        if priority_faces is None:
            priority_faces = []

        # 移除避免修改的面
        available_priority_faces = [
            face for face in priority_faces if face not in avoid_faces]

        # 创建干扰项cube的副本
        distractor_cube = self.duplicate_cube(correct_cube)

        # 获取当前视角的可见面
        visible_faces = self.get_visible_faces(self.current_view)

        # 确保至少有一个可见面被修改
        force_visible_face_change = True

        # 根据难度级别选择不同的修改策略
        if difficulty == "easy":
            # 简单：随机替换一个面的图标或图案，确保至少一处差异

            # 优先使用可见面
            candidates = [f for f in visible_faces if f not in avoid_faces]
            if not candidates and force_visible_face_change:
                # 如果所有可见面都需要避免修改，但我们需要强制修改可见面，则从可见面中选择
                candidates = visible_faces
            elif not candidates:
                # 如果不强制修改可见面，则使用任何未避免的面
                candidates = [f for f in range(
                    6) if f not in avoid_faces] or list(range(6))

            face_to_change = random.choice(candidates)
            # 获取原始材质和基础颜色
            orig_mat = distractor_cube.material_slots[face_to_change].material
            base_color = None
            for node in orig_mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    base_color = node.inputs['Base Color'].default_value
                    break
            # 创建新材质副本
            new_mat = bpy.data.materials.new(
                name=f"EasyDistractor_Mat_{face_to_change}")
            new_mat.use_nodes = True
            # 初始化节点树
            nodes = new_mat.node_tree.nodes
            links = new_mat.node_tree.links
            nodes.clear()
            # 输出与BSDF
            out = nodes.new('ShaderNodeOutputMaterial')
            out.location = (300, 0)
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = (0, 0)
            bsdf.inputs['Base Color'].default_value = base_color
            links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
            # 优先使用图标库，仅当 icon_files >=2 时
            if hasattr(self, 'icon_files') and len(self.icon_files) > 1:
                orig_icon = face_assignments[face_to_change].get('icon')
                icon_choices = [i for i in self.icon_files if os.path.basename(i).split('.')[
                    0] != orig_icon]
                if not icon_choices:
                    icon_choices = [i for i in self.icon_files]
                choice_icon = random.choice(icon_choices)
                self.add_cube_icon_texture(new_mat, choice_icon, base_color,
                                           texture_scale=self.cube_texture_scale, face_name=self.face_index_to_name.get(face_to_change))
                change_label = os.path.splitext(
                    os.path.basename(choice_icon))[0]
            else:
                # 图标库不可用或不足量，使用图案库替换
                orig_pat = face_assignments[face_to_change].get('icon')
                pat_choices = [p for p in self.face_patterns if p != orig_pat]
                if not pat_choices:
                    pat_choices = list(self.face_patterns)
                choice_pattern = random.choice(pat_choices)
                self.add_pattern_texture(new_mat, choice_pattern, base_color)
                change_label = choice_pattern
            # 应用新材质
            distractor_cube.material_slots[face_to_change].material = new_mat
            changed_faces = [face_to_change]
            change_type = f"easy_replaced_{change_label}"

        elif difficulty == "medium":
            # 中等：使用多样化的修改策略，确保干扰项之间的差异

            # 增加更多变化类型，避免选项重复
            modification_types = [
                "flip_texture",
                "rotate_texture",
                "change_texture",
                "combined_modification"
            ]

            # 根据已经使用过的面（avoid_faces）来选择变化类型
            # 如果已经有较多的面被修改过，那么优先选择组合修改
            if len(avoid_faces) > 2:
                weights = [0.15, 0.15, 0.2, 0.5]  # 偏向组合修改
            else:
                weights = [0.25, 0.25, 0.25, 0.25]  # 均衡权重

            # 根据权重选择修改类型
            total_weight = sum(weights)
            r = random.uniform(0, total_weight)
            cumulative = 0

            for i, weight in enumerate(weights):
                cumulative += weight
                if r <= cumulative:
                    modification_type = modification_types[i]
                    break
            else:
                modification_type = random.choice(modification_types)

            # 获取当前视角的半可见面（视角边缘的面，通常是移动相机就能看到的）
            less_visible_faces = self.get_less_visible_faces(self.current_view)

            # 面选择策略：基于可见性和避免修改的面
            available_visible_faces = [
                face for face in visible_faces if face not in avoid_faces]
            available_less_visible = [
                face for face in less_visible_faces if face not in avoid_faces]

            # 如果强制修改可见面且没有可用的可见面
            if force_visible_face_change and not available_visible_faces:
                # 从可见面中选择，即使在避免列表中
                available_visible_faces = visible_faces

            # 如果有可见面可用，优先使用可见面 (给予更高权重，80%)
            # 如果可见面被用完，使用半可见面
            # 如果半可见面也被用完，使用任何未避免的面
            usable_faces = []

            # 强化可见面选择策略
            if available_visible_faces:
                # 80%几率使用可见面
                if random.random() < 0.8 or force_visible_face_change:
                    usable_faces = available_visible_faces
                elif available_less_visible:
                    usable_faces = available_less_visible
                else:
                    # 兜底：使用任何未避免的面
                    usable_faces = [f for f in range(
                        6) if f not in avoid_faces]
                    if not usable_faces:  # 如果所有面都要避免，随机选择一个面
                        usable_faces = list(range(6))
            elif available_less_visible:
                usable_faces = available_less_visible
            else:
                # 兜底：使用任何未避免的面
                usable_faces = [f for f in range(6) if f not in avoid_faces]
                if not usable_faces:  # 如果所有面都要避免，随机选择一个面
                    usable_faces = list(range(6))

            if modification_type == "flip_texture":
                # 翻转一个面的纹理方向（上下或左右翻转）
                face_to_flip = random.choice(usable_faces)
                changed_faces, change_type = self.modify_texture_directions(
                    distractor_cube, face_assignments, seed,
                    priority_faces=[face_to_flip],
                    flip_type="flip"  # 指定仅使用翻转而非旋转
                )

            elif modification_type == "rotate_texture":
                # 旋转一个面的纹理（90°、180°或270°）
                face_to_rotate = random.choice(usable_faces)
                # 确保选择一个具有方向性的纹理的面
                # 尝试找到一个更适合旋转的面（方向性明显的纹理）
                directional_faces = []
                for face in usable_faces:
                    mat = distractor_cube.material_slots[face].material
                    # 简化判断：如果面有纹理节点，则认为其有方向性
                    if any(node.type == 'TEX_IMAGE' for node in mat.node_tree.nodes):
                        directional_faces.append(face)

                if directional_faces:
                    face_to_rotate = random.choice(directional_faces)

                changed_faces, change_type = self.modify_texture_directions(
                    distractor_cube, face_assignments, seed,
                    priority_faces=[face_to_rotate],
                    flip_type="rotate"  # 指定仅使用旋转而非翻转
                )

            elif modification_type == "change_texture":
                # 替换一个面的纹理/图标/图案
                face_to_change = random.choice(usable_faces)
                changed_faces, change_type = self.modify_cube_textures(
                    distractor_cube, face_assignments, [face_to_change], seed)

            else:  # combined_modification
                # 组合修改：同时修改两个不同面，但修改程度较小
                # 例如：轻微旋转一个面 + 替换一个不太明显的面

                if len(usable_faces) >= 2:
                    # 选择两个不同的面进行修改
                    modification_faces = random.sample(usable_faces, 2)

                    # 第一个面：轻微的纹理方向调整
                    first_changed, first_change_type = self.modify_texture_directions(
                        distractor_cube, face_assignments, seed,
                        priority_faces=[modification_faces[0]],
                        subtle=True  # 进行轻微调整
                    )

                    # 第二个面：替换纹理或图案
                    second_changed, second_change_type = self.modify_cube_textures(
                        distractor_cube, face_assignments, [
                            modification_faces[1]],
                        seed=seed+1 if seed else None  # 使用不同的种子
                    )

                    # 合并修改信息
                    changed_faces = first_changed + second_changed
                    change_type = f"combined_{first_change_type}_{second_change_type}"
                else:
                    # 如果可用面不足两个，退回到单面修改
                    face_to_change = random.choice(usable_faces)
                    changed_faces, change_type = self.modify_cube_textures(
                        distractor_cube, face_assignments, [face_to_change], seed)
                    change_type = "fallback_" + change_type

        elif difficulty == "hard":
            # 困难：复杂的组合变化，增加更多不规则性和不可预测性
            all_faces = list(range(6))
            # 可用面（排除 avoid_faces）
            available_faces = [f for f in all_faces if f not in avoid_faces]

            # 确保可用的可见面
            available_visible_faces = [
                f for f in visible_faces if f not in avoid_faces]
            if force_visible_face_change and not available_visible_faces:
                available_visible_faces = visible_faces  # 强制使用可见面

            # 选择干扰策略
            distractor_strategies = [
                "swap_and_flip",  # 交换并翻转
                "multi_face_change",  # 多面变化
                "complex_rotation",  # 复杂旋转
                "pattern_swap"  # 图案互换
            ]

            strategy = random.choice(distractor_strategies)

            if strategy == "swap_and_flip":
                # 1) 优先从可见面中选两面交换
                if len(available_visible_faces) >= 2:
                    swap_pair = random.sample(available_visible_faces, 2)
                # 2) 然后检查是否有配对（一个可见一个不可见）
                elif available_visible_faces and available_faces:
                    visible_face = random.choice(available_visible_faces)
                    other_faces = [
                        f for f in available_faces if f not in available_visible_faces]
                    if other_faces:
                        other_face = random.choice(other_faces)
                        swap_pair = [visible_face, other_face]
                    else:
                        swap_pair = [visible_face, random.choice(
                            [f for f in all_faces if f != visible_face])]
                # 3) 最后兜底：从所有6面中选两面
                else:
                    swap_pair = random.sample(all_faces, 2)

                # 执行贴图交换
                texture_changed_faces, texture_change_type = self.swap_cube_textures(
                    distractor_cube, [tuple(swap_pair)]
                )
                # 交换后剩余可供翻转的面
                remaining_faces = [
                    f for f in all_faces if f not in texture_changed_faces and f not in avoid_faces
                ] or all_faces

                # 选择一个可见面进行翻转，如果有
                flip_candidates = [
                    f for f in remaining_faces if f in visible_faces]
                if not flip_candidates:
                    flip_candidates = remaining_faces

                face_to_flip = random.choice(flip_candidates)

                # 执行翻转
                flip_changed_faces, flip_change_type = self.modify_texture_directions(
                    distractor_cube, face_assignments, seed=seed,
                    priority_faces=[face_to_flip],
                    flip_type="flip"  # 强制使用翻转
                )

                # 合并结果
                changed_faces = texture_changed_faces + flip_changed_faces
                change_type = f"swap_{texture_change_type}_and_{flip_change_type}"

            elif strategy == "multi_face_change":
                # 修改多个面的纹理或图案

                # 优先选择包含可见面的组合
                available_faces_with_visible = []

                # 确保至少有一个可见面被修改
                if available_visible_faces:
                    # 至少选择一个可见面，然后随机选择其他面
                    visible_face = random.choice(available_visible_faces)
                    remaining_candidates = [
                        f for f in available_faces if f != visible_face]

                    num_faces_to_change = min(3, len(remaining_candidates) + 1)

                    if num_faces_to_change > 1 and remaining_candidates:
                        # 添加额外的面到修改列表
                        additional_faces = random.sample(
                            remaining_candidates, num_faces_to_change - 1)
                        faces_to_change = [visible_face] + additional_faces
                    else:
                        faces_to_change = [visible_face]
                else:
                    # 没有可用的可见面，退回到普通选择
                    num_faces_to_change = min(3, len(available_faces)) or 1
                    faces_to_change = random.sample(
                        available_faces or all_faces, num_faces_to_change)

                # 对每个面应用不同的变化
                all_changed_faces = []
                change_types = []

                for i, face in enumerate(faces_to_change):
                    # 为每个面选择一个不同的修改方式
                    mod_type = random.choice(["texture", "direction", "both"])
                    face_seed = seed + i if seed else None

                    if mod_type == "texture" or mod_type == "both":
                        face_changed, face_change = self.modify_cube_textures(
                            distractor_cube, face_assignments, [face], face_seed)
                        all_changed_faces.extend(face_changed)
                        change_types.append(face_change)

                    if mod_type == "direction" or mod_type == "both":
                        dir_changed, dir_change = self.modify_texture_directions(
                            distractor_cube, face_assignments, face_seed, priority_faces=[face])
                        all_changed_faces.extend(
                            [f for f in dir_changed if f not in all_changed_faces])
                        change_types.append(dir_change)

                changed_faces = all_changed_faces
                change_type = f"multi_face_{'_'.join(change_types)}"

            elif strategy == "complex_rotation":
                # 对多个面应用复杂的旋转模式
                rotation_candidates = available_faces or all_faces

                # 优先选择可见面进行旋转
                visible_candidates = [
                    f for f in rotation_candidates if f in visible_faces]
                if visible_candidates:
                    rotation_candidates = visible_candidates

                # 选择多个面进行旋转（1-3个）
                num_faces_to_rotate = random.randint(
                    1, min(3, len(rotation_candidates)))
                faces_to_rotate = random.sample(
                    rotation_candidates, num_faces_to_rotate)

                # 对每个面应用不同角度的旋转
                all_rotated_faces = []
                rotation_types = []

                for i, face in enumerate(faces_to_rotate):
                    face_seed = seed + i if seed else None
                    angle = random.choice([90, 180, 270])

                    rotated_faces, rotation_type = self.modify_texture_directions(
                        distractor_cube, face_assignments, face_seed,
                        priority_faces=[face],
                        flip_type="rotate",
                        rotation_angle=angle
                    )

                    all_rotated_faces.extend(rotated_faces)
                    rotation_types.append(rotation_type)

                changed_faces = all_rotated_faces
                change_type = f"complex_rotation_{'_'.join(rotation_types)}"

            elif strategy == "pattern_swap":
                # 在不同面之间互换图案，确保至少有一个可见面被修改

                # 确保选择至少一个可见面
                if available_visible_faces:
                    visible_face = random.choice(available_visible_faces)

                    # 找到另一个面进行交换
                    other_faces = [f for f in all_faces if f !=
                                   visible_face and f not in avoid_faces]
                    if not other_faces:
                        other_faces = [
                            f for f in all_faces if f != visible_face]

                    other_face = random.choice(other_faces)
                    swap_pairs = [(visible_face, other_face)]

                    # 可能添加第二对交换
                    remaining_faces = [f for f in all_faces if f not in [
                        visible_face, other_face] and f not in avoid_faces]
                    if len(remaining_faces) >= 2 and random.random() < 0.5:
                        second_pair = random.sample(remaining_faces, 2)
                        swap_pairs.append(tuple(second_pair))
                else:
                    # 没有可用的可见面，退回到普通选择
                    available_for_swap = available_faces or all_faces
                    if len(available_for_swap) >= 2:
                        swap_pairs = [
                            tuple(random.sample(available_for_swap, 2))]

                        # 可能添加第二对交换
                        remaining_faces = [
                            f for f in available_for_swap if f not in swap_pairs[0]]
                        if len(remaining_faces) >= 2 and random.random() < 0.5:
                            second_pair = random.sample(remaining_faces, 2)
                            swap_pairs.append(tuple(second_pair))
                    else:
                        # 如果没有足够的面可用，退回到修改单个面
                        face_to_change = random.choice(all_faces)
                        changed_faces, change_type = self.modify_cube_textures(
                            distractor_cube, face_assignments, [face_to_change], seed)
                        return distractor_cube, changed_faces, f"fallback_{change_type}"

                # 执行贴图交换
                changed_faces, change_type = self.swap_cube_textures(
                    distractor_cube, swap_pairs
                )
            else:
                # 兜底：如果没有匹配的策略，至少修改一个可见面
                face_to_change = random.choice(
                    visible_faces) if visible_faces else random.choice(all_faces)
                changed_faces, change_type = self.modify_cube_textures(
                    distractor_cube, face_assignments, [face_to_change], seed)
                change_type = "fallback_" + change_type

        # 验证干扰项与正确答案在可见面上是否有足够的视觉差异
        has_visible_difference, different_visible_faces = self.validate_visual_difference(
            distractor_cube, correct_cube, visible_faces)

        # 如果在可见面上没有足够的视觉差异，则强制修改一个可见面
        if not has_visible_difference and force_visible_face_change:
            # 选择一个可见面进行修改
            face_to_change = random.choice(visible_faces)
            # 记录原始的 changed_faces
            original_changed_faces = changed_faces.copy() if changed_faces else []

            # 使用更明显的纹理替换来确保差异
            additional_changed, additional_type = self.modify_cube_textures(
                distractor_cube, face_assignments, [face_to_change],
                seed=seed+100 if seed else None)

            # 更新修改信息
            if face_to_change not in changed_faces:
                changed_faces = original_changed_faces + additional_changed
            change_type = f"{change_type}_forced_{additional_type}"

        return distractor_cube, changed_faces, change_type

    def get_less_visible_faces(self, view):
        """获取在当前视角中不太明显的面（部分可见或边缘可见）

        这些面通常在视角的边缘，或者被其他面部分遮挡，但仍然可见

        Args:
            view: 视角信息

        Returns:
            list: 半可见面的索引列表
        """
        # 从特定视角，哪些面通常是部分可见的
        view_to_less_visible = {
            "iso_front_top_right": [2, 5],    # 后面、左面
            "iso_back_top_right": [0, 5],     # 前面、左面
            "iso_front_top_left": [2, 4],     # 后面、右面
            "iso_back_top_left": [0, 4],      # 前面、右面
        }

        # 获取当前视角的名称
        view_name = view.get("name")

        # 返回对应的半可见面
        return view_to_less_visible.get(view_name, [3])  # 默认返回底面

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
                        self.add_cube_icon_texture(
                            material, random_icon, color, texture_scale=texture_scale, face_name=face_name)
                    else:
                        # Exclude the original geometric pattern
                        original_pattern = face_assignments[face_idx]['icon']
                        available_patterns = [
                            p for p in self.face_patterns if p != original_pattern]
                        if not available_patterns:
                            available_patterns = self.face_patterns
                        random_pattern = random.choice(available_patterns)
                        self.add_pattern_texture(
                            material, random_pattern, color)

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
        self.clear_question_objects()  # 使用基类的方法

        # 创建随机种子
        question_seed = hash(f"box_folding_{q_id}") % 10000
        random.seed(question_seed)

        # 获取当前难度级别
        difficulty = self.config.get('difficulty', 'medium')

        # 创建带贴图的立方体
        cube, face_assignments = self.create_cube_with_textures(
            seed=question_seed, texture_scale=self.cube_texture_scale)

        # 保存原始立方体材质的副本
        original_materials = []
        for i in range(len(cube.material_slots)):
            if cube.material_slots[i].material:
                original_materials.append(cube.material_slots[i].material)

        # 选择展开图类型 - 0表示十字形，1表示T型
        pattern_index = random.randint(0, 1)  # 随机选择0,1展开图类型

        # 创建展开图（用于问题图像）
        unfolded_cube = self.create_unfolded_cube(
            cube, face_assignments, pattern_index, texture_scale=self.unfolded_texture_scale)

        # 设置相机视角，从上方俯视展开图
        cam = bpy.context.scene.camera

        # 设置相机为正交模式以获得更好的2D效果
        cam.data.type = 'ORTHO'

        # 计算展开图的边界框，找到所有子对象
        min_x = float('inf')
        max_x = float('-inf')
        min_y = float('inf')
        max_y = float('-inf')

        # 找到所有展开图子面的边界
        for child in unfolded_cube.children:
            # 获取子对象的世界坐标边界
            for corner in child.bound_box:
                # 转换到世界坐标
                world_corner = child.matrix_world @ mathutils.Vector(corner)
                min_x = min(min_x, world_corner.x)
                max_x = max(max_x, world_corner.x)
                min_y = min(min_y, world_corner.y)
                max_y = max(max_y, world_corner.y)

        # 计算展开图的中心点
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2

        # 计算展开图的尺寸
        width = max_x - min_x
        height = max_y - min_y

        # 设置相机位置到展开图中心上方
        cam.location = (center_x, center_y, 10)
        cam.rotation_euler = (0, 0, 0)

        # 设置正交视场大小，确保完全覆盖展开图并添加一些边距
        margin_factor = 1.6  # 添加20%的边距
        ortho_scale = max(width, height) * margin_factor

        # 确保正交视场大小足够大但不至于过大
        min_scale = 8.0
        max_scale = 20.0
        ortho_scale = max(min_scale, min(ortho_scale, max_scale))

        cam.data.ortho_scale = ortho_scale

        print(
            f"展开图边界: 宽度={width:.2f}, 高度={height:.2f}, 中心=({center_x:.2f}, {center_y:.2f})")
        print(f"设置相机正交视场大小: {ortho_scale:.2f}")

        # 确保展开图可见，立方体不可见
        if cube:
            cube.hide_render = True
        if unfolded_cube:
            unfolded_cube.hide_render = False

        # 渲染问题图像（展开图）
        question_img = os.path.join(
            self.output_dir, f"{q_id}_Q.png")
        self.render_image(question_img)

        # 准备答案选项
        options = []

        # 清除场景，为渲染正确答案做准备
        self.clear_question_objects()

        # 重新创建立方体，确保具有与原始立方体完全相同的材质和贴图
        correct_cube, _ = self.create_cube_with_textures(
            seed=question_seed, texture_scale=self.cube_texture_scale)

        # 确保正确答案立方体的面顺序和材质与原始立方体完全相同
        # 这是确保正确答案与问题图像一一对应的关键
        if len(original_materials) == 6 and len(correct_cube.material_slots) >= 6:
            for i in range(6):
                correct_cube.material_slots[i].material = original_materials[i]

        # 设置相机为透视模式，从等轴测视角观察立方体
        cam = bpy.context.scene.camera
        cam.data.type = 'PERSP'

        # 使用预定义的等轴测视角
        view = random.choice(self.iso_views)
        # 保存当前视角，用于干扰项生成时获取可见面
        self.current_view = view
        # 使用固定的前上左等轴测视角，不再随机选择
        # view = self.iso_views[0]  # iso_front_top_left
        self.set_camera_to_view(cam, view, add_randomness=True)

        # 保存详细的视角信息，包括相机位置和旋转
        view_info = {
            "name": view["name"],
            "position": [float(round(coord, 3)) for coord in cam.location],
            "rotation": [float(round(angle, 3)) for angle in cam.rotation_euler],
            "look_at": view["look_at"],
            "description": self.get_view_description(view["name"])
        }

        # 确保立方体可见
        if correct_cube:
            correct_cube.hide_render = False

        # 渲染正确答案图像
        correct_img = os.path.join(
            self.output_dir, f"{q_id}_A0.png")
        self.render_image(correct_img)

        # 添加正确答案到选项列表
        options.append({
            "image": correct_img,
            "label": "correct",
            "cube_seed": question_seed,
            "view_name": view["name"],
            "view_info": view_info,
        })

        # 生成干扰项
        # 记录已使用的变化类型和修改的面，确保干扰项之间各不相同
        used_change_types = []
        used_face_changes = []

        # 获取当前视角的可见面
        visible_faces = self.get_visible_faces(self.current_view)

        # 保存正确答案立方体的引用，用于可视化差异检查
        # 注意：我们保留正确答案立方体的副本，但在场景中隐藏它
        reference_correct_cube = None
        try:
            # 创建正确答案立方体的副本用于比较
            reference_correct_cube = self.duplicate_cube(correct_cube)
            if reference_correct_cube:
                reference_correct_cube.hide_render = True
                reference_correct_cube.hide_viewport = True  # 在视口中也隐藏
        except Exception as e:
            print(f"警告: 无法创建正确答案立方体的参考副本: {e}")

        for i in range(self.config['num_distractors']):
            # 清理场景，只保留相机和参考用正确答案立方体
            objects_to_keep = [
                reference_correct_cube] if reference_correct_cube else []
            self.clear_scene_except(
                objects_to_keep + [bpy.context.scene.camera])

            # 为干扰项创建单独的随机种子
            distractor_seed = hash(f"distractor_{q_id}_{i}") % 10000

            # 重新创建原始立方体用于复制
            try:
                original_cube, face_assignments = self.create_cube_with_textures(
                    seed=question_seed, texture_scale=self.cube_texture_scale)

                # 确保材质与原始立方体相同
                if len(original_materials) == 6 and len(original_cube.material_slots) >= 6:
                    for j in range(6):
                        original_cube.material_slots[j].material = original_materials[j]
            except Exception as e:
                print(f"警告: 创建干扰项 {i+1} 的原始立方体时出错: {e}")
                continue

            # 创建尝试次数计数器，确保能找到不同的干扰项
            max_attempts = 15  # 增加最大尝试次数
            attempts = 0
            distractor_cube = None
            changed_faces = []
            change_type = ""
            unique_distractor = False
            valid_visual_difference = False

            while (not unique_distractor or not valid_visual_difference) and attempts < max_attempts:
                try:
                    # 根据难度级别创建干扰项
                    distractor_cube, changed_faces, change_type = self.create_distractor_by_difficulty(
                        original_cube, face_assignments, difficulty,
                        seed=distractor_seed + attempts,  # 每次尝试使用不同的种子
                        avoid_faces=used_face_changes if attempts < max_attempts // 2 else [],  # 后半部分尝试不再避免已用面
                        priority_faces=visible_faces)  # 优先修改可见面

                    # 检查是否与已有干扰项有足够的不同
                    distractor_signature = (
                        str(change_type), str(sorted(changed_faces)))

                    # 检查distractor_cube是否有效
                    if not distractor_cube or not hasattr(distractor_cube, "material_slots"):
                        print(f"警告: 干扰项 {i+1} 尝试 {attempts}: 生成的干扰立方体无效")
                        attempts += 1
                        continue

                    # 检查在可见面上是否有明显的视觉差异
                    # 使用参考的正确答案立方体进行比较
                    compare_cube = reference_correct_cube if reference_correct_cube else correct_cube
                    has_visible_difference, different_visible_faces = self.validate_visual_difference(
                        distractor_cube, compare_cube, visible_faces)

                    # 干扰项有效的条件：
                    # 1. 与已有干扰项足够不同
                    # 2. 至少有一个可见面存在差异
                    if distractor_signature not in used_change_types and has_visible_difference:
                        unique_distractor = True
                        valid_visual_difference = True
                        used_change_types.append(distractor_signature)
                        # 只记录可见面的更改，以允许在其他面上有更多变化
                        used_face_changes.extend(
                            [f for f in changed_faces if f in visible_faces])
                    else:
                        attempts += 1
                        reason = []
                        if distractor_signature in used_change_types:
                            reason.append("与已有干扰项重复")
                        if not has_visible_difference:
                            reason.append("在可见面上没有明显差异")
                        print(
                            f"干扰项 {i+1} 尝试 {attempts}: {', '.join(reason)}，重试...")

                        # 如果尝试次数过多但仍无法找到有可见差异的干扰项，降低标准
                        if attempts >= max_attempts // 2 and not valid_visual_difference:
                            # 只要与已有选项不同就可以了
                            if distractor_signature not in used_change_types:
                                print(
                                    f"警告: 干扰项 {i+1} 在可见面上差异不明显，但已尝试多次，接受当前结果")
                                unique_distractor = True
                                valid_visual_difference = True  # 强制接受
                                used_change_types.append(distractor_signature)
                                used_face_changes.extend(
                                    [f for f in changed_faces if f in visible_faces])
                except Exception as e:
                    print(f"创建干扰项时出错 (尝试 {attempts}): {e}")
                    attempts += 1
                    import traceback
                    traceback.print_exc()
                    continue

            if not unique_distractor or not valid_visual_difference:
                print(f"警告: 无法为干扰项 {i+1} 创建有效的变化，使用最后一次尝试的结果")
                # 记录这个干扰项的特征，避免后续干扰项与之重复
                distractor_signature = (
                    str(change_type), str(sorted(changed_faces)))
                used_change_types.append(distractor_signature)
                used_face_changes.extend(
                    [f for f in changed_faces if f in visible_faces])

            # 检查distractor_cube是否有效
            if not distractor_cube or not hasattr(distractor_cube, "material_slots"):
                print(f"错误: 干扰项 {i+1} 无效，跳过")
                continue

            try:
                # 隐藏原始立方体和参考立方体，只显示干扰项
                if original_cube and hasattr(original_cube, "hide_render"):
                    original_cube.hide_render = True
                if reference_correct_cube and hasattr(reference_correct_cube, "hide_render"):
                    reference_correct_cube.hide_render = True
                distractor_cube.hide_render = False

                # 重新设置相机视角，确保与正确答案一致
                self.set_camera_to_view(cam, view, add_randomness=False)

                # 使用相同的视角渲染干扰项
                distractor_img = os.path.join(
                    self.output_dir, f"{q_id}_A{i+1}.png")
                self.render_image(distractor_img)

                # 将干扰项添加到选项列表，包含变化信息
                options.append({
                    "image": distractor_img,
                    "label": f"distractor_{i+1}",
                    "cube_seed": distractor_seed,
                    "view_name": view["name"],
                    "view_info": view_info,
                    "changed_faces": changed_faces,
                    "change_type": change_type,
                    "visible_difference": valid_visual_difference,
                    "different_visible_faces": different_visible_faces if has_visible_difference else []
                })
            except Exception as e:
                print(f"渲染干扰项 {i+1} 时出错: {e}")
                import traceback
                traceback.print_exc()

        # 清理场景，删除所有对象
        self.clear_question_objects()  # 使用基类的方法

        # 创建元数据信息
        metadata = {
            "question_id": q_id,
            "question_type": "box_folding",
            "question_image": question_img,
            "options": options,
            "pattern_index": pattern_index,
            "correct_answer": 0,  # 正确答案始终是第一个选项
        }

        # 保存元数据到JSON文件
        metadata_file = os.path.join(
            self.output_dir, f"{q_id}_meta.json")
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=lambda x: str(x) if isinstance(
                x, (mathutils.Vector, mathutils.Euler, mathutils.Matrix)) else None)

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

    def get_view_description(self, view_name):
        """获取视角的详细描述"""
        view_descriptions = {
            "iso_front_top_right": "前上右视角 - 可见前面、顶面和右面",
            "iso_back_top_right": "后上右视角 - 可见后面、顶面和右面",
            "iso_front_top_left": "前上左视角 - 可见前面、顶面和左面",
            "iso_back_top_left": "后上左视角 - 可见后面、顶面和左面",
            "iso_front_bottom_right": "前下右视角 - 可见前面、底面和右面",
            "iso_back_bottom_right": "后下右视角 - 可见后面、底面和右面",
            "iso_front_bottom_left": "前下左视角 - 可见前面、底面和左面",
            "iso_back_bottom_left": "后下左视角 - 可见后面、底面和左面",
            "front": "正前视角 - 主要可见前面",
            "back": "正后视角 - 主要可见后面",
            "left": "左侧视角 - 主要可见左面",
            "right": "右侧视角 - 主要可见右面",
            "top": "俯视视角 - 主要可见顶面",
            "bottom": "仰视视角 - 主要可见底面"
        }
        return view_descriptions.get(view_name, "未知视角")

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
