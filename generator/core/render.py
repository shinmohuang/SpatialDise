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
            log.warn("GPU acceleration requires Cycles; current render engine is unsupported")
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

                # OPTIX, OPTIX
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
                            log.info(f"Detected {device_type} device: {len(gpu_devices)} GPUs")
                            device_type_set = True
                            break
                    except Exception as e:
                        log.warn(f"Testing {device_type} device typeerror while processing: {e}")

                if not device_type_set and 'CPU' in allowed_types:
                    try:
                        cycles_prefs.compute_device_type = 'CPU'
                    except Exception:
                        pass

                if device_type_set:
                    log.info(f"Set {cycles_prefs.compute_device_type} as compute device type")
                else:
                    log.warn("No available GPU device type found; using CPU")

            if hasattr(cycles_prefs, 'devices'):
                cycles_prefs.get_devices()
                log.info("Available render devices:")
                gpu_count = 0
                for i, device in enumerate(cycles_prefs.devices):
                    log.info(f"{i}: {device.name} (type: {device.type})")

                    if optix_mode:
                        # OPTIX OPTIX device, ( CUDA)
                        if device.type == 'OPTIX':
                            try:
                                device.use = True
                                gpu_count += 1
                                log.info(f"✓ Enabled GPU device: {device.name}")
                            except Exception as e:
                                log.warn(f"✗ Failed to enable device: {device.name} - {e}")
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
                                log.info(f"✓ Enabled GPU device: {device.name}")
                            except Exception as e:
                                log.warn(f"✗ Failed to enable device: {device.name} - {e}")
                        elif device.type == 'CPU':
                            if gpu_count == 0:
                                try:
                                    device.use = True
                                    log.info(f"✓ Enabled CPU device: {device.name}")
                                except Exception:
                                    pass

                if gpu_count > 0:
                    bpy.context.scene.cycles.device = 'GPU'
                    log.info("Render device set to GPU")
                    log.info(f"Successfully enabled {gpu_count} GPUsdevice")
                else:
                    bpy.context.scene.cycles.device = 'CPU'
                    log.warn("No available GPU device found; using CPU rendering")
        else:
            bpy.context.scene.cycles.device = 'CPU'

        if bpy.context.scene.cycles.device == 'GPU':
            bpy.context.scene.cycles.samples = 128
            bpy.context.scene.cycles.max_bounces = 8
            bpy.context.scene.cycles.use_denoising = True
            if hasattr(bpy.context.scene.cycles, 'tile_size'):
                bpy.context.scene.cycles.tile_size = 256
            log.info("Applied GPU optimization settings")

        if hasattr(bpy.context.scene.cycles, 'device'):
            log.info(f"Current render device: {bpy.context.scene.cycles.device}")

        if 'cycles' in bpy.context.preferences.addons:
            cycles_prefs = bpy.context.preferences.addons['cycles'].preferences
            if hasattr(cycles_prefs, 'compute_device_type'):
                log.info(f"Compute device type: {cycles_prefs.compute_device_type}")

        log.info("GPU acceleration configuration completed")
        return True

    except Exception as e:
        from generator.core import logging as log
        log.warn(f"Error configuring GPU acceleration: {e}")
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
