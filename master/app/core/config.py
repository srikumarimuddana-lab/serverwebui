import os


class MasterConfig:
    def __init__(self):
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./server_webui.db")
        self.jwt_secret: str = os.getenv("JWT_SECRET", "CHANGE-ME-IN-PRODUCTION")
        self.jwt_algorithm: str = "HS256"
        self.access_token_expire_minutes: int = 15
        self.refresh_token_expire_days: int = 7
        self.cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        self.bind_host: str = os.getenv("BIND_HOST", "0.0.0.0")
        self.bind_port: int = int(os.getenv("BIND_PORT", "8400"))
        self.cert_dir: str = os.getenv("CERT_DIR", "/etc/server-webui/certs")
        self.agent_health_interval: int = 60
