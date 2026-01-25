"""
PR Review Agent - Automated pre-review of new function proposals

This agent performs automated checks before human review:
1. Syntax validation - Can the code be parsed?
2. Safety checks - Are there dangerous operations?
3. Duplication detection - Does similar function already exist?
4. Value assessment - Reusability, Generality, Complexity
5. Blender execution test - Does it run without errors?
6. Generate review summary and recommendations
"""

import os
import sys
import ast
import json
import socket
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from function_library import FunctionLibraryManager, FunctionLevel, FunctionRegistry


class ReviewDecision(Enum):
    """Possible review decisions"""
    RECOMMEND_APPROVE = "recommend_approve"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    AUTO_REJECT = "auto_reject"


class ValueLevel(Enum):
    """Value assessment levels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SafetyCheckResult:
    """Result of safety checks"""
    is_safe: bool
    dangerous_ops: List[str]
    infinite_loop_risk: bool
    file_system_access: bool
    network_access: bool
    system_commands: bool


@dataclass
class ValueAssessment:
    """Assessment of function value"""
    reusability: ValueLevel
    generality: ValueLevel
    duplication: ValueLevel
    complexity: ValueLevel


@dataclass
class TestResult:
    """Result of Blender execution test"""
    executed: bool
    success: bool
    error: Optional[str]
    output: Optional[str]


@dataclass
class ReviewResult:
    """Complete review result"""
    pr_id: str
    decision: ReviewDecision
    syntax_valid: bool
    safety_check: SafetyCheckResult
    test_result: TestResult
    similar_existing_functions: List[str]
    value_assessment: ValueAssessment
    recommendation_reason: str
    human_review_questions: List[str]


class PRReviewAgent:
    """
    PR Review Agent - Pre-review new function proposals

    Performs automated checks:
    1. Syntax validation
    2. Safety checks
    3. Duplication detection
    4. Value assessment
    5. Blender execution test
    """

    # Dangerous patterns to check for
    DANGEROUS_PATTERNS = {
        "os.system": "System command execution",
        "subprocess": "Subprocess execution",
        "eval(": "Code evaluation",
        "exec(": "Code execution",
        "open(": "File system access",
        "socket": "Network access",
        "import socket": "Network access",
        "shutil.rmtree": "Recursive file deletion",
        "os.remove": "File deletion",
        "os.unlink": "File deletion",
        "__import__": "Dynamic import",
        "compile(": "Code compilation",
    }

    # Patterns that might indicate infinite loops
    LOOP_RISK_PATTERNS = [
        "while True:",
        "while 1:",
        "for .* in itertools.count",
    ]

    def __init__(self, blender_port: int = 8089):
        self.project_root = project_root
        self.blender_port = blender_port
        self.registry = FunctionRegistry()
        self.library_manager = FunctionLibraryManager(
            project_root=self.project_root,
            initial_level=FunctionLevel.FULL
        )

    def review_proposed_function(self, submission: Dict[str, Any]) -> Dict[str, Any]:
        """
        Review a function proposal.

        Args:
            submission: {
                "pr_id": str,
                "function_name": str,
                "function_code": str,
                "description": str,
                "parameters": List[Dict],
                "returns": str,
                "context": str
            }

        Returns:
            ReviewResult as dict
        """
        pr_id = submission["pr_id"]
        function_name = submission["function_name"]
        function_code = submission["function_code"]
        description = submission["description"]

        # 1. Syntax validation
        syntax_valid, syntax_error = self._check_syntax(function_code)

        # 2. Safety checks
        safety_result = self._check_safety(function_code)

        # 3. Find similar functions
        similar_functions = self._find_similar_functions(function_name, description)

        # 4. Value assessment
        value_assessment = self._assess_value(
            function_code=function_code,
            description=description,
            similar_functions=similar_functions
        )

        # 5. Blender execution test (only if syntax is valid and safe)
        if syntax_valid and safety_result.is_safe:
            test_result = self._test_in_blender(function_code, function_name)
        else:
            test_result = TestResult(
                executed=False,
                success=False,
                error="Skipped due to syntax or safety issues",
                output=None
            )

        # 6. Make decision
        decision, reason = self._make_decision(
            syntax_valid=syntax_valid,
            syntax_error=syntax_error,
            safety_result=safety_result,
            value_assessment=value_assessment,
            test_result=test_result,
            similar_functions=similar_functions
        )

        # 7. Generate human review questions
        questions = self._generate_review_questions(
            submission=submission,
            safety_result=safety_result,
            value_assessment=value_assessment,
            similar_functions=similar_functions
        )

        result = ReviewResult(
            pr_id=pr_id,
            decision=decision,
            syntax_valid=syntax_valid,
            safety_check=safety_result,
            test_result=test_result,
            similar_existing_functions=similar_functions,
            value_assessment=value_assessment,
            recommendation_reason=reason,
            human_review_questions=questions
        )

        return self._result_to_dict(result)

    def _check_syntax(self, code: str) -> tuple[bool, Optional[str]]:
        """Check if the code has valid Python syntax"""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"

    def _check_safety(self, code: str) -> SafetyCheckResult:
        """Check for dangerous patterns in the code"""
        dangerous_ops = []
        file_system_access = False
        network_access = False
        system_commands = False

        code_lower = code.lower()

        for pattern, description in self.DANGEROUS_PATTERNS.items():
            if pattern.lower() in code_lower:
                dangerous_ops.append(f"{pattern}: {description}")
                if "file" in description.lower() or "delete" in description.lower():
                    file_system_access = True
                if "network" in description.lower():
                    network_access = True
                if "system" in description.lower() or "subprocess" in description.lower():
                    system_commands = True

        # Check for infinite loop risk
        import re
        infinite_loop_risk = any(
            re.search(pattern, code) for pattern in self.LOOP_RISK_PATTERNS
        )

        # open() for reading is generally safe in Blender context
        # Refine file_system_access check
        if "open(" in code and ("'r'" in code or '"r"' in code):
            # Reading files is less dangerous
            file_system_access = False

        is_safe = (
            len(dangerous_ops) == 0 or
            (len(dangerous_ops) == 1 and "File system access" in dangerous_ops[0] and not file_system_access)
        )

        return SafetyCheckResult(
            is_safe=is_safe,
            dangerous_ops=dangerous_ops,
            infinite_loop_risk=infinite_loop_risk,
            file_system_access=file_system_access,
            network_access=network_access,
            system_commands=system_commands
        )

    def _find_similar_functions(self, function_name: str, description: str) -> List[str]:
        """Find similar existing functions"""
        # Check by name similarity
        all_functions = self.registry.get_all_functions()
        similar = []

        # Exact name match
        if self.registry.function_exists(function_name):
            similar.append(f"{function_name} (exact match)")
            return similar

        # Check description similarity
        similar_by_desc = self.registry.find_similar_functions(description)
        for func in similar_by_desc:
            similar.append(func.name)

        # Check name parts
        name_parts = function_name.split('_')
        for func in all_functions:
            func_parts = func.name.split('_')
            common = set(name_parts) & set(func_parts)
            if len(common) >= 2 and func.name not in similar:
                similar.append(func.name)

        return similar[:5]  # Limit to 5

    def _assess_value(self,
                      function_code: str,
                      description: str,
                      similar_functions: List[str]) -> ValueAssessment:
        """Assess the value of the function"""

        # Reusability: based on parameter count and generalization
        param_count = function_code.count('def ') + function_code.count('=')
        if param_count >= 3:
            reusability = ValueLevel.HIGH
        elif param_count >= 1:
            reusability = ValueLevel.MEDIUM
        else:
            reusability = ValueLevel.LOW

        # Generality: based on hardcoded values and description
        hardcoded_indicators = ['"', "'", "0x", "0b"]
        hardcoded_count = sum(function_code.count(i) for i in hardcoded_indicators)
        lines = function_code.count('\n')

        if hardcoded_count / max(lines, 1) > 0.5:
            generality = ValueLevel.LOW
        elif hardcoded_count / max(lines, 1) > 0.2:
            generality = ValueLevel.MEDIUM
        else:
            generality = ValueLevel.HIGH

        # Duplication: based on similar functions
        if any("exact match" in s for s in similar_functions):
            duplication = ValueLevel.HIGH
        elif len(similar_functions) >= 3:
            duplication = ValueLevel.MEDIUM
        elif len(similar_functions) >= 1:
            duplication = ValueLevel.LOW
        else:
            duplication = ValueLevel.LOW

        # Complexity: based on code length and nesting
        complexity_indicators = ['if ', 'for ', 'while ', 'try:', 'except']
        complexity_count = sum(function_code.count(i) for i in complexity_indicators)

        if complexity_count > 10 or lines > 50:
            complexity = ValueLevel.HIGH
        elif complexity_count > 5 or lines > 20:
            complexity = ValueLevel.MEDIUM
        else:
            complexity = ValueLevel.LOW

        return ValueAssessment(
            reusability=reusability,
            generality=generality,
            duplication=duplication,
            complexity=complexity
        )

    def _test_in_blender(self, function_code: str, function_name: str) -> TestResult:
        """Test the function in Blender via socket connection"""
        test_code = f"""
# Test function definition
{function_code}

# Verify function exists
import inspect
if '{function_name}' in dir():
    sig = inspect.signature({function_name})
    result = {{"success": True, "signature": str(sig)}}
else:
    result = {{"success": False, "error": "Function not defined"}}

import json
print("TEST_RESULT:" + json.dumps(result))
"""

        try:
            # Connect to Blender server
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect(('localhost', self.blender_port))

                # Send test code
                request = json.dumps({"code": test_code})
                s.sendall(request.encode() + b'\n')

                # Receive response
                response = b''
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                    if b'\n' in response:
                        break

                response_str = response.decode().strip()

                # Parse result
                if "TEST_RESULT:" in response_str:
                    result_json = response_str.split("TEST_RESULT:")[1].strip()
                    result = json.loads(result_json)
                    return TestResult(
                        executed=True,
                        success=result.get("success", False),
                        error=result.get("error"),
                        output=result.get("signature")
                    )
                else:
                    return TestResult(
                        executed=True,
                        success=True,
                        error=None,
                        output="Code executed without errors"
                    )

        except socket.timeout:
            return TestResult(
                executed=False,
                success=False,
                error="Blender connection timeout",
                output=None
            )
        except ConnectionRefusedError:
            return TestResult(
                executed=False,
                success=False,
                error="Blender server not running",
                output=None
            )
        except Exception as e:
            return TestResult(
                executed=False,
                success=False,
                error=str(e),
                output=None
            )

    def _make_decision(self,
                       syntax_valid: bool,
                       syntax_error: Optional[str],
                       safety_result: SafetyCheckResult,
                       value_assessment: ValueAssessment,
                       test_result: TestResult,
                       similar_functions: List[str]) -> tuple[ReviewDecision, str]:
        """Make a review decision based on all checks"""

        # Auto-reject cases
        if not syntax_valid:
            return ReviewDecision.AUTO_REJECT, f"Syntax error: {syntax_error}"

        if not safety_result.is_safe:
            return ReviewDecision.AUTO_REJECT, f"Safety issues: {', '.join(safety_result.dangerous_ops)}"

        if any("exact match" in s for s in similar_functions):
            return ReviewDecision.AUTO_REJECT, "Function with same name already exists"

        if value_assessment.reusability == ValueLevel.LOW:
            return ReviewDecision.AUTO_REJECT, "Low reusability - appears to be a one-time solution"

        if value_assessment.duplication == ValueLevel.HIGH:
            return ReviewDecision.AUTO_REJECT, "High duplication with existing functions"

        # Recommend approve cases
        if (value_assessment.reusability == ValueLevel.HIGH and
            value_assessment.generality in [ValueLevel.HIGH, ValueLevel.MEDIUM] and
            value_assessment.duplication == ValueLevel.LOW and
            test_result.success):
            return ReviewDecision.RECOMMEND_APPROVE, "High value function with good test results"

        if (value_assessment.reusability == ValueLevel.HIGH and
            value_assessment.generality == ValueLevel.HIGH and
            value_assessment.duplication == ValueLevel.LOW):
            return ReviewDecision.RECOMMEND_APPROVE, "High reusability and generality"

        # Needs human review cases
        reasons = []
        if value_assessment.generality == ValueLevel.LOW:
            reasons.append("low generality")
        if value_assessment.complexity == ValueLevel.HIGH:
            reasons.append("high complexity")
        if not test_result.executed:
            reasons.append("could not test in Blender")
        if len(similar_functions) > 0:
            reasons.append(f"similar to: {', '.join(similar_functions[:2])}")

        reason = "Needs human review: " + "; ".join(reasons) if reasons else "Borderline case"
        return ReviewDecision.NEEDS_HUMAN_REVIEW, reason

    def _generate_review_questions(self,
                                   submission: Dict[str, Any],
                                   safety_result: SafetyCheckResult,
                                   value_assessment: ValueAssessment,
                                   similar_functions: List[str]) -> List[str]:
        """Generate questions for human reviewer"""
        questions = []

        if similar_functions:
            questions.append(
                f"Similar functions exist ({', '.join(similar_functions[:3])}). "
                "Is this function sufficiently different to justify addition?"
            )

        if value_assessment.generality == ValueLevel.LOW:
            questions.append(
                "The function appears to have hardcoded values. "
                "Should these be parameterized for better reusability?"
            )

        if value_assessment.complexity == ValueLevel.HIGH:
            questions.append(
                "The function is complex. "
                "Could it be simplified or split into smaller functions?"
            )

        if safety_result.file_system_access:
            questions.append(
                "The function accesses the file system. "
                "Is this necessary and are the paths properly validated?"
            )

        if not submission.get("description"):
            questions.append(
                "The function lacks a description. "
                "Please ensure proper documentation before approval."
            )

        # Default question
        if not questions:
            questions.append(
                "Does this function align with the project's API design patterns?"
            )

        return questions

    def _result_to_dict(self, result: ReviewResult) -> Dict[str, Any]:
        """Convert ReviewResult to dictionary for JSON serialization"""
        return {
            "pr_id": result.pr_id,
            "decision": result.decision.value,
            "syntax_valid": result.syntax_valid,
            "safety_check": {
                "is_safe": result.safety_check.is_safe,
                "dangerous_ops": result.safety_check.dangerous_ops,
                "infinite_loop_risk": result.safety_check.infinite_loop_risk,
                "file_system_access": result.safety_check.file_system_access,
                "network_access": result.safety_check.network_access,
                "system_commands": result.safety_check.system_commands
            },
            "test_result": {
                "executed": result.test_result.executed,
                "success": result.test_result.success,
                "error": result.test_result.error,
                "output": result.test_result.output
            },
            "similar_existing_functions": result.similar_existing_functions,
            "value_assessment": {
                "reusability": result.value_assessment.reusability.value,
                "generality": result.value_assessment.generality.value,
                "duplication": result.value_assessment.duplication.value,
                "complexity": result.value_assessment.complexity.value
            },
            "recommendation_reason": result.recommendation_reason,
            "human_review_questions": result.human_review_questions
        }
