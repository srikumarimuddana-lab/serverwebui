# Server WebUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-server management platform with a web UI for file browsing, terminal access, live stats, log tailing, and service management — supporting centralized Linux fleets and standalone Windows servers.

**Architecture:** Three-layer system — Agent (FastAPI daemon on each server), Master API (FastAPI coordinator on Linux), Frontend (Next.js on Vercel). Agents expose a uniform REST/WebSocket API with a platform abstraction layer. Master proxies requests over mTLS. Frontend routes to master (Linux fleet) or directly to Windows standalone servers.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, psutil, cryptography, python-jose, passlib | Next.js 14+, React, TypeScript, Tailwind CSS, xterm.js, Recharts

---

## Phase 1: Agent Core

The agent is the foundation. Everything else depends on it.

---

### Task 1: Agent Project Scaffolding

**Files:**
- Create: `agent/requirements.txt`
- Create: `agent/app/__init__.py`
- Create: `agent/app/main.py`
- Create: `agent/app/core/__init__.py`
- Create: `agent/app/core/config.py`
- Create: `agent/app/api/__init__.py`
- Create: `agent/app/api/health.py`
- Create: `agent/app/platforms/__init__.py`
- Create: `agent/app/platforms/base.py`
- Create: `agent/app/platforms/linux.py`
- Create: `agent/app/platforms/windows.py`
- Create: `agent/app/services/__init__.py`
- Test: `agent/tests/__init__.py`
- Test: `agent/tests/test_health.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
psutil==5.9.8
pyyaml==6.0.1
cryptography==42.0.0
python-jose[cryptography]==3.3.0
python-multipart==0.0.9
websockets==12.0
pytest==8.2.0
pytest-asyncio==0.23.0
httpx==0.27.0
```

- [ ] **Step 2: Create config module**

```python
# agent/app/core/config.py
import platform
import os
from pathlib import Path
import yaml

class AgentConfig:
    def __init__(self, config_path: str | None = None):
        self.os_type: str = platform.system().lower()  # "linux" or "windows"
        self.hostname: str = platform.node()

        if config_path is None:
            if self.os_type == "windows":
                config_path = r"C:\ProgramData\server-agent\config.yaml"
            else:
                config_path = "/etc/server-agent/config.yaml"

        self.config_path = Path(config_path)
        self._data: dict = {}
        if self.config_path.exists():
            with open(self.config_path) as f:
                self._data = yaml.safe_load(f) or {}

        self.bind_host: str = self._data.get("bind_host", "0.0.0.0")
        self.bind_port: int = self._data.get("bind_port", 8420)
        self.allowed_paths: list[str] = self._data.get("allowed_paths", [])
        self.max_terminal_sessions: int = self._data.get("max_terminal_sessions", 5)
        self.terminal_idle_timeout: int = self._data.get("terminal_idle_timeout", 1800)
        self.master_url: str | None = self._data.get("master_url")
        self.cert_dir: str = self._data.get("cert_dir", self._default_cert_dir())

    def _default_cert_dir(self) -> str:
        if self.os_type == "windows":
            return r"C:\ProgramData\server-agent\certs"
        return "/etc/server-agent/certs"

    def is_path_allowed(self, path: str) -> bool:
        if not self.allowed_paths:
            return True  # no whitelist = allow all
        resolved = os.path.realpath(path)
        return any(resolved.startswith(os.path.realpath(p)) for p in self.allowed_paths)
```

- [ ] **Step 3: Create platform abstraction base**

```python
# agent/app/platforms/base.py
from abc import ABC, abstractmethod

class PlatformBase(ABC):
    @abstractmethod
    def get_shell_command(self) -> list[str]:
        """Return the default shell command for PTY sessions."""
        ...

    @abstractmethod
    def list_services(self) -> list[dict]:
        """Return list of services with name, status, description."""
        ...

    @abstractmethod
    def control_service(self, name: str, action: str) -> dict:
        """Start/stop/restart a service. Returns result dict."""
        ...

    @abstractmethod
    def get_service_status(self, name: str) -> dict:
        """Get status of a single service."""
        ...
```

```python
# agent/app/platforms/linux.py
import subprocess
from agent.app.platforms.base import PlatformBase

class LinuxPlatform(PlatformBase):
    def get_shell_command(self) -> list[str]:
        return ["/bin/bash"]

    def list_services(self) -> list[dict]:
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain"],
            capture_output=True, text=True, timeout=10
        )
        services = []
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split(None, 4)
            if len(parts) >= 4:
                services.append({
                    "name": parts[0].replace(".service", ""),
                    "status": parts[2],  # active/inactive
                    "sub_status": parts[3],  # running/dead/exited
                    "description": parts[4] if len(parts) > 4 else "",
                })
        return services

    def control_service(self, name: str, action: str) -> dict:
        if action not in ("start", "stop", "restart"):
            return {"success": False, "error": f"Invalid action: {action}"}
        result = subprocess.run(
            ["systemctl", action, name],
            capture_output=True, text=True, timeout=30
        )
        return {
            "success": result.returncode == 0,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }

    def get_service_status(self, name: str) -> dict:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=10
        )
        return {"name": name, "status": result.stdout.strip()}
```

```python
# agent/app/platforms/windows.py
import subprocess
import json
from agent.app.platforms.base import PlatformBase

class WindowsPlatform(PlatformBase):
    def get_shell_command(self) -> list[str]:
        return ["powershell.exe", "-NoLogo", "-NoProfile"]

    def list_services(self) -> list[dict]:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-Service | Select-Object Name,Status,DisplayName | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15
        )
        raw = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(raw, dict):
            raw = [raw]
        return [
            {
                "name": s["Name"],
                "status": "active" if s["Status"] == 4 else "inactive",
                "sub_status": "running" if s["Status"] == 4 else "stopped",
                "description": s["DisplayName"],
            }
            for s in raw
        ]

    def control_service(self, name: str, action: str) -> dict:
        cmd_map = {"start": "Start-Service", "stop": "Stop-Service", "restart": "Restart-Service"}
        if action not in cmd_map:
            return {"success": False, "error": f"Invalid action: {action}"}
        result = subprocess.run(
            ["powershell", "-Command", f"{cmd_map[action]} -Name '{name}'"],
            capture_output=True, text=True, timeout=30
        )
        return {
            "success": result.returncode == 0,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }

    def get_service_status(self, name: str) -> dict:
        result = subprocess.run(
            ["powershell", "-Command",
             f"(Get-Service -Name '{name}').Status"],
            capture_output=True, text=True, timeout=10
        )
        status_text = result.stdout.strip()
        return {"name": name, "status": "active" if status_text == "Running" else "inactive"}
```

```python
# agent/app/platforms/__init__.py
from agent.app.core.config import AgentConfig
from agent.app.platforms.base import PlatformBase
from agent.app.platforms.linux import LinuxPlatform
from agent.app.platforms.windows import WindowsPlatform

def get_platform(config: AgentConfig) -> PlatformBase:
    if config.os_type == "windows":
        return WindowsPlatform()
    return LinuxPlatform()
```

- [ ] **Step 4: Create health endpoint and main app**

```python
# agent/app/api/health.py
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
```

```python
# agent/app/main.py
from fastapi import FastAPI
from agent.app.api.health import router as health_router
from agent.app.core.config import AgentConfig
from agent.app.platforms import get_platform

def create_app(config: AgentConfig | None = None) -> FastAPI:
    if config is None:
        config = AgentConfig()

    app = FastAPI(title="Server Agent", version="0.1.0")
    app.state.config = config
    app.state.platform = get_platform(config)

    app.include_router(health_router)

    return app

app = create_app()
```

- [ ] **Step 5: Write health endpoint test**

```python
# agent/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from agent.app.main import create_app
from agent.app.core.config import AgentConfig

@pytest.fixture
def app():
    config = AgentConfig.__new__(AgentConfig)
    config.os_type = "linux"
    config.hostname = "test-host"
    config.bind_host = "127.0.0.1"
    config.bind_port = 8420
    config.allowed_paths = []
    config.max_terminal_sessions = 5
    config.terminal_idle_timeout = 1800
    config.master_url = None
    config.cert_dir = "/tmp/certs"
    return create_app(config)

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "hostname" in data
    assert "os" in data
    assert "version" in data
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd agent && pip install -r requirements.txt && python -m pytest tests/test_health.py -v`
Expected: PASS — `test_health_returns_ok` passes

- [ ] **Step 7: Commit**

```bash
git add agent/
git commit -m "feat(agent): scaffold agent project with health endpoint and platform abstraction"
```

---

### Task 2: File Manager Service

**Files:**
- Create: `agent/app/services/file_manager.py`
- Create: `agent/app/api/files.py`
- Test: `agent/tests/test_files.py`

- [ ] **Step 1: Write failing test for file listing**

```python
# agent/tests/test_files.py
import os
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport
from agent.app.main import create_app
from agent.app.core.config import AgentConfig

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        # Create test files
        os.makedirs(os.path.join(d, "subdir"))
        with open(os.path.join(d, "file1.txt"), "w") as f:
            f.write("hello world")
        with open(os.path.join(d, "subdir", "file2.txt"), "w") as f:
            f.write("nested file")
        yield d

@pytest.fixture
def app(tmp_dir):
    config = AgentConfig.__new__(AgentConfig)
    config.os_type = "linux"
    config.hostname = "test-host"
    config.bind_host = "127.0.0.1"
    config.bind_port = 8420
    config.allowed_paths = [tmp_dir]
    config.max_terminal_sessions = 5
    config.terminal_idle_timeout = 1800
    config.master_url = None
    config.cert_dir = "/tmp/certs"
    return create_app(config)

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_list_directory(client, tmp_dir):
    response = await client.get(f"/files/{tmp_dir}")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "directory"
    names = [e["name"] for e in data["entries"]]
    assert "file1.txt" in names
    assert "subdir" in names

@pytest.mark.asyncio
async def test_download_file(client, tmp_dir):
    file_path = os.path.join(tmp_dir, "file1.txt")
    response = await client.get(f"/files/{file_path}")
    assert response.status_code == 200
    assert response.text == "hello world"

@pytest.mark.asyncio
async def test_upload_file(client, tmp_dir):
    upload_path = os.path.join(tmp_dir, "uploaded.txt")
    response = await client.post(
        f"/files/{upload_path}",
        files={"file": ("uploaded.txt", b"upload content", "text/plain")},
    )
    assert response.status_code == 201
    assert os.path.exists(upload_path)
    with open(upload_path) as f:
        assert f.read() == "upload content"

@pytest.mark.asyncio
async def test_delete_file(client, tmp_dir):
    file_path = os.path.join(tmp_dir, "file1.txt")
    response = await client.delete(f"/files/{file_path}")
    assert response.status_code == 200
    assert not os.path.exists(file_path)

@pytest.mark.asyncio
async def test_rename_file(client, tmp_dir):
    old_path = os.path.join(tmp_dir, "file1.txt")
    new_path = os.path.join(tmp_dir, "renamed.txt")
    response = await client.put(
        f"/files/{old_path}",
        json={"new_path": new_path},
    )
    assert response.status_code == 200
    assert not os.path.exists(old_path)
    assert os.path.exists(new_path)

@pytest.mark.asyncio
async def test_path_outside_whitelist_rejected(client):
    response = await client.get("/files//etc/passwd")
    assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_files.py -v`
Expected: FAIL — routes not found (404)

- [ ] **Step 3: Implement file manager service**

```python
# agent/app/services/file_manager.py
import os
import shutil
from pathlib import Path

class FileManager:
    def __init__(self, config):
        self.config = config

    def _check_path(self, path: str) -> str:
        resolved = os.path.realpath(path)
        if not self.config.is_path_allowed(resolved):
            raise PermissionError(f"Access denied: {path}")
        return resolved

    def list_directory(self, path: str) -> dict:
        resolved = self._check_path(path)
        if not os.path.isdir(resolved):
            raise FileNotFoundError(f"Not a directory: {path}")
        entries = []
        for entry in os.scandir(resolved):
            stat = entry.stat(follow_symlinks=False)
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
        entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))
        return {"type": "directory", "path": resolved, "entries": entries}

    def read_file(self, path: str) -> str:
        resolved = self._check_path(path)
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"Not a file: {path}")
        return resolved  # return path for FileResponse

    def write_file(self, path: str, content: bytes) -> str:
        resolved = self._check_path(path)
        parent = os.path.dirname(resolved)
        os.makedirs(parent, exist_ok=True)
        with open(resolved, "wb") as f:
            f.write(content)
        return resolved

    def delete(self, path: str) -> None:
        resolved = self._check_path(path)
        if os.path.isdir(resolved):
            shutil.rmtree(resolved)
        elif os.path.isfile(resolved):
            os.remove(resolved)
        else:
            raise FileNotFoundError(f"Not found: {path}")

    def rename(self, old_path: str, new_path: str) -> str:
        resolved_old = self._check_path(old_path)
        resolved_new = self._check_path(new_path)
        os.rename(resolved_old, resolved_new)
        return resolved_new
```

- [ ] **Step 4: Implement files API router**

```python
# agent/app/api/files.py
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from agent.app.services.file_manager import FileManager

router = APIRouter()

def _get_fm(request: Request) -> FileManager:
    return FileManager(request.app.state.config)

@router.get("/files/{path:path}")
async def get_file_or_dir(path: str, request: Request):
    path = "/" + path if not path.startswith("/") else path
    fm = _get_fm(request)
    try:
        import os
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
    path = "/" + path if not path.startswith("/") else path
    fm = _get_fm(request)
    try:
        content = await file.read()
        saved = fm.write_file(path, content)
        return {"path": saved, "size": len(content)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.delete("/files/{path:path}")
async def delete_file(path: str, request: Request):
    path = "/" + path if not path.startswith("/") else path
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
    path = "/" + path if not path.startswith("/") else path
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
```

- [ ] **Step 5: Register files router in main.py**

Add to `agent/app/main.py` after the health router import:

```python
from agent.app.api.files import router as files_router
```

And in `create_app()` after `app.include_router(health_router)`:

```python
app.include_router(files_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd agent && python -m pytest tests/test_files.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add agent/app/services/file_manager.py agent/app/api/files.py agent/tests/test_files.py agent/app/main.py
git commit -m "feat(agent): add file manager with list, download, upload, delete, rename"
```

---

### Task 3: System Stats Service

**Files:**
- Create: `agent/app/services/stats.py`
- Create: `agent/app/api/stats.py`
- Test: `agent/tests/test_stats.py`

- [ ] **Step 1: Write failing test**

```python
# agent/tests/test_stats.py
import pytest
from httpx import AsyncClient, ASGITransport
from agent.app.main import create_app
from agent.app.core.config import AgentConfig

@pytest.fixture
def app():
    config = AgentConfig.__new__(AgentConfig)
    config.os_type = "linux"
    config.hostname = "test-host"
    config.bind_host = "127.0.0.1"
    config.bind_port = 8420
    config.allowed_paths = []
    config.max_terminal_sessions = 5
    config.terminal_idle_timeout = 1800
    config.master_url = None
    config.cert_dir = "/tmp/certs"
    return create_app(config)

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_stats_returns_system_info(client):
    response = await client.get("/stats")
    assert response.status_code == 200
    data = response.json()
    assert "cpu" in data
    assert "memory" in data
    assert "disk" in data
    assert "network" in data
    assert 0 <= data["cpu"]["percent"] <= 100
    assert data["memory"]["total"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_stats.py -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement stats service and router**

```python
# agent/app/services/stats.py
import psutil

def get_system_stats() -> dict:
    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    return {
        "cpu": {
            "percent": psutil.cpu_percent(interval=0.1),
            "per_cpu": psutil.cpu_percent(interval=0.1, percpu=True),
            "count": psutil.cpu_count(),
            "freq_mhz": cpu_freq.current if cpu_freq else None,
        },
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
    }
```

```python
# agent/app/api/stats.py
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
```

- [ ] **Step 4: Register stats router in main.py**

Add to `agent/app/main.py`:

```python
from agent.app.api.stats import router as stats_router
```

In `create_app()`:

```python
app.include_router(stats_router)
```

- [ ] **Step 5: Run tests**

Run: `cd agent && python -m pytest tests/test_stats.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agent/app/services/stats.py agent/app/api/stats.py agent/tests/test_stats.py agent/app/main.py
git commit -m "feat(agent): add system stats endpoint with WebSocket streaming"
```

---

### Task 4: Service Manager API

**Files:**
- Create: `agent/app/api/services.py`
- Test: `agent/tests/test_services.py`

- [ ] **Step 1: Write failing test**

```python
# agent/tests/test_services.py
import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from agent.app.main import create_app
from agent.app.core.config import AgentConfig

@pytest.fixture
def mock_platform():
    p = MagicMock()
    p.list_services.return_value = [
        {"name": "nginx", "status": "active", "sub_status": "running", "description": "A web server"},
        {"name": "mysql", "status": "inactive", "sub_status": "dead", "description": "MySQL"},
    ]
    p.control_service.return_value = {"success": True, "error": None}
    p.get_service_status.return_value = {"name": "nginx", "status": "active"}
    return p

@pytest.fixture
def app(mock_platform):
    config = AgentConfig.__new__(AgentConfig)
    config.os_type = "linux"
    config.hostname = "test-host"
    config.bind_host = "127.0.0.1"
    config.bind_port = 8420
    config.allowed_paths = []
    config.max_terminal_sessions = 5
    config.terminal_idle_timeout = 1800
    config.master_url = None
    config.cert_dir = "/tmp/certs"
    a = create_app(config)
    a.state.platform = mock_platform
    return a

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_list_services(client):
    response = await client.get("/services")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "nginx"

@pytest.mark.asyncio
async def test_control_service(client):
    response = await client.post("/services/nginx/restart")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

@pytest.mark.asyncio
async def test_invalid_action_rejected(client):
    response = await client.post("/services/nginx/destroy")
    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_services.py -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement services router**

```python
# agent/app/api/services.py
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
```

- [ ] **Step 4: Register services router in main.py**

Add to `agent/app/main.py`:

```python
from agent.app.api.services import router as services_router
```

In `create_app()`:

```python
app.include_router(services_router)
```

- [ ] **Step 5: Run tests**

Run: `cd agent && python -m pytest tests/test_services.py -v`
Expected: All 3 PASS

- [ ] **Step 6: Commit**

```bash
git add agent/app/api/services.py agent/tests/test_services.py agent/app/main.py
git commit -m "feat(agent): add service list and control endpoints"
```

---

### Task 5: Log Reader Service

**Files:**
- Create: `agent/app/services/log_reader.py`
- Create: `agent/app/api/logs.py`
- Test: `agent/tests/test_logs.py`

- [ ] **Step 1: Write failing test**

```python
# agent/tests/test_logs.py
import os
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport
from agent.app.main import create_app
from agent.app.core.config import AgentConfig

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        log_path = os.path.join(d, "app.log")
        with open(log_path, "w") as f:
            for i in range(100):
                f.write(f"Line {i}: log entry\n")
        yield d

@pytest.fixture
def app(tmp_dir):
    config = AgentConfig.__new__(AgentConfig)
    config.os_type = "linux"
    config.hostname = "test-host"
    config.bind_host = "127.0.0.1"
    config.bind_port = 8420
    config.allowed_paths = [tmp_dir]
    config.max_terminal_sessions = 5
    config.terminal_idle_timeout = 1800
    config.master_url = None
    config.cert_dir = "/tmp/certs"
    return create_app(config)

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_read_log(client, tmp_dir):
    log_path = os.path.join(tmp_dir, "app.log")
    response = await client.get(f"/logs/{log_path}")
    assert response.status_code == 200
    data = response.json()
    assert "lines" in data
    assert len(data["lines"]) <= 50  # default page size

@pytest.mark.asyncio
async def test_read_log_with_pagination(client, tmp_dir):
    log_path = os.path.join(tmp_dir, "app.log")
    response = await client.get(f"/logs/{log_path}?offset=10&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["lines"]) == 5
    assert "Line 10:" in data["lines"][0]

@pytest.mark.asyncio
async def test_read_log_outside_whitelist(client):
    response = await client.get("/logs//etc/shadow")
    assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_logs.py -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement log reader service and router**

```python
# agent/app/services/log_reader.py
import os

class LogReader:
    def __init__(self, config):
        self.config = config

    def read_log(self, path: str, offset: int = 0, limit: int = 50) -> dict:
        resolved = os.path.realpath(path)
        if not self.config.is_path_allowed(resolved):
            raise PermissionError(f"Access denied: {path}")
        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"Not a file: {path}")

        with open(resolved, "r", errors="replace") as f:
            all_lines = f.readlines()

        total = len(all_lines)
        selected = all_lines[offset:offset + limit]
        return {
            "path": resolved,
            "total_lines": total,
            "offset": offset,
            "limit": limit,
            "lines": [line.rstrip("\n") for line in selected],
        }
```

```python
# agent/app/api/logs.py
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
import asyncio
import os
from agent.app.services.log_reader import LogReader

router = APIRouter()

@router.get("/logs/{path:path}")
async def read_log(path: str, request: Request, offset: int = 0, limit: int = 50):
    path = "/" + path if not path.startswith("/") else path
    lr = LogReader(request.app.state.config)
    try:
        return lr.read_log(path, offset, limit)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.websocket("/logs/{path:path}/tail")
async def tail_log(path: str, ws: WebSocket):
    path = "/" + path if not path.startswith("/") else path
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
```

- [ ] **Step 4: Register logs router in main.py**

Add to `agent/app/main.py`:

```python
from agent.app.api.logs import router as logs_router
```

In `create_app()`:

```python
app.include_router(logs_router)
```

- [ ] **Step 5: Run tests**

Run: `cd agent && python -m pytest tests/test_logs.py -v`
Expected: All 3 PASS

- [ ] **Step 6: Commit**

```bash
git add agent/app/services/log_reader.py agent/app/api/logs.py agent/tests/test_logs.py agent/app/main.py
git commit -m "feat(agent): add log reader with pagination and WebSocket tail"
```

---

### Task 6: Terminal (PTY) Service

**Files:**
- Create: `agent/app/services/terminal.py`
- Create: `agent/app/api/terminal.py`
- Test: `agent/tests/test_terminal.py`

- [ ] **Step 1: Write failing test**

```python
# agent/tests/test_terminal.py
import pytest
from unittest.mock import MagicMock, AsyncMock
from agent.app.services.terminal import TerminalManager

@pytest.fixture
def config():
    c = MagicMock()
    c.max_terminal_sessions = 5
    c.terminal_idle_timeout = 1800
    return c

@pytest.fixture
def platform():
    p = MagicMock()
    p.get_shell_command.return_value = ["/bin/bash"]
    return p

def test_terminal_manager_creates_session(config, platform):
    tm = TerminalManager(config, platform)
    session_id = tm.create_session()
    assert session_id is not None
    assert session_id in tm.sessions

def test_terminal_manager_respects_max_sessions(config, platform):
    config.max_terminal_sessions = 2
    tm = TerminalManager(config, platform)
    tm.create_session()
    tm.create_session()
    with pytest.raises(RuntimeError, match="Max sessions"):
        tm.create_session()

def test_terminal_manager_destroys_session(config, platform):
    tm = TerminalManager(config, platform)
    sid = tm.create_session()
    tm.destroy_session(sid)
    assert sid not in tm.sessions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_terminal.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement terminal manager**

```python
# agent/app/services/terminal.py
import os
import sys
import uuid
import time
import select
import subprocess
import threading
from typing import Callable

class TerminalSession:
    def __init__(self, shell_cmd: list[str], idle_timeout: int):
        self.id = str(uuid.uuid4())
        self.created_at = time.time()
        self.last_activity = time.time()
        self.idle_timeout = idle_timeout
        self._process = None
        self._master_fd = None
        self._alive = False

        if sys.platform != "win32":
            self._start_unix(shell_cmd)
        else:
            self._start_windows(shell_cmd)

    def _start_unix(self, shell_cmd: list[str]):
        import pty
        master_fd, slave_fd = pty.openpty()
        self._process = subprocess.Popen(
            shell_cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
        )
        os.close(slave_fd)
        self._master_fd = master_fd
        self._alive = True

    def _start_windows(self, shell_cmd: list[str]):
        # On Windows, use subprocess with pipes as a fallback.
        # For full ConPTY support, winpty or pywinpty would be used.
        self._process = subprocess.Popen(
            shell_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        self._alive = True

    def write(self, data: bytes):
        self.last_activity = time.time()
        if self._master_fd is not None:
            os.write(self._master_fd, data)
        elif self._process and self._process.stdin:
            self._process.stdin.write(data)
            self._process.stdin.flush()

    def read(self, size: int = 4096) -> bytes | None:
        if self._master_fd is not None:
            if select.select([self._master_fd], [], [], 0.05)[0]:
                try:
                    return os.read(self._master_fd, size)
                except OSError:
                    self._alive = False
                    return None
        elif self._process and self._process.stdout:
            if self._process.stdout.readable():
                return self._process.stdout.read1(size) if hasattr(self._process.stdout, 'read1') else None
        return None

    def resize(self, rows: int, cols: int):
        if self._master_fd is not None and sys.platform != "win32":
            import fcntl
            import struct
            import termios
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def is_alive(self) -> bool:
        if not self._alive:
            return False
        if self._process and self._process.poll() is not None:
            self._alive = False
            return False
        if time.time() - self.last_activity > self.idle_timeout:
            self.destroy()
            return False
        return True

    def destroy(self):
        self._alive = False
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                self._process.kill()


class TerminalManager:
    def __init__(self, config, platform):
        self.config = config
        self.platform = platform
        self.sessions: dict[str, TerminalSession] = {}

    def create_session(self) -> str:
        self._cleanup_dead()
        if len(self.sessions) >= self.config.max_terminal_sessions:
            raise RuntimeError(f"Max sessions ({self.config.max_terminal_sessions}) reached")
        shell = self.platform.get_shell_command()
        session = TerminalSession(shell, self.config.terminal_idle_timeout)
        self.sessions[session.id] = session
        return session.id

    def get_session(self, session_id: str) -> TerminalSession | None:
        session = self.sessions.get(session_id)
        if session and not session.is_alive():
            del self.sessions[session_id]
            return None
        return session

    def destroy_session(self, session_id: str):
        session = self.sessions.pop(session_id, None)
        if session:
            session.destroy()

    def _cleanup_dead(self):
        dead = [sid for sid, s in self.sessions.items() if not s.is_alive()]
        for sid in dead:
            self.sessions.pop(sid, None)
```

- [ ] **Step 4: Implement terminal API router**

```python
# agent/app/api/terminal.py
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, HTTPException

router = APIRouter()

def _get_tm(request):
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

    await ws.send_text(f'\x1b]0;Session {session_id}\x07')  # set title
    await ws.send_text(f"SESSION_ID:{session_id}\n")

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
```

- [ ] **Step 5: Register terminal router and manager in main.py**

Add to `agent/app/main.py`:

```python
from agent.app.api.terminal import router as terminal_router
from agent.app.services.terminal import TerminalManager
```

In `create_app()` after setting `app.state.platform`:

```python
app.state.terminal_manager = TerminalManager(config, app.state.platform)
app.include_router(terminal_router)
```

- [ ] **Step 6: Run tests**

Run: `cd agent && python -m pytest tests/test_terminal.py -v`
Expected: All 3 PASS

- [ ] **Step 7: Commit**

```bash
git add agent/app/services/terminal.py agent/app/api/terminal.py agent/tests/test_terminal.py agent/app/main.py
git commit -m "feat(agent): add terminal PTY service with WebSocket and session management"
```

---

### Task 7: Agent mTLS Security

**Files:**
- Create: `agent/app/core/security.py`
- Test: `agent/tests/test_security.py`

- [ ] **Step 1: Write failing test**

```python
# agent/tests/test_security.py
import os
import tempfile
import pytest
from agent.app.core.security import generate_ca, generate_agent_cert, load_ssl_context

@pytest.fixture
def cert_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d

def test_generate_ca_creates_files(cert_dir):
    ca_key, ca_cert = generate_ca(cert_dir)
    assert os.path.exists(ca_key)
    assert os.path.exists(ca_cert)

def test_generate_agent_cert_creates_files(cert_dir):
    ca_key, ca_cert = generate_ca(cert_dir)
    agent_key, agent_cert = generate_agent_cert(cert_dir, ca_key, ca_cert, "test-agent")
    assert os.path.exists(agent_key)
    assert os.path.exists(agent_cert)

def test_load_ssl_context(cert_dir):
    ca_key, ca_cert = generate_ca(cert_dir)
    agent_key, agent_cert = generate_agent_cert(cert_dir, ca_key, ca_cert, "test-agent")
    ctx = load_ssl_context(agent_cert, agent_key, ca_cert)
    assert ctx is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_security.py -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement security module**

```python
# agent/app/core/security.py
import os
import ssl
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def _generate_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=4096)

def _save_key(key: rsa.RSAPrivateKey, path: str):
    with open(path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    os.chmod(path, 0o600)

def _save_cert(cert: x509.Certificate, path: str):
    with open(path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

def generate_ca(cert_dir: str) -> tuple[str, str]:
    os.makedirs(cert_dir, exist_ok=True)
    key = _generate_key()
    key_path = os.path.join(cert_dir, "ca.key")
    cert_path = os.path.join(cert_dir, "ca.crt")

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Server WebUI CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Server WebUI"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    _save_key(key, key_path)
    _save_cert(cert, cert_path)
    return key_path, cert_path

def generate_agent_cert(cert_dir: str, ca_key_path: str, ca_cert_path: str, hostname: str) -> tuple[str, str]:
    os.makedirs(cert_dir, exist_ok=True)

    with open(ca_key_path, "rb") as f:
        ca_key = serialization.load_pem_private_key(f.read(), password=None)
    with open(ca_cert_path, "rb") as f:
        ca_cert = x509.load_pem_x509_certificate(f.read())

    key = _generate_key()
    key_path = os.path.join(cert_dir, f"{hostname}.key")
    cert_path = os.path.join(cert_dir, f"{hostname}.crt")

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _save_key(key, key_path)
    _save_cert(cert, cert_path)
    return key_path, cert_path

def load_ssl_context(cert_path: str, key_path: str, ca_cert_path: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(cert_path, key_path)
    ctx.load_verify_locations(ca_cert_path)
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx
```

- [ ] **Step 4: Run tests**

Run: `cd agent && python -m pytest tests/test_security.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/core/security.py agent/tests/test_security.py
git commit -m "feat(agent): add mTLS certificate generation and SSL context"
```

---

### Task 8: Agent Installer Scripts

**Files:**
- Create: `agent/install_linux.sh`
- Create: `agent/install_windows.ps1`
- Create: `agent/config.example.yaml`

- [ ] **Step 1: Create example config**

```yaml
# agent/config.example.yaml
# Server Agent Configuration

bind_host: "0.0.0.0"
bind_port: 8420

# Master URL (leave empty for standalone Windows mode)
master_url: ""

# Restrict file browsing to these directories (empty = allow all)
allowed_paths: []
  # - /var/log
  # - /home/deploy

# Terminal settings
max_terminal_sessions: 5
terminal_idle_timeout: 1800  # seconds (30 min)

# Certificate directory
# cert_dir: /etc/server-agent/certs  (Linux default)
# cert_dir: C:\ProgramData\server-agent\certs  (Windows default)
```

- [ ] **Step 2: Create Linux installer**

```bash
#!/bin/bash
# agent/install_linux.sh
set -euo pipefail

INSTALL_DIR="/opt/server-agent"
CONFIG_DIR="/etc/server-agent"
CERT_DIR="/etc/server-agent/certs"
SERVICE_USER="serveragent"

echo "=== Server Agent Installer (Linux) ==="

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Run as root"
    exit 1
fi

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    echo "Created user: $SERVICE_USER"
fi

# Create directories
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$CERT_DIR"

# Install Python deps
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
cp -r "$(dirname "$0")"/* "$INSTALL_DIR/"
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Config
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.example.yaml" "$CONFIG_DIR/config.yaml"
    echo "Config created at $CONFIG_DIR/config.yaml — edit before starting"
fi

# Set permissions
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR" "$CONFIG_DIR"
chmod 700 "$CERT_DIR"

# Create systemd service
cat > /etc/systemd/system/server-agent.service <<EOF
[Unit]
Description=Server Agent
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/uvicorn agent.app.main:app --host 0.0.0.0 --port 8420
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable server-agent

echo ""
echo "=== Installation complete ==="
echo "1. Edit config: $CONFIG_DIR/config.yaml"
echo "2. Place certificates in: $CERT_DIR"
echo "3. Start: systemctl start server-agent"
```

- [ ] **Step 3: Create Windows installer**

```powershell
# agent/install_windows.ps1
#Requires -RunAsAdministrator

$INSTALL_DIR = "C:\ProgramData\server-agent"
$CONFIG_DIR = "C:\ProgramData\server-agent"
$CERT_DIR = "C:\ProgramData\server-agent\certs"

Write-Host "=== Server Agent Installer (Windows) ==="

# Create directories
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $CERT_DIR | Out-Null

# Copy files
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Copy-Item -Path "$ScriptDir\*" -Destination $INSTALL_DIR -Recurse -Force

# Create venv and install deps
python -m venv "$INSTALL_DIR\venv"
& "$INSTALL_DIR\venv\Scripts\pip.exe" install --upgrade pip
& "$INSTALL_DIR\venv\Scripts\pip.exe" install -r "$INSTALL_DIR\requirements.txt"

# Config
$ConfigPath = "$CONFIG_DIR\config.yaml"
if (-not (Test-Path $ConfigPath)) {
    Copy-Item "$INSTALL_DIR\config.example.yaml" $ConfigPath
    Write-Host "Config created at $ConfigPath - edit before starting"
}

# Restrict cert directory permissions
$acl = Get-Acl $CERT_DIR
$acl.SetAccessRuleProtection($true, $false)
$adminRule = New-Object System.Security.AccessControl.FileSystemAccessRule("BUILTIN\Administrators", "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.AddAccessRule($adminRule)
Set-Acl $CERT_DIR $acl

# Install as Windows Service using NSSM (must be on PATH)
$NssmPath = Get-Command nssm -ErrorAction SilentlyContinue
if ($NssmPath) {
    nssm install ServerAgent "$INSTALL_DIR\venv\Scripts\uvicorn.exe" "agent.app.main:app --host 0.0.0.0 --port 8420"
    nssm set ServerAgent AppDirectory $INSTALL_DIR
    nssm set ServerAgent Description "Server Agent for WebUI"
    nssm set ServerAgent Start SERVICE_AUTO_START
    Write-Host "Windows Service 'ServerAgent' installed"
} else {
    Write-Host "WARNING: NSSM not found. Install NSSM to run as a Windows Service."
    Write-Host "Manual start: $INSTALL_DIR\venv\Scripts\uvicorn.exe agent.app.main:app --host 0.0.0.0 --port 8420"
}

Write-Host ""
Write-Host "=== Installation complete ==="
Write-Host "1. Edit config: $ConfigPath"
Write-Host "2. Place certificates in: $CERT_DIR"
Write-Host "3. Start service: nssm start ServerAgent"
```

- [ ] **Step 4: Commit**

```bash
git add agent/install_linux.sh agent/install_windows.ps1 agent/config.example.yaml
git commit -m "feat(agent): add Linux and Windows installer scripts"
```

---

## Phase 2: Master API

---

### Task 9: Master Project Scaffolding & Database

**Files:**
- Create: `master/requirements.txt`
- Create: `master/app/__init__.py`
- Create: `master/app/main.py`
- Create: `master/app/core/__init__.py`
- Create: `master/app/core/config.py`
- Create: `master/app/core/database.py`
- Create: `master/app/models/__init__.py`
- Create: `master/app/models/user.py`
- Create: `master/app/models/agent.py`
- Create: `master/app/models/audit.py`
- Test: `master/tests/__init__.py`
- Test: `master/tests/conftest.py`
- Test: `master/tests/test_models.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.30
aiosqlite==0.20.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
cryptography==42.0.0
httpx==0.27.0
websockets==12.0
pyyaml==6.0.1
python-multipart==0.0.9
pytest==8.2.0
pytest-asyncio==0.23.0
```

- [ ] **Step 2: Create config**

```python
# master/app/core/config.py
import os

class MasterConfig:
    def __init__(self):
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./server_webui.db")
        self.jwt_secret: str = os.getenv("JWT_SECRET", "CHANGE-ME-IN-PRODUCTION")
        self.jwt_algorithm: str = "HS256"
        self.access_token_expire_minutes: int = 15
        self.refresh_token_expire_days: int = 7
        self.cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        self.bind_host: str = os.getenv("BIND_HOST", "0.0.0.0")
        self.bind_port: int = int(os.getenv("BIND_PORT", "8400"))
        self.cert_dir: str = os.getenv("CERT_DIR", "/etc/server-webui/certs")
        self.agent_health_interval: int = 60
```

- [ ] **Step 3: Create database module**

```python
# master/app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

engine = None
async_session = None

def init_db(database_url: str):
    global engine, async_session
    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

- [ ] **Step 4: Create models**

```python
# master/app/models/user.py
import datetime
from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from master.app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")  # admin, operator, viewer
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
```

```python
# master/app/models/agent.py
import datetime
from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from master.app.core.database import Base

class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=8420)
    cert_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    last_seen: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    registered_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())

class RegistrationToken(Base):
    __tablename__ = "registration_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
```

```python
# master/app/models/audit.py
import datetime
from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from master.app.core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
```

```python
# master/app/models/__init__.py
from master.app.models.user import User
from master.app.models.agent import Agent, RegistrationToken
from master.app.models.audit import AuditLog
```

- [ ] **Step 5: Write test for models**

```python
# master/tests/conftest.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from master.app.core.database import Base

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

```python
# master/tests/test_models.py
import pytest
from master.app.models.user import User
from master.app.models.agent import Agent, RegistrationToken
from master.app.models.audit import AuditLog

@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(username="admin", password_hash="hashed", role="admin")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.id is not None
    assert user.username == "admin"
    assert user.role == "admin"

@pytest.mark.asyncio
async def test_create_agent(db_session):
    agent = Agent(hostname="server1", ip_address="192.168.1.10", port=8420)
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    assert agent.id is not None
    assert agent.status == "pending"

@pytest.mark.asyncio
async def test_create_audit_log(db_session):
    log = AuditLog(user_id=1, agent_id=1, action="terminal.open", details="Opened terminal session")
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    assert log.id is not None
```

- [ ] **Step 6: Run tests**

Run: `cd master && pip install -r requirements.txt && python -m pytest tests/test_models.py -v`
Expected: All 3 PASS

- [ ] **Step 7: Commit**

```bash
git add master/
git commit -m "feat(master): scaffold master project with database models"
```

---

### Task 10: Authentication System

**Files:**
- Create: `master/app/core/auth.py`
- Create: `master/app/api/__init__.py`
- Create: `master/app/api/auth.py`
- Test: `master/tests/test_auth.py`

- [ ] **Step 1: Write failing test**

```python
# master/tests/test_auth.py
import pytest
from httpx import AsyncClient, ASGITransport
from master.app.main import create_app
from master.app.core.config import MasterConfig
from master.app.core.database import Base
from master.app.core.auth import hash_password
from master.app.models.user import User
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

@pytest.fixture
def config():
    c = MasterConfig()
    c.database_url = "sqlite+aiosqlite:///:memory:"
    c.jwt_secret = "test-secret"
    c.cors_origins = ["http://localhost:3000"]
    return c

@pytest.fixture
async def app(config):
    application = create_app(config)

    # Create tables and seed admin user
    from master.app.core.database import engine, create_tables
    await create_tables()
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        admin = User(username="admin", password_hash=hash_password("admin123"), role="admin")
        session.add(admin)
        await session.commit()

    yield application

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_login_success(client):
    response = await client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_wrong_password(client):
    response = await client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_refresh_token(client):
    login = await client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    token = login.json()["access_token"]
    response = await client.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_protected_route_without_token(client):
    response = await client.get("/users")
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd master && python -m pytest tests/test_auth.py -v`
Expected: FAIL — import errors

- [ ] **Step 3: Implement auth module**

```python
# master/app/core/auth.py
import datetime
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

_config = None

def init_auth(config):
    global _config
    _config = config

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=_config.access_token_expire_minutes)
    payload = {"sub": str(user_id), "username": username, "role": role, "exp": expire, "type": "access"}
    return jwt.encode(payload, _config.jwt_secret, algorithm=_config.jwt_algorithm)

def create_refresh_token(user_id: int) -> str:
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=_config.refresh_token_expire_days)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, _config.jwt_secret, algorithm=_config.jwt_algorithm)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _config.jwt_secret, algorithms=[_config.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user_id = int(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_role(*roles: str):
    async def checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker
```

- [ ] **Step 4: Implement auth API router**

```python
# master/app/api/auth.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import (
    verify_password, create_access_token, create_refresh_token,
    decode_token, get_current_user,
)
from master.app.models.user import User

router = APIRouter(prefix="/auth")

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(
        access_token=create_access_token(user.id, user.username, user.role),
        refresh_token=create_refresh_token(user.id),
    )

@router.post("/refresh")
async def refresh(user: User = Depends(get_current_user)):
    return {
        "access_token": create_access_token(user.id, user.username, user.role),
        "token_type": "bearer",
    }
```

- [ ] **Step 5: Create master main.py**

```python
# master/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from master.app.core.config import MasterConfig
from master.app.core.database import init_db, create_tables
from master.app.core.auth import init_auth
from master.app.api.auth import router as auth_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield

def create_app(config: MasterConfig | None = None) -> FastAPI:
    if config is None:
        config = MasterConfig()

    init_db(config.database_url)
    init_auth(config)

    app = FastAPI(title="Server WebUI Master", version="0.1.0", lifespan=lifespan)
    app.state.config = config

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)

    return app

app = create_app()
```

- [ ] **Step 6: Run tests**

Run: `cd master && python -m pytest tests/test_auth.py -v`
Expected: All 4 PASS

- [ ] **Step 7: Commit**

```bash
git add master/app/core/auth.py master/app/api/auth.py master/app/main.py master/tests/test_auth.py
git commit -m "feat(master): add JWT authentication with login, refresh, and role-based access"
```

---

### Task 11: User Management API

**Files:**
- Create: `master/app/api/users.py`
- Test: `master/tests/test_users.py`

- [ ] **Step 1: Write failing test**

```python
# master/tests/test_users.py
import pytest
from httpx import AsyncClient, ASGITransport
from master.app.main import create_app
from master.app.core.config import MasterConfig
from master.app.core.auth import hash_password
from master.app.models.user import User
from master.app.core.database import engine, create_tables
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

@pytest.fixture
def config():
    c = MasterConfig()
    c.database_url = "sqlite+aiosqlite:///:memory:"
    c.jwt_secret = "test-secret"
    c.cors_origins = ["http://localhost:3000"]
    return c

@pytest.fixture
async def app(config):
    application = create_app(config)
    await create_tables()
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        admin = User(username="admin", password_hash=hash_password("admin123"), role="admin")
        session.add(admin)
        await session.commit()
    yield application

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
async def admin_token(client):
    resp = await client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]

@pytest.mark.asyncio
async def test_list_users(client, admin_token):
    resp = await client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

@pytest.mark.asyncio
async def test_create_user(client, admin_token):
    resp = await client.post("/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"username": "operator1", "password": "pass123", "role": "operator"})
    assert resp.status_code == 201
    assert resp.json()["username"] == "operator1"

@pytest.mark.asyncio
async def test_update_user_role(client, admin_token):
    await client.post("/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"username": "user2", "password": "pass123", "role": "viewer"})
    resp = await client.put("/users/2/role",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "operator"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "operator"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd master && python -m pytest tests/test_users.py -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement users router**

```python
# master/app/api/users.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import require_role, hash_password
from master.app.models.user import User

router = APIRouter()

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"

class UpdateRoleRequest(BaseModel):
    role: str

@router.get("/users")
async def list_users(
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]

@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = await session.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists")
    new_user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username, "role": new_user.role}

@router.put("/users/{user_id}/role")
async def update_role(
    user_id: int,
    body: UpdateRoleRequest,
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = body.role
    await session.commit()
    return {"id": target.id, "username": target.username, "role": target.role}
```

- [ ] **Step 4: Register users router in main.py**

Add to `master/app/main.py`:

```python
from master.app.api.users import router as users_router
```

In `create_app()`:

```python
app.include_router(users_router)
```

- [ ] **Step 5: Run tests**

Run: `cd master && python -m pytest tests/test_users.py -v`
Expected: All 3 PASS

- [ ] **Step 6: Commit**

```bash
git add master/app/api/users.py master/tests/test_users.py master/app/main.py
git commit -m "feat(master): add user management with RBAC"
```

---

### Task 12: Agent Registry & Proxy

**Files:**
- Create: `master/app/api/agents.py`
- Create: `master/app/services/__init__.py`
- Create: `master/app/services/agent_proxy.py`
- Test: `master/tests/test_agents.py`

- [ ] **Step 1: Write failing test**

```python
# master/tests/test_agents.py
import pytest
from httpx import AsyncClient, ASGITransport
from master.app.main import create_app
from master.app.core.config import MasterConfig
from master.app.core.auth import hash_password
from master.app.models.user import User
from master.app.core.database import engine, create_tables
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

@pytest.fixture
def config():
    c = MasterConfig()
    c.database_url = "sqlite+aiosqlite:///:memory:"
    c.jwt_secret = "test-secret"
    c.cors_origins = ["http://localhost:3000"]
    return c

@pytest.fixture
async def app(config):
    application = create_app(config)
    await create_tables()
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        admin = User(username="admin", password_hash=hash_password("admin123"), role="admin")
        session.add(admin)
        await session.commit()
    yield application

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
async def admin_token(client):
    resp = await client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]

@pytest.mark.asyncio
async def test_list_agents_empty(client, admin_token):
    resp = await client.get("/agents", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.asyncio
async def test_generate_registration_token(client, admin_token):
    resp = await client.post("/agents/token",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    assert "token" in resp.json()

@pytest.mark.asyncio
async def test_register_agent(client, admin_token):
    token_resp = await client.post("/agents/token",
        headers={"Authorization": f"Bearer {admin_token}"})
    token = token_resp.json()["token"]

    resp = await client.post("/agents/register", json={
        "token": token,
        "hostname": "server1",
        "ip_address": "192.168.1.10",
        "port": 8420,
    })
    assert resp.status_code == 201
    assert resp.json()["hostname"] == "server1"

@pytest.mark.asyncio
async def test_register_agent_invalid_token(client):
    resp = await client.post("/agents/register", json={
        "token": "invalid-token",
        "hostname": "server1",
        "ip_address": "192.168.1.10",
        "port": 8420,
    })
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_delete_agent(client, admin_token):
    # Register first
    token_resp = await client.post("/agents/token",
        headers={"Authorization": f"Bearer {admin_token}"})
    token = token_resp.json()["token"]
    reg = await client.post("/agents/register", json={
        "token": token, "hostname": "server1", "ip_address": "192.168.1.10", "port": 8420,
    })
    agent_id = reg.json()["id"]

    resp = await client.delete(f"/agents/{agent_id}",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd master && python -m pytest tests/test_agents.py -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement agent proxy service**

```python
# master/app/services/agent_proxy.py
import httpx
import ssl
from master.app.core.config import MasterConfig

class AgentProxy:
    def __init__(self, config: MasterConfig):
        self.config = config
        self._client = httpx.AsyncClient(timeout=30.0, verify=False)  # mTLS configured per-request in production

    async def forward_get(self, ip: str, port: int, path: str, params: dict | None = None) -> dict:
        url = f"https://{ip}:{port}{path}"
        resp = await self._client.get(url, params=params)
        return {"status_code": resp.status_code, "body": resp.json()}

    async def forward_post(self, ip: str, port: int, path: str, body: dict | None = None, files=None) -> dict:
        url = f"https://{ip}:{port}{path}"
        if files:
            resp = await self._client.post(url, files=files)
        else:
            resp = await self._client.post(url, json=body)
        return {"status_code": resp.status_code, "body": resp.json()}

    async def forward_delete(self, ip: str, port: int, path: str) -> dict:
        url = f"https://{ip}:{port}{path}"
        resp = await self._client.delete(url)
        return {"status_code": resp.status_code, "body": resp.json()}

    async def forward_put(self, ip: str, port: int, path: str, body: dict) -> dict:
        url = f"https://{ip}:{port}{path}"
        resp = await self._client.put(url, json=body)
        return {"status_code": resp.status_code, "body": resp.json()}

    async def check_health(self, ip: str, port: int) -> dict:
        try:
            result = await self.forward_get(ip, port, "/health")
            return result["body"]
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}
```

- [ ] **Step 4: Implement agents router**

```python
# master/app/api/agents.py
import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import require_role, get_current_user
from master.app.models.agent import Agent, RegistrationToken
from master.app.models.user import User

router = APIRouter(prefix="/agents")

class RegisterRequest(BaseModel):
    token: str
    hostname: str
    ip_address: str
    port: int = 8420

@router.get("")
async def list_agents(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Agent))
    agents = result.scalars().all()
    return [
        {"id": a.id, "hostname": a.hostname, "ip_address": a.ip_address,
         "port": a.port, "status": a.status, "last_seen": str(a.last_seen) if a.last_seen else None}
        for a in agents
    ]

@router.post("/token", status_code=201)
async def generate_token(
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    token = secrets.token_urlsafe(32)
    reg_token = RegistrationToken(token=token)
    session.add(reg_token)
    await session.commit()
    return {"token": token}

@router.post("/register", status_code=201)
async def register_agent(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(RegistrationToken).where(
            RegistrationToken.token == body.token,
            RegistrationToken.used == False,
        )
    )
    reg_token = result.scalar_one_or_none()
    if not reg_token:
        raise HTTPException(status_code=401, detail="Invalid or used registration token")

    reg_token.used = True
    agent = Agent(hostname=body.hostname, ip_address=body.ip_address, port=body.port, status="active")
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return {"id": agent.id, "hostname": agent.hostname, "status": agent.status}

@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await session.delete(agent)
    await session.commit()
    return {"deleted": agent_id}

@router.get("/{agent_id}/health")
async def agent_health(
    agent_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    proxy = request.app.state.agent_proxy
    return await proxy.check_health(agent.ip_address, agent.port)
```

- [ ] **Step 5: Register agents router in main.py**

Add to `master/app/main.py`:

```python
from master.app.api.agents import router as agents_router
from master.app.services.agent_proxy import AgentProxy
```

In `create_app()`:

```python
app.state.agent_proxy = AgentProxy(config)
app.include_router(agents_router)
```

- [ ] **Step 6: Run tests**

Run: `cd master && python -m pytest tests/test_agents.py -v`
Expected: All 5 PASS

- [ ] **Step 7: Commit**

```bash
git add master/app/api/agents.py master/app/services/agent_proxy.py master/tests/test_agents.py master/app/main.py
git commit -m "feat(master): add agent registry with token-based registration and proxy"
```

---

### Task 13: Audit Logging & Master Proxy Routes

**Files:**
- Create: `master/app/services/audit.py`
- Create: `master/app/api/audit.py`
- Create: `master/app/api/proxy.py`
- Test: `master/tests/test_audit.py`

- [ ] **Step 1: Write failing test**

```python
# master/tests/test_audit.py
import pytest
from httpx import AsyncClient, ASGITransport
from master.app.main import create_app
from master.app.core.config import MasterConfig
from master.app.core.auth import hash_password
from master.app.models.user import User
from master.app.core.database import engine, create_tables
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

@pytest.fixture
def config():
    c = MasterConfig()
    c.database_url = "sqlite+aiosqlite:///:memory:"
    c.jwt_secret = "test-secret"
    c.cors_origins = ["http://localhost:3000"]
    return c

@pytest.fixture
async def app(config):
    application = create_app(config)
    await create_tables()
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        admin = User(username="admin", password_hash=hash_password("admin123"), role="admin")
        session.add(admin)
        await session.commit()
    yield application

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
async def admin_token(client):
    resp = await client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]

@pytest.mark.asyncio
async def test_audit_log_empty(client, admin_token):
    resp = await client.get("/audit", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd master && python -m pytest tests/test_audit.py -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement audit service**

```python
# master/app/services/audit.py
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.models.audit import AuditLog

async def log_action(session: AsyncSession, user_id: int | None, agent_id: int | None, action: str, details: str | None = None):
    entry = AuditLog(user_id=user_id, agent_id=agent_id, action=action, details=details)
    session.add(entry)
    await session.commit()
```

- [ ] **Step 4: Implement audit router**

```python
# master/app/api/audit.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import require_role
from master.app.models.audit import AuditLog

router = APIRouter()

@router.get("/audit")
async def get_audit_logs(
    user=Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
):
    result = await session.execute(
        select(AuditLog).order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit)
    )
    logs = result.scalars().all()
    return [
        {"id": l.id, "user_id": l.user_id, "agent_id": l.agent_id,
         "action": l.action, "details": l.details, "timestamp": str(l.timestamp)}
        for l in logs
    ]
```

- [ ] **Step 5: Implement proxy routes for agent forwarding**

```python
# master/app/api/proxy.py
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from master.app.core.database import get_session
from master.app.core.auth import get_current_user
from master.app.models.agent import Agent
from master.app.models.user import User
import httpx
import asyncio

router = APIRouter(prefix="/agents/{agent_id}")

async def _get_agent(agent_id: int, session: AsyncSession) -> Agent:
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@router.get("/files/{path:path}")
async def proxy_files_get(agent_id: int, path: str, request: Request,
                          user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_get(agent.ip_address, agent.port, f"/files/{path}", dict(request.query_params))
    return result["body"]

@router.post("/files/{path:path}")
async def proxy_files_post(agent_id: int, path: str, request: Request,
                           user: User = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    body = await request.body()
    result = await proxy.forward_post(agent.ip_address, agent.port, f"/files/{path}", body=None)
    return result["body"]

@router.delete("/files/{path:path}")
async def proxy_files_delete(agent_id: int, path: str, request: Request,
                             user: User = Depends(get_current_user),
                             session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_delete(agent.ip_address, agent.port, f"/files/{path}")
    return result["body"]

@router.get("/stats")
async def proxy_stats(agent_id: int, request: Request,
                      user: User = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_get(agent.ip_address, agent.port, "/stats")
    return result["body"]

@router.get("/services")
async def proxy_services(agent_id: int, request: Request,
                         user: User = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_get(agent.ip_address, agent.port, "/services")
    return result["body"]

@router.post("/services/{name}/{action}")
async def proxy_service_action(agent_id: int, name: str, action: str, request: Request,
                               user: User = Depends(get_current_user),
                               session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_post(agent.ip_address, agent.port, f"/services/{name}/{action}")
    return result["body"]

@router.get("/logs/{path:path}")
async def proxy_logs(agent_id: int, path: str, request: Request,
                     user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    agent = await _get_agent(agent_id, session)
    proxy = request.app.state.agent_proxy
    result = await proxy.forward_get(agent.ip_address, agent.port, f"/logs/{path}", dict(request.query_params))
    return result["body"]

@router.websocket("/terminal")
async def proxy_terminal(agent_id: int, ws: WebSocket):
    session_factory = ws.app.state.config  # will need proper session handling
    await ws.accept()
    # WebSocket proxy: connect to agent's terminal WebSocket and relay
    agent_url = f"wss://AGENT_IP:AGENT_PORT/terminal/open"
    # In production, look up agent from DB and connect
    # This is a placeholder for the WebSocket relay logic
    try:
        import websockets
        async with websockets.connect(agent_url) as agent_ws:
            async def client_to_agent():
                async for msg in ws.iter_bytes():
                    await agent_ws.send(msg)
            async def agent_to_client():
                async for msg in agent_ws:
                    if isinstance(msg, bytes):
                        await ws.send_bytes(msg)
                    else:
                        await ws.send_text(msg)
            await asyncio.gather(client_to_agent(), agent_to_client())
    except WebSocketDisconnect:
        pass
    except Exception:
        await ws.close()
```

- [ ] **Step 6: Register audit and proxy routers in main.py**

Add to `master/app/main.py`:

```python
from master.app.api.audit import router as audit_router
from master.app.api.proxy import router as proxy_router
```

In `create_app()`:

```python
app.include_router(audit_router)
app.include_router(proxy_router)
```

- [ ] **Step 7: Run tests**

Run: `cd master && python -m pytest tests/test_audit.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add master/app/services/audit.py master/app/api/audit.py master/app/api/proxy.py master/tests/test_audit.py master/app/main.py
git commit -m "feat(master): add audit logging and agent proxy routes"
```

---

## Phase 3: Frontend (Next.js)

---

### Task 14: Next.js Project Scaffolding

**Files:**
- Create: `frontend/` (via create-next-app)
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/auth.ts`
- Create: `frontend/src/types/index.ts`

- [ ] **Step 1: Create Next.js project**

Run:
```bash
cd "C:/Users/swarn/Documents/Project/Server-WEbUI"
npx create-next-app@latest frontend --typescript --tailwind --app --src-dir --eslint --no-import-alias
```

- [ ] **Step 2: Install dependencies**

Run:
```bash
cd frontend
npm install @xterm/xterm @xterm/addon-fit @xterm/addon-web-links recharts lucide-react
```

- [ ] **Step 3: Create type definitions**

```typescript
// frontend/src/types/index.ts
export interface Server {
  id: number;
  hostname: string;
  ip_address: string;
  port: number;
  status: "active" | "inactive" | "pending" | "unreachable";
  mode: "linux-fleet" | "windows-independent";
  os: "linux" | "windows";
  last_seen: string | null;
}

export interface SystemStats {
  cpu: { percent: number; per_cpu: number[]; count: number; freq_mhz: number | null };
  memory: { total: number; available: number; used: number; percent: number };
  disk: { total: number; used: number; free: number; percent: number };
  network: { bytes_sent: number; bytes_recv: number; packets_sent: number; packets_recv: number };
}

export interface FileEntry {
  name: string;
  type: "file" | "directory";
  size: number;
  modified: number;
}

export interface DirectoryListing {
  type: "directory";
  path: string;
  entries: FileEntry[];
}

export interface ServiceInfo {
  name: string;
  status: string;
  sub_status: string;
  description: string;
}

export interface LogResponse {
  path: string;
  total_lines: number;
  offset: number;
  limit: number;
  lines: string[];
}

export interface User {
  id: number;
  username: string;
  role: "admin" | "operator" | "viewer";
}

export interface AuditEntry {
  id: number;
  user_id: number | null;
  agent_id: number | null;
  action: string;
  details: string | null;
  timestamp: string;
}
```

- [ ] **Step 4: Create auth utility**

```typescript
// frontend/src/lib/auth.ts
const TOKEN_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
```

- [ ] **Step 5: Create API client with mode routing**

```typescript
// frontend/src/lib/api.ts
import { getToken, setTokens, clearTokens } from "./auth";
import type { Server } from "@/types";

const MASTER_URL = process.env.NEXT_PUBLIC_MASTER_URL || "http://localhost:8400";

// Server config stored in localStorage for now (settings page writes here)
export function getServers(): Server[] {
  if (typeof window === "undefined") return [];
  const raw = localStorage.getItem("servers_config");
  return raw ? JSON.parse(raw) : [];
}

export function getApiBase(server: Server): string {
  if (server.mode === "linux-fleet") {
    return `${MASTER_URL}/agents/${server.id}`;
  }
  // windows-independent: direct connection
  return `https://${server.ip_address}:${server.port}`;
}

async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (!headers["Content-Type"] && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    clearTokens();
    window.location.href = "/login";
  }

  return response;
}

export async function login(username: string, password: string): Promise<boolean> {
  const resp = await fetch(`${MASTER_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) return false;
  const data = await resp.json();
  setTokens(data.access_token, data.refresh_token);
  return true;
}

export async function fetchStats(server: Server) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/stats`);
  return resp.json();
}

export async function fetchFiles(server: Server, path: string) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/files/${encodeURIComponent(path)}`);
  return resp.json();
}

export async function fetchServices(server: Server) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/services`);
  return resp.json();
}

export async function controlService(server: Server, name: string, action: string) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/services/${name}/${action}`, { method: "POST" });
  return resp.json();
}

export async function fetchLogs(server: Server, path: string, offset = 0, limit = 50) {
  const base = getApiBase(server);
  const resp = await apiFetch(`${base}/logs/${encodeURIComponent(path)}?offset=${offset}&limit=${limit}`);
  return resp.json();
}

export async function fetchAgents() {
  const resp = await apiFetch(`${MASTER_URL}/agents`);
  return resp.json();
}

export function getTerminalWsUrl(server: Server): string {
  const base = getApiBase(server).replace("http", "ws");
  return `${base}/terminal/open`;
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold Next.js project with API client, auth, and type definitions"
```

---

### Task 15: Login Page

**Files:**
- Create: `frontend/src/app/login/page.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Create login page**

```tsx
// frontend/src/app/login/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const ok = await login(username, password);
    setLoading(false);
    if (ok) {
      router.push("/");
    } else {
      setError("Invalid credentials");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <form onSubmit={handleSubmit} className="bg-gray-900 p-8 rounded-lg shadow-lg w-full max-w-sm">
        <h1 className="text-2xl font-bold text-white mb-6 text-center">Server WebUI</h1>
        {error && <p className="text-red-400 text-sm mb-4 text-center">{error}</p>}
        <div className="mb-4">
          <label className="block text-gray-400 text-sm mb-1">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
            required
          />
        </div>
        <div className="mb-6">
          <label className="block text-gray-400 text-sm mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign In"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Update root page to redirect**

```tsx
// frontend/src/app/page.tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
    } else {
      router.push("/dashboard");
    }
  }, [router]);

  return null;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add login page with JWT auth"
```

---

### Task 16: Dashboard Page

**Files:**
- Create: `frontend/src/app/dashboard/page.tsx`
- Create: `frontend/src/components/dashboard/ServerCard.tsx`

- [ ] **Step 1: Create ServerCard component**

```tsx
// frontend/src/components/dashboard/ServerCard.tsx
"use client";

import type { Server } from "@/types";
import { Monitor, Server as ServerIcon } from "lucide-react";

const statusColors: Record<string, string> = {
  active: "bg-green-500",
  inactive: "bg-gray-500",
  pending: "bg-yellow-500",
  unreachable: "bg-red-500",
};

interface Props {
  server: Server;
  onClick: () => void;
}

export default function ServerCard({ server, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-blue-500 transition-colors text-left w-full"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {server.os === "windows" ? (
            <Monitor className="w-5 h-5 text-blue-400" />
          ) : (
            <ServerIcon className="w-5 h-5 text-green-400" />
          )}
          <h3 className="text-white font-medium">{server.hostname}</h3>
        </div>
        <span className={`w-2.5 h-2.5 rounded-full ${statusColors[server.status] || "bg-gray-500"}`} />
      </div>
      <div className="text-gray-400 text-sm space-y-1">
        <p>{server.ip_address}:{server.port}</p>
        <p className="capitalize">{server.os} &middot; {server.mode.replace("-", " ")}</p>
      </div>
    </button>
  );
}
```

- [ ] **Step 2: Create dashboard page**

```tsx
// frontend/src/app/dashboard/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import { getServers } from "@/lib/api";
import ServerCard from "@/components/dashboard/ServerCard";
import type { Server } from "@/types";

export default function DashboardPage() {
  const router = useRouter();
  const [servers, setServers] = useState<Server[]>([]);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    setServers(getServers());
  }, [router]);

  return (
    <div className="min-h-screen bg-gray-950 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold text-white">Servers</h1>
          <button
            onClick={() => router.push("/settings")}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded text-sm"
          >
            Settings
          </button>
        </div>
        {servers.length === 0 ? (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-lg mb-2">No servers configured</p>
            <p className="text-sm">Go to Settings to add your servers</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {servers.map((server) => (
              <ServerCard
                key={server.id}
                server={server}
                onClick={() => router.push(`/server/${server.id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add dashboard with server cards"
```

---

### Task 17: Server Management View — Terminal Tab

**Files:**
- Create: `frontend/src/app/server/[id]/page.tsx`
- Create: `frontend/src/components/terminal/TerminalPanel.tsx`

- [ ] **Step 1: Create xterm.js terminal component**

```tsx
// frontend/src/components/terminal/TerminalPanel.tsx
"use client";

import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import type { Server } from "@/types";
import { getTerminalWsUrl } from "@/lib/api";
import { getToken } from "@/lib/auth";

interface Props {
  server: Server;
}

export default function TerminalPanel({ server }: Props) {
  const termRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!termRef.current) return;

    const terminal = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
      theme: {
        background: "#0d1117",
        foreground: "#c9d1d9",
        cursor: "#58a6ff",
        selectionBackground: "#264f78",
      },
    });

    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);
    terminal.loadAddon(new WebLinksAddon());
    terminal.open(termRef.current);
    fitAddon.fit();
    terminalRef.current = terminal;

    // Connect WebSocket
    const token = getToken();
    const wsUrl = getTerminalWsUrl(server) + (token ? `?token=${token}` : "");
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      terminal.writeln("\x1b[32mConnected to " + server.hostname + "\x1b[0m\r\n");
      // Send initial resize
      const dims = fitAddon.proposeDimensions();
      if (dims) {
        fetch(getTerminalWsUrl(server).replace("ws", "http").replace("/terminal/open", "") +
          `/terminal/resize`, {  // This will be updated with proper session ID handling
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rows: dims.rows, cols: dims.cols }),
        }).catch(() => {});
      }
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        terminal.write(new Uint8Array(event.data));
      } else {
        terminal.write(event.data);
      }
    };

    ws.onclose = () => {
      terminal.writeln("\r\n\x1b[31mDisconnected\x1b[0m");
    };

    terminal.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(new TextEncoder().encode(data));
      }
    });

    const handleResize = () => {
      fitAddon.fit();
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      ws.close();
      terminal.dispose();
    };
  }, [server]);

  return (
    <div className="h-full min-h-[500px] bg-[#0d1117] rounded-lg p-1">
      <div ref={termRef} className="h-full" />
    </div>
  );
}
```

- [ ] **Step 2: Create server management page with tabs**

```tsx
// frontend/src/app/server/[id]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import { getServers } from "@/lib/api";
import TerminalPanel from "@/components/terminal/TerminalPanel";
import type { Server } from "@/types";
import { ArrowLeft, TerminalSquare, FolderOpen, Activity, FileText, Settings } from "lucide-react";

type Tab = "terminal" | "files" | "stats" | "logs" | "services";

const tabs: { id: Tab; label: string; icon: typeof TerminalSquare }[] = [
  { id: "terminal", label: "Terminal", icon: TerminalSquare },
  { id: "files", label: "Files", icon: FolderOpen },
  { id: "stats", label: "Stats", icon: Activity },
  { id: "logs", label: "Logs", icon: FileText },
  { id: "services", label: "Services", icon: Settings },
];

export default function ServerPage() {
  const params = useParams();
  const router = useRouter();
  const [server, setServer] = useState<Server | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("terminal");

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    const servers = getServers();
    const found = servers.find((s) => s.id === Number(params.id));
    if (found) setServer(found);
  }, [params.id, router]);

  if (!server) return <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">Loading...</div>;

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <div className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center gap-4">
          <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-bold text-white">{server.hostname}</h1>
          <span className="text-gray-500 text-sm">{server.ip_address}</span>
          <span className="text-gray-600 text-xs capitalize">{server.os}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-800 px-6">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-gray-400 hover:text-white"
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-6">
        {activeTab === "terminal" && <TerminalPanel server={server} />}
        {activeTab === "files" && <div className="text-gray-400">Files tab — implemented in next task</div>}
        {activeTab === "stats" && <div className="text-gray-400">Stats tab — implemented in next task</div>}
        {activeTab === "logs" && <div className="text-gray-400">Logs tab — implemented in next task</div>}
        {activeTab === "services" && <div className="text-gray-400">Services tab — implemented in next task</div>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add server management page with xterm.js terminal"
```

---

### Task 18: File Browser Tab

**Files:**
- Create: `frontend/src/components/files/FileBrowser.tsx`

- [ ] **Step 1: Create file browser component**

```tsx
// frontend/src/components/files/FileBrowser.tsx
"use client";

import { useEffect, useState } from "react";
import { fetchFiles } from "@/lib/api";
import type { Server, DirectoryListing, FileEntry } from "@/types";
import { Folder, File, ArrowUp, Download, Upload, Trash2 } from "lucide-react";

interface Props {
  server: Server;
}

export default function FileBrowser({ server }: Props) {
  const [currentPath, setCurrentPath] = useState(server.os === "windows" ? "C:\\" : "/");
  const [listing, setListing] = useState<DirectoryListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDir(path: string) {
    setLoading(true);
    setError("");
    try {
      const data = await fetchFiles(server, path);
      setListing(data);
      setCurrentPath(data.path || path);
    } catch (e) {
      setError("Failed to load directory");
    }
    setLoading(false);
  }

  useEffect(() => {
    loadDir(currentPath);
  }, []);

  function navigateUp() {
    const sep = server.os === "windows" ? "\\" : "/";
    const parts = currentPath.split(sep).filter(Boolean);
    parts.pop();
    const parent = server.os === "windows" ? parts.join(sep) + "\\" : "/" + parts.join(sep);
    loadDir(parent || (server.os === "windows" ? "C:\\" : "/"));
  }

  function handleClick(entry: FileEntry) {
    if (entry.type === "directory") {
      const sep = server.os === "windows" ? "\\" : "/";
      loadDir(currentPath.endsWith(sep) ? currentPath + entry.name : currentPath + sep + entry.name);
    }
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + " GB";
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800">
        <button onClick={navigateUp} className="text-gray-400 hover:text-white p-1">
          <ArrowUp className="w-4 h-4" />
        </button>
        <span className="text-gray-300 text-sm font-mono">{currentPath}</span>
      </div>

      {error && <p className="text-red-400 text-sm px-4 py-2">{error}</p>}

      {loading ? (
        <p className="text-gray-500 text-center py-8">Loading...</p>
      ) : (
        <div className="divide-y divide-gray-800">
          {listing?.entries.map((entry) => (
            <button
              key={entry.name}
              onClick={() => handleClick(entry)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800 transition-colors text-left"
            >
              {entry.type === "directory" ? (
                <Folder className="w-4 h-4 text-blue-400 shrink-0" />
              ) : (
                <File className="w-4 h-4 text-gray-500 shrink-0" />
              )}
              <span className="text-gray-200 text-sm flex-1 truncate">{entry.name}</span>
              <span className="text-gray-500 text-xs">
                {entry.type === "file" ? formatSize(entry.size) : ""}
              </span>
            </button>
          ))}
          {listing?.entries.length === 0 && (
            <p className="text-gray-500 text-sm text-center py-8">Empty directory</p>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire into server page**

In `frontend/src/app/server/[id]/page.tsx`, add import and replace the files placeholder:

```tsx
import FileBrowser from "@/components/files/FileBrowser";
```

Replace `{activeTab === "files" && <div ...>}` with:

```tsx
{activeTab === "files" && <FileBrowser server={server} />}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add file browser with directory navigation"
```

---

### Task 19: Stats Tab with Live Charts

**Files:**
- Create: `frontend/src/components/stats/StatsPanel.tsx`

- [ ] **Step 1: Create stats panel with recharts**

```tsx
// frontend/src/components/stats/StatsPanel.tsx
"use client";

import { useEffect, useState, useRef } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { getApiBase } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { Server, SystemStats } from "@/types";

interface Props {
  server: Server;
}

interface DataPoint {
  time: string;
  cpu: number;
  memory: number;
  disk: number;
}

function formatBytes(bytes: number): string {
  const gb = bytes / (1024 * 1024 * 1024);
  return gb.toFixed(1) + " GB";
}

export default function StatsPanel({ server }: Props) {
  const [current, setCurrent] = useState<SystemStats | null>(null);
  const [history, setHistory] = useState<DataPoint[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const base = getApiBase(server).replace("http", "ws");
    const token = getToken();
    const ws = new WebSocket(`${base}/stats/stream${token ? `?token=${token}` : ""}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data: SystemStats = JSON.parse(event.data);
      setCurrent(data);
      setHistory((prev) => {
        const point: DataPoint = {
          time: new Date().toLocaleTimeString(),
          cpu: data.cpu.percent,
          memory: data.memory.percent,
          disk: data.disk.percent,
        };
        const updated = [...prev, point];
        return updated.slice(-30); // keep last 30 data points
      });
    };

    return () => ws.close();
  }, [server]);

  if (!current) return <p className="text-gray-400">Connecting...</p>;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="CPU" value={`${current.cpu.percent.toFixed(1)}%`} sub={`${current.cpu.count} cores`} color="blue" />
        <StatCard label="Memory" value={`${current.memory.percent.toFixed(1)}%`} sub={`${formatBytes(current.memory.used)} / ${formatBytes(current.memory.total)}`} color="green" />
        <StatCard label="Disk" value={`${current.disk.percent.toFixed(1)}%`} sub={`${formatBytes(current.disk.used)} / ${formatBytes(current.disk.total)}`} color="yellow" />
        <StatCard label="Network" value={formatBytes(current.network.bytes_sent)} sub={`Recv: ${formatBytes(current.network.bytes_recv)}`} color="purple" />
      </div>

      {/* Chart */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h3 className="text-white text-sm font-medium mb-4">Usage Over Time</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={history}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="time" stroke="#6b7280" fontSize={11} />
            <YAxis domain={[0, 100]} stroke="#6b7280" fontSize={11} />
            <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151", borderRadius: "8px" }} />
            <Line type="monotone" dataKey="cpu" stroke="#3b82f6" strokeWidth={2} dot={false} name="CPU %" />
            <Line type="monotone" dataKey="memory" stroke="#10b981" strokeWidth={2} dot={false} name="Memory %" />
            <Line type="monotone" dataKey="disk" stroke="#f59e0b" strokeWidth={2} dot={false} name="Disk %" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  const colors: Record<string, string> = {
    blue: "text-blue-400",
    green: "text-green-400",
    yellow: "text-yellow-400",
    purple: "text-purple-400",
  };
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={`text-2xl font-bold ${colors[color]}`}>{value}</p>
      <p className="text-gray-500 text-xs mt-1">{sub}</p>
    </div>
  );
}
```

- [ ] **Step 2: Wire into server page**

In `frontend/src/app/server/[id]/page.tsx`, import and replace placeholder:

```tsx
import StatsPanel from "@/components/stats/StatsPanel";
```

```tsx
{activeTab === "stats" && <StatsPanel server={server} />}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add live stats dashboard with recharts"
```

---

### Task 20: Logs Tab and Services Tab

**Files:**
- Create: `frontend/src/components/logs/LogViewer.tsx`
- Create: `frontend/src/components/services/ServiceManager.tsx`

- [ ] **Step 1: Create log viewer**

```tsx
// frontend/src/components/logs/LogViewer.tsx
"use client";

import { useState } from "react";
import { fetchLogs } from "@/lib/api";
import type { Server, LogResponse } from "@/types";

interface Props {
  server: Server;
}

export default function LogViewer({ server }: Props) {
  const [logPath, setLogPath] = useState("");
  const [logData, setLogData] = useState<LogResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadLog() {
    if (!logPath.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await fetchLogs(server, logPath);
      setLogData(data);
    } catch {
      setError("Failed to load log file");
    }
    setLoading(false);
  }

  async function loadMore() {
    if (!logData) return;
    setLoading(true);
    try {
      const data = await fetchLogs(server, logPath, logData.offset + logData.limit);
      setLogData((prev) => prev ? {
        ...data,
        lines: [...prev.lines, ...data.lines],
      } : data);
    } catch {
      setError("Failed to load more");
    }
    setLoading(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          type="text"
          value={logPath}
          onChange={(e) => setLogPath(e.target.value)}
          placeholder={server.os === "windows" ? "C:\\path\\to\\log.txt" : "/var/log/syslog"}
          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500 font-mono"
        />
        <button
          onClick={loadLog}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm disabled:opacity-50"
        >
          Load
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {logData && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg">
          <div className="px-4 py-2 border-b border-gray-800 flex justify-between items-center">
            <span className="text-gray-400 text-xs font-mono">{logData.path}</span>
            <span className="text-gray-500 text-xs">{logData.total_lines} total lines</span>
          </div>
          <pre className="p-4 text-sm text-gray-300 font-mono overflow-auto max-h-[600px] leading-relaxed">
            {logData.lines.map((line, i) => (
              <div key={i} className="hover:bg-gray-800">
                <span className="text-gray-600 select-none mr-3">{logData.offset + i + 1}</span>
                {line}
              </div>
            ))}
          </pre>
          {logData.offset + logData.lines.length < logData.total_lines && (
            <div className="px-4 py-2 border-t border-gray-800">
              <button onClick={loadMore} disabled={loading} className="text-blue-400 text-sm hover:underline">
                Load more...
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create service manager**

```tsx
// frontend/src/components/services/ServiceManager.tsx
"use client";

import { useEffect, useState } from "react";
import { fetchServices, controlService } from "@/lib/api";
import type { Server, ServiceInfo } from "@/types";
import { Play, Square, RotateCcw } from "lucide-react";

interface Props {
  server: Server;
}

export default function ServiceManager({ server }: Props) {
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await fetchServices(server);
      setServices(data);
    } catch {
      // handle error
    }
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function handleAction(name: string, action: string) {
    setActionLoading(`${name}-${action}`);
    try {
      await controlService(server, name, action);
      await load(); // refresh
    } catch {
      // handle error
    }
    setActionLoading(null);
  }

  const filtered = services.filter(
    (s) => s.name.toLowerCase().includes(filter.toLowerCase()) ||
           s.description.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter services..."
        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
      />

      <div className="bg-gray-900 border border-gray-800 rounded-lg divide-y divide-gray-800">
        {loading ? (
          <p className="text-gray-500 text-center py-8">Loading services...</p>
        ) : filtered.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No services found</p>
        ) : (
          filtered.map((svc) => (
            <div key={svc.name} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-gray-200 text-sm font-medium">{svc.name}</p>
                <p className="text-gray-500 text-xs">{svc.description}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2 py-0.5 rounded ${
                  svc.status === "active" ? "bg-green-900 text-green-400" : "bg-gray-800 text-gray-400"
                }`}>
                  {svc.sub_status}
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={() => handleAction(svc.name, "start")}
                    disabled={actionLoading === `${svc.name}-start`}
                    className="p-1.5 text-gray-400 hover:text-green-400 hover:bg-gray-800 rounded"
                    title="Start"
                  >
                    <Play className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => handleAction(svc.name, "stop")}
                    disabled={actionLoading === `${svc.name}-stop`}
                    className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-gray-800 rounded"
                    title="Stop"
                  >
                    <Square className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => handleAction(svc.name, "restart")}
                    disabled={actionLoading === `${svc.name}-restart`}
                    className="p-1.5 text-gray-400 hover:text-yellow-400 hover:bg-gray-800 rounded"
                    title="Restart"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire both into server page**

In `frontend/src/app/server/[id]/page.tsx`:

```tsx
import LogViewer from "@/components/logs/LogViewer";
import ServiceManager from "@/components/services/ServiceManager";
```

Replace placeholders:

```tsx
{activeTab === "logs" && <LogViewer server={server} />}
{activeTab === "services" && <ServiceManager server={server} />}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add log viewer and service manager tabs"
```

---

### Task 21: Settings Page (Server Configuration)

**Files:**
- Create: `frontend/src/app/settings/page.tsx`

- [ ] **Step 1: Create settings page**

```tsx
// frontend/src/app/settings/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import type { Server } from "@/types";
import { Plus, Trash2, ArrowLeft } from "lucide-react";

export default function SettingsPage() {
  const router = useRouter();
  const [servers, setServers] = useState<Server[]>([]);

  useEffect(() => {
    if (!isAuthenticated()) { router.push("/login"); return; }
    const raw = localStorage.getItem("servers_config");
    if (raw) setServers(JSON.parse(raw));
  }, [router]);

  function save(updated: Server[]) {
    setServers(updated);
    localStorage.setItem("servers_config", JSON.stringify(updated));
  }

  function addServer() {
    const newServer: Server = {
      id: Date.now(),
      hostname: "",
      ip_address: "",
      port: 8420,
      status: "pending",
      mode: "linux-fleet",
      os: "linux",
      last_seen: null,
    };
    save([...servers, newServer]);
  }

  function updateServer(index: number, field: keyof Server, value: string | number) {
    const updated = [...servers];
    (updated[index] as any)[field] = value;
    // Auto-set os based on mode
    if (field === "mode") {
      updated[index].os = value === "windows-independent" ? "windows" : "linux";
    }
    save(updated);
  }

  function removeServer(index: number) {
    save(servers.filter((_, i) => i !== index));
  }

  return (
    <div className="min-h-screen bg-gray-950 p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <button onClick={() => router.push("/dashboard")} className="text-gray-400 hover:text-white">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-white">Servers</h2>
            <button
              onClick={addServer}
              className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
            >
              <Plus className="w-4 h-4" /> Add Server
            </button>
          </div>

          {servers.map((server, i) => (
            <div key={server.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-gray-400 text-xs">Hostname</label>
                  <input
                    value={server.hostname}
                    onChange={(e) => updateServer(i, "hostname", e.target.value)}
                    className="w-full mt-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                    placeholder="my-server"
                  />
                </div>
                <div>
                  <label className="text-gray-400 text-xs">IP Address</label>
                  <input
                    value={server.ip_address}
                    onChange={(e) => updateServer(i, "ip_address", e.target.value)}
                    className="w-full mt-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                    placeholder="192.168.1.10"
                  />
                </div>
                <div>
                  <label className="text-gray-400 text-xs">Port</label>
                  <input
                    type="number"
                    value={server.port}
                    onChange={(e) => updateServer(i, "port", Number(e.target.value))}
                    className="w-full mt-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                  />
                </div>
                <div>
                  <label className="text-gray-400 text-xs">Mode</label>
                  <select
                    value={server.mode}
                    onChange={(e) => updateServer(i, "mode", e.target.value)}
                    className="w-full mt-1 px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                  >
                    <option value="linux-fleet">Linux Fleet</option>
                    <option value="windows-independent">Windows Independent</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end">
                <button onClick={() => removeServer(i)} className="text-red-400 hover:text-red-300 p-1">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}

          {servers.length === 0 && (
            <p className="text-gray-500 text-center py-8">No servers configured. Click "Add Server" to get started.</p>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add settings page for server configuration"
```

---

### Task 22: Final Integration Test

**Files:** None new — this is a verification task.

- [ ] **Step 1: Verify agent starts**

Run:
```bash
cd agent
python -m uvicorn agent.app.main:app --host 127.0.0.1 --port 8420
```
Expected: Server starts on port 8420

- [ ] **Step 2: Verify agent health endpoint**

Run (in a second terminal):
```bash
curl http://127.0.0.1:8420/health
```
Expected: JSON with status "ok", hostname, os, version

- [ ] **Step 3: Verify master starts**

Run:
```bash
cd master
python -m uvicorn master.app.main:app --host 127.0.0.1 --port 8400
```
Expected: Server starts on port 8400

- [ ] **Step 4: Verify frontend builds**

Run:
```bash
cd frontend
npm run build
```
Expected: Build succeeds with no errors

- [ ] **Step 5: Run all agent tests**

Run: `cd agent && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Run all master tests**

Run: `cd master && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "chore: verify full integration — agent, master, frontend all build and pass tests"
```
