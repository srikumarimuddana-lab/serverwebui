import pytest
from httpx import AsyncClient, ASGITransport
from master.app.main import create_app
from master.app.core.config import MasterConfig
from master.app.core.auth import hash_password
from master.app.models.user import User
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


@pytest.fixture
async def admin_token(client):
    response = await client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_list_agents_empty(client, admin_token):
    response = await client.get("/agents", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_generate_registration_token(client, admin_token):
    response = await client.post("/agents/token", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 201
    data = response.json()
    assert "token" in data


@pytest.mark.asyncio
async def test_register_agent(client, admin_token):
    # Generate a token
    token_resp = await client.post("/agents/token", headers={"Authorization": f"Bearer {admin_token}"})
    token = token_resp.json()["token"]

    # Register an agent
    response = await client.post(
        "/agents/register",
        json={"token": token, "hostname": "server01", "ip_address": "192.168.1.10", "port": 8420},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["hostname"] == "server01"


@pytest.mark.asyncio
async def test_register_agent_invalid_token(client):
    response = await client.post(
        "/agents/register",
        json={"token": "invalid-token", "hostname": "server01", "ip_address": "192.168.1.10"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_agent(client, admin_token):
    # Generate token and register agent
    token_resp = await client.post("/agents/token", headers={"Authorization": f"Bearer {admin_token}"})
    token = token_resp.json()["token"]

    register_resp = await client.post(
        "/agents/register",
        json={"token": token, "hostname": "server02", "ip_address": "192.168.1.11", "port": 8420},
    )
    agent_id = register_resp.json()["id"]

    # Delete agent
    delete_resp = await client.delete(
        f"/agents/{agent_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] == agent_id
