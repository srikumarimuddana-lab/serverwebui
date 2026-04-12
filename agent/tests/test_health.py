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
