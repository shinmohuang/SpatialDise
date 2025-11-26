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
            from generator.core import logging as log
            log.warn("GPU加速需要Cycles渲染引擎，当前引擎不支持")
            return False

        from generator.core import logging as log
        if 'cycles' in bpy.context.preferences.addons:
            cycles_prefs = bpy.context.preferences.addons['cycles'].preferences
            device_type_set = False
            allowed_types = []
            optix_mode = False

            if hasattr(cycles_prefs, 'compute_device_type'):
                enum_items = cycles_prefs.bl_rna.properties['compute_device_type'].enum_items
                allowed_types = [item.identifier for item in enum_items]

                # 如果支持 OPTIX，则强制优先使用 OPTIX 后端
                if 'OPTIX' in allowed_types:
                    tested_types = ['OPTIX']
                    optix_mode = True
                else:
                    preferred = ['CUDA', 'HIP', 'ONEAPI', 'METAL']
                    tested_types = [t for t in preferred if t in allowed_types] or allowed_types

                for device_type in tested_types:
                    try:
                        cycles_prefs.compute_device_type = device_type
                        cycles_prefs.get_devices()
                        gpu_devices = [
                            d for d in cycles_prefs.devices
                            if d.type in ('GPU', 'METAL', 'CUDA', 'OPTIX', 'HIP', 'ONEAPI')
                        ]
                        if gpu_devices:
                            log.info(f"检测到 {device_type} 设备: {len(gpu_devices)} 个GPU")
                            device_type_set = True
                            break
                    except Exception as e:
                        log.warn(f"测试 {device_type} 设备类型时出错: {e}")

                if not device_type_set and 'CPU' in allowed_types:
                    try:
                        cycles_prefs.compute_device_type = 'CPU'
                    except Exception:
                        pass

                if device_type_set:
                    log.info(f"已设置 {cycles_prefs.compute_device_type} 作为计算设备类型")
                else:
                    log.warn("未找到可用的GPU设备类型，将使用CPU")

            if hasattr(cycles_prefs, 'devices'):
                cycles_prefs.get_devices()
                log.info("可用渲染设备:")
                gpu_count = 0
                for i, device in enumerate(cycles_prefs.devices):
                    log.info(f"  {i}: {device.name} (类型: {device.type})")

                    if optix_mode:
                        # 仅在 OPTIX 模式下启用 OPTIX 设备，其余（包括 CUDA）全部关闭
                        if device.type == 'OPTIX':
                            try:
                                device.use = True
                                gpu_count += 1
                                log.info(f"    ✓ 已启用GPU设备: {device.name}")
                            except Exception as e:
                                log.warn(f"    ✗ 无法启用设备: {device.name} - {e}")
                        else:
                            try:
                                device.use = False
                            except Exception:
                                pass
                    else:
                        if device.type in ('GPU', 'METAL', 'CUDA', 'HIP', 'ONEAPI'):
                            try:
                                device.use = True
                                gpu_count += 1
                                log.info(f"    ✓ 已启用GPU设备: {device.name}")
                            except Exception as e:
                                log.warn(f"    ✗ 无法启用设备: {device.name} - {e}")
                        elif device.type == 'CPU':
                            if gpu_count == 0:
                                try:
                                    device.use = True
                                    log.info(f"    ✓ 已启用CPU设备: {device.name}")
                                except Exception:
                                    pass

                if gpu_count > 0:
                    bpy.context.scene.cycles.device = 'GPU'
                    log.info("已设置渲染设备为GPU")
                    log.info(f"成功启用 {gpu_count} 个GPU设备")
                else:
                    bpy.context.scene.cycles.device = 'CPU'
                    log.warn("未找到可用GPU设备，将使用CPU渲染")
        else:
            bpy.context.scene.cycles.device = 'CPU'

        if bpy.context.scene.cycles.device == 'GPU':
            bpy.context.scene.cycles.samples = 128
            bpy.context.scene.cycles.max_bounces = 8
            bpy.context.scene.cycles.use_denoising = True
            if hasattr(bpy.context.scene.cycles, 'tile_size'):
                bpy.context.scene.cycles.tile_size = 256
            log.info("已应用GPU优化设置")

        if hasattr(bpy.context.scene.cycles, 'device'):
            log.info(f"当前渲染设备: {bpy.context.scene.cycles.device}")

        if 'cycles' in bpy.context.preferences.addons:
            cycles_prefs = bpy.context.preferences.addons['cycles'].preferences
            if hasattr(cycles_prefs, 'compute_device_type'):
                log.info(f"计算设备类型: {cycles_prefs.compute_device_type}")

        log.info("GPU加速配置完成")
        return True

    except Exception as e:
        from generator.core import logging as log
        log.warn(f"配置GPU加速时出错: {e}")
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
