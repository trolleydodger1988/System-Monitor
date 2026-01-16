"""
System monitoring service for CPU, memory, swap, and system info.

This module provides functions to gather system metrics using psutil.
"""

import platform
import time
from typing import Dict, Any, List

import psutil

from config import state_manager, GPU_AVAILABLE


def get_cpu() -> Dict[str, Any]:
    """
    Get CPU statistics.

    Returns:
        dict: CPU metrics including percent, per-core percent, counts,
              frequency, context switches, interrupts, process/thread counts.
    """
    freq = psutil.cpu_freq()
    ctx = psutil.cpu_stats()

    # Count threads with error handling for terminated processes
    thread_count = 0
    for p in psutil.process_iter(["num_threads"]):
        try:
            num_threads = p.info.get("num_threads")
            if num_threads:
                thread_count += num_threads
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Process terminated or is inaccessible, skip it
            continue

    return {
        "percent": psutil.cpu_percent(interval=None),
        "per_cpu": psutil.cpu_percent(percpu=True, interval=None),
        "count": psutil.cpu_count(),
        "count_logical": psutil.cpu_count(logical=True),
        "count_physical": psutil.cpu_count(logical=False),
        "freq_current": freq.current if freq else None,
        "freq_max": freq.max if freq else None,
        "ctx_switches": ctx.ctx_switches,
        "interrupts": ctx.interrupts,
        "processes": len(psutil.pids()),
        "threads": thread_count,
    }


def get_mem() -> Dict[str, Any]:
    """
    Get memory (RAM) statistics.

    Returns:
        dict: Memory metrics including total, available, used, and percent.
    """
    m = psutil.virtual_memory()
    return {
        "total": m.total,
        "available": m.available,
        "used": m.used,
        "percent": m.percent,
    }


def get_swap() -> Dict[str, Any]:
    """
    Get swap memory statistics.

    Returns:
        dict: Swap metrics including total, used, free, and percent.
    """
    sw = psutil.swap_memory()
    return {
        "total": sw.total,
        "used": sw.used,
        "free": sw.free,
        "percent": sw.percent,
    }


def get_info() -> Dict[str, Any]:
    """
    Get system information.

    Returns:
        dict: System info including hostname, platform, boot time, GPU availability.
    """
    return {
        "hostname": platform.node(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "boot_time": psutil.boot_time(),
        "gpu_available": GPU_AVAILABLE,
    }


def get_overview() -> Dict[str, Any]:
    """
    Get aggregated system overview for dashboard.

    Returns:
        dict: Combined CPU, memory, swap, network, and disk I/O stats.
              Includes GPU data if available.
    """
    from .network_service import get_net
    from .disk_monitor import get_disk_io
    from .gpu_monitor import get_gpu

    data = {
        "cpu": get_cpu(),
        "memory": get_mem(),
        "swap": get_swap(),
        "network": get_net(),
        "disk_io": get_disk_io(),
    }

    # Add GPU data if available
    if GPU_AVAILABLE:
        data["gpu"] = get_gpu()

    return data
