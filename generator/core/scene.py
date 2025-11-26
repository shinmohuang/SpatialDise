"""Scene and camera setup utilities."""

from __future__ import annotations

import math

import bpy
import mathutils

from generator.core import render as render_utils


def clear_scene():
    for collection in bpy.data.collections:
        bpy.data.collections.remove(collection)

    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj, do_unlink=True)

    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)


def clear_question_objects():
    for obj in bpy.context.scene.objects:
        if obj.type not in {'CAMERA', 'LIGHT'}:
            bpy.data.objects.remove(obj, do_unlink=True)


def setup_scene(config):
    scene = bpy.context.scene
    scene.render.resolution_x = config["image_resolution"][0]
    scene.render.resolution_y = config["image_resolution"][1]
    scene.render.resolution_percentage = 100

    render_engine = config.get("render_engine", "CYCLES")
    available_engines = {'CYCLES', 'BLENDER_WORKBENCH'}

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

    if render_engine not in available_engines:
        print(f"警告: 渲染引擎 '{render_engine}' 不可用，将使用 'CYCLES'")
        render_engine = 'CYCLES'

    try:
        scene.render.engine = render_engine
        print(f"使用渲染引擎: {render_engine}")
    except Exception as e:
        print(f"设置渲染引擎失败: {e}，尝试使用CYCLES")
        try:
            scene.render.engine = 'CYCLES'
        except Exception as e2:
            print(f"设置CYCLES引擎也失败: {e2}")

    if scene.render.engine == 'CYCLES':
        gpu_enabled = config.get("use_gpu", True)
        if gpu_enabled:
            print("正在配置GPU加速...")
            render_utils.setup_gpu_acceleration(config)
        else:
            print("GPU加速已禁用")

    try:
        if 'EEVEE' in render_engine:
            try:
                scene.eevee.taa_render_samples = 64
                scene.eevee.use_soft_shadows = True
                scene.eevee.use_bloom = True
                scene.eevee.bloom_intensity = 0.05
                scene.eevee.use_ssr = True
            except AttributeError as e:
                print(f"警告: 无法设置EEVEE参数: {e}")
        elif render_engine == "CYCLES":
            try:
                if not config.get("use_gpu", True) or bpy.context.scene.cycles.device != 'GPU':
                    scene.cycles.samples = 64
                scene.cycles.use_denoising = True
            except AttributeError as e:
                print(f"警告: 无法设置CYCLES参数: {e}")
    except Exception as e:
        print(f"设置渲染质量参数失败: {e}")

    try:
        if not scene.world:
            scene.world = bpy.data.worlds.new("World")
        scene.world.use_nodes = True
        nodes = scene.world.node_tree.nodes
        links = scene.world.node_tree.links
        for node in nodes:
            nodes.remove(node)
        background = nodes.new(type='ShaderNodeBackground')
        background.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        background.inputs['Strength'].default_value = 1.0
        background.location = (0, 0)
        output = nodes.new(type='ShaderNodeOutputWorld')
        output.location = (200, 0)
        links.new(background.outputs['Background'], output.inputs['Surface'])
        scene.world.node_tree.update_tag()
        bpy.context.view_layer.update()
        print("✓ 成功设置纯白色背景 (强度1.0)")
    except Exception as e:
        print(f"✗ 设置背景时出错: {e}")

    try:
        render = scene.render
        render.film_transparent = False
        scene.world.color = (1.0, 1.0, 1.0)
        if hasattr(scene.view_settings, 'view_transform'):
            scene.view_settings.view_transform = 'Raw'
        if hasattr(scene.view_settings, 'look'):
            scene.view_settings.look = 'None'
        if hasattr(scene.display_settings, 'display_device'):
            scene.display_settings.display_device = 'sRGB'
        print("✓ 成功设置film属性为不透明，并配置颜色管理为Raw")
    except Exception as e:
        print(f"✗ 设置film属性时出错: {e}")

    try:
        render = scene.render
        render.engine = config.get("render_engine", "CYCLES")
        if hasattr(scene, 'cycles') and render.engine == 'CYCLES':
            gpu_enabled = config.get("use_gpu", True)
            if gpu_enabled and hasattr(bpy.context.scene.cycles, 'device') and bpy.context.scene.cycles.device == 'GPU':
                scene.cycles.samples = 128
            else:
                scene.cycles.samples = 64
            scene.cycles.use_denoising = True
            if hasattr(scene.cycles, 'denoiser'):
                scene.cycles.denoiser = 'OPENIMAGEDENOISE'
            scene.cycles.max_bounces = 2
            scene.cycles.diffuse_bounces = 1
            scene.cycles.glossy_bounces = 1
            scene.cycles.transmission_bounces = 1
            scene.cycles.volume_bounces = 0
            scene.cycles.transparent_max_bounces = 2
            print(f"✓ 设置Cycles采样数: {scene.cycles.samples}")
    except Exception as e:
            print(f"✗ 设置渲染引擎时出错: {e}")

    # Optional line-art (Freestyle) rendering for higher contrast
    if config.get("wireframe_render", False):
        try:
            scene.render.use_freestyle = True
            fs = bpy.context.view_layer.freestyle_settings
            if not fs.linesets:
                lineset = fs.linesets.new("LineSet")
            else:
                lineset = fs.linesets[0]
            linestyle = lineset.linestyle
            linestyle.color = (0, 0, 0)
            linestyle.thickness = 1.0
            fs.use_smoothness = True
            fs.use_culling = True
            fs.crease_angle = math.radians(134)
            print("✓ 启用线稿渲染 (Freestyle)")
        except Exception as e:
            print(f"✗ 启用线稿渲染失败: {e}")

    try:
        cam_data = bpy.data.cameras.new("Camera")
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = config.get("ortho_scale", 15.0)
        cam = bpy.data.objects.new("Camera", cam_data)
        scene.collection.objects.link(cam)
        cam.location = mathutils.Vector((5.0, -5.0, 5.0))
        cam.rotation_euler = mathutils.Euler(
            (math.radians(62), math.radians(2), math.radians(43)), 'XYZ')
        scene.camera = cam
    except Exception as e:
        print(f"设置相机失败: {e}")
        for obj in scene.objects:
            if obj.type == 'CAMERA':
                scene.camera = obj
                cam = obj
                break
        else:
            print("找不到可用相机，渲染可能会失败")
            return None

    try:
        light_data = bpy.data.lights.new(name="Sun", type='SUN')
        light_data.energy = 2.0
        if hasattr(light_data, 'angle'):
            light_data.angle = 0.1
        light = bpy.data.objects.new(name="Sun", object_data=light_data)
        scene.collection.objects.link(light)
        light.location = (20, 0, 15)
        light.rotation_euler = mathutils.Euler(
            (math.radians(45), 0, math.radians(90)), 'XYZ')
    except Exception as e:
        print(f"设置太阳光失败: {e}")

    try:
        ambient_light = bpy.data.lights.new(name="Ambient", type='AREA')
        ambient_light.energy = 1.5
        if hasattr(ambient_light, 'size'):
            ambient_light.size = 5.0
        ambient_obj = bpy.data.objects.new(
            name="AmbientLight", object_data=ambient_light)
        scene.collection.objects.link(ambient_obj)
        ambient_obj.location = (-10, -10, 15)
        ambient_obj.rotation_euler = mathutils.Euler(
            (math.radians(60), 0, math.radians(45)), 'XYZ')
    except Exception as e:
        print(f"设置环境光失败: {e}")

    try:
        if hasattr(scene.render, 'use_simplify'):
            scene.render.use_simplify = True
            scene.render.simplify_subdivision = 1
    except Exception as e:
        print(f"设置简化参数失败: {e}")

    try:
        if hasattr(bpy.context.scene, 'display') and hasattr(bpy.context.scene.display, 'shading'):
            bpy.context.scene.display.shading.light = 'STUDIO'
            bpy.context.scene.display.shading.show_object_outline = True
    except Exception as e:
        print(f"设置阴影样式失败: {e}")

    try:
        bpy.context.view_layer.update()
    except Exception as e:
        print(f"更新视图层失败: {e}")

    return cam
