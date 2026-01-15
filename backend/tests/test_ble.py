"""
Tests for BLE (Bluetooth Low Energy) endpoints.

Tests /api/ble/* endpoints with hardware-dependent skipping.
"""

import pytest
from tests.conftest import skip_no_bluetooth


class TestBLEScan:
    """Tests for /api/ble/scan endpoint."""

    @skip_no_bluetooth
    def test_scan_returns_200(self, client):
        """Test that BLE scan returns 200 OK."""
        response = client.get("/api/ble/scan")
        assert response.status_code == 200

    @skip_no_bluetooth
    def test_scan_returns_list(self, client):
        """Test that BLE scan returns a list."""
        response = client.get("/api/ble/scan")
        data = response.json()
        assert isinstance(data, list)


class TestBLEConnections:
    """Tests for /api/ble/connections endpoint."""

    @skip_no_bluetooth
    def test_connections_returns_200(self, client):
        """Test that BLE connections returns 200 OK."""
        response = client.get("/api/ble/connections")
        assert response.status_code == 200

    @skip_no_bluetooth
    def test_connections_returns_list(self, client):
        """Test that BLE connections returns a list."""
        response = client.get("/api/ble/connections")
        data = response.json()
        assert isinstance(data, list)


class TestBLESystemDevices:
    """Tests for /api/ble/system-devices endpoint."""

    @skip_no_bluetooth
    def test_system_devices_returns_200(self, client):
        """Test that system devices returns 200 OK."""
        response = client.get("/api/ble/system-devices")
        assert response.status_code == 200

    @skip_no_bluetooth
    def test_system_devices_structure(self, client):
        """Test that system devices has expected structure."""
        response = client.get("/api/ble/system-devices")
        data = response.json()

        # Either has devices list or error
        assert "devices" in data or "error" in data


class TestBLESystemConnected:
    """Tests for /api/ble/system-connected endpoint."""

    @skip_no_bluetooth
    def test_system_connected_returns_200(self, client):
        """Test that system connected returns 200 OK."""
        response = client.get("/api/ble/system-connected")
        assert response.status_code == 200

    @skip_no_bluetooth
    def test_system_connected_structure(self, client):
        """Test that system connected has expected structure."""
        response = client.get("/api/ble/system-connected")
        data = response.json()

        assert "devices" in data or "error" in data
        if "devices" in data:
            assert "count" in data


class TestBLEStream:
    """Tests for /api/ble/stream/* endpoints."""

    @skip_no_bluetooth
    def test_stream_status_returns_200(self, client):
        """Test that stream status returns 200 OK."""
        response = client.get("/api/ble/stream/status")
        assert response.status_code == 200

    @skip_no_bluetooth
    def test_stream_status_structure(self, client):
        """Test that stream status has expected structure."""
        response = client.get("/api/ble/stream/status")
        data = response.json()

        assert "isStreaming" in data
        assert "targetAddress" in data

    @skip_no_bluetooth
    def test_stream_stop_returns_200(self, client):
        """Test that stream stop returns 200 OK."""
        response = client.post("/api/ble/stream/stop")
        assert response.status_code == 200


class TestBLEConnect:
    """Tests for /api/ble/connect and disconnect endpoints."""

    @skip_no_bluetooth
    def test_disconnect_nonexistent(self, client):
        """Test disconnecting a non-connected device."""
        response = client.post("/api/ble/disconnect/00:00:00:00:00:00")
        data = response.json()
        assert data["status"] == "not_found"
