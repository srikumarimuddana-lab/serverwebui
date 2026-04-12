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
