import platform
import psutil


def _get_disk_usage() -> psutil._common.sdiskusage:
    """Get disk usage, using the correct root path for the OS."""
    if platform.system().lower() == "windows":
        return psutil.disk_usage("C:\\")
    return psutil.disk_usage("/")


def get_system_stats() -> dict:
    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk = _get_disk_usage()
    net = psutil.net_io_counters()

    return {
        "cpu": {
            "percent": psutil.cpu_percent(interval=0.1),
            "per_cpu": psutil.cpu_percent(interval=0.1, percpu=True),
            "count": psutil.cpu_count(),
            "freq_mhz": cpu_freq.current if cpu_freq else None,
        },
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
    }
