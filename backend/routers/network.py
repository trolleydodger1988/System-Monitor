"""
Network monitoring router for stats, connections, and speed testing.

Provides /api/network/* endpoints.
"""

import asyncio

from fastapi import APIRouter

from services.network_service import get_net, get_conns, run_speedtest_sync
from config import speed_test_state, logger

router = APIRouter(prefix="/api/network", tags=["network"])


@router.get("/stats")
def net_stats():
    """
    Get network I/O statistics with speed calculations.

    Returns:
        dict: Network metrics including bytes/packets and speeds.
    """
    return get_net()


@router.get("/connections")
def net_conns():
    """
    Get active network connections.

    Returns:
        list: List of connection dicts.
    """
    return get_conns()


@router.post("/speedtest")
async def run_speed_test():
    """
    Run an internet speed test. Returns download/upload speeds in Mbps.
    This can take 20-60 seconds to complete.

    Returns:
        dict: Speed test results or status.
    """
    if speed_test_state.is_running:
        return {"status": "running", "message": "Speed test already in progress"}

    speed_test_state.is_running = True

    try:
        result = await asyncio.to_thread(run_speedtest_sync)
        speed_test_state.last_result = result
        return result
    except Exception as e:
        logger.error(f"Speed test failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        speed_test_state.is_running = False


@router.get("/speedtest/status")
async def get_speed_test_status():
    """
    Get the current speed test status and last result.

    Returns:
        dict: Running status and last result.
    """
    return {
        "running": speed_test_state.is_running,
        "lastResult": speed_test_state.last_result,
    }
