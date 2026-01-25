"""
Full Function Library - 14 Functions
Complete set of all available functions for scene construction.

Additional functions (5):
10. set_object_location - Set object position in 3D space
11. rotate_object - Rotate object by specified angles
12. get_object_bounds - Get object bounding box information
13. place_objects_around_house - Place objects with collision detection
14. setup_lighting - Configure scene lighting
"""

import bpy
import os
import math
import random
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

# Import all partial functions
from .partial import (
    # Minimal functions
    clear_scene,
    import_object,
    scale_object,
    render_all_hemisphere_cameras,
    export_obj,
    # Partial functions
    add_ground,
    stick_object_to_ground,
    remove_ground,
    create_hemisphere_cameras
)


def set_object_location(object_name, x, y, z):
    """
    Set the location of an object in 3D space.

    Args:
        object_name: Name of the object to move
        x: X coordinate
        y: Y coordinate
        z: Z coordinate

    Returns:
        True if successful, False otherwise
    """
    obj = bpy.data.objects.get(object_name)
    if obj:
        obj.location = Vector((x, y, z))
        return True
    else:
        print(f"Object {object_name} not found.")
        return False


def rotate_object(object_name, x_angle=0, y_angle=0, z_angle=0):
    """
    Rotate an object by the specified angles (in degrees).

    Args:
        object_name: Name of the object to rotate
        x_angle: Rotation around X axis in degrees
        y_angle: Rotation around Y axis in degrees
        z_angle: Rotation around Z axis in degrees

    Returns:
        True if successful, False otherwise
    """
    obj = bpy.data.objects.get(object_name)
    if obj:
        obj.rotation_euler = (
            math.radians(x_angle),
            math.radians(y_angle),
            math.radians(z_angle)
        )
        return True
    else:
        print(f"Object {object_name} not found.")
        return False


def get_object_bounds(object_name):
    """
    Get the bounding box information of an object.

    Args:
        object_name: Name of the object

    Returns:
        Dictionary with bounding box info, or None if object not found
    """
    obj = bpy.data.objects.get(object_name)
    if not obj:
        print(f"Object {object_name} not found.")
        return None

    # Get world-space bounding box coordinates
    world_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

    # Calculate bounds
    xs = [c.x for c in world_corners]
    ys = [c.y for c in world_corners]
    zs = [c.z for c in world_corners]

    return {
        "min": {"x": min(xs), "y": min(ys), "z": min(zs)},
        "max": {"x": max(xs), "y": max(ys), "z": max(zs)},
        "center": {
            "x": (min(xs) + max(xs)) / 2,
            "y": (min(ys) + max(ys)) / 2,
            "z": (min(zs) + max(zs)) / 2
        },
        "dimensions": {
            "x": max(xs) - min(xs),
            "y": max(ys) - min(ys),
            "z": max(zs) - min(zs)
        }
    }


def place_objects_around_house(
    house_name="house",
    ground_name="ground",
    object_names=None,
    min_clearance=1.0,
    max_distance=5.0,
    prop_clearance=1.0,
    house_clearance=0.1,
    max_tries_per_object=200,
    random_yaw=True,
    align_to_ground_normal=False
):
    """
    Place objects around a house without collision.

    Args:
        house_name: Name of the house object
        ground_name: Name of the ground object
        object_names: List of object names to place (None for auto-detect)
        min_clearance: Minimum distance from house
        max_distance: Maximum distance from house
        prop_clearance: Clearance between props
        house_clearance: Extra clearance from house boundary
        max_tries_per_object: Maximum placement attempts per object
        random_yaw: Apply random rotation around Z axis
        align_to_ground_normal: Align objects to ground surface normal

    Returns:
        Dictionary with placement results
    """
    def get_obj(name):
        obj = bpy.data.objects.get(name)
        if not obj:
            raise RuntimeError(f"Object '{name}' not found")
        return obj

    def build_bvh_from_obj(obj, depsgraph):
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()
        try:
            mat = obj_eval.matrix_world
            verts_world = [mat @ v.co for v in mesh.vertices]
            polys = [p.vertices[:] for p in mesh.polygons]
            return BVHTree.FromPolygons(verts_world, polys, all_triangles=False)
        finally:
            obj_eval.to_mesh_clear()

    def get_local_mesh(obj, depsgraph):
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()
        try:
            verts_local = [v.co.copy() for v in mesh.vertices]
            polys = [p.vertices[:] for p in mesh.polygons]
            return verts_local, polys
        finally:
            obj_eval.to_mesh_clear()

    def bvh_from_transformed_local(verts_local, polys, matrix_world):
        verts_world = [matrix_world @ v for v in verts_local]
        return BVHTree.FromPolygons(verts_world, polys, all_triangles=False)

    def raycast_down(bvh, x, y, z_top):
        hit = bvh.ray_cast(Vector((x, y, z_top)), Vector((0, 0, -1)))
        if hit[0] is None:
            return None
        return hit[0], hit[1]

    def make_rot_align_z_to(normal):
        z_axis = normal.normalized()
        tmp = Vector((1, 0, 0)) if abs(z_axis.x) < 0.9 else Vector((0, 1, 0))
        x_axis = tmp.cross(z_axis).normalized()
        y_axis = z_axis.cross(x_axis).normalized()
        return Matrix((
            (x_axis.x, y_axis.x, z_axis.x, 0),
            (x_axis.y, y_axis.y, z_axis.y, 0),
            (x_axis.z, y_axis.z, z_axis.z, 0),
            (0, 0, 0, 1)
        ))

    def bbox_xy_radius(obj):
        world_coords = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        xs = [v.x for v in world_coords]
        ys = [v.y for v in world_coords]
        return 0.5 * max((max(xs) - min(xs)), (max(ys) - min(ys)))

    def world_bbox_xy(obj):
        world_coords = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        xs = [v.x for v in world_coords]
        ys = [v.y for v in world_coords]
        return min(xs), max(xs), min(ys), max(ys)

    def is_point_inside_hollow_house(bvh_house, x, y, z, ray_directions=None):
        if ray_directions is None:
            ray_directions = [
                Vector((1, 0, 0)), Vector((-1, 0, 0)),
                Vector((0, 1, 0)), Vector((0, -1, 0)),
                Vector((0, 0, 1)), Vector((0, 0, -1))
            ]
        point = Vector((x, y, z))
        hit_count = sum(1 for d in ray_directions if bvh_house.ray_cast(point, d)[0] is not None)
        return hit_count >= len(ray_directions) * 0.5

    def sample_around_house_bbox(house_bbox, min_clearance, max_clearance):
        hx0, hx1, hy0, hy1 = house_bbox
        x0, x1 = hx0 - max_clearance, hx1 + max_clearance
        y0, y1 = hy0 - max_clearance, hy1 + max_clearance
        inner_x0, inner_x1 = hx0 - min_clearance, hx1 + min_clearance
        inner_y0, inner_y1 = hy0 - min_clearance, hy1 + min_clearance

        side = random.choice(['left', 'right', 'top', 'bottom'])
        if side == 'left':
            return random.uniform(x0, inner_x0), random.uniform(y0, y1)
        elif side == 'right':
            return random.uniform(inner_x1, x1), random.uniform(y0, y1)
        elif side == 'top':
            return random.uniform(x0, x1), random.uniform(inner_y1, y1)
        else:
            return random.uniform(x0, x1), random.uniform(y0, inner_y0)

    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        house = get_obj(house_name)
        ground = get_obj(ground_name)

        # Remove shrinkwrap constraints
        for obj in (house, ground):
            for constraint in list(obj.constraints):
                if constraint.type in {'SHRINKWRAP'}:
                    obj.constraints.remove(constraint)

        bvh_ground = build_bvh_from_obj(ground, depsgraph)
        bvh_house = build_bvh_from_obj(house, depsgraph)

        gx0, gx1, gy0, gy1 = world_bbox_xy(ground)
        hx0, hx1, hy0, hy1 = world_bbox_xy(house)
        house_bbox = (hx0, hx1, hy0, hy1)

        z_top = max((ground.matrix_world @ Vector(c)).z for c in ground.bound_box) + 5.0

        if object_names is None:
            objects_to_place = [
                obj for obj in bpy.data.objects
                if obj.type == 'MESH' and obj.visible_get()
                and obj.name not in {house_name, ground_name}
            ]
        else:
            objects_to_place = [get_obj(name) for name in object_names]

        local_cache = {obj.name: get_local_mesh(obj, depsgraph) for obj in objects_to_place}
        placed = []
        failed = []

        house_forbid_rect = (
            hx0 - house_clearance, hx1 + house_clearance,
            hy0 - house_clearance, hy1 + house_clearance
        )

        def outside_house_rect(x, y):
            x0, x1, y0, y1 = house_forbid_rect
            return not (x0 <= x <= x1 and y0 <= y <= y1)

        random.shuffle(objects_to_place)

        for obj in objects_to_place:
            verts_local, polys = local_cache[obj.name]
            approx_r = bbox_xy_radius(obj) + prop_clearance
            success = False

            for attempt in range(max_tries_per_object):
                x, y = sample_around_house_bbox(house_bbox, min_clearance, max_distance)

                if not (gx0 <= x <= gx1 and gy0 <= y <= gy1):
                    continue

                hit = raycast_down(bvh_ground, x, y, z_top)
                if hit is None:
                    continue
                hit_loc, hit_normal = hit
                z = hit_loc.z

                scale = obj.matrix_world.to_scale()
                scale_mat = Matrix.Diagonal((scale.x, scale.y, scale.z, 1.0))
                rot = Matrix.Identity(4)
                if align_to_ground_normal:
                    rot = make_rot_align_z_to(hit_normal)
                if random_yaw:
                    yaw = Matrix.Rotation(random.uniform(0, 2 * math.pi), 4, 'Z')
                    rot = rot @ yaw

                candidate_world = Matrix.Translation(Vector((x, y, z))) @ rot @ scale_mat

                too_close = any(
                    ((_mw.to_translation().x - x)**2 + (_mw.to_translation().y - y)**2) < (approx_r + _r)**2
                    for (_obj, _bvh, _r, _mw) in placed
                )
                if too_close:
                    continue

                candidate_bvh = bvh_from_transformed_local(verts_local, polys, candidate_world)
                if bvh_house.overlap(candidate_bvh):
                    continue
                if is_point_inside_hollow_house(bvh_house, x, y, z):
                    continue
                if any(_bvh.overlap(candidate_bvh) for (_obj, _bvh, _r, _mw) in placed):
                    continue

                obj.matrix_world = candidate_world
                placed.append((obj, candidate_bvh, approx_r, candidate_world))
                success = True
                break

            if not success:
                failed.append(obj.name)

        return {"success": len(placed), "total": len(objects_to_place), "failed": failed}

    except Exception as e:
        return {"success": 0, "total": 0, "failed": [], "error": str(e)}


def setup_lighting(hdri_path=None, strength=1.0, rotation_z=0.0):
    """
    Set up scene lighting using HDRI environment map.

    Args:
        hdri_path: Path to HDRI file (optional)
        strength: Light strength multiplier
        rotation_z: Rotation of environment around Z axis in radians

    Returns:
        True if successful, False otherwise
    """
    if hdri_path and not os.path.exists(hdri_path):
        print(f"Error: HDRI file not found: {hdri_path}")
        return False

    world = bpy.context.scene.world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    # Clear existing nodes
    nodes.clear()

    if hdri_path:
        # HDRI lighting setup
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-800, 300)

        mapping = nodes.new(type='ShaderNodeMapping')
        mapping.location = (-600, 300)
        mapping.inputs['Rotation'].default_value[2] = rotation_z

        env_texture = nodes.new(type='ShaderNodeTexEnvironment')
        env_texture.location = (-400, 300)
        env_texture.image = bpy.data.images.load(hdri_path)
        env_texture.interpolation = 'Linear'

        background = nodes.new(type='ShaderNodeBackground')
        background.location = (-100, 300)
        background.inputs['Strength'].default_value = strength

        output = nodes.new(type='ShaderNodeOutputWorld')
        output.location = (100, 300)

        links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], env_texture.inputs['Vector'])
        links.new(env_texture.outputs['Color'], background.inputs['Color'])
        links.new(background.outputs['Background'], output.inputs['Surface'])

        print(f"HDRI environment set: {hdri_path}")
    else:
        # Simple sky lighting
        background = nodes.new(type='ShaderNodeBackground')
        background.location = (-100, 300)
        background.inputs['Color'].default_value = (0.8, 0.9, 1.0, 1.0)
        background.inputs['Strength'].default_value = strength

        output = nodes.new(type='ShaderNodeOutputWorld')
        output.location = (100, 300)

        links.new(background.outputs['Background'], output.inputs['Surface'])

        print("Simple sky lighting configured")

    # Update viewport settings
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.use_scene_world = True
                    space.shading.use_scene_lights = True

    return True


# Export list for this module
__all__ = [
    # Minimal functions
    'clear_scene',
    'import_object',
    'scale_object',
    'render_all_hemisphere_cameras',
    'export_obj',
    # Partial functions
    'add_ground',
    'stick_object_to_ground',
    'remove_ground',
    'create_hemisphere_cameras',
    # Full additions
    'set_object_location',
    'rotate_object',
    'get_object_bounds',
    'place_objects_around_house',
    'setup_lighting'
]
