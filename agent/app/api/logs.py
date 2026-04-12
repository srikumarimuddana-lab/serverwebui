import asyncio
import os
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from agent.app.services.log_reader import LogReader

router = APIRouter()


def _normalize_path(path: str) -> str:
    """
    Normalize the path captured from the URL path parameter.

    FastAPI captures '/logs/{path:path}' without the leading slash, so:
    - Unix absolute paths arrive as 'etc/shadow' (stripped of leading '/')
    - Windows absolute paths arrive as 'C:\\Users\\...' (drive letter intact)

    We restore the leading slash for Unix paths only.
    """
    # Windows absolute path: starts with a drive letter (e.g. C:\ or C:/)
    if len(path) >= 2 and path[1] == ':':
        return path
    # Unix absolute path: restore the leading slash
    if not path.startswith('/'):
        return '/' + path
    return path


@router.get("/logs/{path:path}")
async def read_log(path: str, request: Request, offset: int = 0, limit: int = 50):
    path = _normalize_path(path)
    lr = LogReader(request.app.state.config)
    try:
        return lr.read_log(path, offset, limit)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.websocket("/logs/{path:path}/tail")
async def tail_log(path: str, ws: WebSocket):
    path = _normalize_path(path)
    config = ws.app.state.config
    resolved = os.path.realpath(path)
    if not config.is_path_allowed(resolved):
        await ws.close(code=4003, reason="Access denied")
        return
    if not os.path.isfile(resolved):
        await ws.close(code=4004, reason="File not found")
        return

    await ws.accept()
    try:
        with open(resolved, "r", errors="replace") as f:
            f.seek(0, 2)  # seek to end
            while True:
                line = f.readline()
                if line:
                    await ws.send_text(line.rstrip("\n"))
                else:
                    await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
