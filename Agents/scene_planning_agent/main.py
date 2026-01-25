from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from core import ScenePlanningAgent

app = FastAPI(title="Scene Planning Agent")
agent = ScenePlanningAgent()

class PlanSceneRequest(BaseModel):
    description: str
    assets_csv_path: str 
    num_combinations: int 

class PlanSceneResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    parsed_config: Optional[dict] = None
    total_combinations: Optional[int] = None
    combinations: Optional[list] = None
    missing_assets: Optional[list] = None

@app.post("/plan-scene", response_model=PlanSceneResponse)
async def plan_scene(req: PlanSceneRequest):
    try:
        result = agent.plan_scene(
            description=req.description,
            assets_csv_path=req.assets_csv_path,
            num_combinations=req.num_combinations
        )
        return PlanSceneResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "scene_planning"}