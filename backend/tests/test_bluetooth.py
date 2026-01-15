"""
Tests for Classic Bluetooth endpoints.

Tests /api/bt/* endpoints with hardware-dependent skipping.
"""

import pytest
from tests.conftest import skip_no_bluetooth


class TestBluetoothEventLogs:
    """Tests for /api/bt/event-logs endpoint."""

    @skip_no_bluetooth
    def test_event_logs_returns_200(self, client):
        """Test that event logs returns 200 OK."""
        response = client.get("/api/bt/event-logs")
        assert response.status_code == 200

    @skip_no_bluetooth
    def test_event_logs_structure(self, client):
        """Test that event logs has expected structure."""
        response = client.get("/api/bt/event-logs")
        data = response.json()

        assert "events" in data or "error" in data
        if "events" in data:
            assert "count" in data
            assert isinstance(data["events"], list)

    @skip_no_bluetooth
    def test_event_logs_max_events(self, client):
        """Test that max_events parameter works."""
        response = client.get("/api/bt/event-logs?max_events=5")
        data = response.json()

        if "events" in data:
            assert len(data["events"]) <= 5


class TestBluetoothDeviceInfo:
    """Tests for /api/bt/system-device-info endpoint."""

    @skip_no_bluetooth
    def test_device_info_invalid_address(self, client):
        """Test device info with invalid address."""
        response = client.get("/api/bt/system-device-info/00:00:00:00:00:00")
        # Should return 200 with error in body, or could be 404 depending on implementation
        assert response.status_code == 200
        data = response.json()
        assert "error" in data or "address" in data
