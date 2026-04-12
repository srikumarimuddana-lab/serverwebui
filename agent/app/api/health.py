import psutil
import platform
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "hostname": platform.node(),
        "os": platform.system(),
        "os_version": platform.version(),
        "cpu_count": psutil.cpu_count(),
        "version": "0.1.0",
    }
