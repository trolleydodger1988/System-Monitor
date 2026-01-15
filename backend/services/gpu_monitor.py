"""
GPU monitoring service for NVIDIA, Intel, and AMD GPUs.

This module provides GPU stats using GPUtil (NVIDIA) or WMI (Intel/AMD on Windows).
"""

from typing import Dict, Any, List
import pprint
import psutil
import sys
from pathlib import Path

try:
    # Handle imports for both direct execution and package import
    if __name__ == "__main__":
        # Add the backend directory to sys.path for direct script execution
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from config import GPUTIL_AVAILABLE, WMI_AVAILABLE, logger
    else:
        from ..config import GPUTIL_AVAILABLE, WMI_AVAILABLE, logger
except ImportError as e:
    from config import GPUTIL_AVAILABLE, WMI_AVAILABLE, logger


def get_gpu() -> List[Dict[str, Any]]:
    """
    Get GPU statistics using GPUtil (NVIDIA) or WMI + Performance Counters (Intel/AMD on Windows).

    Returns:
        list: List of GPU info dicts with load, memory, temperature, etc.
    """
    gpus = []

    # Try GPUtil first for NVIDIA GPUs (provides detailed stats)
    if GPUTIL_AVAILABLE:
        try:
            import GPUtil

            nvidia_gpus = GPUtil.getGPUs()
            for gpu in nvidia_gpus:
                gpus.append(
                    {
                        "id": gpu.id,
                        "name": gpu.name,
                        "load": gpu.load * 100,
                        "memory_total": gpu.memoryTotal,  # Already in MB from GPUtil
                        "memory_used": gpu.memoryUsed,
                        "memory_free": gpu.memoryFree,
                        "memory_percent": (
                            (gpu.memoryUsed / gpu.memoryTotal * 100)
                            if gpu.memoryTotal > 0
                            else 0
                        ),
                        "temperature": gpu.temperature,
                        "driver": gpu.driver,
                        "uuid": gpu.uuid,
                        "type": "nvidia",
                    }
                )
        except Exception as e:
            print(f"GPUtil error: {e}")

    # If no NVIDIA GPUs found, try WMI for Intel/AMD on Windows
    if len(gpus) == 0 and WMI_AVAILABLE:
        try:
            import wmi
            import pythoncom

            pythoncom.CoInitialize()

            c = wmi.WMI()

            # Get GPU utilization from Performance Counters
            gpu_util = 0.0
            try:
                # Query GPU Engine performance counters - get max across ALL engine types
                perf_data = c.query(
                    "SELECT UtilizationPercentage FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine"
                )
                utilizations = [
                    int(e.UtilizationPercentage)
                    for e in perf_data
                    if e.UtilizationPercentage
                ]
                if utilizations:
                    gpu_util = max(
                        utilizations
                    )  # Take max across all engines (like Task Manager)
            except Exception as e:
                print(f"GPU perf counter error: {e}")

            # Get GPU memory from Performance Counters
            gpu_mem_used = 0
            gpu_mem_total = 0
            try:
                # Query GPU memory counters
                mem_data = c.query(
                    "SELECT * FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory"
                )
                for mem in mem_data:
                    if hasattr(mem, "DedicatedUsage"):
                        gpu_mem_used += int(mem.DedicatedUsage or 0)
                    if hasattr(mem, "SharedUsage"):
                        gpu_mem_used += int(mem.SharedUsage or 0)
                    # Total memory from dedicated + shared limit
                    if hasattr(mem, "TotalCommitted"):
                        gpu_mem_total = max(gpu_mem_total, int(mem.TotalCommitted or 0))
            except Exception:
                pass

            # Get GPU info from VideoController
            for i, gpu in enumerate(c.Win32_VideoController()):
                # Skip virtual/display adapters
                if any(
                    skip in gpu.Name.lower()
                    for skip in ["displaylink", "citrix", "virtual", "basic"]
                ):
                    continue

                # AdapterRAM is dedicated VRAM in bytes
                vram_bytes = gpu.AdapterRAM or 0
                vram_mb = vram_bytes / (1024 * 1024) if vram_bytes > 0 else 0

                # For shared memory GPUs (Intel), use system RAM allocation
                # Task Manager shows ~8GB shared for Intel Iris Xe
                total_mem_mb = (
                    gpu_mem_total / (1024 * 1024) if gpu_mem_total > 0 else vram_mb
                )
                used_mem_mb = gpu_mem_used / (1024 * 1024) if gpu_mem_used > 0 else None

                # If total is still 0 or too low, estimate from system RAM (Intel uses up to half)
                if total_mem_mb < 1024:  # Less than 1GB seems wrong for modern GPUs
                    sys_mem = psutil.virtual_memory().total
                    total_mem_mb = (sys_mem / 2) / (1024 * 1024)  # Half of system RAM

                mem_percent = (
                    (used_mem_mb / total_mem_mb * 100)
                    if used_mem_mb and total_mem_mb
                    else None
                )

                gpus.append(
                    {
                        "id": i,
                        "name": gpu.Name,
                        "load": gpu_util,
                        "memory_total": total_mem_mb,
                        "memory_used": used_mem_mb,
                        "memory_free": (
                            (total_mem_mb - used_mem_mb) if used_mem_mb else None
                        ),
                        "memory_percent": mem_percent,
                        "temperature": None,  # Intel GPUs don't expose temp via WMI
                        "driver": gpu.DriverVersion,
                        "uuid": gpu.PNPDeviceID,
                        "type": (
                            "intel"
                            if "intel" in gpu.Name.lower()
                            else "amd" if "amd" in gpu.Name.lower() else "other"
                        ),
                    }
                )
        except Exception as e:
            print(f"WMI GPU error: {e}")

    return gpus


if __name__ == "__main__":
    # Simple test run
    gpu_stats = get_gpu()
    for gpu in gpu_stats:
        pprint.pprint(gpu)
