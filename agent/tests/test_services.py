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
