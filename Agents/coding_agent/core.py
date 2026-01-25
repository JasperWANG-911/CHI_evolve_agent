import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from anthropic import Anthropic

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from function_library import FunctionLibraryManager, FunctionLevel


class CodingAgent:
    """
    Coding Agent: Generate and manage Blender Python code for scene construction.

    Enhanced with Capability Gatekeeping:
    - Can detect capability gaps when current function library is insufficient
    - Can generate new function proposals for missing capabilities
    - Submits proposals to PR Review Agent for approval
    """

    def __init__(self, initial_level: FunctionLevel = FunctionLevel.FULL):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY environment variable")

        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"

        # Path to execution_code.py in project root
        self.project_root = Path(__file__).parent.parent.parent
        self.execution_code_path = self.project_root / "execution_code.py"

        # Track fixed steps
        self.fixed_steps = set()

        # Store combination data
        self.current_combination = None

        # Initialize Function Library Manager
        self.library_manager = FunctionLibraryManager(
            project_root=self.project_root,
            initial_level=initial_level
        )

        # Store generated code and step info
        self.generated_code = ""
        self.step_descriptions = {}

        # Store capability gap info for current task
        self.current_capability_gaps = []
        self.pending_prs = []

    @property
    def api_summary(self) -> str:
        """Dynamic API summary based on current function library level"""
        return self.library_manager.get_function_summary()
    
    def _load_api_reference(self) -> str:
        """Load scene construction API reference."""
        api_path = self.project_root / "API.py"
        if api_path.exists():
            with open(api_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    
    def set_combination_data(self, combination: Dict):
        """Set the current combination data for intelligent code generation"""
        self.current_combination = combination
        self.fixed_steps.clear()  # Reset fixed steps for new combination
        self.step_descriptions.clear()
    
    def _generate_complete_scene_code(self) -> str:
        """Generate complete scene construction code based on combination data"""
        if not self.current_combination:
            raise RuntimeError("No combination data set")
        
        # Fix file paths to be absolute
        fixed_combination = self.current_combination.copy()
        fixed_combination["objects"] = []
        
        for obj in self.current_combination["objects"]:
            fixed_obj = obj.copy()
            # Convert relative path to absolute path
            if not os.path.isabs(obj["file_path"]):
                fixed_obj["file_path"] = str(self.project_root / obj["file_path"])
            # Normalize path separators for current OS
            # On macOS/Linux, convert backslashes to forward slashes
            # On Windows, the path will already use backslashes
            import platform
            if platform.system() != "Windows":
                fixed_obj["file_path"] = fixed_obj["file_path"].replace("\\", "/")
            fixed_combination["objects"].append(fixed_obj)
        
        # Build prompt for Claude
        prompt = f"""Generate complete Blender Python code to construct a scene with the following objects:

    {json.dumps(fixed_combination, indent=2)}

    Available API functions:
    {self.api_summary}

    CRITICAL RULES:
    1. When you use import_object("path/to/file", "instance_id"), the object will be renamed to exactly "instance_id"
    2. In ALL subsequent operations (stick_object_to_ground, scale_object, etc.), you MUST use the exact same "instance_id"
    3. NEVER use names like "tree", "tree.000", "tree.001" - ALWAYS use the instance_id from the combination data

    Example:
    - If combination says instance_id is "tree_1", then:
    - import_object("path/to/tree.blend", "tree_1")
    - stick_object_to_ground("tree_1")  # NOT "tree" or "tree.000"
    - scale_object("tree_1", 2.0)       # NOT "tree" or "tree.000"

    Requirements:
    1. Start by clearing the scene and adding a ground plane (size 100)
    2. Import the house first (if present) and stick it to the ground using stick_object_to_ground("house")
    3. For each other object one by one: import, place, and scale
        - use import_object("file/path/to/object", "instance_id") to import
        - use stick_object_to_ground("instance_id") to stick it to the ground
        - use scale_object("instance_id", scale_factors) to scale
    4. After all objects are imported and scaled, use place_objects_around_house(). The max_distance parameter should be set to be smaller than 5.
    5. Remove the ground plane using remove_ground() to show the HDRI ground instead
    6. Set up HDRI environment lighting using set_hdri_environment() before creating cameras
    - IMPORTANT: The HDRI path must be an absolute path. Use the project root path: {self.project_root}
    - HDRI files are located in "{self.project_root}/Assets/hdri/" directory
    - Example: set_hdri_environment(r"{self.project_root}/Assets/hdri/env_1.exr")
    7. Create hemisphere cameras to capture the scene from all angles use create_hemisphere_cameras()
    8. Export the image captured by each camera using render_all_hemisphere_cameras()
    9. Export camera parameters using export_camera_parameters() with 'opencv' coordinate system
    10. Export scene mesh as .obj file using export_obj() for ground truth data
    11. Remove all objects except the house using remove_all_except_house()
    12. Export house-only results using export_house_only_results() to separate directory

    IMPORTANT: Include step comments in this exact format:
    # Step 1: Clear the scene
    clear_scene()

    # Step 2: Add ground plane
    add_ground(size=100)

    etc.

    Output only the Python code without markdown formatting."""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=3000,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        
        generated_code = response.content[0].text.strip()
        
        # Clean any markdown formatting
        import re
        if generated_code.startswith('```') and generated_code.endswith('```'):
            generated_code = re.sub(r'^```(?:python)?\n?', '', generated_code)
            generated_code = re.sub(r'\n?```$', '', generated_code)
        
        # Parse step descriptions from the generated code
        self._parse_step_descriptions(generated_code)
        
        # Debug: Print parsed steps
        print(f"DEBUG: Parsed {len(self.step_descriptions)} steps:")
        for step_num, desc in self.step_descriptions.items():
            print(f"  Step {step_num}: {desc}")
        
        return generated_code
    
    def _parse_step_descriptions(self, code: str):
        """Parse step descriptions from the code"""
        lines = code.split('\n')
        for line in lines:
            if line.strip().startswith('# Step ') and ':' in line:
                try:
                    parts = line.split(':', 1)
                    step_num = int(parts[0].split('Step ')[1])
                    description = parts[1].strip()
                    self.step_descriptions[step_num] = description
                except:
                    pass
    
    def get_step_info(self, step: int) -> dict:
        """Get information about a specific step"""
        return {
            "step": step,
            "description": self.step_descriptions.get(step, f"Step {step}"),
            "is_scale_step": "scale" in self.step_descriptions.get(step, "").lower()
        }
    
    def get_step_code(self, step: int) -> Optional[str]:
        """Extract only the code for a specific step"""
        if not self.generated_code:
            return None
            
        current_code = self._read_current_code()
        step_code = self._extract_step_from_code(current_code, step)
        
        if step_code:
            # Add necessary imports and setup for this step
            imports = """import bpy
import math
import random
from mathutils import Vector
import sys
import os

# Add API path and import functions
sys.path.append(r'{}')
from API import *

""".format(self.project_root)
            
            # Return just the step code with imports
            return imports + step_code
        
        return None
    
    def _extract_step_from_code(self, code: str, step_num: int) -> Optional[str]:
        """Extract a specific step from the complete code"""
        lines = code.split('\n')
        step_start = None
        step_lines = []
        
        for i, line in enumerate(lines):
            if f'# Step {step_num}:' in line:
                step_start = i
                step_lines = [line]
            elif step_start is not None:
                if line.strip().startswith('# Step ') and ':' in line:
                    # Found next step
                    break
                else:
                    step_lines.append(line)
        
        if step_lines:
            return '\n'.join(step_lines)
        return None
    
    def generate_code(self, step: int, task_description: str, review_result: Optional[dict] = None) -> dict:
        """
        Generate or update code based on step and review results.
        If step is 1, generate complete code. Otherwise, extract/update specific step.
        """
        try:
            # Check if we have combination data
            if not self.current_combination:
                return {
                    "success": False,
                    "message": "No combination data set. Please set combination data first.",
                    "code_path": str(self.execution_code_path)
                }
            
            # Handle review results
            if review_result:
                if review_result.get("ok", False):
                    self.fixed_steps.add(step)
                    return {
                        "success": True,
                        "message": f"Step {step} passed review and marked as fixed",
                        "code_path": str(self.execution_code_path)
                    }
            
            # For step 1, generate complete code
            if step == 1:
                complete_code = self._generate_complete_scene_code()
                self.generated_code = complete_code
                
                # Add imports
                final_code = "import bpy\nimport math\nimport random\nfrom mathutils import Vector\n"
                final_code += "import sys\nimport os\n\n"
                final_code += "# Add API path and import functions\n"
                final_code += f"sys.path.append(r'{self.project_root}')\n"
                final_code += "from API import *\n\n"
                final_code += complete_code
                
                self._write_code(final_code)
                
                # Count total steps in generated code
                total_steps = len(self.step_descriptions)
                
                return {
                    "success": True,
                    "message": f"Generated complete scene code with {total_steps} steps",
                    "code_path": str(self.execution_code_path),
                    "total_steps": total_steps
                }
            
            # For other steps, extract from existing code or regenerate if needed
            current_code = self._read_current_code()
            
            if review_result and not review_result.get("ok", False):
                # Need to fix this step based on review comment
                step_code = self._fix_step_code(step, task_description, review_result["comment"])
                
                # Replace the step in the code
                updated_code = self._replace_step_in_code(current_code, step, step_code)
                self._write_code(updated_code)
                
                return {
                    "success": True,
                    "message": f"Fixed step {step} based on review feedback",
                    "code_path": str(self.execution_code_path)
                }
            
            # Extract and execute the specific step
            step_code = self._extract_step_from_code(current_code, step)
            if step_code:
                return {
                    "success": True,
                    "message": f"Ready to execute step {step}",
                    "code_path": str(self.execution_code_path)
                }
            else:
                return {
                    "success": False,
                    "message": f"Step {step} not found in generated code",
                    "code_path": str(self.execution_code_path)
                }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Error generating code: {str(e)}",
                "code_path": str(self.execution_code_path)
            }
    
    def _fix_step_code(self, step: int, task_description: str, review_comment: str) -> str:
        """Generate fixed code for a specific step based on review feedback"""
        current_code = self._read_current_code()
        current_step_code = self._extract_step_from_code(current_code, step)
        
        # Check if this is a scaling step
        is_scale_step = "scale" in task_description.lower()
        
        # Check if object is not visible
        if "not visible" in review_comment.lower():
            if is_scale_step:
                # For scale steps, we should NOT change to placement
                # Instead, suggest checking if the object was properly placed
                prompt = f"""The object is not visible during a scaling step. This likely means the object wasn't properly placed in a previous step.

        Current scale code:
        {current_step_code}

        Task: {task_description}
        Review comment: {review_comment}

        Available API functions:
        {self.api_summary}

        IMPORTANT RULES:
        1. ONLY use functions that exist in the API reference above
        2. Do NOT create new functions like object_exists() or check_object_visibility()
        3. The scale operation should remain as is - do NOT replace it with placement
        4. You can use bpy.data.objects.get() to check if an object exists
        5. Keep the same step comment format

        Generate only the fixed code for this step.
        Output only the Python code without markdown formatting."""
            else:
                # For placement steps, use place_single_object_around_house
                import re
                object_match = re.search(r'["\']([\w_]+)["\']', current_step_code)
                if object_match:
                    object_name = object_match.group(1)
                    
                    # Generate code to use place_single_object_around_house
                    prompt = f"""The object {object_name} is not visible, likely inside the house.
        Generate code for this step that uses place_single_object_around_house() instead of the current placement method.

        Current code:
        {current_step_code}

        Generate only the fixed code that places the object around the house safely.
        Output only the Python code without markdown formatting."""
                else:
                    # Fallback to regular fix
                    prompt = self._build_fix_prompt(current_step_code, task_description, review_comment)
        else:
            # Regular scaling or other fixes
            prompt = self._build_fix_prompt(current_step_code, task_description, review_comment)
        
        # Get response from Claude
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        
        fixed_code = response.content[0].text.strip()
        
        # Clean markdown if present
        import re
        if fixed_code.startswith('```') and fixed_code.endswith('```'):
            fixed_code = re.sub(r'^```(?:python)?\n?', '', fixed_code)
            fixed_code = re.sub(r'\n?```$', '', fixed_code)
        
        return fixed_code

    def _build_fix_prompt(self, current_step_code: str, task_description: str, review_comment: str) -> str:
        """Build the prompt for fixing code"""
        # Check if this is a scaling step
        is_scale_step = "scale" in task_description.lower()
        
        prompt = f"""Fix the following Blender Python code based on the review feedback:

    Current code:
    {current_step_code}

    Task description: {task_description}
    Review comment: {review_comment}

    Available API functions:
    {self.api_summary}

    {"IMPORTANT: This is a scaling step. Adjust the scale factor based on the review comment to make the object proportional to the house. Remember that scale_object uses absolute scaling, not relative." if is_scale_step else ""}

    Generate only the fixed code for this step, maintaining the same comment format.
    Output only the Python code without markdown formatting."""
        
        return prompt
    
    def _replace_step_in_code(self, full_code: str, step_num: int, new_step_code: str) -> str:
        """Replace a specific step in the full code"""
        lines = full_code.split('\n')
        new_lines = []
        skip_mode = False
        step_found = False
        
        for line in lines:
            if f'# Step {step_num}:' in line:
                skip_mode = True
                step_found = True
                # Add the new step code
                new_lines.extend(new_step_code.split('\n'))
            elif skip_mode and line.strip().startswith('# Step ') and ':' in line:
                # Found next step, stop skipping
                skip_mode = False
                new_lines.append(line)
            elif not skip_mode:
                new_lines.append(line)
        
        return '\n'.join(new_lines)
    
    def _read_current_code(self) -> str:
        """Read current execution_code.py content."""
        if self.execution_code_path.exists():
            with open(self.execution_code_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    
    def _write_code(self, code: str):
        """Write code to execution_code.py."""
        with open(self.execution_code_path, 'w', encoding='utf-8') as f:
            f.write(code)

    # ========== Capability Gatekeeping Methods ==========

    def set_library_level(self, level: FunctionLevel):
        """Set the function library level"""
        self.library_manager.set_level(level)

    def get_library_status(self) -> Dict[str, Any]:
        """Get current function library status"""
        return self.library_manager.get_library_status()

    def generate_task_outline(self, task_description: str) -> List[Dict[str, Any]]:
        """
        Generate a pseudo-code outline for the task, identifying required capabilities.

        Returns:
            List of steps, each with:
            - step: int
            - action: str (what to do)
            - required_capability: str (function name or capability needed)
            - input: str (expected input)
            - output: str (expected output)
        """
        available_functions = self.library_manager.get_available_function_names()

        prompt = f"""Analyze this Blender scene generation task and create a step-by-step outline.

Task: {task_description}

Available functions in the current library:
{', '.join(available_functions)}

For each step, identify:
1. What action needs to be performed
2. What capability/function is needed (use exact function name if available, or describe the needed capability)
3. What input is required
4. What output is expected

Return a JSON array with this format:
[
    {{"step": 1, "action": "Clear the scene", "required_capability": "clear_scene", "input": "none", "output": "empty scene"}},
    {{"step": 2, "action": "Import house model", "required_capability": "import_object", "input": "filepath", "output": "house object"}},
    ...
]

IMPORTANT:
- If a required capability doesn't match any available function, describe what capability is needed
- Be specific about function names when they exist
- Output ONLY the JSON array, no other text"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Clean markdown if present
        if response_text.startswith('```'):
            response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)

        try:
            outline = json.loads(response_text)
            return outline
        except json.JSONDecodeError:
            # Try to extract JSON from response
            match = re.search(r'\[[\s\S]*\]', response_text)
            if match:
                return json.loads(match.group())
            return []

    def check_capability_coverage(self, outline: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check if the current function library can cover all required capabilities.

        Returns:
            {
                "has_gaps": bool,
                "gaps": List of missing capabilities,
                "coverage_rate": float (0-1),
                "covered_steps": List of step numbers that are covered,
                "uncovered_steps": List of step numbers that need new functions
            }
        """
        available_functions = set(self.library_manager.get_available_function_names())

        covered_steps = []
        uncovered_steps = []
        gaps = []

        for step in outline:
            capability = step.get("required_capability", "")

            # Check if exact match exists
            if capability in available_functions:
                covered_steps.append(step["step"])
            else:
                # Check if similar function exists
                check_result = self.library_manager.check_capability(capability)
                if check_result["has_capability"]:
                    covered_steps.append(step["step"])
                else:
                    uncovered_steps.append(step["step"])
                    gaps.append({
                        "step": step["step"],
                        "action": step.get("action", ""),
                        "required_capability": capability,
                        "similar_functions": check_result.get("similar_functions", [])
                    })

        total_steps = len(outline)
        coverage_rate = len(covered_steps) / total_steps if total_steps > 0 else 1.0

        result = {
            "has_gaps": len(gaps) > 0,
            "gaps": gaps,
            "coverage_rate": coverage_rate,
            "covered_steps": covered_steps,
            "uncovered_steps": uncovered_steps
        }

        # Store gaps for later use
        self.current_capability_gaps = gaps

        return result

    def propose_new_function(self, gap: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a new function proposal for a capability gap.

        Args:
            gap: {
                "step": int,
                "action": str,
                "required_capability": str,
                "similar_functions": List[str]
            }

        Returns:
            {
                "function_name": str,
                "function_code": str,
                "description": str,
                "parameters": List[Dict],
                "returns": str,
                "context": str
            }
        """
        # Load existing API for reference
        api_reference = self._load_api_reference()

        prompt = f"""Generate a new Blender Python function for this capability gap.

Required capability: {gap['required_capability']}
Action needed: {gap['action']}
Similar existing functions: {', '.join(gap.get('similar_functions', [])) or 'None'}

Current API reference (for style consistency):
```python
{api_reference[:3000]}  # Truncated for context
```

Requirements:
1. The function should be reusable, not just a one-time solution
2. Follow the naming convention of existing functions (snake_case)
3. Include proper docstring with parameters and return value
4. Handle edge cases gracefully
5. Use bpy (Blender Python API) appropriately

Return a JSON object with this format:
{{
    "function_name": "descriptive_function_name",
    "function_code": "def function_name(param1, param2=default):\\n    \\\"\\\"\\\"Docstring\\\"\\\"\\\"\\n    # implementation\\n    pass",
    "description": "Brief description of what the function does",
    "parameters": [
        {{"name": "param1", "type": "str", "description": "Description", "required": true}},
        {{"name": "param2", "type": "int", "description": "Description", "required": false, "default": "10"}}
    ],
    "returns": "Return type and description"
}}

Output ONLY the JSON object, no other text."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Clean markdown if present
        if response_text.startswith('```'):
            response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)

        try:
            proposal = json.loads(response_text)
            proposal["context"] = f"Task required: {gap['action']}. Capability gap: {gap['required_capability']}"
            return proposal
        except json.JSONDecodeError:
            # Try to extract JSON
            match = re.search(r'\{[\s\S]*\}', response_text)
            if match:
                proposal = json.loads(match.group())
                proposal["context"] = f"Task required: {gap['action']}. Capability gap: {gap['required_capability']}"
                return proposal
            raise ValueError(f"Failed to parse function proposal: {response_text}")

    def submit_pr(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit a new function proposal as a PR to the review queue.

        Args:
            proposal: Function proposal from propose_new_function()

        Returns:
            {
                "pr_id": str,
                "status": str,
                "message": str
            }
        """
        pr_id = self.library_manager.submit_new_function(
            function_name=proposal["function_name"],
            function_code=proposal["function_code"],
            description=proposal["description"],
            parameters=proposal["parameters"],
            returns=proposal["returns"],
            context=proposal["context"]
        )

        self.pending_prs.append(pr_id)

        return {
            "pr_id": pr_id,
            "status": "pending_pr_review",
            "message": f"Function '{proposal['function_name']}' submitted for review"
        }

    def check_capabilities_and_propose(self, task_description: str) -> Dict[str, Any]:
        """
        Complete capability check workflow:
        1. Generate task outline
        2. Check capability coverage
        3. If gaps exist, propose new functions

        Returns:
            {
                "outline": List of steps,
                "coverage": Coverage check result,
                "proposals": List of function proposals (if gaps exist),
                "submitted_prs": List of PR IDs (if proposals were submitted)
            }
        """
        # Step 1: Generate outline
        outline = self.generate_task_outline(task_description)

        # Step 2: Check coverage
        coverage = self.check_capability_coverage(outline)

        result = {
            "outline": outline,
            "coverage": coverage,
            "proposals": [],
            "submitted_prs": []
        }

        # Step 3: If gaps exist, propose new functions
        if coverage["has_gaps"]:
            for gap in coverage["gaps"]:
                try:
                    proposal = self.propose_new_function(gap)
                    result["proposals"].append(proposal)

                    # Submit PR
                    pr_result = self.submit_pr(proposal)
                    result["submitted_prs"].append(pr_result)
                except Exception as e:
                    result["proposals"].append({
                        "error": str(e),
                        "gap": gap
                    })

        return result

    def process_approved_functions(self) -> List[str]:
        """
        Check and process any approved functions from human review.

        Returns:
            List of newly approved function names
        """
        completed = self.library_manager.process_completed_reviews()
        approved_names = [
            r["function_name"] for r in completed
            if r.get("human_decision") == "approve"
        ]
        return approved_names
