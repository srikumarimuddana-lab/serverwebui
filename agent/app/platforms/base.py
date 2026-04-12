from abc import ABC, abstractmethod

class PlatformBase(ABC):
    @abstractmethod
    def get_shell_command(self) -> list[str]:
        """Return the default shell command for PTY sessions."""
        ...

    @abstractmethod
    def list_services(self) -> list[dict]:
        """Return list of services with name, status, description."""
        ...

    @abstractmethod
    def control_service(self, name: str, action: str) -> dict:
        """Start/stop/restart a service. Returns result dict."""
        ...

    @abstractmethod
    def get_service_status(self, name: str) -> dict:
        """Get status of a single service."""
        ...
