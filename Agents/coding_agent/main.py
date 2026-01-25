from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from function_library import FunctionLevel
from core import CodingAgent

app = FastAPI(title="Coding Agent")

# Default to FULL level, can be changed via API
agent = CodingAgent(initial_level=FunctionLevel.FULL)

# Request/Response Models
class SetCombinationRequest(BaseModel):
    combination: Dict

class SetCombinationResponse(BaseModel):
    success: bool
    message: str

class GenerateCodeRequest(BaseModel):
    step: int
    task_description: str
    review_result: Optional[dict] = None

class GenerateCodeResponse(BaseModel):
    success: bool
    message: str
    code_path: str
    fixed_steps: Optional[List[int]] = None
    used_function: Optional[str] = None
    total_steps: Optional[int] = None

class GetStepInfoRequest(BaseModel):
    step: int

class GetStepInfoResponse(BaseModel):
    step: int
    description: str
    is_scale_step: bool

class GetStepCodeRequest(BaseModel):
    step: int

class GetStepCodeResponse(BaseModel):
    success: bool
    code: Optional[str] = None
    message: Optional[str] = None

# API Endpoints
@app.post("/set-combination", response_model=SetCombinationResponse)
async def set_combination(req: SetCombinationRequest):
    try:
        agent.set_combination_data(req.combination)
        return SetCombinationResponse(
            success=True,
            message="Combination data set successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-code", response_model=GenerateCodeResponse)
async def generate_code(req: GenerateCodeRequest):
    try:
        result = agent.generate_code(
            step=req.step,
            task_description=req.task_description,
            review_result=req.review_result
        )
        
        return GenerateCodeResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get-step-info", response_model=GetStepInfoResponse)
async def get_step_info(req: GetStepInfoRequest):
    try:
        info = agent.get_step_info(req.step)
        return GetStepInfoResponse(**info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/get-step-code", response_model=GetStepCodeResponse)
async def get_step_code(req: GetStepCodeRequest):
    try:
        code = agent.get_step_code(req.step)
        if code:
            return GetStepCodeResponse(
                success=True,
                code=code
            )
        else:
            return GetStepCodeResponse(
                success=False,
                message=f"No code found for step {req.step}"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "coding"}

@app.get("/status")
async def status():
    """Get current status of the coding agent"""
    return {
        "fixed_steps": list(agent.fixed_steps),
        "execution_code_exists": agent.execution_code_path.exists(),
        "has_combination_data": agent.current_combination is not None,
        "total_steps": len(agent.step_descriptions)
    }


# ========== Capability Gatekeeping Endpoints ==========

class SetLibraryLevelRequest(BaseModel):
    level: str  # "minimal", "partial", "full"

class SetLibraryLevelResponse(BaseModel):
    success: bool
    message: str
    current_level: str

@app.post("/set-library-level", response_model=SetLibraryLevelResponse)
async def set_library_level(req: SetLibraryLevelRequest):
    """Set the function library level"""
    try:
        level_map = {
            "minimal": FunctionLevel.MINIMAL,
            "partial": FunctionLevel.PARTIAL,
            "full": FunctionLevel.FULL
        }
        if req.level.lower() not in level_map:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid level. Must be one of: minimal, partial, full"
            )

        level = level_map[req.level.lower()]
        agent.set_library_level(level)

        return SetLibraryLevelResponse(
            success=True,
            message=f"Library level set to {req.level}",
            current_level=req.level.lower()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/library-status")
async def library_status():
    """Get current function library status"""
    try:
        return agent.get_library_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CheckCapabilitiesRequest(BaseModel):
    task_description: str

class CheckCapabilitiesResponse(BaseModel):
    success: bool
    outline: List[Dict[str, Any]]
    coverage: Dict[str, Any]
    has_gaps: bool
    message: str

@app.post("/check-capabilities", response_model=CheckCapabilitiesResponse)
async def check_capabilities(req: CheckCapabilitiesRequest):
    """Check if current function library can handle the task"""
    try:
        outline = agent.generate_task_outline(req.task_description)
        coverage = agent.check_capability_coverage(outline)

        return CheckCapabilitiesResponse(
            success=True,
            outline=outline,
            coverage=coverage,
            has_gaps=coverage["has_gaps"],
            message=f"Coverage: {coverage['coverage_rate']*100:.1f}% ({len(coverage['covered_steps'])}/{len(outline)} steps)"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ProposeGapInfo(BaseModel):
    step: int
    action: str
    required_capability: str
    similar_functions: Optional[List[str]] = []

class ProposeFunctionRequest(BaseModel):
    gap: ProposeGapInfo

class ProposeFunctionResponse(BaseModel):
    success: bool
    proposal: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@app.post("/propose-function", response_model=ProposeFunctionResponse)
async def propose_function(req: ProposeFunctionRequest):
    """Generate a new function proposal for a capability gap"""
    try:
        gap_dict = req.gap.model_dump()
        proposal = agent.propose_new_function(gap_dict)
        return ProposeFunctionResponse(success=True, proposal=proposal)
    except Exception as e:
        return ProposeFunctionResponse(success=False, error=str(e))


class SubmitPRRequest(BaseModel):
    proposal: Dict[str, Any]

class SubmitPRResponse(BaseModel):
    success: bool
    pr_id: Optional[str] = None
    status: Optional[str] = None
    message: str

@app.post("/submit-pr", response_model=SubmitPRResponse)
async def submit_pr(req: SubmitPRRequest):
    """Submit a function proposal as a PR"""
    try:
        result = agent.submit_pr(req.proposal)
        return SubmitPRResponse(
            success=True,
            pr_id=result["pr_id"],
            status=result["status"],
            message=result["message"]
        )
    except Exception as e:
        return SubmitPRResponse(success=False, message=str(e))


class CheckAndProposeRequest(BaseModel):
    task_description: str

@app.post("/check-and-propose")
async def check_and_propose(req: CheckAndProposeRequest):
    """
    Complete capability check workflow:
    1. Generate task outline
    2. Check capability coverage
    3. If gaps exist, propose and submit new functions
    """
    try:
        result = agent.check_capabilities_and_propose(req.task_description)
        return {
            "success": True,
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process-approved-functions")
async def process_approved_functions():
    """Check and process any approved functions from human review"""
    try:
        approved = agent.process_approved_functions()
        return {
            "success": True,
            "approved_functions": approved,
            "count": len(approved)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))