import subprocess
import json
from agent.app.platforms.base import PlatformBase

class WindowsPlatform(PlatformBase):
    def get_shell_command(self) -> list[str]:
        return ["powershell.exe", "-NoLogo", "-NoProfile"]

    def list_services(self) -> list[dict]:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-Service | Select-Object Name,Status,DisplayName | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15
        )
        raw = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(raw, dict):
            raw = [raw]
        return [
            {
                "name": s["Name"],
                "status": "active" if s["Status"] == 4 else "inactive",
                "sub_status": "running" if s["Status"] == 4 else "stopped",
                "description": s["DisplayName"],
            }
            for s in raw
        ]

    def control_service(self, name: str, action: str) -> dict:
        cmd_map = {"start": "Start-Service", "stop": "Stop-Service", "restart": "Restart-Service"}
        if action not in cmd_map:
            return {"success": False, "error": f"Invalid action: {action}"}
        result = subprocess.run(
            ["powershell", "-Command", f"{cmd_map[action]} -Name '{name}'"],
            capture_output=True, text=True, timeout=30
        )
        return {
            "success": result.returncode == 0,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }

    def get_service_status(self, name: str) -> dict:
        result = subprocess.run(
            ["powershell", "-Command",
             f"(Get-Service -Name '{name}').Status"],
            capture_output=True, text=True, timeout=10
        )
        status_text = result.stdout.strip()
        return {"name": name, "status": "active" if status_text == "Running" else "inactive"}
