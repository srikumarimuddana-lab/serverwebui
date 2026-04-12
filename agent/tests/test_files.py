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
