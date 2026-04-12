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
