"""
PR Review Agent - FastAPI endpoints for automated function review
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core import PRReviewAgent

app = FastAPI(title="PR Review Agent")
agent = PRReviewAgent()


# Request/Response Models

class ReviewRequest(BaseModel):
    pr_id: str
    function_name: str
    function_code: str
    description: str
    parameters: List[Dict[str, Any]]
    returns: str
    context: str


class ReviewResponse(BaseModel):
    success: bool
    pr_id: str
    decision: str
    syntax_valid: bool
    safety_check: Dict[str, Any]
    test_result: Dict[str, Any]
    similar_existing_functions: List[str]
    value_assessment: Dict[str, str]
    recommendation_reason: str
    human_review_questions: List[str]


class QuickCheckRequest(BaseModel):
    function_code: str


class QuickCheckResponse(BaseModel):
    syntax_valid: bool
    syntax_error: Optional[str] = None
    is_safe: bool
    dangerous_ops: List[str]


# API Endpoints

@app.post("/review", response_model=ReviewResponse)
async def review(req: ReviewRequest):
    """
    Perform full review of a function proposal.

    This is the main endpoint for reviewing new functions.
    """
    try:
        submission = req.model_dump()
        result = agent.review_proposed_function(submission)

        return ReviewResponse(
            success=True,
            **result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/quick-check", response_model=QuickCheckResponse)
async def quick_check(req: QuickCheckRequest):
    """
    Quick syntax and safety check without full review.

    Useful for immediate feedback during function generation.
    """
    try:
        syntax_valid, syntax_error = agent._check_syntax(req.function_code)
        safety_result = agent._check_safety(req.function_code)

        return QuickCheckResponse(
            syntax_valid=syntax_valid,
            syntax_error=syntax_error,
            is_safe=safety_result.is_safe,
            dangerous_ops=safety_result.dangerous_ops
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class FindSimilarRequest(BaseModel):
    function_name: str
    description: str


class FindSimilarResponse(BaseModel):
    similar_functions: List[str]
    has_exact_match: bool


@app.post("/find-similar", response_model=FindSimilarResponse)
async def find_similar(req: FindSimilarRequest):
    """
    Find similar existing functions.

    Useful for checking duplication before generating a new function.
    """
    try:
        similar = agent._find_similar_functions(req.function_name, req.description)
        has_exact = any("exact match" in s for s in similar)

        return FindSimilarResponse(
            similar_functions=similar,
            has_exact_match=has_exact
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "agent": "pr_review"}


@app.get("/status")
async def status():
    """Get agent status"""
    return {
        "agent": "pr_review",
        "blender_port": agent.blender_port,
        "total_registered_functions": len(agent.registry.get_all_functions()),
        "safety_patterns_count": len(agent.DANGEROUS_PATTERNS)
    }
