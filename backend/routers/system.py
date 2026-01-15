"""
System monitoring router for CPU, memory, swap, and system info endpoints.

Provides /api/system/* endpoints.
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.system_monitor import get_overview, get_info

router = APIRouter(prefix="/api/system", tags=["system"])

# WebSocket connections list
ws_connections = []


@router.get("/overview")
def overview():
    """
    Get system overview with CPU, memory, swap, network, disk I/O, and GPU stats.

    Returns:
        dict: Aggregated system statistics.
    """
    return get_overview()


@router.get("/info")
def info():
    """
    Get system information including hostname, platform, and boot time.

    Returns:
        dict: System information.
    """
    return get_info()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """
    WebSocket endpoint for real-time system stats streaming.

    Args:
        ws: WebSocket connection.
    """
    await ws.accept()
    ws_connections.append(ws)
    try:
        while True:
            # Run get_overview in a thread to avoid blocking the event loop and
            # to keep WMI COM initialization off the main thread.
            data = await asyncio.to_thread(get_overview)
            await ws.send_json({"type": "system_stats", "data": data})
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        if ws in ws_connections:
            ws_connections.remove(ws)
