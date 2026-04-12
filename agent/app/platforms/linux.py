import subprocess
from agent.app.platforms.base import PlatformBase

class LinuxPlatform(PlatformBase):
    def get_shell_command(self) -> list[str]:
        return ["/bin/bash"]

    def list_services(self) -> list[dict]:
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain"],
            capture_output=True, text=True, timeout=10
        )
        services = []
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split(None, 4)
            if len(parts) >= 4:
                services.append({
                    "name": parts[0].replace(".service", ""),
                    "status": parts[2],
                    "sub_status": parts[3],
                    "description": parts[4] if len(parts) > 4 else "",
                })
        return services

    def control_service(self, name: str, action: str) -> dict:
        if action not in ("start", "stop", "restart"):
            return {"success": False, "error": f"Invalid action: {action}"}
        result = subprocess.run(
            ["systemctl", action, name],
            capture_output=True, text=True, timeout=30
        )
        return {
            "success": result.returncode == 0,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }

    def get_service_status(self, name: str) -> dict:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=10
        )
        return {"name": name, "status": result.stdout.strip()}
