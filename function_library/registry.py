"""
Function Registry - 定义所有可用函数的元数据

函数按三级划分:
- Minimal (5): 最基础的场景操作
- Partial (9): Minimal + 地面和相机操作
- Full (14): 所有函数
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional


class FunctionLevel(Enum):
    """函数所属的级别"""
    MINIMAL = "minimal"
    PARTIAL = "partial"
    FULL = "full"


@dataclass
class ParameterInfo:
    """函数参数信息"""
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[str] = None


@dataclass
class FunctionInfo:
    """函数元数据"""
    name: str
    description: str
    level: FunctionLevel
    parameters: List[ParameterInfo] = field(default_factory=list)
    returns: str = "None"
    example: str = ""
    category: str = "general"

    def to_summary(self) -> str:
        """生成函数摘要供LLM使用"""
        params_str = ", ".join([
            f"{p.name}: {p.type}" + (f" = {p.default}" if p.default else "")
            for p in self.parameters
        ])
        return f"{self.name}({params_str}) -> {self.returns}\n    {self.description}"


class FunctionRegistry:
    """函数注册表 - 管理所有可用函数的元数据"""

    def __init__(self):
        self._functions: Dict[str, FunctionInfo] = {}
        self._register_all_functions()

    def _register_all_functions(self):
        """注册所有14个内置函数"""

        # ========== MINIMAL LEVEL (5 functions) ==========

        self._register(FunctionInfo(
            name="clear_scene",
            description="Clear all objects from the Blender scene, preparing for a fresh start",
            level=FunctionLevel.MINIMAL,
            parameters=[],
            returns="None",
            example="clear_scene()",
            category="scene"
        ))

        self._register(FunctionInfo(
            name="import_object",
            description="Import a 3D object (GLB/GLTF/OBJ) into the scene at a specified location",
            level=FunctionLevel.MINIMAL,
            parameters=[
                ParameterInfo("filepath", "str", "Path to the 3D model file"),
                ParameterInfo("location", "tuple", "XYZ coordinates for placement", default="(0, 0, 0)"),
                ParameterInfo("name", "str", "Name to assign to the imported object", required=False),
            ],
            returns="bpy.types.Object",
            example='import_object("/path/to/house.glb", location=(0, 0, 0), name="House")',
            category="object"
        ))

        self._register(FunctionInfo(
            name="scale_object",
            description="Scale an object uniformly or non-uniformly",
            level=FunctionLevel.MINIMAL,
            parameters=[
                ParameterInfo("obj", "bpy.types.Object", "The object to scale"),
                ParameterInfo("scale", "float or tuple", "Scale factor (uniform) or XYZ scale tuple"),
            ],
            returns="None",
            example="scale_object(house_obj, scale=2.0)  # or scale_object(tree_obj, scale=(1, 1, 2))",
            category="object"
        ))

        self._register(FunctionInfo(
            name="render_all_hemisphere_cameras",
            description="Render the scene from all hemisphere camera positions and save images",
            level=FunctionLevel.MINIMAL,
            parameters=[
                ParameterInfo("output_dir", "str", "Directory to save rendered images"),
                ParameterInfo("resolution", "tuple", "Image resolution (width, height)", default="(1920, 1080)"),
            ],
            returns="List[str]",
            example='render_all_hemisphere_cameras("/output/renders", resolution=(1920, 1080))',
            category="render"
        ))

        self._register(FunctionInfo(
            name="export_obj",
            description="Export the current scene or selected objects to OBJ format",
            level=FunctionLevel.MINIMAL,
            parameters=[
                ParameterInfo("filepath", "str", "Output file path"),
                ParameterInfo("selected_only", "bool", "Export only selected objects", default="False"),
            ],
            returns="None",
            example='export_obj("/output/scene.obj")',
            category="export"
        ))

        # ========== PARTIAL LEVEL (4 additional functions) ==========

        self._register(FunctionInfo(
            name="add_ground",
            description="Add a ground plane to the scene with optional material",
            level=FunctionLevel.PARTIAL,
            parameters=[
                ParameterInfo("size", "float", "Size of the ground plane", default="100"),
                ParameterInfo("material", "str", "Material name or texture path", required=False),
            ],
            returns="bpy.types.Object",
            example="ground = add_ground(size=100)",
            category="scene"
        ))

        self._register(FunctionInfo(
            name="stick_object_to_ground",
            description="Move an object so its bottom touches the ground plane (Z=0)",
            level=FunctionLevel.PARTIAL,
            parameters=[
                ParameterInfo("obj", "bpy.types.Object", "The object to adjust"),
            ],
            returns="None",
            example="stick_object_to_ground(tree_obj)",
            category="object"
        ))

        self._register(FunctionInfo(
            name="remove_ground",
            description="Remove the ground plane from the scene",
            level=FunctionLevel.PARTIAL,
            parameters=[],
            returns="None",
            example="remove_ground()",
            category="scene"
        ))

        self._register(FunctionInfo(
            name="create_hemisphere_cameras",
            description="Create a set of cameras arranged in a hemisphere around the scene center",
            level=FunctionLevel.PARTIAL,
            parameters=[
                ParameterInfo("num_cameras", "int", "Number of cameras to create", default="8"),
                ParameterInfo("radius", "float", "Distance from center", default="10"),
                ParameterInfo("target", "tuple", "Point cameras look at", default="(0, 0, 0)"),
            ],
            returns="List[bpy.types.Object]",
            example="cameras = create_hemisphere_cameras(num_cameras=12, radius=15)",
            category="camera"
        ))

        # ========== FULL LEVEL (5 additional functions) ==========

        self._register(FunctionInfo(
            name="set_object_location",
            description="Set the world location of an object",
            level=FunctionLevel.FULL,
            parameters=[
                ParameterInfo("obj", "bpy.types.Object", "The object to move"),
                ParameterInfo("location", "tuple", "New XYZ coordinates"),
            ],
            returns="None",
            example="set_object_location(tree_obj, (5, 3, 0))",
            category="object"
        ))

        self._register(FunctionInfo(
            name="rotate_object",
            description="Rotate an object by specified Euler angles",
            level=FunctionLevel.FULL,
            parameters=[
                ParameterInfo("obj", "bpy.types.Object", "The object to rotate"),
                ParameterInfo("rotation", "tuple", "Euler angles (X, Y, Z) in radians"),
            ],
            returns="None",
            example="rotate_object(house_obj, (0, 0, math.pi/4))  # Rotate 45 degrees around Z",
            category="object"
        ))

        self._register(FunctionInfo(
            name="get_object_bounds",
            description="Get the bounding box dimensions of an object",
            level=FunctionLevel.FULL,
            parameters=[
                ParameterInfo("obj", "bpy.types.Object", "The object to measure"),
            ],
            returns="Dict[str, float]",
            example='bounds = get_object_bounds(house_obj)  # Returns {"width": ..., "depth": ..., "height": ...}',
            category="object"
        ))

        self._register(FunctionInfo(
            name="place_objects_around_house",
            description="Automatically place objects around a central house with collision avoidance",
            level=FunctionLevel.FULL,
            parameters=[
                ParameterInfo("house_obj", "bpy.types.Object", "The central house object"),
                ParameterInfo("objects", "List[Dict]", "List of objects to place with their properties"),
                ParameterInfo("min_distance", "float", "Minimum distance from house", default="2.0"),
                ParameterInfo("max_distance", "float", "Maximum distance from house", default="10.0"),
            ],
            returns="List[bpy.types.Object]",
            example='place_objects_around_house(house, [{"filepath": "tree.glb", "count": 3}])',
            category="object"
        ))

        self._register(FunctionInfo(
            name="setup_lighting",
            description="Set up scene lighting with sun and ambient light",
            level=FunctionLevel.FULL,
            parameters=[
                ParameterInfo("sun_angle", "tuple", "Sun direction angles", default="(45, 45)"),
                ParameterInfo("sun_intensity", "float", "Sun light intensity", default="5.0"),
                ParameterInfo("ambient_intensity", "float", "Ambient light intensity", default="0.5"),
            ],
            returns="None",
            example="setup_lighting(sun_angle=(60, 30), sun_intensity=3.0)",
            category="scene"
        ))

    def _register(self, func_info: FunctionInfo):
        """注册一个函数"""
        self._functions[func_info.name] = func_info

    def get_function(self, name: str) -> Optional[FunctionInfo]:
        """获取函数信息"""
        return self._functions.get(name)

    def get_functions_by_level(self, level: FunctionLevel, include_lower: bool = True) -> List[FunctionInfo]:
        """
        获取指定级别的函数

        Args:
            level: 目标级别
            include_lower: 是否包含更低级别的函数
        """
        level_order = [FunctionLevel.MINIMAL, FunctionLevel.PARTIAL, FunctionLevel.FULL]
        target_idx = level_order.index(level)

        if include_lower:
            valid_levels = set(level_order[:target_idx + 1])
        else:
            valid_levels = {level}

        return [f for f in self._functions.values() if f.level in valid_levels]

    def get_all_functions(self) -> List[FunctionInfo]:
        """获取所有函数"""
        return list(self._functions.values())

    def get_function_names_by_level(self, level: FunctionLevel, include_lower: bool = True) -> List[str]:
        """获取指定级别的函数名列表"""
        return [f.name for f in self.get_functions_by_level(level, include_lower)]

    def function_exists(self, name: str) -> bool:
        """检查函数是否存在"""
        return name in self._functions

    def get_summary_for_level(self, level: FunctionLevel) -> str:
        """
        生成指定级别的函数摘要，供LLM使用
        """
        functions = self.get_functions_by_level(level)

        # 按类别分组
        by_category: Dict[str, List[FunctionInfo]] = {}
        for f in functions:
            if f.category not in by_category:
                by_category[f.category] = []
            by_category[f.category].append(f)

        lines = [f"# Available Functions (Level: {level.value})"]
        lines.append(f"# Total: {len(functions)} functions\n")

        for category, funcs in sorted(by_category.items()):
            lines.append(f"## {category.upper()}")
            for f in funcs:
                lines.append(f.to_summary())
                lines.append("")

        return "\n".join(lines)

    def find_similar_functions(self, description: str) -> List[FunctionInfo]:
        """
        根据描述找到可能相似的函数（简单关键词匹配）
        用于检测新函数是否与现有函数重复
        """
        description_lower = description.lower()
        keywords = description_lower.split()

        scored_functions = []
        for func in self._functions.values():
            score = 0
            func_text = f"{func.name} {func.description}".lower()
            for keyword in keywords:
                if keyword in func_text:
                    score += 1
            if score > 0:
                scored_functions.append((score, func))

        # 按得分排序，返回匹配的函数
        scored_functions.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored_functions[:5]]  # 返回前5个


# 模块级别的单例
_registry_instance: Optional[FunctionRegistry] = None


def get_registry() -> FunctionRegistry:
    """获取函数注册表单例"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = FunctionRegistry()
    return _registry_instance
