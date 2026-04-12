import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from agent.app.services.stats import get_system_stats

router = APIRouter()


@router.get("/stats")
async def stats():
    return get_system_stats()


@router.websocket("/stats/stream")
async def stats_stream(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = get_system_stats()
            await ws.send_text(json.dumps(data))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
