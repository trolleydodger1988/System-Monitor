"""
Pytest configuration and fixtures for SysMon backend tests.

This module provides shared fixtures and configuration for all tests.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add backend to path for imports
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Set COM flags before importing main (required for WMI)
try:
    sys.coinit_flags = 0
except Exception:
    pass

from main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    Create a test client for the FastAPI app.

    Returns:
        TestClient: A test client instance for making requests.
    """
    return TestClient(app)


@pytest.fixture(scope="session")
def base_url() -> str:
    """
    Get the base URL for API requests.

    Returns:
        str: The base API URL.
    """
    return "/api"


# Hardware detection flags for skipping tests
def _has_gpu() -> bool:
    """Check if GPU monitoring is available."""
    try:
        import GPUtil

        return len(GPUtil.getGPUs()) > 0
    except Exception:
        pass
    try:
        import wmi

        c = wmi.WMI()
        return len(list(c.Win32_VideoController())) > 0
    except Exception:
        return False


def _has_bluetooth() -> bool:
    """Check if Bluetooth/BLE is available."""
    try:
        from winrt.windows.devices.bluetooth import BluetoothLEDevice

        return True
    except ImportError:
        return False


# Pytest markers for hardware-dependent tests
HAS_GPU = _has_gpu()
HAS_BLUETOOTH = _has_bluetooth()

skip_no_gpu = pytest.mark.skipif(not HAS_GPU, reason="GPU hardware not available")

skip_no_bluetooth = pytest.mark.skipif(
    not HAS_BLUETOOTH, reason="Bluetooth/BLE hardware not available"
)
