"""
Classic Bluetooth router for device info and event logs.

Provides /api/bt/* endpoints.
"""

import time

from fastapi import APIRouter

from config import logger, WINRT_AVAILABLE

router = APIRouter(prefix="/api/bt", tags=["bluetooth"])


@router.get("/system-device-info/{address}")
async def get_classic_system_device_info(address: str):
    """
    Get detailed information about a Classic Bluetooth device.

    Args:
        address: The Bluetooth address (e.g., 41:42:2A:3C:11:28)

    Returns:
        dict: Device info for Classic Bluetooth device.
    """
    if not WINRT_AVAILABLE:
        return {"error": "WinRT not available"}

    try:
        from winrt.windows.devices.bluetooth import (
            BluetoothDevice,
            BluetoothConnectionStatus,
        )

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


@router.get("/event-logs")
async def get_bluetooth_event_logs(max_events: int = 50):
    """
    Get recent Bluetooth-related events from Windows Event Log.
    This shows connection/disconnection events, pairing, and other BT activity.

    Args:
        max_events: Maximum number of events to return (default 50)

    Returns:
        dict: List of Bluetooth events.
    """
    try:
        import asyncio

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
                        "eventId": record.EventID & 0xFFFF,
                        "eventType": _get_event_type_name(record.EventType),
                        "message": (message[:500] if message else "No message"),
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
    for prefix, name in services.items():
        if uuid_lower.startswith(prefix):
            return name
    return uuid
