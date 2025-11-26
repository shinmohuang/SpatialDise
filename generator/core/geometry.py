"""Geometry helpers for shape creation and analysis."""

from __future__ import annotations

import random
import math
import bmesh
import bpy
import mathutils


def _emission_material(name="SimpleMaterial", color=(0.7, 0.7, 0.7, 1.0), strength=1.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    emission = nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = color
    emission.inputs['Strength'].default_value = strength
    output = nodes.new(type='ShaderNodeOutputMaterial')
    links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return mat


def create_cube(parent, size=1.0, location=(0, 0, 0)):
    mesh = bpy.data.meshes.new("CubeMesh")
    cube = bpy.data.objects.new("Cube", mesh)
    bpy.context.scene.collection.objects.link(cube)
    cube.parent = parent
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(mesh)
    bm.free()
    cube.location = mathutils.Vector(location)
    cube.display_type = 'WIRE'
    mat = _emission_material()
    cube.data.materials.append(mat)
    return cube


def create_rectangular_prism(parent, dimensions=(2.0, 1.0, 1.0), location=(0, 0, 0)):
    mesh = bpy.data.meshes.new("RectangularPrismMesh")
    prism = bpy.data.objects.new("RectangularPrism", mesh)
    bpy.context.scene.collection.objects.link(prism)
    prism.parent = parent
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    prism.scale = mathutils.Vector(dimensions) / 2.0
    prism.location = mathutils.Vector(location)
    prism.display_type = 'WIRE'
    mat = _emission_material()
    prism.data.materials.append(mat)
    return prism


def create_combination_shape(ctx, use_rectangular=None, rect_prob=None, seed=None,
                             remove_blocks=0, growth_history=None):
    """
    Port of the original create_combination_shape with adaptive rectangular placement,
    collision checks, and growth history preservation. Expects a context `ctx`
    (BaseGenerator) providing config, shape_types, check_collision, check_and_fix_overlaps.
    """
    if use_rectangular is None:
        use_rectangular = ctx.config["use_rectangular_prisms"]
    if rect_prob is None:
        rect_prob = ctx.config["rectangular_prism_prob"]

    if seed is not None:
        random.seed(seed)

    master_obj = bpy.data.objects.new("Master", None)
    bpy.context.scene.collection.objects.link(master_obj)
    num_cells = random.randint(ctx.config["num_cells_min"],
                               ctx.config["num_cells_max"])

    added_positions = set()
    candidate_positions = set()
    position_shapes = {}
    growth_directions = {}
    position_offsets = {}
    growth_order = []
    created_objects = []

    def get_neighbors(pos):
        x, y, z = pos
        neighbors = []
        directions = [
            (1, 0, 0), (-1, 0, 0),
            (0, 1, 0), (0, -1, 0),
            (0, 0, 1), (0, 0, -1)
        ]
        for dx, dy, dz in directions:
            new_pos = (x+dx, y+dy, z+dz)
            if all(-2 <= c <= 2 for c in new_pos):
                neighbors.append((new_pos, (dx, dy, dz)))
        return neighbors

    def select_shape_by_direction(direction, position):
        if not use_rectangular or random.random() >= rect_prob:
            return ctx.shape_types[0], (0, 0, 0)
        dx, dy, dz = direction
        x, y, z = position
        grid_min, grid_max = -2, 2
        is_near_x_edge = abs(x) >= 2
        is_near_y_edge = abs(y) >= 2
        is_near_z_edge = abs(z) >= 2
        priority_shapes = []
        if dx != 0:
            shape = ctx.shape_types[1]
            offset_x = (shape["dimensions"][0] - 1.0) / 2 * dx
            priority_shapes.append((1, (offset_x, 0, 0)))
        elif dy != 0:
            shape = ctx.shape_types[2]
            offset_y = (shape["dimensions"][1] - 1.0) / 2 * dy
            priority_shapes.append((2, (0, offset_y, 0)))
        elif dz != 0:
            shape = ctx.shape_types[3]
            offset_z = (shape["dimensions"][2] - 1.0) / 2 * dz
            priority_shapes.append((3, (0, 0, offset_z)))

        for shape_idx in [1, 2, 3]:
            if (shape_idx == 1 and dx != 0) or (shape_idx == 2 and dy != 0) or (shape_idx == 3 and dz != 0):
                continue
            shape = ctx.shape_types[shape_idx]
            if shape_idx == 1:
                offset = ((shape["dimensions"][0] - 1.0) / 2, 0, 0)
            elif shape_idx == 2:
                offset = (0, (shape["dimensions"][1] - 1.0) / 2, 0)
            else:
                offset = (0, 0, (shape["dimensions"][2] - 1.0) / 2)
            priority_shapes.append((shape_idx, offset))

        for shape_idx, offset in priority_shapes:
            shape = ctx.shape_types[shape_idx]
            offset_x, offset_y, offset_z = offset
            dimensions = shape["dimensions"]
            final_x = x + offset_x
            final_y = y + offset_y
            final_z = z + offset_z
            if (final_x - dimensions[0]/2 < grid_min or final_x + dimensions[0]/2 > grid_max or
                final_y - dimensions[1]/2 < grid_min or final_y + dimensions[1]/2 > grid_max or
                    final_z - dimensions[2]/2 < grid_min or final_z + dimensions[2]/2 > grid_max):
                continue
            if (shape_idx == 1 and is_near_x_edge) or (shape_idx == 2 and is_near_y_edge) or (shape_idx == 3 and is_near_z_edge):
                continue
            return shape, offset
        return ctx.shape_types[0], (0, 0, 0)

    def would_collide(new_pos, new_shape, new_offset):
        dimensions = new_shape["dimensions"]
        grid_min, grid_max = -2, 2
        offset_x, offset_y, offset_z = new_offset
        x, y, z = new_pos
        x_min = x + offset_x - dimensions[0]/2
        x_max = x + offset_x + dimensions[0]/2
        y_min = y + offset_y - dimensions[1]/2
        y_max = y + offset_y + dimensions[1]/2
        z_min = z + offset_z - dimensions[2]/2
        z_max = z + offset_z + dimensions[2]/2
        if (x_min < grid_min or x_max > grid_max or
            y_min < grid_min or y_max > grid_max or
                z_min < grid_min or z_max > grid_max):
            return True

        temp_mesh = bpy.data.meshes.new("TempCollisionMesh")
        temp_obj = bpy.data.objects.new("TempCollision", temp_mesh)
        bpy.context.scene.collection.objects.link(temp_obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= dimensions[0]
            v.co.y *= dimensions[1]
            v.co.z *= dimensions[2]
        bm.to_mesh(temp_mesh)
        bm.free()
        temp_obj.location = (new_pos[0] + offset_x,
                             new_pos[1] + offset_y, new_pos[2] + offset_z)
        bpy.context.view_layer.update()
        is_rectangular = new_shape != ctx.shape_types[0]
        difficulty = ctx.config.get('distractor_difficulty', 0.5)
        block_count_factor = min(1.0, len(created_objects) / 10.0)
        base_threshold = 0.005 if is_rectangular else 0.01
        adjusted_threshold = base_threshold * \
            (1 - difficulty * 0.5) * (1 - block_count_factor * 0.5)
        collision = False
        for existing_obj in created_objects:
            if ctx.check_collision(temp_obj, existing_obj, threshold=adjusted_threshold):
                collision = True
                break
        bpy.data.objects.remove(temp_obj, do_unlink=True)
        if temp_mesh.users == 0:
            bpy.data.meshes.remove(temp_mesh)
        return collision

    def evaluate_candidate_position(pos, direction):
        if not use_rectangular:
            return 0
        dx, dy, dz = direction
        x, y, z = pos
        score = 0
        is_edge = abs(x) >= 2 or abs(y) >= 2 or abs(z) >= 2
        if is_edge:
            return 0
        if dx != 0:
            shape = ctx.shape_types[1]
            offset_x = (shape["dimensions"][0] - 1.0) / 2 * dx
            offset = (offset_x, 0, 0)
            if not would_collide(pos, shape, offset):
                score += 3
        elif dy != 0:
            shape = ctx.shape_types[2]
            offset_y = (shape["dimensions"][1] - 1.0) / 2 * dy
            offset = (0, offset_y, 0)
            if not would_collide(pos, shape, offset):
                score += 3
        elif dz != 0:
            shape = ctx.shape_types[3]
            offset_z = (shape["dimensions"][2] - 1.0) / 2 * dz
            offset = (0, 0, offset_z)
            if not would_collide(pos, shape, offset):
                score += 3
        for shape_idx in [1, 2, 3]:
            if (shape_idx == 1 and dx != 0) or (shape_idx == 2 and dy != 0) or (shape_idx == 3 and dz != 0):
                continue
            shape = ctx.shape_types[shape_idx]
            if shape_idx == 1:
                offset_val = (shape["dimensions"][0] - 1.0) / 2
                offset = (offset_val, 0, 0)
            elif shape_idx == 2:
                offset_val = (shape["dimensions"][1] - 1.0) / 2
                offset = (0, offset_val, 0)
            else:
                offset_val = (shape["dimensions"][2] - 1.0) / 2
                offset = (0, 0, offset_val)
            if not would_collide(pos, shape, offset):
                score += 1
        return score

    if growth_history:
        for step in growth_history[:-remove_blocks if remove_blocks > 0 else None]:
            pos = step["position"]
            added_positions.add(pos)
            position_shapes[pos] = step["shape"]
            position_offsets[pos] = step["offset"]
            growth_order.append(pos)
    else:
        start_pos = random.choice(
            [(x, y, z) for x in range(-2, 3) for y in range(-2, 3) for z in range(-2, 3)])
        added_positions.add(start_pos)
        position_shapes[start_pos] = ctx.shape_types[0]
        position_offsets[start_pos] = (0, 0, 0)
        growth_order.append(start_pos)
        for neighbor, direction in get_neighbors(start_pos):
            if neighbor not in added_positions:
                candidate_positions.add(neighbor)
                growth_directions[neighbor] = direction
        current_rect_prob = rect_prob
        while len(added_positions) < num_cells and candidate_positions:
            candidate_scores = []
            for pos in candidate_positions:
                direction = growth_directions.get(pos, (0, 0, 0))
                score = evaluate_candidate_position(pos, direction)
                candidate_scores.append((pos, score))
            candidate_scores.sort(key=lambda x: x[1], reverse=True)
            if candidate_scores and random.random() < 0.8 and candidate_scores[0][1] > 0:
                top_candidates = candidate_scores[:max(
                    1, len(candidate_scores)//3)]
                next_pos, _ = random.choice(top_candidates)
            else:
                next_pos = random.choice(list(candidate_positions))
            candidate_positions.remove(next_pos)
            direction = growth_directions.get(next_pos, (0, 0, 0))
            rect_count = sum(
                1 for pos in position_shapes if position_shapes[pos] != ctx.shape_types[0])
            if len(added_positions) > 0:
                rect_ratio = rect_count / len(added_positions)
                if rect_ratio < rect_prob * 0.8:
                    current_rect_prob = min(0.95, rect_prob * 1.5)
                else:
                    current_rect_prob = rect_prob
            use_rect_this_time = use_rectangular and random.random() < current_rect_prob
            if use_rect_this_time:
                shape, offset = select_shape_by_direction(
                    direction, next_pos)
            else:
                shape, offset = ctx.shape_types[0], (0, 0, 0)
            if created_objects and would_collide(next_pos, shape, offset):
                continue
            added_positions.add(next_pos)
            growth_order.append(next_pos)
            position_shapes[next_pos] = shape
            position_offsets[next_pos] = offset
            for neighbor, new_direction in get_neighbors(next_pos):
                if neighbor not in added_positions and neighbor not in candidate_positions:
                    candidate_positions.add(neighbor)
                    growth_directions[neighbor] = new_direction

    created_blocks = []
    for pos in growth_order:
        shape = position_shapes[pos]
        offset = position_offsets[pos]
        dimensions = shape["dimensions"]
        mesh = bpy.data.meshes.new(f"{shape['name']}Mesh")
        obj = bpy.data.objects.new(shape['name'], mesh)
        bpy.context.scene.collection.objects.link(obj)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= dimensions[0]
            v.co.y *= dimensions[1]
            v.co.z *= dimensions[2]
        bm.to_mesh(mesh)
        bm.free()
        offset_x, offset_y, offset_z = offset
        obj.location = (pos[0] + offset_x, pos[1] +
                        offset_y, pos[2] + offset_z)
        bpy.context.view_layer.update()
        from generator.core import logging as log
        for existing_obj in created_objects:
            if ctx.check_collision(obj, existing_obj):
                log.warn(f"警告: 检测到在位置 {pos} 的方块与现有方块碰撞")
                break
        created_objects.append(obj)
        obj.display_type = 'WIRE'
        mat = _emission_material()
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        obj.parent = master_obj
        created_blocks.append({
            "object": obj,
            "position": pos,
            "shape": shape,
            "offset": offset
        })

    fixed_count = ctx.check_and_fix_overlaps(master_obj)
    if fixed_count > 0:
        ctx.check_and_fix_overlaps(master_obj)

    generation_history = []
    for pos in growth_order:
        generation_history.append({
            "position": pos,
            "shape": position_shapes[pos],
            "offset": position_offsets[pos]
        })
    master_obj["growth_history"] = str(generation_history)
    master_obj["seed"] = seed
    return master_obj


def get_shape_center(blocks):
    if not blocks:
        return (0, 0, 0)
    sum_x, sum_y, sum_z = 0, 0, 0
    for block in blocks:
        pos = block.location
        sum_x += pos.x
        sum_y += pos.y
        sum_z += pos.z
    count = len(blocks)
    return (sum_x / count, sum_y / count, sum_z / count)


def get_shape_extent(blocks):
    if not blocks:
        return (0, 0, 0)
    min_x = max_x = blocks[0].location.x
    min_y = max_y = blocks[0].location.y
    min_z = max_z = blocks[0].location.z
    for block in blocks:
        x, y, z = block.location
        if hasattr(block, "dimensions"):
            half_x = block.dimensions.x / 2
            half_y = block.dimensions.y / 2
            half_z = block.dimensions.z / 2
        else:
            half_x = half_y = half_z = 0.5
        min_x = min(min_x, x - half_x)
        max_x = max(max_x, x + half_x)
        min_y = min(min_y, y - half_y)
        max_y = max(max_y, y + half_y)
        min_z = min(min_z, z - half_z)
        max_z = max(max_z, z + half_z)
    return (max_x - min_x, max_y - min_y, max_z - min_z)


def is_top_view_different(original_positions, distractor_blocks):
    distractor_top_visible = set()
    for block in distractor_blocks:
        pos = block.location
        x, y = round(pos.x), round(pos.y)
        distractor_top_visible.add((x, y))
    original_top_visible = original_positions
    diff_coords = original_top_visible.symmetric_difference(
        distractor_top_visible)
    total_coords = original_top_visible.union(distractor_top_visible)
    if not total_coords:
        return False
    difference_ratio = len(diff_coords) / len(total_coords)
    return difference_ratio >= 0.3


def check_collision(obj1, obj2, threshold):
    if not hasattr(obj1, "bound_box") or not hasattr(obj2, "bound_box"):
        return False
    mat1 = obj1.matrix_world
    mat2 = obj2.matrix_world
    bbox1 = [mat1 @ mathutils.Vector(v) for v in obj1.bound_box]
    bbox2 = [mat2 @ mathutils.Vector(v) for v in obj2.bound_box]
    min1 = mathutils.Vector((min(v.x for v in bbox1), min(
        v.y for v in bbox1), min(v.z for v in bbox1)))
    max1 = mathutils.Vector((max(v.x for v in bbox1), max(
        v.y for v in bbox1), max(v.z for v in bbox1)))
    min2 = mathutils.Vector((min(v.x for v in bbox2), min(
        v.y for v in bbox2), min(v.z for v in bbox2)))
    max2 = mathutils.Vector((max(v.x for v in bbox2), max(
        v.y for v in bbox2), max(v.z for v in bbox2)))
    min1 -= mathutils.Vector((threshold, threshold, threshold))
    max1 += mathutils.Vector((threshold, threshold, threshold))
    if (max1.x < min2.x or min1.x > max2.x or
        max1.y < min2.y or min1.y > max2.y or
            max1.z < min2.z or min1.z > max2.z):
        return False
    return True
