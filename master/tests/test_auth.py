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
    # /auth/refresh requires a valid Bearer token; without one FastAPI returns 403
    # (HTTPBearer returns 403 when no Authorization header is present)
    response = await client.post("/auth/refresh")
    assert response.status_code in (401, 403)
