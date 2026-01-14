import asyncio
import platform
import time
import random
import logging
import sys
import os
import shutil
from pathlib import Path
from typing import List, Dict, Literal
from contextlib import asynccontextmanager

# Set CoInitialize flags to MTA (Multi Threaded Apartment) to satisfy Bleak requirements
# This must be done before any library imports pythoncom (e.g. wmi)
try:
    sys.coinit_flags = 0
except:
    pass

import psutil
from bleak import BleakScanner, BleakClient
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# WinRT imports for system-level BLE device enumeration
try:
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.devices.bluetooth import (
        BluetoothLEDevice,
        BluetoothConnectionStatus,
        BluetoothDevice,  # Classic Bluetooth
    )
    from winrt.windows.devices.bluetooth.rfcomm import RfcommDeviceService

    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False
    print("⚠️  WinRT not available. System BLE enumeration disabled.")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BLE_Monitor")


# --- BLE Connection Manager ---
class BLEConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, BleakClient] = {}
        self.websockets: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.websockets.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.websockets:
            self.websockets.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.websockets:
            try:
                await connection.send_json(message)
            except:
                pass


ble_manager = BLEConnectionManager()


# --- Advertisement Stream State ---
class AdvertisementStreamer:
    """
    Manages streaming of BLE advertisement data for a single device.
    """

    def __init__(self):
        self.target_address: str | None = None
        self.scanner: BleakScanner | None = None
        self.is_streaming: bool = False
        self._lock = asyncio.Lock()

    async def _stop_internal(self):
        """Internal stop without lock - called when lock is already held."""
        if self.scanner:
            try:
                await self.scanner.stop()
            except Exception as e:
                logger.error(f"Error stopping scanner: {e}")
            self.scanner = None
        self.target_address = None
        self.is_streaming = False
        logger.info("Stopped advertisement streaming")

    async def start(self, address: str):
        """Start streaming advertisements for a specific device."""
        async with self._lock:
            if self.is_streaming:
                await self._stop_internal()

            self.target_address = address.upper()
            self.is_streaming = True

            def detection_callback(device, advertisement_data):
                if device.address.upper() == self.target_address:
                    # Build advertisement info
                    adv_info = {
                        "type": "advertisement",
                        "address": device.address,
                        "name": device.name or "Unknown",
                        "rssi": advertisement_data.rssi,
                        "timestamp": time.time(),
                        "tx_power": advertisement_data.tx_power,
                        "service_uuids": [
                            str(u) for u in (advertisement_data.service_uuids or [])
                        ],
                        "manufacturer_data": {
                            str(k): v.hex()
                            for k, v in (
                                advertisement_data.manufacturer_data or {}
                            ).items()
                        },
                        "service_data": {
                            str(k): v.hex()
                            for k, v in (advertisement_data.service_data or {}).items()
                        },
                        "local_name": advertisement_data.local_name,
                    }
                    # Broadcast to websockets (fire and forget)
                    asyncio.create_task(ble_manager.broadcast(adv_info))

            self.scanner = BleakScanner(detection_callback=detection_callback)
            await self.scanner.start()
            logger.info(f"Started advertisement streaming for {address}")

    async def stop(self):
        """Stop streaming advertisements."""
        async with self._lock:
            await self._stop_internal()

    def get_status(self) -> dict:
        """Get current streaming status."""
        return {"isStreaming": self.is_streaming, "targetAddress": self.target_address}


adv_streamer = AdvertisementStreamer()

# Try to import GPUtil for NVIDIA GPU monitoring
try:
    import GPUtil

    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False

# Check if WMI is available without importing it to avoid COM threading issues
WMI_AVAILABLE = False
try:
    import importlib.util

    if importlib.util.find_spec("wmi"):
        WMI_AVAILABLE = True
except:
    pass

# GPU is available if either method works
GPU_AVAILABLE = GPUTIL_AVAILABLE or WMI_AVAILABLE
if not GPU_AVAILABLE:
    print(
        "⚠️  No GPU monitoring available. Install GPUtil (NVIDIA) or wmi (Intel/AMD on Windows)"
    )

# Force Bleak to use the correct backend and avoid pythoncom issues
import os

os.environ["BLEAK_LOGGING"] = "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI app startup and shutdown events.

    Args:
        app (FastAPI): The FastAPI application instance.

    Yields:
        None: Control is yielded to the application during its lifetime.
    """
    # Startup
    asyncio.create_task(rssi_updater())
    yield
    # Shutdown (cleanup can go here if needed)


app = FastAPI(title="SysMon", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_prev = {}


def get_cpu():
    freq = psutil.cpu_freq()
    ctx = psutil.cpu_stats()
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
        "threads": sum(
            p.num_threads()
            for p in psutil.process_iter(["num_threads"])
            if p.info.get("num_threads")
        ),
    }


def get_mem():
    m = psutil.virtual_memory()
    return {
        "total": m.total,
        "available": m.available,
        "used": m.used,
        "percent": m.percent,
    }


def get_swap():
    sw = psutil.swap_memory()
    return {"total": sw.total, "used": sw.used, "free": sw.free, "percent": sw.percent}


def get_net():
    n = psutil.net_io_counters()
    t = time.time()
    prev = _prev.get(
        "net", {"bytes_sent": n.bytes_sent, "bytes_recv": n.bytes_recv, "time": t}
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
    _prev["net"] = {"bytes_sent": n.bytes_sent, "bytes_recv": n.bytes_recv, "time": t}
    return r


def get_disks():
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


def get_disk_io():
    """Get disk I/O statistics with read/write speeds per disk."""
    t = time.time()
    io_counters = psutil.disk_io_counters(perdisk=True)
    result = {}

    for disk_name, io in io_counters.items():
        prev_key = f"disk_io_{disk_name}"
        prev = _prev.get(
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

        _prev[prev_key] = {
            "read_bytes": io.read_bytes,
            "write_bytes": io.write_bytes,
            "read_count": io.read_count,
            "write_count": io.write_count,
            "time": t,
        }

    return result


def get_gpu():
    """
    Get GPU statistics using GPUtil (NVIDIA) or WMI + Performance Counters (Intel/AMD on Windows).

    Returns:
        list: List of GPU info dicts with load, memory, temperature, etc.
    """
    gpus = []

    # Try GPUtil first for NVIDIA GPUs (provides detailed stats)
    if GPUTIL_AVAILABLE:
        try:
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
            except:
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


def get_conns():
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


def get_info():
    return {
        "hostname": platform.node(),
        "platform": platform.system(),
        "platform_release": platform.release(),
        "boot_time": psutil.boot_time(),
        "gpu_available": GPU_AVAILABLE,
    }


def get_overview():
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


@app.get("/api/system/overview")
def overview():
    return get_overview()


@app.get("/api/system/info")
def info():
    return get_info()


@app.get("/api/gpu")
def gpu():
    """API endpoint for GPU statistics."""
    return get_gpu()


@app.get("/api/processes")
def processes(sort: str = "cpu_percent", order: str = "desc"):
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


@app.post("/api/processes/{pid}/kill")
def kill(pid: int):
    try:
        psutil.Process(pid).kill()
        return {"success": True}
    except:
        return {"success": False}


@app.post("/api/processes/{pid}/suspend")
def suspend(pid: int):
    try:
        psutil.Process(pid).suspend()
        return {"success": True}
    except:
        return {"success": False}


@app.post("/api/processes/{pid}/resume")
def resume(pid: int):
    try:
        psutil.Process(pid).resume()
        return {"success": True}
    except:
        return {"success": False}


@app.get("/api/network/stats")
def net_stats():
    return get_net()


@app.get("/api/network/connections")
def net_conns():
    return get_conns()


# Speed test state
speed_test_running = False
speed_test_result = None


@app.post("/api/network/speedtest")
async def run_speed_test():
    """
    Run an internet speed test. Returns download/upload speeds in Mbps.
    This can take 20-60 seconds to complete.
    """
    global speed_test_running, speed_test_result

    if speed_test_running:
        return {"status": "running", "message": "Speed test already in progress"}

    speed_test_running = True
    speed_test_result = None

    try:
        result = await asyncio.to_thread(_run_speedtest_sync)
        speed_test_result = result
        return result
    except Exception as e:
        logger.error(f"Speed test failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        speed_test_running = False


@app.get("/api/network/speedtest/status")
async def get_speed_test_status():
    """Get the current speed test status and last result."""
    return {
        "running": speed_test_running,
        "lastResult": speed_test_result,
    }


def _run_speedtest_sync() -> dict:
    """
    Run speed test synchronously (called from thread).

    Returns:
        Dict with download, upload speeds in MB/s and other info
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


@app.get("/api/disks/partitions")
def disks():
    return get_disks()


@app.get("/api/disk-io")
def disk_io():
    return get_disk_io()


def clear_temp_files() -> Dict[str, any]:
    """
    Clear temporary files from common Windows temp directories.

    Returns:
        dict: Results of the cleanup operation including files deleted and errors.
    """
    temp_directories = [
        Path(r"C:\Users\harritx9\AppData\Local\Temp"),
        Path(r"C:\Windows\Temp"),
        Path(r"C:\Temp"),
        Path(r"C:\Users\harritx9\AppData\Local\Microsoft\Windows\INetCache"),
        Path(r"C:\Users\harritx9\AppData\Local\CrashDumps"),
        Path(r"C:\Users\harritx9\AppData\Local\Microsoft\Windows\WebCache"),
        Path(r"C:\Users\harritx9\AppData\Local\Google\Chrome\User Data\Default\Cache"),
        Path(r"C:\Users\harritx9\AppData\Local\Microsoft\Edge\User Data\Default\Cache"),
        Path(r"C:\Users\harritx9\AppData\Local\pip\cache"),
        Path(r"C:\Users\harritx9\AppData\Roaming\Code\CachedExtensionVSIXs"),
        Path(r"C:\Windows\SoftwareDistribution\Download"),
    ]

    results = {
        "success": True,
        "total_deleted": 0,
        "total_size_freed": 0,
        "directories_processed": 0,
        "errors": [],
        "details": [],
    }

    for temp_dir in temp_directories:
        try:
            if not temp_dir.exists():
                results["details"].append(
                    {
                        "directory": str(temp_dir),
                        "status": "skipped",
                        "reason": "Directory does not exist",
                        "files_deleted": 0,
                        "size_freed": 0,
                    }
                )
                continue

            files_deleted = 0
            size_freed = 0

            # Get total size before cleanup
            for item in temp_dir.iterdir():
                try:
                    if item.is_file():
                        size_freed += item.stat().st_size
                        item.unlink()
                        files_deleted += 1
                    elif item.is_dir():
                        # Calculate directory size before removal
                        for sub_item in item.rglob("*"):
                            if sub_item.is_file():
                                try:
                                    size_freed += sub_item.stat().st_size
                                except (OSError, PermissionError):
                                    pass
                        shutil.rmtree(item, ignore_errors=True)
                        files_deleted += 1
                except (PermissionError, FileNotFoundError, OSError) as e:
                    # Some files might be in use, log but continue
                    results["errors"].append(f"Could not delete {item}: {str(e)}")

            results["details"].append(
                {
                    "directory": str(temp_dir),
                    "status": "completed",
                    "files_deleted": files_deleted,
                    "size_freed": size_freed,
                }
            )

            results["total_deleted"] += files_deleted
            results["total_size_freed"] += size_freed
            results["directories_processed"] += 1

        except Exception as e:
            error_msg = f"Error processing {temp_dir}: {str(e)}"
            results["errors"].append(error_msg)
            results["details"].append(
                {
                    "directory": str(temp_dir),
                    "status": "error",
                    "reason": str(e),
                    "files_deleted": 0,
                    "size_freed": 0,
                }
            )
            logger.error(error_msg)

    if results["errors"]:
        results["success"] = len(results["errors"]) < len(temp_directories)

    return results


@app.post("/api/cleanup/temp-files")
def cleanup_temp_files():
    """
    API endpoint to clear temporary files.

    Returns:
        dict: Results of the cleanup operation.
    """
    try:
        results = clear_temp_files()
        logger.info(
            f"Temp cleanup completed: {results['total_deleted']} files, {results['total_size_freed']} bytes freed"
        )
        return results
    except Exception as e:
        error_msg = f"Temp file cleanup failed: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "total_deleted": 0,
            "total_size_freed": 0,
            "directories_processed": 0,
            "errors": [error_msg],
            "details": [],
        }


ws_connections = []


@app.websocket("/ws/system")
async def ws_endpoint(ws: WebSocket):
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


# --- BLE Endpoints & Logic ---


@app.get("/api/ble/scan")
async def scan_devices():
    try:
        # return_adv=True returns a dict{address: (device, advertisement_data)}
        # AdvertisementData contains the RSSI
        devices = await BleakScanner.discover(return_adv=True)
        device_map = {k.upper(): v for k, v in devices.items()}

        results = []
        for d, adv in devices.values():
            results.append(
                {"address": d.address, "name": d.name or "Unknown", "rssi": adv.rssi}
            )

        return results
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        # Return empty list or error object, but as valid JSON
        return []


@app.get("/api/ble/connections")
async def get_active_connections():
    """Return list of currently connected devices (app-initiated via Bleak)"""
    connections = []
    for address, client in ble_manager.active_connections.items():
        connections.append(
            {
                "address": address,
                "name": client.name or "Unknown",
                "isConnected": client.is_connected,
            }
        )
    return connections


# --- System BLE Device Enumeration (WinRT) ---


def _enumerate_ble_devices_sync(selector: str, timeout: float = 5.0) -> list:
    """
    Synchronously enumerate BLE devices using WinRT DeviceWatcher.

    Args:
        selector: AQS selector string from BluetoothLEDevice
        timeout: Max seconds to wait for enumeration

    Returns:
        List of DeviceInformation objects
    """
    devices_found = []
    enumeration_complete = False

    def on_added(watcher, info):
        devices_found.append(info)

    def on_completed(watcher, obj):
        nonlocal enumeration_complete
        enumeration_complete = True

    def on_stopped(watcher, obj):
        nonlocal enumeration_complete
        enumeration_complete = True

    watcher = DeviceInformation.create_watcher_aqs_filter(selector)
    watcher.add_added(on_added)
    watcher.add_enumeration_completed(on_completed)
    watcher.add_stopped(on_stopped)

    watcher.start()

    start = time.time()
    while not enumeration_complete and (time.time() - start) < timeout:
        time.sleep(0.05)

    watcher.stop()
    return devices_found


async def _get_ble_device_details(device_id: str) -> dict | None:
    """
    Get detailed info about a BLE device.

    Args:
        device_id: The device ID string

    Returns:
        Dict with address, name, connected status, or None if failed
    """
    try:
        ble_device = await BluetoothLEDevice.from_id_async(device_id)
        if ble_device:
            addr = ble_device.bluetooth_address
            addr_str = ":".join(
                f"{(addr >> (8*i)) & 0xFF:02X}" for i in range(5, -1, -1)
            )
            return {
                "address": addr_str,
                "name": ble_device.name or "Unknown",
                "isConnected": ble_device.connection_status
                == BluetoothConnectionStatus.CONNECTED,
                "source": "system",
            }
    except Exception as e:
        logger.error(f"Failed to get device details for {device_id}: {e}")
    return None


@app.get("/api/ble/system-devices")
async def get_system_ble_devices():
    """
    Return all paired BLE devices from Windows (system-level).
    These are devices paired through Windows Bluetooth settings.
    """
    if not WINRT_AVAILABLE:
        return {"error": "WinRT not available", "devices": []}

    try:
        selector = BluetoothLEDevice.get_device_selector()
        device_infos = await asyncio.to_thread(_enumerate_ble_devices_sync, selector)

        devices = []
        for dev_info in device_infos:
            details = await _get_ble_device_details(dev_info.id)
            if details:
                devices.append(details)

        return {"devices": devices, "count": len(devices)}
    except Exception as e:
        logger.error(f"System BLE enumeration failed: {e}")
        return {"error": str(e), "devices": []}


async def _get_classic_bluetooth_details(device_id: str) -> dict | None:
    """
    Get details for a Classic Bluetooth device.

    Args:
        device_id: Windows device ID

    Returns:
        Device details dict or None
    """
    try:
        device = await BluetoothDevice.from_id_async(device_id)
        if device:
            # Extract address from device
            address_int = device.bluetooth_address
            # Convert to MAC address format
            address = ":".join(
                f"{(address_int >> (8 * i)) & 0xFF:02X}" for i in range(5, -1, -1)
            )
            return {
                "address": address,
                "name": device.name or "Unknown Classic Device",
                "isConnected": device.connection_status
                == BluetoothConnectionStatus.CONNECTED,
                "source": "classic",
                "deviceClass": (
                    str(device.class_of_device.raw_value)
                    if device.class_of_device
                    else None
                ),
            }
    except Exception as e:
        logger.error(f"Failed to get classic BT details for {device_id}: {e}")
    return None


@app.get("/api/ble/system-connected")
async def get_system_connected_devices():
    """
    Return currently connected Bluetooth devices from Windows (system-level).
    This includes both BLE and Classic Bluetooth devices.
    """
    if not WINRT_AVAILABLE:
        return {"error": "WinRT not available", "devices": []}

    devices = []

    try:
        # Get connected BLE devices
        ble_selector = BluetoothLEDevice.get_device_selector_from_connection_status(
            BluetoothConnectionStatus.CONNECTED
        )
        ble_device_infos = await asyncio.to_thread(
            _enumerate_ble_devices_sync, ble_selector
        )

        for dev_info in ble_device_infos:
            details = await _get_ble_device_details(dev_info.id)
            if details:
                details["deviceId"] = dev_info.id
                details["type"] = "ble"
                devices.append(details)
    except Exception as e:
        logger.error(f"BLE enumeration failed: {e}")

    try:
        # Get connected Classic Bluetooth devices
        classic_selector = BluetoothDevice.get_device_selector_from_connection_status(
            BluetoothConnectionStatus.CONNECTED
        )
        classic_device_infos = await asyncio.to_thread(
            _enumerate_ble_devices_sync, classic_selector
        )

        for dev_info in classic_device_infos:
            details = await _get_classic_bluetooth_details(dev_info.id)
            if details:
                details["deviceId"] = dev_info.id
                details["type"] = "classic"
                devices.append(details)
    except Exception as e:
        logger.error(f"Classic Bluetooth enumeration failed: {e}")

    return {"devices": devices, "count": len(devices)}


@app.get("/api/ble/system-device-info/{address}")
async def get_system_device_info(address: str):
    """
    Get detailed information about a system BLE device including services and characteristics.

    Args:
        address: The Bluetooth address (e.g., FF:F6:19:AC:EE:35)

    Returns:
        Detailed device info including GATT services
    """
    if not WINRT_AVAILABLE:
        return {"error": "WinRT not available"}

    try:
        from winrt.windows.devices.bluetooth.genericattributeprofile import (
            GattDeviceServicesResult,
        )

        # First find the device by enumerating connected devices
        selector = BluetoothLEDevice.get_device_selector_from_connection_status(
            BluetoothConnectionStatus.CONNECTED
        )
        device_infos = await asyncio.to_thread(_enumerate_ble_devices_sync, selector)

        # Find the device with matching address
        target_device = None
        for dev_info in device_infos:
            ble_device = await BluetoothLEDevice.from_id_async(dev_info.id)
            if ble_device:
                addr = ble_device.bluetooth_address
                addr_str = ":".join(
                    f"{(addr >> (8*i)) & 0xFF:02X}" for i in range(5, -1, -1)
                )
                if addr_str.upper() == address.upper():
                    target_device = ble_device
                    break

        if not target_device:
            return {"error": f"Device {address} not found or not connected"}

        # Build device info
        addr = target_device.bluetooth_address
        addr_str = ":".join(f"{(addr >> (8*i)) & 0xFF:02X}" for i in range(5, -1, -1))

        device_info = {
            "address": addr_str,
            "name": target_device.name or "Unknown",
            "isConnected": target_device.connection_status
            == BluetoothConnectionStatus.CONNECTED,
            "bluetoothAddress": addr,
            "deviceId": target_device.device_id,
            "rssi": None,  # Will try to get via scan
            "services": [],
        }

        # Try to get RSSI via a quick Bleak scan (only works if device is advertising)
        try:
            devices = await BleakScanner.discover(timeout=2.0, return_adv=True)
            for d, adv in devices.values():
                if d.address.upper() == address.upper():
                    device_info["rssi"] = adv.rssi
                    break
        except Exception as e:
            logger.debug(f"RSSI scan failed (device may not be advertising): {e}")

        # Try to get GATT services
        try:
            services_result = await target_device.get_gatt_services_async()
            if services_result and services_result.services:
                for service in services_result.services:
                    service_info = {"uuid": str(service.uuid), "characteristics": []}

                    # Get characteristics for this service
                    try:
                        chars_result = await service.get_characteristics_async()
                        if chars_result and chars_result.characteristics:
                            for char in chars_result.characteristics:
                                char_info = {"uuid": str(char.uuid), "properties": []}

                                # Decode characteristic properties
                                props = char.characteristic_properties
                                if props & 0x01:
                                    char_info["properties"].append("Broadcast")
                                if props & 0x02:
                                    char_info["properties"].append("Read")
                                if props & 0x04:
                                    char_info["properties"].append(
                                        "WriteWithoutResponse"
                                    )
                                if props & 0x08:
                                    char_info["properties"].append("Write")
                                if props & 0x10:
                                    char_info["properties"].append("Notify")
                                if props & 0x20:
                                    char_info["properties"].append("Indicate")
                                if props & 0x40:
                                    char_info["properties"].append(
                                        "AuthenticatedSignedWrites"
                                    )
                                if props & 0x80:
                                    char_info["properties"].append("ExtendedProperties")

                                service_info["characteristics"].append(char_info)
                    except Exception as e:
                        service_info["characteristicsError"] = str(e)

                    device_info["services"].append(service_info)
        except Exception as e:
            device_info["servicesError"] = str(e)

        return device_info

    except Exception as e:
        logger.error(f"Failed to get device info for {address}: {e}")
        return {"error": str(e)}


@app.get("/api/bt/system-device-info/{address}")
async def get_classic_system_device_info(address: str):
    """
    Get detailed information about a Classic Bluetooth device.

    Args:
        address: The Bluetooth address (e.g., 41:42:2A:3C:11:28)

    Returns:
        Device info for Classic Bluetooth device
    """
    if not WINRT_AVAILABLE:
        return {"error": "WinRT not available"}

    try:
        # Convert address to integer format for WinRT
        address_clean = address.replace(":", "").replace("-", "")
        address_int = int(address_clean, 16)

        # Get the device
        device = await BluetoothDevice.from_bluetooth_address_async(address_int)

        if not device:
            return {"error": f"Device {address} not found or not connected"}

        device_info = {
            "address": address,
            "name": device.name or "Unknown Device",
            "isConnected": device.connection_status
            == BluetoothConnectionStatus.CONNECTED,
            "type": "classic",
        }

        # Get device class info
        if device.class_of_device:
            cod = device.class_of_device
            device_info["classOfDevice"] = {
                "rawValue": cod.raw_value,
                "majorClass": _get_major_device_class(cod.major_class),
                "minorClass": cod.minor_class,
            }

        # Get SDP records (services) for Classic Bluetooth
        try:
            sdp_result = await device.get_rfcomm_services_async()
            if sdp_result and sdp_result.services:
                device_info["rfcommServices"] = []
                for service in sdp_result.services:
                    service_info = {
                        "serviceName": (
                            service.service_id.uuid
                            if hasattr(service.service_id, "uuid")
                            else str(service.service_id)
                        ),
                    }
                    # Try to get connection info
                    try:
                        host_name = service.connection_host_name
                        if host_name:
                            service_info["hostName"] = host_name
                        service_info["serviceName"] = _get_rfcomm_service_name(
                            str(service.service_id.uuid)
                            if hasattr(service.service_id, "uuid")
                            else str(service.service_id)
                        )
                    except Exception:
                        pass
                    device_info["rfcommServices"].append(service_info)
        except Exception as e:
            device_info["rfcommServicesError"] = str(e)

        return device_info

    except Exception as e:
        logger.error(f"Failed to get classic BT device info for {address}: {e}")
        return {"error": str(e)}


def _get_major_device_class(major_class) -> str:
    """Convert major device class enum to string."""
    class_map = {
        0: "Miscellaneous",
        1: "Computer",
        2: "Phone",
        3: "LAN/Network",
        4: "Audio/Video",
        5: "Peripheral",
        6: "Imaging",
        7: "Wearable",
        8: "Toy",
        9: "Health",
    }
    try:
        return class_map.get(int(major_class), f"Unknown ({major_class})")
    except Exception:
        return str(major_class)


def _get_rfcomm_service_name(uuid: str) -> str:
    """Get human-readable name for common RFCOMM service UUIDs."""
    uuid_lower = uuid.lower()
    services = {
        "0000110a": "Audio Source",
        "0000110b": "Audio Sink",
        "0000110c": "A/V Remote Control Target",
        "0000110e": "A/V Remote Control",
        "0000110f": "A/V Remote Control Controller",
        "00001108": "Headset",
        "00001112": "Headset AG",
        "0000111e": "Handsfree",
        "0000111f": "Handsfree AG",
        "00001101": "Serial Port",
        "00001102": "LAN Access",
        "00001103": "Dialup Networking",
        "00001104": "IrMC Sync",
        "00001105": "OBEX Object Push",
        "00001106": "OBEX File Transfer",
        "0000112d": "SIM Access",
        "0000112e": "Phonebook Access PCE",
        "0000112f": "Phonebook Access PSE",
        "00001132": "Message Access Server",
        "00001133": "Message Notification Server",
        "00001200": "PnP Information",
        "00001800": "Generic Access",
        "00001801": "Generic Attribute",
    }
    # Check if it starts with any known prefix
    for prefix, name in services.items():
        if uuid_lower.startswith(prefix):
            return name
    return uuid


# --- Bluetooth Event Log Endpoints ---


@app.get("/api/bt/event-logs")
async def get_bluetooth_event_logs(max_events: int = 50):
    """
    Get recent Bluetooth-related events from Windows Event Log.
    This shows connection/disconnection events, pairing, and other BT activity.

    Args:
        max_events: Maximum number of events to return (default 50)

    Returns:
        List of Bluetooth events
    """
    try:
        events = await asyncio.to_thread(_get_bt_event_logs, max_events)
        return {"events": events, "count": len(events)}
    except Exception as e:
        logger.error(f"Failed to get Bluetooth event logs: {e}")
        return {"error": str(e), "events": []}


def _get_bt_event_logs(max_events: int = 50) -> list:
    """
    Fetch Bluetooth events from Windows Event Log.

    Args:
        max_events: Maximum events to retrieve

    Returns:
        List of event dictionaries
    """
    import win32evtlog
    import win32evtlogutil

    events = []

    # Bluetooth-related log sources
    log_sources = [
        ("Microsoft-Windows-Bluetooth-BthLEPrepairing/Operational", "BthLEPrepairing"),
        ("Microsoft-Windows-Bluetooth-MTPEnum/Operational", "MTPEnum"),
        ("System", "System"),  # BTHUSB, BTHENUM events
    ]

    for log_name, source_label in log_sources:
        try:
            handle = win32evtlog.OpenEventLog(None, log_name)
            flags = (
                win32evtlog.EVENTLOG_BACKWARDS_READ
                | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            )

            while len(events) < max_events:
                records = win32evtlog.ReadEventLog(handle, flags, 0)
                if not records:
                    break

                for record in records:
                    if len(events) >= max_events:
                        break

                    # Filter for Bluetooth-related events in System log
                    if log_name == "System":
                        source = record.SourceName.lower()
                        if "bth" not in source and "bluetooth" not in source:
                            continue

                    # Parse event
                    try:
                        message = win32evtlogutil.SafeFormatMessage(record, log_name)
                    except Exception:
                        message = (
                            str(record.StringInserts)
                            if record.StringInserts
                            else "No message"
                        )

                    event = {
                        "timestamp": record.TimeGenerated.Format("%Y-%m-%d %H:%M:%S"),
                        "source": record.SourceName,
                        "eventId": record.EventID
                        & 0xFFFF,  # Mask to get actual event ID
                        "eventType": _get_event_type_name(record.EventType),
                        "message": (
                            message[:500] if message else "No message"
                        ),  # Truncate long messages
                        "logSource": source_label,
                    }
                    events.append(event)

            win32evtlog.CloseEventLog(handle)
        except Exception as e:
            logger.debug(f"Could not read log {log_name}: {e}")
            continue

    # Sort by timestamp descending
    events.sort(key=lambda x: x["timestamp"], reverse=True)
    return events[:max_events]


def _get_event_type_name(event_type: int) -> str:
    """Convert Windows event type to string."""
    types = {
        1: "Error",
        2: "Warning",
        4: "Information",
        8: "Audit Success",
        16: "Audit Failure",
    }
    return types.get(event_type, f"Unknown ({event_type})")


# --- Advertisement Streaming Endpoints ---


@app.post("/api/ble/stream/start/{address}")
async def start_advertisement_stream(address: str):
    """
    Start streaming advertisement data for a specific BLE device.
    Only one device can be streamed at a time.

    Args:
        address: The Bluetooth address to monitor

    Returns:
        Status of the streaming operation
    """
    try:
        await adv_streamer.start(address)
        return {"status": "started", "address": address}
    except Exception as e:
        logger.error(f"Failed to start advertisement stream: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/ble/stream/stop")
async def stop_advertisement_stream():
    """Stop the current advertisement stream."""
    try:
        await adv_streamer.stop()
        return {"status": "stopped"}
    except Exception as e:
        logger.error(f"Failed to stop advertisement stream: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/ble/stream/status")
async def get_stream_status():
    """Get the current advertisement streaming status."""
    return adv_streamer.get_status()


@app.post("/api/ble/connect/{address}")
async def connect_device(address: str):
    if address in ble_manager.active_connections:
        client = ble_manager.active_connections[address]
        if client.is_connected:
            return {"status": "already_connected"}

    def handle_disconnect(client: BleakClient):
        logger.info(f"Disconnected from {client.address}")
        if client.address in ble_manager.active_connections:
            del ble_manager.active_connections[client.address]
        # Notify clients via WebSocket?
        # For now, frontend polling connections list will handle UI

    client = BleakClient(address, disconnected_callback=handle_disconnect)
    try:
        await client.connect()
        ble_manager.active_connections[address] = client
        logger.info(f"Connected to {address}")
        return {"status": "connected", "address": address}
    except Exception as e:
        logger.error(f"Failed to connect to {address}: {e}")
        return {"status": "failed", "error": str(e)}


@app.post("/api/ble/disconnect/{address}")
async def disconnect_device(address: str):
    if address in ble_manager.active_connections:
        client = ble_manager.active_connections[address]
        try:
            await client.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting {address}: {e}")

        del ble_manager.active_connections[address]
        return {"status": "disconnected", "address": address}
    return {"status": "not_found"}


async def handle_notification(address, data):
    # Broadcast notification to frontend
    hex_data = data.hex()
    await ble_manager.broadcast(
        {
            "type": "notification",
            "address": address,
            "data": hex_data,
            "timestamp": time.time(),
        }
    )


async def rssi_updater():
    """Background task to push RSSI updates to connected clients"""
    logger.info("RSSI Updater started")
    while True:
        try:
            # Simple check if we have connections to monitor
            if not ble_manager.active_connections:
                await asyncio.sleep(2)
                continue

            # logger.info(f"Scanning for RSSI for {len(ble_manager.active_connections)} devices...")

            # Scan for advertisements
            devices = await BleakScanner.discover(timeout=2.0, return_adv=True)

            # Create a lookup map for case-insensitive comparison
            device_map = {k.upper(): v for k, v in devices.items()}

            # Match found devices with active connections
            for address, client in list(ble_manager.active_connections.items()):
                addr_upper = address.upper()

                if addr_upper in device_map:
                    d, adv = device_map[addr_upper]
                    # Check for valid RSSI (some stacks return 127 for invalid)
                    if adv.rssi is not None and adv.rssi < 10:
                        await ble_manager.broadcast(
                            {
                                "type": "rssi_update",
                                "address": address,
                                "rssi": adv.rssi,
                            }
                        )
                else:
                    # Fallback: Try to read RSSI from client directly if supported (mostly MacOS/BlueZ, but worth a shot)
                    # or just skip.
                    pass

        except Exception as e:
            logger.error(f"RSSI update error: {e}")

        await asyncio.sleep(0.5)


@app.websocket("/ws/ble")
async def ble_websocket_endpoint(websocket: WebSocket):
    await ble_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection open
    except WebSocketDisconnect:
        ble_manager.disconnect(websocket)


# Serve the frontend
import os

from fastapi.responses import FileResponse

# Frontend is in ../frontend relative to this file (backend/main.py)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


@app.get("/favicon.ico")
async def serve_favicon():
    """Serve the favicon."""
    # Keep favicon in backend/static for now, or move it to frontend
    favicon_path = os.path.join(os.path.dirname(__file__), "static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return FileResponse(os.path.join(FRONTEND_DIR, "favicon.ico"))


@app.get("/styles.css")
async def serve_styles():
    """Serve the CSS file."""
    return FileResponse(os.path.join(FRONTEND_DIR, "styles.css"))


@app.get("/app.js")
async def serve_js():
    """Serve the JavaScript file."""
    return FileResponse(os.path.join(FRONTEND_DIR, "app.js"))


@app.get("/")
async def serve_frontend():
    """Serve the main HTML page."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


def get_cyber_banner() -> str:
    """
    Get a badass cyber-themed ASCII art banner for SysMon startup.

    Returns:
        str: The ASCII art banner string without color codes.
    """
    banner_2 = r"""
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
║                    ┌──────────────────────────────────────────────────────────────────┐                    ║
║                    │    [*] Initializing neural interface...                          │                    ║
║                    │    [*] Establishing quantum link to hardware sensors...          │                    ║
║                    │    [*] Decrypting system telemetry streams...                    │                    ║
║                    └──────────────────────────────────────────────────────────────────┘                    ║
╚════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
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

    status_box_2 = f"""
┌──────────────────────────────────────────────┐
│  ▸ GPU Monitoring    : {gpu_status:<22}│
│  ▸ BLE Module        : {ble_status:<22}│
│  ▸ WebSocket         :  Ready                │
├──────────────────────────────────────────────┤
│  [ACCESS POINT] http://localhost:9090        │
└──────────────────────────────────────────────┘
"""
    status_box = f"""
                               ┌─────────────────────────────────────────────┐
                               │  ▸ GPU Monitoring    : {gpu_status:<21}│
                               │  ▸ BLE Module        : {ble_status:<21}│
                               │  ▸ WebSocket         :  Ready               │
                               └─────────────────────────────────────────────┘

"""
    return status_box


def main(
    log_level: Literal[
        "debug", "info", "warning", "error", "critical", "trace"
    ] = "warning",
):
    import uvicorn
    from terminaltexteffects.effects.effect_print import Print
    from terminaltexteffects.effects.effect_decrypt import Decrypt
    from terminaltexteffects.utils.graphics import Color

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

    uvicorn.run(app, host="0.0.0.0", port=9090, log_level=log_level)


if __name__ == "__main__":
    main("warning")
