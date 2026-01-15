"""
BLE connection management service.

This module provides classes for managing BLE connections and advertisement streaming.
"""

import asyncio
import time
from typing import Dict, List, Optional

from bleak import BleakScanner, BleakClient
from fastapi import WebSocket

from config import logger


class BLEConnectionManager:
    """
    Manages BLE connections and WebSocket broadcasts for real-time updates.
    """

    def __init__(self):
        """Initialize the BLE connection manager."""
        self.active_connections: Dict[str, BleakClient] = {}
        self.websockets: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept a WebSocket connection and add to the list.

        Args:
            websocket: The WebSocket connection to add.
        """
        await websocket.accept()
        self.websockets.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from the list.

        Args:
            websocket: The WebSocket connection to remove.
        """
        if websocket in self.websockets:
            self.websockets.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """
        Broadcast a message to all connected WebSocket clients.

        Args:
            message: The message dict to broadcast.
        """
        for connection in self.websockets:
            try:
                await connection.send_json(message)
            except Exception:
                pass


class AdvertisementStreamer:
    """
    Manages streaming of BLE advertisement data for a single device.
    """

    def __init__(self):
        """Initialize the advertisement streamer."""
        self.target_address: Optional[str] = None
        self.scanner: Optional[BleakScanner] = None
        self.is_streaming: bool = False
        self._lock = asyncio.Lock()
        self._ble_manager: Optional[BLEConnectionManager] = None

    def set_ble_manager(self, manager: BLEConnectionManager) -> None:
        """
        Set the BLE manager for broadcasting.

        Args:
            manager: The BLEConnectionManager instance.
        """
        self._ble_manager = manager

    async def _stop_internal(self) -> None:
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

    async def start(self, address: str) -> None:
        """
        Start streaming advertisements for a specific device.

        Args:
            address: The Bluetooth address to monitor.
        """
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
                    if self._ble_manager:
                        asyncio.create_task(self._ble_manager.broadcast(adv_info))

            self.scanner = BleakScanner(detection_callback=detection_callback)
            await self.scanner.start()
            logger.info(f"Started advertisement streaming for {address}")

    async def stop(self) -> None:
        """Stop streaming advertisements."""
        async with self._lock:
            await self._stop_internal()

    def get_status(self) -> dict:
        """
        Get current streaming status.

        Returns:
            dict: Status including isStreaming and targetAddress.
        """
        return {
            "isStreaming": self.is_streaming,
            "targetAddress": self.target_address,
        }


# Global singleton instances
ble_manager = BLEConnectionManager()
adv_streamer = AdvertisementStreamer()
adv_streamer.set_ble_manager(ble_manager)
