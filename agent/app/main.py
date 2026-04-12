from fastapi import FastAPI
from agent.app.api.health import router as health_router
from agent.app.api.files import router as files_router
from agent.app.api.stats import router as stats_router
from agent.app.api.services import router as services_router
from agent.app.api.logs import router as logs_router
from agent.app.api.terminal import router as terminal_router
from agent.app.core.config import AgentConfig
from agent.app.platforms import get_platform
from agent.app.services.terminal import TerminalManager

def create_app(config: AgentConfig | None = None) -> FastAPI:
    if config is None:
        config = AgentConfig()

    app = FastAPI(title="Server Agent", version="0.1.0")
    app.state.config = config
    app.state.platform = get_platform(config)
    app.state.terminal_manager = TerminalManager(config, app.state.platform)

    app.include_router(health_router)
    app.include_router(files_router)
    app.include_router(stats_router)
    app.include_router(services_router)
    app.include_router(logs_router)
    app.include_router(terminal_router)

    return app

app = create_app()
