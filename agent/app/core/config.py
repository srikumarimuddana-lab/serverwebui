import platform
import os
from pathlib import Path
import yaml

class AgentConfig:
    def __init__(self, config_path: str | None = None):
        self.os_type: str = platform.system().lower()  # "linux" or "windows"
        self.hostname: str = platform.node()

        if config_path is None:
            if self.os_type == "windows":
                config_path = r"C:\ProgramData\server-agent\config.yaml"
            else:
                config_path = "/etc/server-agent/config.yaml"

        self.config_path = Path(config_path)
        self._data: dict = {}
        if self.config_path.exists():
            with open(self.config_path) as f:
                self._data = yaml.safe_load(f) or {}

        self.bind_host: str = self._data.get("bind_host", "0.0.0.0")
        self.bind_port: int = self._data.get("bind_port", 8420)
        self.allowed_paths: list[str] = self._data.get("allowed_paths", [])
        self.max_terminal_sessions: int = self._data.get("max_terminal_sessions", 5)
        self.terminal_idle_timeout: int = self._data.get("terminal_idle_timeout", 1800)
        self.master_url: str | None = self._data.get("master_url")
        self.cert_dir: str = self._data.get("cert_dir", self._default_cert_dir())

    def _default_cert_dir(self) -> str:
        if self.os_type == "windows":
            return r"C:\ProgramData\server-agent\certs"
        return "/etc/server-agent/certs"

    def is_path_allowed(self, path: str) -> bool:
        if not self.allowed_paths:
            return True  # no whitelist = allow all
        resolved = os.path.realpath(path)
        return any(resolved.startswith(os.path.realpath(p)) for p in self.allowed_paths)
