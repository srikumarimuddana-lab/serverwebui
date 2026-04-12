import os
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from agent.app.services.file_manager import FileManager

router = APIRouter()


def _normalize_path(path: str) -> str:
    """
    Normalize the path captured from the URL path parameter.

    FastAPI captures '/files/{path:path}' without the leading slash, so:
    - Unix absolute paths arrive as 'etc/passwd' (stripped of leading '/')
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


def _get_fm(request: Request) -> FileManager:
    return FileManager(request.app.state.config)


@router.get("/files/{path:path}")
async def get_file_or_dir(path: str, request: Request):
    path = _normalize_path(path)
    fm = _get_fm(request)
    try:
        if os.path.isdir(os.path.realpath(path)):
            return fm.list_directory(path)
        file_path = fm.read_file(path)
        return FileResponse(file_path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/files/{path:path}", status_code=201)
async def upload_file(path: str, request: Request, file: UploadFile = File(...)):
    path = _normalize_path(path)
    fm = _get_fm(request)
    try:
        content = await file.read()
        saved = fm.write_file(path, content)
        return {"path": saved, "size": len(content)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/files/{path:path}")
async def delete_file(path: str, request: Request):
    path = _normalize_path(path)
    fm = _get_fm(request)
    try:
        fm.delete(path)
        return {"deleted": path}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/files/{path:path}")
async def rename_file(path: str, request: Request, body: dict):
    path = _normalize_path(path)
    fm = _get_fm(request)
    new_path = body.get("new_path")
    if not new_path:
        raise HTTPException(status_code=400, detail="new_path required")
    try:
        result = fm.rename(path, new_path)
        return {"old_path": path, "new_path": result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
