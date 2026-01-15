"""
Tests for network endpoints.

Tests /api/network/stats, /api/network/connections, and speedtest endpoints.
"""

import pytest


class TestNetworkStats:
    """Tests for /api/network/stats endpoint."""

    def test_stats_returns_200(self, client):
        """Test that network stats returns 200 OK."""
        response = client.get("/api/network/stats")
        assert response.status_code == 200

    def test_stats_contains_bytes(self, client):
        """Test that stats contains byte counters."""
        response = client.get("/api/network/stats")
        data = response.json()
        assert "bytes_sent" in data
        assert "bytes_recv" in data
        assert data["bytes_sent"] >= 0
        assert data["bytes_recv"] >= 0

    def test_stats_contains_packets(self, client):
        """Test that stats contains packet counters."""
        response = client.get("/api/network/stats")
        data = response.json()
        assert "packets_sent" in data
        assert "packets_recv" in data

    def test_stats_contains_speeds(self, client):
        """Test that stats contains speed calculations."""
        response = client.get("/api/network/stats")
        data = response.json()
        assert "bytes_sent_speed" in data
        assert "bytes_recv_speed" in data


class TestNetworkConnections:
    """Tests for /api/network/connections endpoint."""

    def test_connections_returns_200(self, client):
        """Test that connections endpoint returns 200 OK."""
        response = client.get("/api/network/connections")
        assert response.status_code == 200

    def test_connections_returns_list(self, client):
        """Test that connections returns a list."""
        response = client.get("/api/network/connections")
        data = response.json()
        assert isinstance(data, list)

    def test_connection_structure(self, client):
        """Test that connections have expected structure."""
        response = client.get("/api/network/connections")
        data = response.json()

        if len(data) > 0:
            conn = data[0]
            assert "local_addr" in conn
            assert "remote_addr" in conn
            assert "status" in conn
            assert "pid" in conn


class TestSpeedTest:
    """Tests for speed test endpoints."""

    def test_speedtest_status_returns_200(self, client):
        """Test that speedtest status returns 200 OK."""
        response = client.get("/api/network/speedtest/status")
        assert response.status_code == 200

    def test_speedtest_status_structure(self, client):
        """Test that speedtest status has expected structure."""
        response = client.get("/api/network/speedtest/status")
        data = response.json()
        assert "running" in data
        assert isinstance(data["running"], bool)

    # Note: Not testing POST /api/network/speedtest as it takes 20-60 seconds
    # and requires internet connection. Can be tested manually.
