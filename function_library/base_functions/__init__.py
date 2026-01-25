"""
Base Functions Package - Three-tiered function library for Blender scene construction.

Levels:
- Minimal: 5 core functions for basic operations
- Partial: 9 functions including ground and camera management
- Full: 14 functions with advanced placement and lighting

Usage:
    from function_library.base_functions.minimal import *  # 5 functions
    from function_library.base_functions.partial import *  # 9 functions
    from function_library.base_functions.full import *     # 14 functions
"""

# Define which level to use by default
from .full import *
