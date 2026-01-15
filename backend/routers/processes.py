"""
Process management router for listing and controlling processes.

Provides /api/processes/* endpoints.
"""

from fastapi import APIRouter

import psutil

router = APIRouter(prefix="/api/processes", tags=["processes"])


@router.get("")
def processes(sort: str = "cpu_percent", order: str = "desc"):
    """
    Get list of running processes.

    Args:
        sort: Field to sort by (cpu_percent, memory_percent, name, etc.).
        order: Sort order ('asc' or 'desc').

    Returns:
        list: List of process dicts.
    """
    procs = []
    # Skip Windows system idle process and cap CPU values
    skip_names = {"System Idle Process", "Idle"}

    for p in psutil.process_iter(
        [
            "pid",
            "name",
            "username",
            "status",
            "cpu_percent",
            "memory_percent",
            "memory_info",
        ]
    ):
        try:
            info = p.info.copy()
            # Skip idle processes
            if info.get("name") in skip_names:
                continue
            # Cap CPU percent to 100 * core count (sanity check)
            if info.get("cpu_percent") and info["cpu_percent"] > 100:
                info["cpu_percent"] = min(info["cpu_percent"], 100.0)
            # Convert memory_info named tuple to dict for proper JSON serialization
            if info.get("memory_info"):
                mem = info["memory_info"]
                info["memory_info"] = {"rss": mem.rss, "vms": mem.vms}
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Handle sorting for different field types
    def sort_key(x):
        val = x.get(sort)
        if sort == "name":
            return (val or "").lower()
        return val or 0

    return sorted(procs, key=sort_key, reverse=(order == "desc"))


@router.post("/{pid}/kill")
def kill(pid: int):
    """
    Kill a process by PID.

    Args:
        pid: Process ID to kill.

    Returns:
        dict: Success status.
    """
    try:
        psutil.Process(pid).kill()
        return {"success": True}
    except Exception:
        return {"success": False}


@router.post("/{pid}/suspend")
def suspend(pid: int):
    """
    Suspend a process by PID.

    Args:
        pid: Process ID to suspend.

    Returns:
        dict: Success status.
    """
    try:
        psutil.Process(pid).suspend()
        return {"success": True}
    except Exception:
        return {"success": False}


@router.post("/{pid}/resume")
def resume(pid: int):
    """
    Resume a suspended process by PID.

    Args:
        pid: Process ID to resume.

    Returns:
        dict: Success status.
    """
    try:
        psutil.Process(pid).resume()
        return {"success": True}
    except Exception:
        return {"success": False}
