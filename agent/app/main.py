from fastapi import FastAPI
from agent.app.api.health import router as health_router
from agent.app.api.files import router as files_router
from agent.app.core.config import AgentConfig
from agent.app.platforms import get_platform

def create_app(config: AgentConfig | None = None) -> FastAPI:
    if config is None:
        config = AgentConfig()

    app = FastAPI(title="Server Agent", version="0.1.0")
    app.state.config = config
    app.state.platform = get_platform(config)

    app.include_router(health_router)
    app.include_router(files_router)

    return app

app = create_app()
