"""Render and GPU helpers."""

from __future__ import annotations

import os
import random
import math

import bpy
import mathutils


def setup_gpu_acceleration(config):
    """
    Configure GPU rendering for Cycles if available.
    Mirrors legacy behavior; expects a config dict with `use_gpu`.
    """
    try:
        if bpy.context.scene.render.engine != 'CYCLES':
            print("GPU加速需要Cycles渲染引擎，当前引擎不支持")
            return False

        bpy.context.scene.cycles.device = 'GPU'
        print("已设置渲染设备为GPU")

        if 'cycles' in bpy.context.preferences.addons:
            cycles_prefs = bpy.context.preferences.addons['cycles'].preferences
            available_devices = []
            device_type_set = False
            if hasattr(cycles_prefs, 'compute_device_type'):
                device_types = ['METAL', 'CUDA', 'OPENCL', 'CPU']
                for device_type in device_types:
                    try:
                        old_type = cycles_prefs.compute_device_type
                        cycles_prefs.compute_device_type = device_type
                        cycles_prefs.get_devices()
                        gpu_devices = [
                            d for d in cycles_prefs.devices if d.type == 'GPU' or d.type == 'METAL' or device_type in d.name.upper()]
                        if gpu_devices:
                            print(f"检测到 {device_type} 设备: {len(gpu_devices)} 个GPU")
                            device_type_set = True
                            break
                        else:
                            cycles_prefs.compute_device_type = old_type
                    except Exception as e:
                        print(f"测试 {device_type} 设备类型时出错: {e}")
                        try:
                            cycles_prefs.compute_device_type = old_type
                        except Exception:
                            pass

                if device_type_set:
                    print(f"已设置 {cycles_prefs.compute_device_type} 作为计算设备类型")
                else:
                    print("未找到可用的GPU设备类型，将使用CPU")

            if hasattr(cycles_prefs, 'devices'):
                cycles_prefs.get_devices()
                print("可用渲染设备:")
                gpu_count = 0
                for i, device in enumerate(cycles_prefs.devices):
                    print(f"  {i}: {device.name} (类型: {device.type})")
                    if device.type == 'GPU' or device.type == 'METAL':
                        try:
                            device.use = True
                            gpu_count += 1
                            print(f"    ✓ 已启用GPU设备: {device.name}")
                        except Exception as e:
                            print(f"    ✗ 无法启用设备: {device.name} - {e}")
                    elif device.type == 'CPU':
                        if gpu_count == 0:
                            try:
                                device.use = True
                                print(f"    ✓ 已启用CPU设备: {device.name}")
                            except Exception:
                                pass

                if gpu_count > 0:
                    print(f"成功启用 {gpu_count} 个GPU设备")
                else:
                    print("未找到可用GPU设备，将使用CPU渲染")

        if bpy.context.scene.cycles.device == 'GPU':
            bpy.context.scene.cycles.samples = 128
            bpy.context.scene.cycles.max_bounces = 8
            bpy.context.scene.cycles.use_denoising = True
            if hasattr(bpy.context.scene.cycles, 'tile_size'):
                bpy.context.scene.cycles.tile_size = 256
            print("已应用GPU优化设置")

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


def render_image(filepath):
    """Render the current scene to an image file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    bpy.context.view_layer.update()
    bpy.context.scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    return filepath
