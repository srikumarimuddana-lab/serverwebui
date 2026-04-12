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
async def test_list_users(client, admin_token):
    response = await client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_create_user(client, admin_token):
    response = await client.post(
        "/users",
        json={"username": "newuser", "password": "pass123", "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
    assert data["role"] == "viewer"


@pytest.mark.asyncio
async def test_update_user_role(client, admin_token):
    # Create a user first
    create_resp = await client.post(
        "/users",
        json={"username": "roleuser", "password": "pass123", "role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    # Update role
    update_resp = await client.put(
        f"/users/{user_id}/role",
        json={"role": "operator"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["role"] == "operator"
