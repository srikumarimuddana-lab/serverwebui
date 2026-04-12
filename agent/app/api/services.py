from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

VALID_ACTIONS = {"start", "stop", "restart"}

@router.get("/services")
async def list_services(request: Request):
    platform = request.app.state.platform
    return platform.list_services()

@router.post("/services/{name}/{action}")
async def control_service(name: str, action: str, request: Request):
    if action not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}. Must be one of: {VALID_ACTIONS}")
    platform = request.app.state.platform
    result = platform.control_service(name, action)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result
