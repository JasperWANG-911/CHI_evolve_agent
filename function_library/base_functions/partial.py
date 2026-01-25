"""
Partial Function Library - 9 Functions
Includes Minimal functions plus ground and camera management.

Additional functions (4):
6. add_ground - Add ground plane with physics
7. stick_object_to_ground - Attach object to ground surface
8. remove_ground - Remove ground plane safely
9. create_hemisphere_cameras - Create camera array around scene
"""

import bpy
import os
import math
from mathutils import Vector

# Import all minimal functions
from .minimal import (
    clear_scene,
    import_object,
    scale_object,
    render_all_hemisphere_cameras,
    export_obj
)


def add_ground(size=50):
    """
    Add a ground plane with rigid body physics.

    Args:
        size: Size of the ground plane (default: 50)

    Returns:
        The ground object
    """
    # Create a plane
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "ground"

    # Add rigid body physics
    bpy.ops.rigidbody.object_add()
    ground.rigid_body.type = 'PASSIVE'
    ground.rigid_body.collision_shape = 'MESH'

    # Set friction and restitution
    ground.rigid_body.friction = 0.5
    ground.rigid_body.restitution = 0.1

    # Add material
    mat = bpy.data.materials.new(name="GroundMaterial")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
    ground.data.materials.append(mat)

    return ground


def stick_object_to_ground(object):
    """
    Attach an object to the ground surface using shrinkwrap constraint.

    Args:
        object: Name of the object to attach
    """
    ground = bpy.data.objects.get("ground")
    obj = bpy.data.objects.get(object)

    if not ground:
        print("Ground object not found")
        return

    if not obj:
        print(f"Object {object} not found")
        return

    # Add shrinkwrap constraint
    constraint = obj.constraints.new('SHRINKWRAP')
    constraint.target = ground
    constraint.shrinkwrap_type = 'NEAREST_SURFACE'
    constraint.use_track_normal = True
    constraint.track_axis = 'TRACK_Z'


def remove_ground():
    """
    Remove the ground plane while preserving object positions.

    Returns:
        True if successful
    """
    # Apply all constraints to lock object positions
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj.name != 'ground':
            bpy.context.view_layer.objects.active = obj

            for constraint in obj.constraints:
                if constraint.type == 'SHRINKWRAP':
                    current_loc = obj.location.copy()
                    try:
                        bpy.ops.constraint.apply(constraint=constraint.name)
                    except:
                        obj.constraints.remove(constraint)
                    obj.location = current_loc

    # Remove the ground
    ground = bpy.data.objects.get('ground')
    if ground:
        bpy.data.objects.remove(ground, do_unlink=True)
        print("Ground plane removed successfully")
    else:
        print("No ground plane found to remove")

    return True


def create_hemisphere_cameras(num_cameras=50, camera_height_ratio=1.2):
    """
    Create a hemisphere of cameras around all objects in the scene.

    Args:
        num_cameras: Number of cameras to create (default: 50)
        camera_height_ratio: Multiplier for hemisphere radius (default: 1.2)

    Returns:
        List of created camera objects
    """
    import numpy as np

    # Get all mesh objects except ground
    objects = [obj for obj in bpy.context.scene.objects
               if obj.type == 'MESH' and obj.name != 'ground']

    if not objects:
        print("No objects found to create hemisphere around")
        return []

    # Calculate bounding box of all objects
    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')

    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            min_x = min(min_x, world_corner.x)
            max_x = max(max_x, world_corner.x)
            min_y = min(min_y, world_corner.y)
            max_y = max(max_y, world_corner.y)
            min_z = min(min_z, world_corner.z)
            max_z = max(max_z, world_corner.z)

    # Calculate center
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    center_z = 0  # Hemisphere center at ground level

    # Calculate radius
    radius = 0
    max_height = max_z

    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            horizontal_dist = math.sqrt((world_corner.x - center_x)**2 +
                                        (world_corner.y - center_y)**2)
            effective_radius = math.sqrt(horizontal_dist**2 + world_corner.z**2)
            radius = max(radius, horizontal_dist, effective_radius)

    hemisphere_radius = radius * camera_height_ratio

    # Create collection for cameras
    camera_collection = bpy.data.collections.new("Hemisphere_Cameras")
    bpy.context.scene.collection.children.link(camera_collection)

    # Generate camera positions using golden ratio for better distribution
    cameras = []
    golden_ratio = (1 + math.sqrt(5)) / 2

    for i in range(num_cameras):
        theta = 2 * math.pi * i / golden_ratio  # Azimuth angle
        phi = math.acos(1 - i / num_cameras)  # Polar angle

        # Convert to cartesian coordinates
        x = center_x + hemisphere_radius * math.sin(phi) * math.cos(theta)
        y = center_y + hemisphere_radius * math.sin(phi) * math.sin(theta)
        z = hemisphere_radius * math.cos(phi)

        # Create camera
        bpy.ops.object.camera_add(location=(x, y, z))
        camera = bpy.context.active_object
        camera.name = f"Camera_Hemisphere_{i:03d}"

        # Point camera to scene center
        look_at_point = Vector((center_x, center_y, max_height/2))
        direction = look_at_point - camera.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()

        # Move to camera collection
        if camera.name not in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.link(camera)
        bpy.context.scene.collection.objects.unlink(camera)
        camera_collection.objects.link(camera)

        # Set camera properties
        camera.data.lens = 35
        camera.data.clip_end = hemisphere_radius * 3

        cameras.append(camera)

    # Create center marker
    bpy.ops.object.empty_add(type='SPHERE', location=(center_x, center_y, 0))
    empty = bpy.context.active_object
    empty.name = "Hemisphere_Center"
    empty.empty_display_size = 0.5

    return cameras


# Export list for this module
__all__ = [
    # Minimal functions
    'clear_scene',
    'import_object',
    'scale_object',
    'render_all_hemisphere_cameras',
    'export_obj',
    # Partial additions
    'add_ground',
    'stick_object_to_ground',
    'remove_ground',
    'create_hemisphere_cameras'
]
