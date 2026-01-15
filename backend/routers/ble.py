"""
BLE (Bluetooth Low Energy) router for scanning, connecting, and streaming.

Provides /api/ble/* endpoints and WebSocket for real-time BLE updates.
"""

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from bleak import BleakScanner, BleakClient

from services.ble_manager import ble_manager, adv_streamer
from config import logger, WINRT_AVAILABLE

router = APIRouter(prefix="/api/ble", tags=["ble"])


@router.get("/scan")
async def scan_devices():
    """
    Scan for nearby BLE devices.

    Returns:
        list: List of discovered BLE devices.
    """
    try:
        # return_adv=True returns a dict{address: (device, advertisement_data)}
        devices = await BleakScanner.discover(return_adv=True)

        results = []
        for d, adv in devices.values():
            results.append(
                {"address": d.address, "name": d.name or "Unknown", "rssi": adv.rssi}
            )

        return results
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        return []


@router.get("/connections")
async def get_active_connections():
    """
    Return list of currently connected devices (app-initiated via Bleak).

    Returns:
        list: List of connected device dicts.
    """
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


@router.get("/system-devices")
async def get_system_ble_devices():
    """
    Return all paired BLE devices from Windows (system-level).
    These are devices paired through Windows Bluetooth settings.

    Returns:
        dict: Dictionary with devices list and count.
    """
    if not WINRT_AVAILABLE:
        return {"error": "WinRT not available", "devices": []}

    try:
        from winrt.windows.devices.bluetooth import (
            BluetoothLEDevice,
            BluetoothConnectionStatus,
        )
        from winrt.windows.devices.enumeration import DeviceInformation

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


@router.get("/system-connected")
async def get_system_connected_devices():
    """
    Return currently connected Bluetooth devices from Windows (system-level).
    This includes both BLE and Classic Bluetooth devices.

    Returns:
        dict: Dictionary with devices list and count.
    """
    if not WINRT_AVAILABLE:
        return {"error": "WinRT not available", "devices": []}

    devices = []

    try:
        from winrt.windows.devices.bluetooth import (
            BluetoothLEDevice,
            BluetoothConnectionStatus,
            BluetoothDevice,
        )

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
        from winrt.windows.devices.bluetooth import (
            BluetoothDevice,
            BluetoothConnectionStatus,
        )

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


@router.get("/system-device-info/{address}")
async def get_system_device_info(address: str):
    """
    Get detailed information about a system BLE device including services and characteristics.

    Args:
        address: The Bluetooth address (e.g., FF:F6:19:AC:EE:35)

    Returns:
        dict: Detailed device info including GATT services.
    """
    if not WINRT_AVAILABLE:
        return {"error": "WinRT not available"}

    try:
        from winrt.windows.devices.bluetooth import (
            BluetoothLEDevice,
            BluetoothConnectionStatus,
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
            "rssi": None,
            "services": [],
        }

        # Try to get RSSI via a quick Bleak scan
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

                    try:
                        chars_result = await service.get_characteristics_async()
                        if chars_result and chars_result.characteristics:
                            for char in chars_result.characteristics:
                                char_info = {"uuid": str(char.uuid), "properties": []}

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


@router.post("/stream/start/{address}")
async def start_advertisement_stream(address: str):
    """
    Start streaming advertisement data for a specific BLE device.

    Args:
        address: The Bluetooth address to monitor.

    Returns:
        dict: Status of the streaming operation.
    """
    try:
        await adv_streamer.start(address)
        return {"status": "started", "address": address}
    except Exception as e:
        logger.error(f"Failed to start advertisement stream: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/stream/stop")
async def stop_advertisement_stream():
    """
    Stop the current advertisement stream.

    Returns:
        dict: Status of the stop operation.
    """
    try:
        await adv_streamer.stop()
        return {"status": "stopped"}
    except Exception as e:
        logger.error(f"Failed to stop advertisement stream: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/stream/status")
async def get_stream_status():
    """
    Get the current advertisement streaming status.

    Returns:
        dict: Status including isStreaming and targetAddress.
    """
    return adv_streamer.get_status()


@router.post("/connect/{address}")
async def connect_device(address: str):
    """
    Connect to a BLE device.

    Args:
        address: The Bluetooth address to connect to.

    Returns:
        dict: Connection status.
    """
    if address in ble_manager.active_connections:
        client = ble_manager.active_connections[address]
        if client.is_connected:
            return {"status": "already_connected"}

    def handle_disconnect(client: BleakClient):
        logger.info(f"Disconnected from {client.address}")
        if client.address in ble_manager.active_connections:
            del ble_manager.active_connections[client.address]

    client = BleakClient(address, disconnected_callback=handle_disconnect)
    try:
        await client.connect()
        ble_manager.active_connections[address] = client
        logger.info(f"Connected to {address}")
        return {"status": "connected", "address": address}
    except Exception as e:
        logger.error(f"Failed to connect to {address}: {e}")
        return {"status": "failed", "error": str(e)}


@router.post("/disconnect/{address}")
async def disconnect_device(address: str):
    """
    Disconnect from a BLE device.

    Args:
        address: The Bluetooth address to disconnect from.

    Returns:
        dict: Disconnection status.
    """
    if address in ble_manager.active_connections:
        client = ble_manager.active_connections[address]
        try:
            await client.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting {address}: {e}")

        del ble_manager.active_connections[address]
        return {"status": "disconnected", "address": address}
    return {"status": "not_found"}


# Background task for RSSI updates
async def rssi_updater():
    """Background task to push RSSI updates to connected clients."""
    logger.info("RSSI Updater started")
    while True:
        try:
            if not ble_manager.active_connections:
                await asyncio.sleep(2)
                continue

            devices = await BleakScanner.discover(timeout=2.0, return_adv=True)
            device_map = {k.upper(): v for k, v in devices.items()}

            for address, client in list(ble_manager.active_connections.items()):
                addr_upper = address.upper()

                if addr_upper in device_map:
                    d, adv = device_map[addr_upper]
                    if adv.rssi is not None and adv.rssi < 10:
                        await ble_manager.broadcast(
                            {
                                "type": "rssi_update",
                                "address": address,
                                "rssi": adv.rssi,
                            }
                        )

        except Exception as e:
            logger.error(f"RSSI update error: {e}")

        await asyncio.sleep(0.5)


# WebSocket endpoint for BLE updates
async def ble_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time BLE updates.

    Args:
        websocket: WebSocket connection.
    """
    await ble_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection open
    except WebSocketDisconnect:
        ble_manager.disconnect(websocket)


# Helper functions for WinRT device enumeration
def _enumerate_ble_devices_sync(selector: str, timeout: float = 5.0) -> list:
    """
    Synchronously enumerate BLE devices using WinRT DeviceWatcher.

    Args:
        selector: AQS selector string from BluetoothLEDevice
        timeout: Max seconds to wait for enumeration

    Returns:
        List of DeviceInformation objects
    """
    from winrt.windows.devices.enumeration import DeviceInformation

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
        from winrt.windows.devices.bluetooth import (
            BluetoothLEDevice,
            BluetoothConnectionStatus,
        )

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


async def _get_classic_bluetooth_details(device_id: str) -> dict | None:
    """
    Get details for a Classic Bluetooth device.

    Args:
        device_id: Windows device ID

    Returns:
        Device details dict or None
    """
    try:
        from winrt.windows.devices.bluetooth import (
            BluetoothDevice,
            BluetoothConnectionStatus,
        )

        device = await BluetoothDevice.from_id_async(device_id)
        if device:
            address_int = device.bluetooth_address
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
