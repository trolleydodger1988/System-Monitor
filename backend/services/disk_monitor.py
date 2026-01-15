"""
Disk monitoring service for partitions and I/O statistics.

This module provides disk partition info and I/O metrics with speed calculations.
"""

import time
from typing import Dict, Any, List

import psutil

from config import state_manager


def get_disks() -> List[Dict[str, Any]]:
    """
    Get disk partition information.

    Returns:
        list: List of disk partition dicts with device, mountpoint, fstype, and usage.
    """
    disks = []
    for p in psutil.disk_partitions():
        # Skip snap mounts on Linux, CD-ROMs on Windows
        if p.mountpoint.startswith("/snap") or "cdrom" in p.opts:
            continue
        try:
            usage = psutil.disk_usage(p.mountpoint)._asdict()
            disks.append(
                {
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    **usage,
                }
            )
        except PermissionError:
            continue
    return disks


def get_disk_io() -> Dict[str, Dict[str, Any]]:
    """
    Get disk I/O statistics with read/write speeds per disk.

    Returns:
        dict: Dictionary mapping disk names to their I/O stats including
              read/write bytes, counts, times, speeds, and IOPS.
    """
    t = time.time()
    io_counters = psutil.disk_io_counters(perdisk=True)
    result = {}

    for disk_name, io in io_counters.items():
        prev_key = f"disk_io_{disk_name}"
        prev = state_manager.get(
            prev_key,
            {
                "read_bytes": io.read_bytes,
                "write_bytes": io.write_bytes,
                "read_count": io.read_count,
                "write_count": io.write_count,
                "time": t,
            },
        )
        dt = max(t - prev["time"], 0.1)

        result[disk_name] = {
            "read_bytes": io.read_bytes,
            "write_bytes": io.write_bytes,
            "read_count": io.read_count,
            "write_count": io.write_count,
            "read_time": io.read_time,
            "write_time": io.write_time,
            "read_speed": (io.read_bytes - prev["read_bytes"]) / dt,
            "write_speed": (io.write_bytes - prev["write_bytes"]) / dt,
            "read_iops": (io.read_count - prev["read_count"]) / dt,
            "write_iops": (io.write_count - prev["write_count"]) / dt,
        }

        state_manager.set(
            prev_key,
            {
                "read_bytes": io.read_bytes,
                "write_bytes": io.write_bytes,
                "read_count": io.read_count,
                "write_count": io.write_count,
                "time": t,
            },
        )

    return result
