from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from core import ExecutionAgent

app = FastAPI(title="Execution Agent")
agent = ExecutionAgent()

class RunScriptRequest(BaseModel):
    script_path: str

class RunScriptResponse(BaseModel):
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class RunStepCodeRequest(BaseModel):
    code: str

class RunStepCodeResponse(BaseModel):
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@app.post("/run-step-code", response_model=RunStepCodeResponse)
async def run_step_code(req: RunStepCodeRequest):
    try:
        res = agent.execute_step_code(req.code)
        
        if res is None:
            return RunStepCodeResponse(
                ok=False, 
                error="Execution failed or returned no result",
                result=None
            )
        
        return RunStepCodeResponse(
            ok=res.get("status") == "success", 
            result=res,
            error=res.get("error") if res.get("status") != "success" else None
        )
        
    except Exception as e:
        return RunStepCodeResponse(
            ok=False,
            error=f"Unexpected error: {str(e)}",
            result=None
        )

@app.post("/run-script", response_model=RunScriptResponse)
async def run_script(req: RunScriptRequest):
    try:
        # use socket to send the script to Blender
        res = agent.execute_codes_file(req.script_path)
        
        if res is None:
            return RunScriptResponse(
                ok=False, 
                error="Execution failed or returned no result",
                result=None
            )
        
        return RunScriptResponse(
            ok=res.get("status") == "success", 
            result=res,
            error=res.get("error") if res.get("status") != "success" else None
        )
        
    except FileNotFoundError as e:
        return RunScriptResponse(
            ok=False,
            error=f"Script file not found: {str(e)}",
            result=None
        )
    except ConnectionError as e:
        return RunScriptResponse(
            ok=False,
            error=f"Cannot connect to Blender server: {str(e)}",
            result=None
        )
    except Exception as e:
        return RunScriptResponse(
            ok=False,
            error=f"Unexpected error: {str(e)}",
            result=None
        )

@app.get("/health")
async def health():
    # Test Blender connection
    try:
        if agent.test_connection():
            return {"status": "healthy", "agent": "execution", "blender_connected": True}
        else:
            return {"status": "unhealthy", "agent": "execution", "blender_connected": False}
    except:
        return {"status": "unhealthy", "agent": "execution", "blender_connected": False}