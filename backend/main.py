"""
SysMon - System Monitor FastAPI Application.

This is the main entry point for the SysMon backend.
It creates the FastAPI app, configures middleware, mounts routers,
and serves the frontend static files.
"""

import asyncio
import os
import sys
from typing import Literal
from contextlib import asynccontextmanager
from pathlib import Path

# Set CoInitialize flags to MTA (Multi Threaded Apartment) to satisfy Bleak requirements
# This must be done before any library imports pythoncom (e.g. wmi)
try:
    sys.coinit_flags = 0
except Exception:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Import config first to ensure feature flags are set
from config import (
    GPU_AVAILABLE,
    GPUTIL_AVAILABLE,
    WMI_AVAILABLE,
    WINRT_AVAILABLE,
    logger,
)

# Import routers
from routers import (
    system_router,
    gpu_router,
    network_router,
    processes_router,
    storage_router,
    cleanup_router,
    ble_router,
    bluetooth_router,
)
from routers.ble import rssi_updater, ble_websocket_endpoint
from services.ble_manager import ble_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app startup and shutdown events.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Control is yielded to the application during its lifetime.
    """
    # Startup
    asyncio.create_task(rssi_updater())
    yield
    # Shutdown (cleanup can go here if needed)


app = FastAPI(title="SysMon", lifespan=lifespan)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routers
app.include_router(system_router)
app.include_router(gpu_router)
app.include_router(network_router)
app.include_router(processes_router)
app.include_router(storage_router)
app.include_router(cleanup_router)
app.include_router(ble_router)
app.include_router(bluetooth_router)


# --- WebSocket Endpoints ---


@app.websocket("/ws/system")
async def ws_system_endpoint(ws: WebSocket):
    """
    WebSocket endpoint for real-time system stats streaming.

    Args:
        ws: WebSocket connection.
    """
    from services.system_monitor import get_overview

    await ws.accept()
    try:
        while True:
            data = await asyncio.to_thread(get_overview)
            await ws.send_json({"type": "system_stats", "data": data})
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/ble")
async def ws_ble_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time BLE updates.

    Args:
        websocket: WebSocket connection.
    """
    await ble_websocket_endpoint(websocket)


# --- Frontend Static File Serving ---


# Frontend is in ../frontend relative to this file (backend/main.py)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/favicon.ico")
async def serve_favicon():
    """Serve the favicon (SVG)."""
    favicon_path = STATIC_DIR / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/svg+xml")
    # Return 204 No Content if no favicon found
    from fastapi.responses import Response

    return Response(status_code=204)


@app.get("/styles.css")
async def serve_styles():
    """Serve the CSS file."""
    return FileResponse(FRONTEND_DIR / "styles.css")


@app.get("/app.js")
async def serve_js():
    """Serve the JavaScript file."""
    return FileResponse(FRONTEND_DIR / "app.js")


@app.get("/")
async def serve_frontend():
    """Serve the main HTML page."""
    return FileResponse(FRONTEND_DIR / "index.html")


# --- Startup Display Functions ---


def get_cyber_banner() -> str:
    """
    Get a badass cyber-themed ASCII art banner for SysMon startup.

    Returns:
        str: The ASCII art banner string without color codes.
    """
    banner = r"""
╔════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                                            ║
║           ______   _____      _____        ______      ______  _______           _____  _____   ______     ║
║       ___|\     \ |\    \    /    /|   ___|\     \    |      \/       \     ____|\    \|\    \ |\     \    ║
║      |    |\     \| \    \  /    / |  |    |\     \  /          /\     \   /     /\    \\\    \| \     \   ║
║      |    |/____/||  \____\/    /  /  |    |/____/| /     /\   / /\     | /     /  \    \\|    \  \     |  ║
║   ___|    \|   | | \ |    /    /  /___|    \|   | |/     /\ \_/ / /    /||     |    |    ||     \  |    |  ║
║  |    \    \___|/   \|___/    /  /|    \    \___|/|     |  \|_|/ /    / ||     |    |    ||      \ |    |  ║
║  |    |\     \          /    /  / |    |\     \   |     |       |    |  ||\     \  /    /||    |\ \|    |  ║
║  |\ ___\|_____|        /____/  /  |\ ___\|_____|  |\____\       |____|  /| \_____\/____/ ||____||\_____/|  ║
║  | |    |     |       |`    | /   | |    |     |  | |    |      |    | /  \ |    ||    | /|    |/ \|   ||  ║
║   \|____|_____|       |_____|/     \|____|_____|   \|____|      |____|/    \|____||____|/ |____|   |___|/  ║
║     \(    )/            )/           \(    )/        \(          )/          \(    )/      \(       )/     ║
║      '    '             '             '    '          '          '            '    '        '       '      ║
║                                                                                                            ║
║          ____   ____ ___ ___    ____   __ __ _____ ___ __ __   __ __  __  __  _ _ _____ __  ___            ║    
║         / _| `v' /  \ __| _ \ /' _| `v' /' _/_   _| __|  V  | |  V  |/__\|  \| | |_   _/__\| _ \           ║ 
║        | \__`. .'| -< _|| v / `._`.`. .'`._`. | | | _|| \_/ | | \_/ | \/ | | ' | | | || \/ | v /           ║
║         \__/ !_! |__/___|_|_\ |___/ !_! |___/ |_| |___|_| |_| |_| |_|\__/|_|\__|_| |_| \__/|_|_\           ║
║                                                                                                            ║
║                              ┌─────────────────────────────────────────────┐                               ║
║                              │    [ACCESS POINT] http://localhost:9090     │                               ║
║                              └─────────────────────────────────────────────┘                               ║
╚════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
"""
    return banner


def get_status_info() -> str:
    """
    Get system status information string.

    Returns:
        str: The status info string without color codes.
    """
    gpu_status = (
        "✓ NVIDIA (GPUtil)"
        if GPUTIL_AVAILABLE
        else ("✓ Intel/AMD (WMI)" if WMI_AVAILABLE else "✗ Disabled")
    )

    ble_status = "✓ Active" if WINRT_AVAILABLE else "✗ Unavailable"

    status_box = f"""
                               ┌─────────────────────────────────────────────┐
                               │  ▸ GPU Monitoring    : {gpu_status:<21}│
                               │  ▸ BLE Module        : {ble_status:<21}│
                               │  ▸ WebSocket         :  Ready               │
                               └─────────────────────────────────────────────┘

"""
    return status_box


def _display_startup_effects() -> None:
    """
    Display the startup banner and status effects in a background thread.

    This runs the terminal text effects asynchronously so the server can start
    while the fancy visuals are still rendering.
    """
    from terminaltexteffects.effects.effect_print import Print
    from terminaltexteffects.effects.effect_decrypt import Decrypt
    from terminaltexteffects.utils.graphics import Color

    try:
        # Display banner with terminal text effect
        banner = get_cyber_banner()
        effect = Print(banner)
        effect.effect_config.print_head_return_speed = 10
        effect.effect_config.print_speed = 9
        effect.effect_config.final_gradient_steps = 17
        color1, color2, color3 = Color("#9109F1"), Color("#04f510"), Color("#f5042c")
        effect.effect_config.final_gradient_stops = (color1, color2, color3)
        with effect.terminal_output() as terminal:
            for frame in effect:
                terminal.print(frame)

        # Display status info with decrypt effect
        status_info = get_status_info()
        status_effect = Decrypt(status_info)
        status_effect.effect_config.typing_speed = 10
        status_effect.effect_config.ciphertext_colors = (
            Color("#f5042c"),
            Color("#9109F1"),
            Color("#04f510"),
        )
        status_effect.effect_config.final_gradient_stops = (
            Color("#f5042c"),
            Color("#9109F1"),
            Color("#04f510"),
        )
        status_effect.effect_config.final_gradient_steps = 16
        with status_effect.terminal_output() as terminal:
            for frame in status_effect:
                terminal.print(frame)
    except Exception as e:
        # Don't let visual effects crash the server
        logger.warning(f"Startup effects failed: {e}")


def main(
    log_level: Literal[
        "debug", "info", "warning", "error", "critical", "trace"
    ] = "warning",
):
    """
    Main entry point for the SysMon application.

    Args:
        log_level: The log level for uvicorn (default: "warning").
    """
    import threading
    import uvicorn

    # Start the fancy terminal effects in a background thread
    # so the server can start immediately while the visuals render
    effects_thread = threading.Thread(target=_display_startup_effects, daemon=True)
    effects_thread.start()

    uvicorn.run(app, host="0.0.0.0", port=9090, log_level=log_level)


if __name__ == "__main__":
    main("warning")
