from agent.app.core.config import AgentConfig
from agent.app.platforms.base import PlatformBase
from agent.app.platforms.linux import LinuxPlatform
from agent.app.platforms.windows import WindowsPlatform

def get_platform(config: AgentConfig) -> PlatformBase:
    if config.os_type == "windows":
        return WindowsPlatform()
    return LinuxPlatform()
