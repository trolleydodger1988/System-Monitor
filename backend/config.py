"""
Configuration and shared state management for SysMon backend.

This module contains feature flags, constants, and singleton state managers.
"""

import logging
import sys
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SysMon")


# --- COM Threading Configuration ---
# Set CoInitialize flags to MTA (Multi Threaded Apartment) to satisfy Bleak requirements
# This must be done before any library imports pythoncom (e.g. wmi)
try:
    sys.coinit_flags = 0
except Exception:
    pass


# --- Feature Flags ---
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
except Exception:
    pass

# GPU is available if either method works
GPU_AVAILABLE = GPUTIL_AVAILABLE or WMI_AVAILABLE
if not GPU_AVAILABLE:
    print(
        "⚠️  No GPU monitoring available. Install GPUtil (NVIDIA) or wmi (Intel/AMD on Windows)"
    )

# WinRT imports for system-level BLE device enumeration
try:
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.devices.bluetooth import (
        BluetoothLEDevice,
        BluetoothConnectionStatus,
        BluetoothDevice,
    )
    from winrt.windows.devices.bluetooth.rfcomm import RfcommDeviceService

    WINRT_AVAILABLE = True
except ImportError:
    WINRT_AVAILABLE = False
    print("⚠️  WinRT not available. System BLE enumeration disabled.")


class StateManager:
    """
    Singleton class for managing shared state across the application.

    This class handles the '_prev' dictionary used for calculating speeds
    (network, disk I/O) by storing previous values and timestamps.
    """

    _instance: Optional["StateManager"] = None

    def __new__(cls) -> "StateManager":
        """
        Create or return the singleton instance.

        Returns:
            StateManager: The singleton instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._prev: Dict[str, Any] = {}
        return cls._instance

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the state dictionary.

        Args:
            key: The key to retrieve.
            default: Default value if key doesn't exist.

        Returns:
            The stored value or default.
        """
        return self._prev.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the state dictionary.

        Args:
            key: The key to set.
            value: The value to store.
        """
        self._prev[key] = value

    def clear(self) -> None:
        """Clear all stored state."""
        self._prev.clear()


# Global singleton instance
state_manager = StateManager()


# Speed test state
class SpeedTestState:
    """
    Singleton for managing speed test state.
    """

    _instance: Optional["SpeedTestState"] = None

    def __new__(cls) -> "SpeedTestState":
        """
        Create or return the singleton instance.

        Returns:
            SpeedTestState: The singleton instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.running = False
            cls._instance.result = None
        return cls._instance

    @property
    def is_running(self) -> bool:
        """Check if speed test is running."""
        return self.running

    @is_running.setter
    def is_running(self, value: bool) -> None:
        """Set speed test running state."""
        self.running = value

    @property
    def last_result(self) -> Optional[Dict[str, Any]]:
        """Get the last speed test result."""
        return self.result

    @last_result.setter
    def last_result(self, value: Optional[Dict[str, Any]]) -> None:
        """Set the last speed test result."""
        self.result = value


# Global speed test state instance
speed_test_state = SpeedTestState()
