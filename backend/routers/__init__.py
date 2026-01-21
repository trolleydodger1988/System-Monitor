"""
Routers package for SysMon backend.
"""

from .system import router as system_router
from .gpu import router as gpu_router
from .network import router as network_router
from .processes import router as processes_router
from .storage import router as storage_router
from .cleanup import router as cleanup_router
from .ble import router as ble_router
from .bluetooth import router as bluetooth_router
from .file_monitor import router as file_monitor_router

__all__ = [
    "system_router",
    "gpu_router",
    "network_router",
    "processes_router",
    "storage_router",
    "cleanup_router",
    "ble_router",
    "bluetooth_router",
    "file_monitor_router",
]
