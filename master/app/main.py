import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from master.app.core.config import MasterConfig
from master.app.core.database import init_db, create_tables, async_session
from master.app.core.auth import init_auth, hash_password
from master.app.api.auth import router as auth_router
from master.app.api.users import router as users_router
from master.app.api.agents import router as agents_router
from master.app.api.audit import router as audit_router
from master.app.api.proxy import router as proxy_router
from master.app.models.user import User
from master.app.services.agent_proxy import AgentProxy
from master.app.core.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


async def _bootstrap_default_admin(config: MasterConfig) -> None:
    """Create the default admin user on first startup if no users exist."""
    if async_session is None:
        return
    async with async_session() as session:
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return
        if not config.default_admin_password:
            logger.warning(
                "No users exist and DEFAULT_ADMIN_PASSWORD is not set. "
                "Set DEFAULT_ADMIN_USERNAME and DEFAULT_ADMIN_PASSWORD env vars "
                "to bootstrap an initial admin account."
            )
            return
        admin = User(
            username=config.default_admin_username,
            password_hash=hash_password(config.default_admin_password),
            role="admin",
        )
        session.add(admin)
        await session.commit()
        logger.info(
            "Created default admin user '%s'. Change the password after first login.",
            config.default_admin_username,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await _bootstrap_default_admin(app.state.config)
    yield


def create_app(config: MasterConfig | None = None) -> FastAPI:
    if config is None:
        config = MasterConfig()

    init_db(config.database_url)
    init_auth(config)

    app = FastAPI(title="Server WebUI Master", version="0.1.0", lifespan=lifespan)
    app.state.config = config
    app.state.agent_proxy = AgentProxy(config)

    app.add_middleware(RateLimitMiddleware, default_rpm=120, login_rpm=5, login_lockout_seconds=900)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(agents_router)
    app.include_router(audit_router)
    app.include_router(proxy_router)

    return app


def _get_app():
    import os
    if os.getenv("JWT_SECRET"):
        return create_app()
    return None

app = _get_app()
