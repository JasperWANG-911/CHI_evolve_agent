"""
Minimal Function Library - 5 Core Functions
These are the essential functions for basic scene operations.

Functions included:
1. clear_scene - Clear all objects from the scene
2. import_object - Import 3D models from file
3. scale_object - Scale mesh objects
4. render_all_hemisphere_cameras - Render from all hemisphere cameras
5. export_obj - Export scene as OBJ file
"""

import bpy
import os
import math
from mathutils import Vector


def clear_scene():
    """Clear all objects from the current scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def import_object(filepath, object_name=None):
    """
    Import a 3D model from file.

    Args:
        filepath: Path to the model file (.obj, .fbx, .gltf, .glb, .blend)
        object_name: Optional name to assign to the imported object
    """
    # Ensure file exists
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return

    # Get the file extension
    ext = os.path.splitext(filepath)[1].lower()

    # Store list of objects before import
    objects_before = set(bpy.data.objects)

    # Import based on file type
    try:
        if ext == '.obj':
            if 'import_scene.obj' not in dir(bpy.ops):
                bpy.ops.preferences.addon_enable(module='io_scene_obj')
            bpy.ops.import_scene.obj(filepath=filepath)
        elif ext == '.fbx':
            if 'import_scene.fbx' not in dir(bpy.ops):
                bpy.ops.preferences.addon_enable(module='io_scene_fbx')
            bpy.ops.import_scene.fbx(filepath=filepath)
        elif ext == '.gltf' or ext == '.glb':
            if 'import_scene.gltf' not in dir(bpy.ops):
                bpy.ops.preferences.addon_enable(module='io_scene_gltf2')
            bpy.ops.import_scene.gltf(filepath=filepath)
        elif ext == '.blend':
            with bpy.data.libraries.load(filepath) as (data_from, data_to):
                data_to.objects = data_from.objects[:]
            for obj in data_to.objects:
                if obj is not None:
                    bpy.context.collection.objects.link(obj)
        else:
            print(f"Unsupported file type: {ext}")
            return

        print(f"Successfully imported: {filepath}")

        # Get newly imported objects
        objects_after = set(bpy.data.objects)
        new_objects = objects_after - objects_before

        # Rename if object_name is provided
        if object_name and new_objects:
            if len(new_objects) == 1:
                obj = list(new_objects)[0]
                obj.name = object_name
                print(f"Renamed imported object to: {object_name}")
            else:
                for i, obj in enumerate(new_objects):
                    if i == 0:
                        obj.name = object_name
                    else:
                        obj.name = f"{object_name}.{i:03d}"
                print(f"Renamed {len(new_objects)} imported objects with base name: {object_name}")

    except Exception as e:
        print(f"Error during import of {filepath}: {str(e)}")
        raise


def scale_object(object_name, scale_factor):
    """
    Scale a mesh object uniformly.

    Args:
        object_name: Name of the object to scale
        scale_factor: Uniform scale factor to apply

    Returns:
        True if successful, False otherwise
    """
    obj = bpy.data.objects.get(object_name)
    if obj and obj.type == 'MESH':
        obj.scale = Vector((scale_factor, scale_factor, scale_factor))
        obj.update_from_editmode()
        return True
    else:
        print(f"Object {object_name} not found or is not a mesh.")
        return False


def render_all_hemisphere_cameras(output_path=None, file_format="PNG"):
    """
    Render the scene from all hemisphere cameras.

    Args:
        output_path: Directory to save rendered images (default: results/images)
        file_format: Image format (PNG, JPEG, etc.)
    """
    # Set default output path
    if output_path is None:
        if bpy.data.filepath:
            project_dir = os.path.dirname(bpy.data.filepath)
        else:
            project_dir = os.getcwd()
        output_path = os.path.join(project_dir, "results", "images")

    # Create output directory
    os.makedirs(output_path, exist_ok=True)

    # Get all hemisphere cameras
    cameras = [obj for obj in bpy.data.objects
               if obj.type == 'CAMERA' and 'Camera_Hemisphere' in obj.name]

    if not cameras:
        print("No hemisphere cameras found!")
        return

    # Store original camera
    original_camera = bpy.context.scene.camera

    # Set render settings
    bpy.context.scene.render.image_settings.file_format = file_format

    # Render from each camera
    for i, camera in enumerate(cameras):
        print(f"Rendering from {camera.name} ({i+1}/{len(cameras)})")

        bpy.context.scene.camera = camera
        output_file = os.path.join(output_path, f"{camera.name}.{file_format.lower()}")
        bpy.context.scene.render.filepath = output_file
        bpy.ops.render.render(write_still=True)

    # Restore original camera
    bpy.context.scene.camera = original_camera

    print(f"Completed rendering {len(cameras)} views to {output_path}")


def export_obj(output_path=None):
    """
    Export the scene as an OBJ file.

    Args:
        output_path: Path for the output file (default: results/models/scene.obj)

    Returns:
        Path to the exported file
    """
    if output_path is None:
        if bpy.data.filepath:
            project_dir = os.path.dirname(bpy.data.filepath)
        else:
            project_dir = os.getcwd()
        output_dir = os.path.join(project_dir, "results", "models")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "scene.obj")

    try:
        # Try new Blender 4.0+ export operator first
        bpy.ops.wm.obj_export(
            filepath=output_path,
            export_selected_objects=False,
            export_triangulated_mesh=False,
            export_smooth_groups=False,
            export_normals=True,
            export_uv=True,
            export_materials=True,
            export_pbr_extensions=False,
            path_mode='AUTO',
            export_animation=False
        )
        print(f"Scene exported to OBJ (Blender 4.0+): {output_path}")

    except AttributeError:
        try:
            # Fallback to legacy operator for older Blender versions
            bpy.ops.export_scene.obj(
                filepath=output_path,
                use_selection=False,
                use_animation=False,
                use_mesh_modifiers=True,
                use_edges=True,
                use_smooth_groups=False,
                use_smooth_groups_bitflags=False,
                use_normals=True,
                use_uvs=True,
                use_materials=True,
                use_triangles=False,
                use_nurbs=False,
                use_vertex_groups=False,
                use_blen_objects=True,
                group_by_object=False,
                group_by_material=False,
                keep_vertex_order=False,
                global_scale=1.0,
                axis_forward='-Z',
                axis_up='Y'
            )
            print(f"Scene exported to OBJ (Legacy): {output_path}")

        except AttributeError:
            raise RuntimeError("Neither new nor legacy OBJ export operators are available")

    return output_path


# Export list for this module
__all__ = [
    'clear_scene',
    'import_object',
    'scale_object',
    'render_all_hemisphere_cameras',
    'export_obj'
]
