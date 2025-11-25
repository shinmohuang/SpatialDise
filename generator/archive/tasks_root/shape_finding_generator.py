from __future__ import annotations

import importlib.util
import math
import os
import random
from pathlib import Path

import bpy
import mathutils


def _load_box_folding_base():
    module_path = Path(__file__).with_name("box_folding_generator.py")
    spec = importlib.util.spec_from_file_location(
        "SpatialDise.generator.tasks.dynamic_box_folding_for_shape",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load box_folding_generator from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return getattr(module, "BoxFoldingGenerator")


BoxFoldingGenerator = _load_box_folding_base()


class ShapeFindingGenerator(BoxFoldingGenerator):
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
            "difficulty": "medium",  # 默认难度改为 medium
            "ortho_scale": 5.0  # 缩小相机视角以放大V0-V2图片中的物体，从默认的15.0缩小到8.0
        }
        if config is None:
            config = {}
        merged = {**default, **config}
        super().__init__(output_dir=output_dir, config=merged)

        # 标记场景是否已初始化，避免重复设置光源
        self._scene_initialized = False

        # 添加面名称映射
        self.face_index_to_name = {
            0: "front",
            1: "top",
            2: "back",
            3: "bottom",
            4: "right",
            5: "left"
        }

    def setup_scene_once(self):
        """设置场景，但只在第一次调用时执行，避免重复创建光源"""
        if not self._scene_initialized:
            super().setup_scene()
            self._scene_initialized = True
            print("Scene initialized for shape finding generator")
        else:
            # 只更新渲染设置，不重新创建光源
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
        # Orthographic settings - 保持选项图片的原始大小
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = 3.0  # 恢复到原来的 3.0，保持选项图片 O0-O3 的原始大小
        bpy.context.view_layer.update()

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

        # 获取难度设置，默认 medium
        difficulty = self.config.get("difficulty", "medium")

        cube, face_assignments = self.create_cube_with_textures(seed=seed)

        # keep original materials list for restoration
        original_materials = [slot.material for slot in cube.material_slots]

        cam = bpy.context.scene.camera

        # 保存初始光源设置，避免在选项图片生成过程中累计修改
        sun = bpy.data.objects.get("Sun")
        original_sun_location = None
        original_sun_rotation = None
        if sun:
            original_sun_location = sun.location.copy()
            original_sun_rotation = sun.rotation_euler.copy()

        # Choose views based on difficulty
        # 难度影响视图选择和排列方式
        views = []
        if difficulty == "easy":
            # Easy: 使用标准视图组合（前后、左右、上下相对），视图间关系明确
            base_view_idx = random.randint(0, 3)  # 随机选择起始视图
            views.append(self.iso_views[base_view_idx])
            # 确保第二个视图与第一个视图有共同的可见面
            second_view_options = [(base_view_idx + i) %
                                   4 for i in [1, 3]]  # 相邻的视图
            views.append(self.iso_views[random.choice(second_view_options)])
            # 第三个视图是前两个视图的延续，形成一个简单的连贯序列
            third_options = [(base_view_idx + 2) % 4]  # 对角视图
            if random.random() < 0.5:  # 50%概率选择另一个相邻视图
                unused_adjacent = [
                    i for i in second_view_options if self.iso_views[i] not in views][0]
                third_options.append(unused_adjacent)
            views.append(self.iso_views[random.choice(third_options)])
        elif difficulty == "medium":
            # Medium: 随机选择三个不同视图，但保持一定的连贯性
            views = random.sample(self.iso_views, 3)
            # 打乱顺序，但增加相邻视图连续出现的概率
            if random.random() < 0.7:  # 70%的概率调整顺序使相邻视图连续
                for i in range(len(self.iso_views)):
                    if self.iso_views[i] in views and self.iso_views[(i+1) % 4] in views:
                        idx1 = views.index(self.iso_views[i])
                        idx2 = views.index(self.iso_views[(i+1) % 4])
                        if abs(idx1 - idx2) != 1:  # 如果这两个视图不相邻
                            # 调整顺序使它们相邻
                            if idx2 != 0:  # 不能把第二个视图移到开头
                                views[idx2], views[idx1 +
                                                   1] = views[idx1+1], views[idx2]
        else:  # hard
            # Hard: 完全随机的视图组合，可能包含更多的心理旋转
            views = random.sample(self.iso_views, 3)
            # 增加视图间的旋转复杂性
            random.shuffle(views)  # 完全打乱顺序

        view_images = []
        replaced_face_idx = None
        original_material_of_replaced = None

        # Capture first two views (no modification)
        for i, view in enumerate(views[:2]):
            self.set_camera_to_view(cam, view, add_randomness=False)
            # 设置更小的ortho_scale来放大V0-V1视图中的物体
            cam.data.ortho_scale = 5.0  # 从默认的5.0减小到3.0，与选项图片保持一致
            # 根据难度添加随机旋转
            if difficulty == "medium":
                # 在 medium 难度下，添加轻微的随机旋转
                yaw = random.uniform(-math.pi/6, math.pi/6)  # ±30度
                cam.rotation_euler.rotate_axis('Z', yaw)
            elif difficulty == "hard":
                # 在 hard 难度下，添加更大的随机旋转
                yaw = random.uniform(0, 2 * math.pi)  # 0-360度
                cam.rotation_euler.rotate_axis('Z', yaw)
            bpy.context.view_layer.update()
            img_path = os.path.join(
                self.output_dir, f"{q_id}_V{i}.png")
            self.render_image(img_path)
            view_images.append(img_path)

        # Prepare blue replacement before third view
        third_view = views[2]
        # 选择替换面，根据难度
        visible_faces_third = self.get_visible_faces(third_view)

        # 根据难度决定蓝色面的选择方式
        if difficulty == "easy":
            # Easy: 优先从前两个视图中已可见的面中选择，确保学习者有足够信息
            # 收集前两个视图中出现的面
            previously_visible_faces = set()
            for v in views[:2]:
                previously_visible_faces.update(self.get_visible_faces(v))

            # 找出前两个视图与第三视图共同可见的面（排除顶面，因为太容易）
            common_visible_faces = previously_visible_faces.intersection(
                visible_faces_third)
            # 如果顶面在其中且不止一个面
            if 1 in common_visible_faces and len(common_visible_faces) > 1:
                common_visible_faces.remove(1)

            if common_visible_faces:
                # 从共同可见面中选择（优先选择频率低的面，增加一点挑战）
                face_appearances = {face: 0 for face in common_visible_faces}
                for v in views[:2]:
                    visible = self.get_visible_faces(v)
                    for face in common_visible_faces:
                        if face in visible:
                            face_appearances[face] += 1

                # 有80%概率选择出现次数少的面
                if random.random() < 0.8:
                    min_appearances = min(face_appearances.values())
                    candidates = [
                        face for face, count in face_appearances.items() if count == min_appearances]
                    replaced_face_idx = random.choice(candidates)
                else:
                    replaced_face_idx = random.choice(
                        list(common_visible_faces))
            else:
                # 如果没有共同可见面，从第三视图可见面中选择非顶面
                non_top_visible_faces = [
                    f for f in visible_faces_third if f != 1]
                if non_top_visible_faces:
                    replaced_face_idx = random.choice(non_top_visible_faces)
                else:
                    replaced_face_idx = 1  # 不得已才选择顶面

        elif difficulty == "medium":
            # Medium: 从第三视图可见面中选择，但避免选择顶面除非没有其他选择
            # 优先选择在之前视图中出现过的面，但非频繁出现的面
            previously_visible = {face: 0 for face in range(6)}
            for v in views[:2]:
                for face in self.get_visible_faces(v):
                    previously_visible[face] += 1

            # 可见性权重 - 倾向于选择之前出现过1次的面（比出现0次或2次更有挑战性）
            candidates = {}
            for face in visible_faces_third:
                # 顶面给予较低权重
                weight = 1.0
                if face == 1:  # 顶面
                    weight *= 0.5

                # 根据之前出现次数调整权重
                prev_count = previously_visible[face]
                if prev_count == 1:
                    weight *= 1.5  # 出现1次的面权重提高
                elif prev_count == 0:
                    weight *= 0.8  # 未出现过的面降低权重

                candidates[face] = weight

            # 基于权重选择面
            total_weight = sum(candidates.values())
            rand_val = random.uniform(0, total_weight)
            cumulative = 0
            for face, weight in candidates.items():
                cumulative += weight
                if rand_val <= cumulative:
                    replaced_face_idx = face
                    break

        else:  # hard
            # Hard: 增加认知挑战
            # 找出之前视图中没有或仅短暂出现的面
            previously_visible = {face: 0 for face in range(6)}
            for v in views[:2]:
                visible = self.get_visible_faces(v)
                for face in visible:
                    previously_visible[face] += 1

            # 在第三视图可见面中，倾向于选择前两个视图中出现较少或没有出现的面
            candidates = {}
            for face in visible_faces_third:
                if previously_visible[face] == 0:
                    # 从未出现过的面权重最高
                    candidates[face] = 3.0
                elif previously_visible[face] == 1:
                    # 出现一次的面次之
                    candidates[face] = 2.0
                else:
                    # 出现两次的面权重最低
                    candidates[face] = 1.0

            # 基于权重选择面
            total_weight = sum(candidates.values())
            rand_val = random.uniform(0, total_weight)
            cumulative = 0
            for face, weight in candidates.items():
                cumulative += weight
                if rand_val <= cumulative:
                    replaced_face_idx = face
                    break

        # 如果以上逻辑未能选出面（不应该发生），则从可见面随机选择一个
        if replaced_face_idx is None:
            replaced_face_idx = random.choice(visible_faces_third)

        original_material_of_replaced = cube.material_slots[replaced_face_idx].material

        # assign blue material
        cube.material_slots[replaced_face_idx].material = self._create_blue_material(
        )

        # capture third view
        self.set_camera_to_view(cam, third_view, add_randomness=False)
        # 设置更小的ortho_scale来放大V2视图中的物体
        cam.data.ortho_scale = 5.0  # 从默认的5.0减小到3.0，与选项图片保持一致
        # 根据难度添加随机旋转
        if difficulty == "medium":
            yaw = random.uniform(-math.pi/6, math.pi/6)  # ±30度
            cam.rotation_euler.rotate_axis('Z', yaw)
        elif difficulty == "hard":
            yaw = random.uniform(0, 2 * math.pi)  # 0-360度
            cam.rotation_euler.rotate_axis('Z', yaw)
        bpy.context.view_layer.update()
        img_path = os.path.join(self.output_dir, f"{q_id}_V2.png")
        self.render_image(img_path)
        view_images.append(img_path)

        # ------------------------------------------------------------------
        # Generate option images
        # ------------------------------------------------------------------
        # Restore original material on cube for options
        cube.material_slots[replaced_face_idx].material = original_material_of_replaced

        # 根据难度生成选项
        if difficulty == "easy":
            # Easy: 选项中包含多个已在视图中明显可见的面，确保有足够熟悉度
            union_visible_faces = set()
            for v in views:
                union_visible_faces.update(self.get_visible_faces(v))

            # 确保正确答案在选项中
            if replaced_face_idx not in union_visible_faces:
                union_visible_faces.add(replaced_face_idx)

            # 如果备选面不足4个，添加更多面
            while len(union_visible_faces) < 4:
                additional_face = random.randint(0, 5)
                union_visible_faces.add(additional_face)

            # 如果备选面超过4个，优先保留正确答案和用户可能见过的面
            if len(union_visible_faces) > 4:
                # 先将正确答案加入最终选项
                option_faces = [replaced_face_idx]
                union_visible_faces.remove(replaced_face_idx)

                # 统计面的出现频率
                face_frequency = {face: 0 for face in union_visible_faces}
                for v in views:
                    visible = self.get_visible_faces(v)
                    for face in union_visible_faces:
                        if face in visible:
                            face_frequency[face] += 1

                # 优先选择出现过的面（易难度希望选项比较容易识别）
                remaining_faces = sorted(
                    list(union_visible_faces),
                    key=lambda f: face_frequency[f],
                    reverse=True  # 降序排列，高频率优先
                )

                # 补全选项到4个
                option_faces.extend(remaining_faces[:3])
            else:
                option_faces = list(union_visible_faces)

        elif difficulty == "medium":
            # Medium: 平衡可见性，选择混合的面
            union_visible_faces = set()
            for v in views:
                union_visible_faces.update(self.get_visible_faces(v))

            # 面的可见次数统计
            face_visibility = {face: 0 for face in range(6)}
            for v in views:
                for face in self.get_visible_faces(v):
                    face_visibility[face] += 1

            # 确保正确答案在选项中
            must_include = [replaced_face_idx]

            # 从所有面中选择，但根据可见度调整概率
            candidate_faces = [f for f in range(6) if f not in must_include]
            weights = [0.5 + face_visibility[f]
                       for f in candidate_faces]  # 可见度越高权重越大

            # 随机选择三个干扰选项（基于权重）
            distractor_faces = []
            for _ in range(3):
                if not candidate_faces:
                    break

                total = sum(weights)
                r = random.uniform(0, total)
                cumulative = 0

                for i, (face, weight) in enumerate(zip(candidate_faces, weights)):
                    cumulative += weight
                    if r <= cumulative:
                        distractor_faces.append(face)
                        candidate_faces.pop(i)
                        weights.pop(i)
                        break

            # 组合所有选项
            option_faces = must_include + distractor_faces

        else:  # hard
            # Hard: 增加混淆性，选择包括不可见面和视觉相似面

            # 获取所有曾经可见的面
            visible_faces = set()
            for v in views:
                visible_faces.update(self.get_visible_faces(v))

            # 将正确答案加入候选
            candidates = [replaced_face_idx]

            # 优先添加视觉相似的面（根据材质/贴图）
            # 简化：通过添加所有面，然后在最后阶段随机化处理
            all_faces = list(range(6))
            all_faces.remove(replaced_face_idx)
            random.shuffle(all_faces)

            # 补全选项至4个
            candidates.extend(all_faces[:3])

            # 最终选项
            option_faces = candidates

        # 随机打乱选项顺序
        random.shuffle(option_faces)
        correct_option_index = option_faces.index(replaced_face_idx)

        option_images = []
        for opt_idx, face_idx in enumerate(option_faces):
            self._set_camera_for_face(cam, cube, face_idx)
            # 临时设置光源位置和方向，使其直射当前面
            if sun:
                # 将光源移至与相机相同的位置和朝向，实现正对面照明
                sun.location = cam.location
                sun.rotation_euler = cam.rotation_euler
            img_path = os.path.join(
                self.output_dir, f"{q_id}_O{opt_idx}.png")
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
            option_images.append({
                "image": img_path,
                "face_index": face_idx,
                "label": label,
                "view_name": face_name_map.get(face_idx, "unknown")
            })

        # 恢复原始光源设置，避免影响后续问题生成
        if sun and original_sun_location and original_sun_rotation:
            sun.location = original_sun_location
            sun.rotation_euler = original_sun_rotation

        # ------------------------------------------------------------------
        # Save metadata
        # ------------------------------------------------------------------
        metadata = {
            "question_id": q_id,
            "question_type": "shape_finding",
            # use third view as main question image
            "question_image": view_images[-1],
            "views": view_images,
            "options": option_images,
            "correct_answer": correct_option_index,
            "replaced_face": replaced_face_idx,
            "third_view": third_view["name"],
            "difficulty": difficulty,
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
                # 只保存 meta 数据，不生成额外的 question json 文件
                question_files.append(meta)
            except Exception as e:
                import traceback
                print(f"Error generating question {q}: {e}")
                traceback.print_exc()
        summary = self.create_summary_file(meta_files)
        print(
            f"Shape finding dataset generation complete. Saved to {self.output_dir}")
        return question_files, summary
