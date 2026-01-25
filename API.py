import bpy
import os
import math
import random
import mathutils
import csv
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree


# ==========================APIs for Scene Construction==========================
# Function to clear the current scene
def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

# Function to add ground plane. Object called "ground" will be created.
def add_ground(size=50):
    # create a plane
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "ground"
    
    # add rigid body physics to the ground
    bpy.ops.rigidbody.object_add()
    ground.rigid_body.type = 'PASSIVE'  
    ground.rigid_body.collision_shape = 'MESH' 

    # Set friction and restitution - these can be adjusted as needed
    ground.rigid_body.friction = 0.5  # Affects how the object slides on the ground
    ground.rigid_body.restitution = 0.1  # Affects how the object bounces when dropped

    # Material - purely visual, optional
    mat = bpy.data.materials.new(name="GroundMaterial")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
    ground.data.materials.append(mat)
    
    return ground

# Function to import objects
def import_object(filepath, object_name=None):
    # Ensure file exists
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return
    
    # get the file extension
    ext = os.path.splitext(filepath)[1].lower()
    
    # Store list of objects before import
    objects_before = set(bpy.data.objects)
    
    # import based on file type
    try:
        if ext == '.obj':
            # Enable OBJ import addon if not enabled
            if 'import_scene.obj' not in dir(bpy.ops):
                bpy.ops.preferences.addon_enable(module='io_scene_obj')
            bpy.ops.import_scene.obj(filepath=filepath)
        elif ext == '.fbx':
            # Enable FBX import addon if not enabled
            if 'import_scene.fbx' not in dir(bpy.ops):
                bpy.ops.preferences.addon_enable(module='io_scene_fbx')
            bpy.ops.import_scene.fbx(filepath=filepath)
        elif ext == '.gltf' or ext == '.glb':
            # Enable glTF import addon if not enabled
            if 'import_scene.gltf' not in dir(bpy.ops):
                bpy.ops.preferences.addon_enable(module='io_scene_gltf2')
            bpy.ops.import_scene.gltf(filepath=filepath)
        elif ext == '.blend':
            # For .blend files, we need to append objects
            with bpy.data.libraries.load(filepath) as (data_from, data_to):
                data_to.objects = data_from.objects[:]
            
            # Link objects to the scene
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
        
        # If object_name is provided and we have new objects, rename them
        if object_name and new_objects:
            if len(new_objects) == 1:
                # Single object - rename it directly
                obj = list(new_objects)[0]
                obj.name = object_name
                print(f"Renamed imported object to: {object_name}")
            else:
                # Multiple objects - rename with suffixes
                for i, obj in enumerate(new_objects):
                    if i == 0:
                        obj.name = object_name
                    else:
                        obj.name = f"{object_name}.{i:03d}"
                print(f"Renamed {len(new_objects)} imported objects with base name: {object_name}")
        
    except Exception as e:
        print(f"Error during import of {filepath}: {str(e)}")
        raise

# Function to stick object to the ground
def stick_object_to_ground(object):
    # obtain the ground object
    ground = bpy.data.objects.get("ground")

    # object to stick
    obj = bpy.data.objects.get(object)

    # stick the object to the ground
    constraint = obj.constraints.new('SHRINKWRAP')
    constraint.target = ground
    constraint.shrinkwrap_type = 'NEAREST_SURFACE'
    constraint.use_track_normal = True
    constraint.track_axis = 'TRACK_Z'

# Function to scale an object(must be a mesh)
def scale_object(object_name, scale_factor):
    obj = bpy.data.objects.get(object_name)
    if obj and obj.type == 'MESH':
        # Scale the object
        obj.scale = Vector((scale_factor, scale_factor, scale_factor))
        # Update the object's bounding box
        obj.update_from_editmode()
        return True
    else:
        print(f"Object {object_name} not found or is not a mesh.")
        return False

# Function to place obstructions around house without collision
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
    
    def get_obj(name):
        """get object by name, raise error if not found"""
        obj = bpy.data.objects.get(name)
        if not obj: 
            raise RuntimeError(f"Object '{name}' not found")
        return obj

    def build_bvh_from_obj(obj, depsgraph):
        """Build BVH tree from object"""
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
        """Get local mesh data from object"""
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()
        try:
            verts_local = [v.co.copy() for v in mesh.vertices]
            polys = [p.vertices[:] for p in mesh.polygons]
            return verts_local, polys
        finally:
            obj_eval.to_mesh_clear()

    def bvh_from_transformed_local(verts_local, polys, matrix_world):
        """Build BVH tree from transformed local vertices"""
        verts_world = [matrix_world @ v for v in verts_local]
        return BVHTree.FromPolygons(verts_world, polys, all_triangles=False)

    def raycast_down(bvh, x, y, z_top):
        """Raycast downwards"""
        hit = bvh.ray_cast(Vector((x, y, z_top)), Vector((0, 0, -1)))
        if hit[0] is None: 
            return None
        return hit[0], hit[1]

    def make_rot_align_z_to(normal):
        """Create a rotation matrix that aligns the Z axis to the given normal vector"""
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
        """Calculate the bounding box radius of the object in the XY plane"""
        world_coords = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        xs = [v.x for v in world_coords]
        ys = [v.y for v in world_coords]
        return 0.5 * max((max(xs) - min(xs)), (max(ys) - min(ys)))

    def world_bbox_xy(obj):
        """Get the object's bounding box in world coordinates (XY)"""
        world_coords = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        xs = [v.x for v in world_coords]
        ys = [v.y for v in world_coords]
        return min(xs), max(xs), min(ys), max(ys)

    def is_point_inside_hollow_house(bvh_house, x, y, z, ray_directions=None):
        """
        Check if a point is inside the hollow house
        """
        if ray_directions is None:
            # Use 6 main directions for raycasting
            ray_directions = [
                Vector((1, 0, 0)),   # +X
                Vector((-1, 0, 0)),  # -X
                Vector((0, 1, 0)),   # +Y
                Vector((0, -1, 0)),  # -Y
                Vector((0, 0, 1)),   # +Z
                Vector((0, 0, -1))   # -Z
            ]
        
        point = Vector((x, y, z))
        hit_count = 0

        # Cast rays in all directions
        for direction in ray_directions:
            hit = bvh_house.ray_cast(point, direction)
            if hit[0] is not None:
                hit_count += 1
        
        return hit_count >= len(ray_directions) * 0.5

    def sample_around_house_bbox(house_bbox, min_clearance, max_clearance):
        """Sample positions around the house bounding box"""
        hx0, hx1, hy0, hy1 = house_bbox

        # Expand the bounding box
        x0 = hx0 - max_clearance
        x1 = hx1 + max_clearance
        y0 = hy0 - max_clearance
        y1 = hy1 + max_clearance

        # Inner bounding box
        inner_x0 = hx0 - min_clearance
        inner_x1 = hx1 + min_clearance
        inner_y0 = hy0 - min_clearance
        inner_y1 = hy1 + min_clearance

        # Randomly choose a side
        side = random.choice(['left', 'right', 'top', 'bottom'])
        
        if side == 'left':
            x = random.uniform(x0, inner_x0)
            y = random.uniform(y0, y1)
        elif side == 'right':
            x = random.uniform(inner_x1, x1)
            y = random.uniform(y0, y1)
        elif side == 'top':
            x = random.uniform(x0, x1)
            y = random.uniform(inner_y1, y1)
        else:  # bottom
            x = random.uniform(x0, x1)
            y = random.uniform(y0, inner_y0)
        
        return x, y

    # main logic
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        house = get_obj(house_name)
        ground = get_obj(ground_name)

        # remove shrinkwrap constraints
        for obj in (house, ground):
            for constraint in list(obj.constraints):
                if constraint.type in {'SHRINKWRAP'}:
                    obj.constraints.remove(constraint)

        # construct BVH trees
        bvh_ground = build_bvh_from_obj(ground, depsgraph)
        bvh_house = build_bvh_from_obj(house, depsgraph)

        # Get the bounding box of the ground and house
        gx0, gx1, gy0, gy1 = world_bbox_xy(ground)
        hx0, hx1, hy0, hy1 = world_bbox_xy(house)
        house_bbox = (hx0, hx1, hy0, hy1)
        
        z_top = max((ground.matrix_world @ Vector(c)).z for c in ground.bound_box) + 5.0

        # Determine the objects to place
        if object_names is None:
            # Auto-detect: all visible MESH objects, except house and ground
            objects_to_place = [
                obj for obj in bpy.data.objects
                if obj.type == 'MESH' and obj.visible_get() 
                and obj.name not in {house_name, ground_name}
            ]
        else:
            # Use specified object list
            objects_to_place = [get_obj(name) for name in object_names]

        # Pre-cache local meshes for each object
        local_cache = {obj.name: get_local_mesh(obj, depsgraph) for obj in objects_to_place}
        placed = []  # (obj, bvh, approx_r, matrix_world)
        failed = []  # failed placements

        # forbidden area around the house
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
                # 1) Sample around the house bounding box
                x, y = sample_around_house_bbox(house_bbox, min_clearance, max_distance)

                # Ensure within ground bounds
                if not (gx0 <= x <= gx1 and gy0 <= y <= gy1):
                    continue

                # 2) Raycast downwards
                hit = raycast_down(bvh_ground, x, y, z_top)
                if hit is None:
                    continue
                hit_loc, hit_normal = hit
                z = hit_loc.z

                # 3) Construct transformation matrix
                scale = obj.matrix_world.to_scale()
                scale_mat = Matrix.Diagonal((scale.x, scale.y, scale.z, 1.0))

                rot = Matrix.Identity(4)
                if align_to_ground_normal:
                    rot = make_rot_align_z_to(hit_normal)

                if random_yaw:
                    yaw = Matrix.Rotation(random.uniform(0, 2 * math.pi), 4, 'Z')
                    rot = rot @ yaw

                candidate_world = Matrix.Translation(Vector((x, y, z))) @ rot @ scale_mat

                # 4) overlap test with placed objects
                too_close = False
                for (_obj, _bvh, _r, _mw) in placed:
                    dx = _mw.to_translation().x - x
                    dy = _mw.to_translation().y - y
                    if (dx * dx + dy * dy) < (approx_r + _r) ** 2:
                        too_close = True
                        break
                if too_close:
                    continue

                # 5) collision test with house
                candidate_bvh = bvh_from_transformed_local(verts_local, polys, candidate_world)
                if bvh_house.overlap(candidate_bvh):
                    continue

                # extra check: prevent objects from being placed inside hollow house
                if is_point_inside_hollow_house(bvh_house, x, y, z):
                    continue
                    
                collided = any(_bvh.overlap(candidate_bvh) for (_obj, _bvh, _r, _mw) in placed)
                if collided:
                    continue

                # 6) success
                obj.matrix_world = candidate_world
                placed.append((obj, candidate_bvh, approx_r, candidate_world))
                success = True
                break

            if not success:
                failed.append(obj.name)

        result = {
            "success": len(placed),
            "total": len(objects_to_place),
            "failed": failed
        }
            
        return result

    except Exception as e:
        return {"success": 0, "total": 0, "failed": [], "error": str(e)}
    
# Function to remove ground plane before rendering
def remove_ground():
    # First, apply all constraints to lock object positions
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj.name != 'ground':
            # Select the object
            bpy.context.view_layer.objects.active = obj
            
            # Apply all constraints to make positions permanent
            for constraint in obj.constraints:
                if constraint.type == 'SHRINKWRAP':
                    # Store the current location
                    current_loc = obj.location.copy()
                    
                    # Apply the constraint
                    try:
                        bpy.ops.constraint.apply(constraint=constraint.name)
                    except:
                        # If apply fails, just remove the constraint
                        obj.constraints.remove(constraint)
                    
                    # Ensure location is preserved
                    obj.location = current_loc
    
    # Now remove the ground
    ground = bpy.data.objects.get('ground')
    if ground:
        bpy.data.objects.remove(ground, do_unlink=True)
        print("Ground plane removed successfully")
    else:
        print("No ground plane found to remove")
    
    return True   

# Function to remove all objects except the house
def remove_all_except_house(house_name="house"):
    objects_to_remove = []
    
    for obj in bpy.data.objects:
        # Only remove mesh objects that are not the house
        if obj.type == 'MESH' and obj.name != house_name:
            objects_to_remove.append(obj)
    
    # Remove objects
    for obj in objects_to_remove:
        bpy.data.objects.remove(obj, do_unlink=True)
    
    print(f"Removed {len(objects_to_remove)} objects, keeping only {house_name}")
    return len(objects_to_remove)

# ========================APIs for Rendering================================
# Function to create a hemisphere of cameras around all objects 
def create_hemisphere_cameras(num_cameras=50, camera_height_ratio=1.2):
    """ 
    Args:
        num_cameras: Number of cameras to create (default 50)
        camera_height_ratio: Multiplier for hemisphere radius (default 1.2)
    """
    import math
    import numpy as np
    
    # Get all mesh objects except ground
    objects = []
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj.name != 'ground':
            objects.append(obj)
    
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
    
    # Calculate center and radius of minimum enclosing circle (on XY plane)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    
    # Force hemisphere center to be at ground level (z=0)
    center_z = 0
    
    # Calculate radius as distance from center to furthest corner
    # Include both horizontal distance and vertical height
    radius = 0
    max_height = max_z  # Maximum height of objects
    
    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            # Horizontal distance from center
            horizontal_dist = math.sqrt((world_corner.x - center_x)**2 + (world_corner.y - center_y)**2)
            # For hemisphere, we need to ensure cameras can see tall objects
            # So we consider both horizontal distance and height
            effective_radius = math.sqrt(horizontal_dist**2 + world_corner.z**2)
            radius = max(radius, horizontal_dist, effective_radius)
    
    # Add some margin to the radius
    hemisphere_radius = radius * camera_height_ratio
    
    # Create collection for cameras
    camera_collection = bpy.data.collections.new("Hemisphere_Cameras")
    bpy.context.scene.collection.children.link(camera_collection)
    
    # Generate camera positions on hemisphere
    cameras = []
    
    # Use golden ratio for better distribution
    golden_ratio = (1 + math.sqrt(5)) / 2
    
    for i in range(num_cameras):
        # Generate points on hemisphere using fibonacci sphere
        theta = 2 * math.pi * i / golden_ratio  # Azimuth angle
        phi = math.acos(1 - i / num_cameras)  # Polar angle (0 to pi/2 for hemisphere)
        
        # Convert spherical to cartesian coordinates
        # Center at (center_x, center_y, 0) instead of origin
        x = center_x + hemisphere_radius * math.sin(phi) * math.cos(theta)
        y = center_y + hemisphere_radius * math.sin(phi) * math.sin(theta)
        z = hemisphere_radius * math.cos(phi)  # z starts from 0 (ground level)
        
        # Create camera
        bpy.ops.object.camera_add(location=(x, y, z))
        camera = bpy.context.active_object
        camera.name = f"Camera_Hemisphere_{i:03d}"
        
        # Point camera to scene center at ground level
        look_at_point = Vector((center_x, center_y, max_height/2))  # Look at middle height of scene
        direction = look_at_point - camera.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()
        
        # Move camera to the hemisphere collection
        # First ensure it's linked to scene collection
        if camera.name not in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.link(camera)
        
        # Now unlink from scene collection and link to camera collection
        bpy.context.scene.collection.objects.unlink(camera)
        camera_collection.objects.link(camera)
        
        # Set camera properties
        camera.data.lens = 35  # Standard lens
        camera.data.clip_end = hemisphere_radius * 3  # Ensure we can see everything
        
        cameras.append(camera)
    
    # Create empty at scene center for visualization
    bpy.ops.object.empty_add(type='SPHERE', location=(center_x, center_y, 0))
    empty = bpy.context.active_object
    empty.name = "Hemisphere_Center"
    empty.empty_display_size = 0.5
    
    return cameras

# Function to render the scene and export images(default path is "results/images")
def render_all_hemisphere_cameras(output_path=None, file_format="PNG"):
    
    # If no path specified, use default path relative to the blend file or current directory
    if output_path is None:
        # Try to get the directory of the current blend file
        if bpy.data.filepath:
            project_dir = os.path.dirname(bpy.data.filepath)
        else:
            # If no blend file saved, use current working directory
            project_dir = os.getcwd()
        
        # Create results/images directory
        output_path = os.path.join(project_dir, "results", "images")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)
    
    # Get all hemisphere cameras
    cameras = [obj for obj in bpy.data.objects if obj.type == 'CAMERA' and 'Camera_Hemisphere' in obj.name]
    
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
        
        # Set active camera
        bpy.context.scene.camera = camera
        
        # Set output path
        output_file = os.path.join(output_path, f"{camera.name}.{file_format.lower()}")
        bpy.context.scene.render.filepath = output_file
        
        # Render
        bpy.ops.render.render(write_still=True)
    
    # Restore original camera
    bpy.context.scene.camera = original_camera
    
    print(f"Completed rendering {len(cameras)} views to {output_path}")

# Function to set HDRI environment lighting
def set_hdri_environment(hdri_path, strength=1.0, rotation_z=0.0):
    # Check if file exists
    if not os.path.exists(hdri_path):
        print(f"Error: HDRI file not found: {hdri_path}")
        return False
    
    # Get the world
    world = bpy.context.scene.world
    
    # Enable use of nodes
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    
    # Clear existing nodes
    nodes.clear()
    
    # Add required nodes
    # 1. Texture Coordinate node
    tex_coord = nodes.new(type='ShaderNodeTexCoord')
    tex_coord.location = (-800, 300)
    
    # 2. Mapping node for rotation control
    mapping = nodes.new(type='ShaderNodeMapping')
    mapping.location = (-600, 300)
    mapping.inputs['Rotation'].default_value[2] = rotation_z  # Z rotation
    
    # 3. Environment Texture node
    env_texture = nodes.new(type='ShaderNodeTexEnvironment')
    env_texture.location = (-400, 300)
    env_texture.image = bpy.data.images.load(hdri_path)
    env_texture.interpolation = 'Linear'  # Better quality
    
    # 4. Background shader
    background = nodes.new(type='ShaderNodeBackground')
    background.location = (-100, 300)
    background.inputs['Strength'].default_value = strength
    
    # 5. World Output
    output = nodes.new(type='ShaderNodeOutputWorld')
    output.location = (100, 300)
    
    # Connect nodes
    links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
    links.new(mapping.outputs['Vector'], env_texture.inputs['Vector'])
    links.new(env_texture.outputs['Color'], background.inputs['Color'])
    links.new(background.outputs['Background'], output.inputs['Surface'])
    
    # Set viewport shading to use scene world
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.use_scene_world = True
                    space.shading.use_scene_lights = True
    
    print(f"HDRI environment set: {hdri_path}")
    return True

# =======================APIs for ground truth extraction=================================
# Function to export camera intrinsics and extrinsics
def export_camera_parameters(output_path=None):
    
    # Default output path
    if output_path is None:
        if bpy.data.filepath:
            project_dir = os.path.dirname(bpy.data.filepath)
        else:
            project_dir = os.getcwd()
        output_path = os.path.join(project_dir, "results", "intrinsics_and_extrinsics.csv")
    
    # Create directory if needed
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Get all hemisphere cameras
    cameras = [obj for obj in bpy.data.objects if obj.type == 'CAMERA' and 'Camera_Hemisphere' in obj.name]
    
    if not cameras:
        print("No hemisphere cameras found!")
        return
    
    # Prepare CSV data
    csv_data = []
    
    # Get render resolution
    render = bpy.context.scene.render
    width = render.resolution_x
    height = render.resolution_y
    
    for camera in cameras:
        cam_data = camera.data
        
        # Calculate intrinsic parameters
        # Focal length in pixels
        if cam_data.sensor_fit == 'HORIZONTAL':
            sensor_size = cam_data.sensor_width
            fx = (width * cam_data.lens) / sensor_size
            fy = fx  # Assuming square pixels
        else:
            sensor_size = cam_data.sensor_height
            fy = (height * cam_data.lens) / sensor_size
            fx = fy
        
        # Principal point (image center)
        cx = width / 2.0
        cy = height / 2.0
        
        # Get camera transformation matrix
        cam_matrix = camera.matrix_world
        
        

        # Convert to OpenCV coordinate system
        flip = Matrix([
            [1, 0, 0],
            [0, -1, 0],
            [0, 0, -1]
        ])

        # get rotation matrix
        R_blender = cam_matrix.to_3x3()
        R_opencv = flip @ R_blender

        # get translation vector
        t_blender = cam_matrix.translation
        t_opencv = flip @ t_blender
        
        # Flatten rotation matrix for CSV (row-major order)
        r11, r12, r13 = R_opencv[0]
        r21, r22, r23 = R_opencv[1]
        r31, r32, r33 = R_opencv[2]
        tx, ty, tz = t_opencv
        
        # Add row to CSV data
        csv_data.append({
            'camera_name': camera.name,
            'fx': fx,
            'fy': fy,
            'cx': cx,
            'cy': cy,
            'k1': 0.0,  # No distortion in Blender
            'k2': 0.0,
            'k3': 0.0,
            'p1': 0.0,
            'p2': 0.0,
            'r11': r11,
            'r12': r12,
            'r13': r13,
            'r21': r21,
            'r22': r22,
            'r23': r23,
            'r31': r31,
            'r32': r32,
            'r33': r33,
            'tx': tx,
            'ty': ty,
            'tz': tz,
            'width': width,
            'height': height
        })
    
    # Write CSV file
    with open(output_path, 'w', newline='') as csvfile:
        fieldnames = ['camera_name', 'fx', 'fy', 'cx', 'cy', 'k1', 'k2', 'k3', 'p1', 'p2',
                     'r11', 'r12', 'r13', 'r21', 'r22', 'r23', 'r31', 'r32', 'r33',
                     'tx', 'ty', 'tz', 'width', 'height']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_data)
    
    print(f"Camera parameters exported to: {output_path}")
    return output_path

# Function to export scene as OBJ file (Blender 4.0+ compatible)
def export_obj(output_path=None):

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
            export_selected_objects=False,  # Export all objects
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
            raise RuntimeError("Neither new (wm.obj_export) nor legacy (export_scene.obj) OBJ export operators are available")
    
    return output_path

# Function to export house-only results (images, camera parameters, and OBJ)
def export_house_only_results(base_output_dir=None):
    if base_output_dir is None:
        if bpy.data.filepath:
            project_dir = os.path.dirname(bpy.data.filepath)
        else:
            project_dir = os.getcwd()
        base_output_dir = os.path.join(project_dir, "results", "house_only")
    
    # Create directories
    images_dir = os.path.join(base_output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # Render all views
    render_all_hemisphere_cameras(output_path=images_dir)
    
    # Export camera parameters
    camera_params_path = os.path.join(base_output_dir, "intrinsics_and_extrinsics.csv")
    export_camera_parameters(output_path=camera_params_path)
    
    # Export OBJ
    obj_path = os.path.join(base_output_dir, "house.obj")
    export_obj(output_path=obj_path)
    
    return {
        "images_dir": images_dir,
        "camera_params": camera_params_path,
        "obj": obj_path
    }