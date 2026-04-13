import os
import secrets


class MasterConfig:
    def __init__(self):
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./server_webui.db")
        jwt_secret = os.getenv("JWT_SECRET")
        if not jwt_secret:
            raise RuntimeError(
                "JWT_SECRET environment variable is required. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        self.jwt_secret: str = jwt_secret
        self.jwt_algorithm: str = "HS256"
        self.access_token_expire_minutes: int = 15
        self.refresh_token_expire_days: int = 7
        self.cors_origins: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        self.bind_host: str = os.getenv("BIND_HOST", "0.0.0.0")
        self.bind_port: int = int(os.getenv("BIND_PORT", "8400"))
        self.cert_dir: str = os.getenv("CERT_DIR", "/etc/server-webui/certs")
        self.agent_health_interval: int = 60

        # Default admin bootstrap credentials. Used on first startup (when no
        # users exist) to seed an initial admin account so the UI is usable.
        # Change the password immediately after first login.
        self.default_admin_username: str = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
        self.default_admin_password: str | None = os.getenv("DEFAULT_ADMIN_PASSWORD")
