"""Camera helpers for SpatialDise generators."""

from __future__ import annotations

import math
import random

import bpy
import mathutils


def evaluate_visibility(view, cubes, camera):
    temp_loc = camera.location.copy()
    temp_rot = camera.rotation_euler.copy()

    pos = view["pos"]
    camera.location = mathutils.Vector((pos[0], pos[1], pos[2]))
    look_at = view["look_at"]
    direction = mathutils.Vector(look_at) - camera.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    camera.rotation_euler = rot_quat.to_euler()
    bpy.context.view_layer.update()

    from mathutils import Vector
    cam_direction = Vector((0, 0, -1))
    cam_direction.rotate(camera.rotation_euler)

    visible_count = 0
    visible_areas = 0
    for cube in cubes:
        to_cube = cube.matrix_world.translation - camera.location
        distance = to_cube.length
        angle = to_cube.normalized().dot(cam_direction.normalized())
        if angle > 0:
            visible_count += 1
            distance_factor = 1.0 / max(1.0, distance * 0.2)
            if hasattr(cube, "dimensions"):
                size = max(cube.dimensions.x,
                           cube.dimensions.y, cube.dimensions.z)
                visible_areas += size * distance_factor
            else:
                visible_areas += distance_factor

    camera.location = temp_loc
    camera.rotation_euler = temp_rot
    return visible_count, visible_areas


def set_camera_to_view(camera, view, add_randomness=True):
    def add_small_offset(value):
        return value + random.uniform(-0.15, 0.15) if add_randomness else value

    pos = view["pos"]
    pos_with_offset = (add_small_offset(pos[0]),
                       add_small_offset(pos[1]),
                       add_small_offset(pos[2]))
    camera.location = mathutils.Vector(pos_with_offset)
    look_at = view["look_at"]
    look_at_with_offset = (add_small_offset(look_at[0]),
                           add_small_offset(look_at[1]),
                           add_small_offset(look_at[2]))
    direction = mathutils.Vector(look_at_with_offset) - camera.location
    rot_quat = direction.to_track_quat('-Z', 'Y')
    euler = rot_quat.to_euler()
    if add_randomness:
        euler.x += math.radians(random.uniform(-2, 2))
        euler.y += math.radians(random.uniform(-2, 2))
        euler.z += math.radians(random.uniform(-2, 2))
    camera.rotation_euler = euler
    return camera


def find_best_view(generator, views, cubes, camera, prefer_isometric=True, iso_bonus=2.0, auto_generate=False, num_candidates=12):
    if not cubes:
        return (views[0], 0) if views else (None, 0)

    shape_center = generator.get_shape_center(cubes)
    shape_extent = generator.get_shape_extent(cubes)

    candidate_views = list(views)
    if auto_generate and len(cubes) > 0:
        additional_views = generator.generate_view_candidates(
            shape_center,
            shape_extent,
            num_candidates=num_candidates
        )
        candidate_views.extend(additional_views)

    view_cache = {}
    view_scores = []
    for view in candidate_views:
        cache_key = str(view["pos"]) + str(view["look_at"])
        if cache_key in view_cache:
            visible_count, visible_areas = view_cache[cache_key]
        else:
            visible_count, visible_areas = evaluate_visibility(
                view, cubes, camera)
            view_cache[cache_key] = (visible_count, visible_areas)

        base_score = visible_count
        total_blocks = len(cubes)
        visibility_ratio = visible_count / total_blocks if total_blocks > 0 else 0
        view_pos = mathutils.Vector(view["pos"])
        view_direction = (view_pos - mathutils.Vector(shape_center)).normalized()
        axis_balance = min(abs(view_direction.x), abs(
            view_direction.y), abs(view_direction.z))
        axis_balance_score = axis_balance * 5.0
        extent_max = max(shape_extent)
        extent_min = min(shape_extent)
        if extent_max > 0:
            shape_elongation = (extent_max - extent_min) / extent_max
        else:
            shape_elongation = 0
        elongation_score = 0
        if shape_elongation > 0.3:
            if shape_extent[0] == extent_max:
                elongation_score = abs(
                    view_direction.y) + abs(view_direction.z)
            elif shape_extent[1] == extent_max:
                elongation_score = abs(
                    view_direction.x) + abs(view_direction.z)
            else:
                elongation_score = abs(
                    view_direction.x) + abs(view_direction.y)
            elongation_score *= 3.0 * shape_elongation

        final_score = (
            base_score * 1.0 +
            visible_areas * 1 +
            visibility_ratio * 10.0 +
            axis_balance_score +
            elongation_score
        )
        is_iso = "iso" in view.get("name", "").lower()
        if prefer_isometric and is_iso:
            final_score *= iso_bonus

        view_scores.append((view, final_score, visible_count))

    view_scores.sort(key=lambda x: x[1], reverse=True)
    if not view_scores:
        return None, 0
    best_view, _, actual_visible = view_scores[0]
    return best_view, actual_visible


def generate_view_candidates(shape_center, shape_extent, num_candidates=12, distance_factor=1.2):
    views = []
    max_extent = max(shape_extent)
    if max_extent <= 0:
        max_extent = 5.0
    base_distance = max_extent * 4.0 * distance_factor
    phi = math.pi * (3. - math.sqrt(5.))
    for i in range(num_candidates):
        y = 1 - (i / float(num_candidates - 1)) * 2 if num_candidates > 1 else 0
        radius = math.sqrt(1 - y * y)
        theta = phi * i
        x = math.cos(theta) * radius
        z = math.sin(theta) * radius
        camera_pos = (
            shape_center[0] + x * base_distance,
            shape_center[1] + y * base_distance,
            shape_center[2] + z * base_distance
        )
        view = {"name": f"auto_view_{i}", "pos": camera_pos,
                "look_at": shape_center}
        views.append(view)

    axes_priority = sorted(
        [(0, shape_extent[0]), (1, shape_extent[1]), (2, shape_extent[2])],
        key=lambda x: x[1],
        reverse=True
    )
    for axis_index, extent in axes_priority:
        axis_weight = extent / max_extent if max_extent > 0 else 1/3
        axis_views = min(3, max(1, round(num_candidates * axis_weight / 3)))
        for i in range(axis_views):
            angle = math.pi * (i+1) / (axis_views+1)
            if axis_index == 0:
                x = math.cos(angle) * base_distance
                y = math.sin(angle) * base_distance * 0.8
                z = math.sin(angle + math.pi/4) * base_distance * 0.6
                camera_pos = (
                    shape_center[0] + x, shape_center[1] + y, shape_center[2] + z)
            elif axis_index == 1:
                x = math.sin(angle) * base_distance * 0.8
                y = math.cos(angle) * base_distance
                z = math.sin(angle + math.pi/4) * base_distance * 0.6
                camera_pos = (
                    shape_center[0] + x, shape_center[1] + y, shape_center[2] + z)
            else:
                x = math.sin(angle) * base_distance * 0.8
                y = math.sin(angle + math.pi/4) * base_distance * 0.6
                z = math.cos(angle) * base_distance
                camera_pos = (
                    shape_center[0] + x, shape_center[1] + y, shape_center[2] + z)
            view = {
                "name": f"axis_{axis_index}_view_{i}",
                "pos": camera_pos,
                "look_at": shape_center
            }
            views.append(view)

    isometric_directions = [
        (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
        (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)
    ]
    for i, direction in enumerate(isometric_directions):
        norm = math.sqrt(direction[0]**2 +
                         direction[1]**2 + direction[2]**2)
        if norm > 0:
            normalized = tuple(d/norm for d in direction)
            camera_pos = (
                shape_center[0] + normalized[0] * base_distance,
                shape_center[1] + normalized[1] * base_distance,
                shape_center[2] + normalized[2] * base_distance
            )
            view = {
                "name": f"auto_iso_view_{i}",
                "pos": camera_pos,
                "look_at": shape_center
            }
            views.append(view)
    return views
