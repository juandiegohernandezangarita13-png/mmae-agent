import shutil
import platform
import os
from typing import Dict, Any

class SystemMonitorSkill:
    """
    Proporciona información operativa sobre el hardware y el sistema operativo anfitrión.
    """
    @staticmethod
    def get_system_stats() -> Dict[str, Any]:
        disk = shutil.disk_usage(os.getcwd())
        return {
            "os": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
            "disk_used_gb": round(disk.used / (1024 ** 3), 2),
            "disk_free_gb": round(disk.free / (1024 ** 3), 2),
            "cpu_count": os.cpu_count()
        }
