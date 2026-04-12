import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, HTTPException

router = APIRouter()


def _get_tm(request: Request):
    return request.app.state.terminal_manager


@router.websocket("/terminal/open")
async def terminal_open(ws: WebSocket):
    tm = ws.app.state.terminal_manager
    try:
        session_id = tm.create_session()
    except RuntimeError as e:
        await ws.close(code=4029, reason=str(e))
        return

    await ws.accept()
    session = tm.get_session(session_id)
    if not session:
        await ws.close(code=4000, reason="Session died")
        return

    await ws.send_text(f"SESSION_ID:{session_id}\n")

    read_task = None
    try:
        async def read_pty():
            while session.is_alive():
                data = session.read()
                if data:
                    await ws.send_bytes(data)
                else:
                    await asyncio.sleep(0.05)

        read_task = asyncio.create_task(read_pty())

        while True:
            data = await ws.receive_bytes()
            session.write(data)

    except WebSocketDisconnect:
        pass
    finally:
        if read_task is not None:
            read_task.cancel()
        tm.destroy_session(session_id)


@router.websocket("/terminal/{session_id}")
async def terminal_attach(session_id: str, ws: WebSocket):
    tm = ws.app.state.terminal_manager
    session = tm.get_session(session_id)
    if not session:
        await ws.close(code=4004, reason="Session not found")
        return

    await ws.accept()
    read_task = None
    try:
        async def read_pty():
            while session.is_alive():
                data = session.read()
                if data:
                    await ws.send_bytes(data)
                else:
                    await asyncio.sleep(0.05)

        read_task = asyncio.create_task(read_pty())

        while True:
            data = await ws.receive_bytes()
            session.write(data)

    except WebSocketDisconnect:
        pass
    finally:
        if read_task is not None:
            read_task.cancel()


@router.post("/terminal/{session_id}/resize")
async def terminal_resize(session_id: str, request: Request):
    tm = _get_tm(request)
    session = tm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    body = await request.json()
    rows = body.get("rows", 24)
    cols = body.get("cols", 80)
    session.resize(rows, cols)
    return {"resized": True}


@router.delete("/terminal/{session_id}")
async def terminal_destroy(session_id: str, request: Request):
    tm = _get_tm(request)
    tm.destroy_session(session_id)
    return {"destroyed": session_id}
