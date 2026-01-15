"""
Network monitoring service for I/O stats, connections, and speed testing.

This module provides network metrics and internet speed testing functionality.
"""

import time
from typing import Dict, Any, List

import psutil

from config import state_manager, logger


def get_net() -> Dict[str, Any]:
    """
    Get network I/O statistics with speed calculations.

    Returns:
        dict: Network metrics including bytes/packets sent/received and speeds.
    """
    n = psutil.net_io_counters()
    t = time.time()
    prev = state_manager.get(
        "net",
        {"bytes_sent": n.bytes_sent, "bytes_recv": n.bytes_recv, "time": t},
    )
    dt = max(t - prev["time"], 0.1)

    r = {
        "bytes_sent": n.bytes_sent,
        "bytes_recv": n.bytes_recv,
        "packets_sent": n.packets_sent,
        "packets_recv": n.packets_recv,
        "bytes_sent_speed": (n.bytes_sent - prev["bytes_sent"]) / dt,
        "bytes_recv_speed": (n.bytes_recv - prev["bytes_recv"]) / dt,
    }

    state_manager.set(
        "net",
        {"bytes_sent": n.bytes_sent, "bytes_recv": n.bytes_recv, "time": t},
    )

    return r


def get_conns() -> List[Dict[str, Any]]:
    """
    Get active network connections.

    Returns:
        list: List of connection dicts with local/remote addresses, status, and PID.
    """
    conns = []
    for c in psutil.net_connections(kind="inet"):
        conns.append(
            {
                "local_addr": (
                    {"ip": c.laddr.ip, "port": c.laddr.port} if c.laddr else None
                ),
                "remote_addr": (
                    {"ip": c.raddr.ip, "port": c.raddr.port} if c.raddr else None
                ),
                "status": c.status,
                "pid": c.pid,
            }
        )
    return conns


def run_speedtest_sync() -> Dict[str, Any]:
    """
    Run speed test synchronously (called from thread).

    Returns:
        dict: Speed test results with download, upload speeds in MB/s and other info.
    """
    import speedtest

    st = speedtest.Speedtest()

    # Get best server
    st.get_best_server()
    server = st.best

    # Run tests
    download_bps = st.download()
    upload_bps = st.upload()

    # Convert to MB/s (bits per second / 8 / 1,000,000 = megabytes per second)
    download_mbps = round(download_bps / 8 / 1_000_000, 2)
    upload_mbps = round(upload_bps / 8 / 1_000_000, 2)

    # Get ping
    ping = round(server.get("latency", 0), 1)

    return {
        "status": "complete",
        "download": download_mbps,
        "upload": upload_mbps,
        "ping": ping,
        "server": {
            "name": server.get("sponsor", "Unknown"),
            "location": f"{server.get('name', '')}, {server.get('country', '')}",
            "host": server.get("host", ""),
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
