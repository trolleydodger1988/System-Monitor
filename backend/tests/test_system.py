"""
Tests for system monitoring endpoints.

Tests /api/system/overview and /api/system/info endpoints.
"""

import pytest


class TestSystemOverview:
    """Tests for /api/system/overview endpoint."""

    def test_overview_returns_200(self, client):
        """Test that overview endpoint returns 200 OK."""
        response = client.get("/api/system/overview")
        assert response.status_code == 200

    def test_overview_contains_cpu(self, client):
        """Test that overview contains CPU data."""
        response = client.get("/api/system/overview")
        data = response.json()
        assert "cpu" in data
        assert "percent" in data["cpu"]
        assert "per_cpu" in data["cpu"]
        assert "count" in data["cpu"]

    def test_overview_contains_memory(self, client):
        """Test that overview contains memory data."""
        response = client.get("/api/system/overview")
        data = response.json()
        assert "memory" in data
        assert "total" in data["memory"]
        assert "available" in data["memory"]
        assert "used" in data["memory"]
        assert "percent" in data["memory"]

    def test_overview_contains_swap(self, client):
        """Test that overview contains swap data."""
        response = client.get("/api/system/overview")
        data = response.json()
        assert "swap" in data
        assert "total" in data["swap"]
        assert "used" in data["swap"]

    def test_overview_contains_network(self, client):
        """Test that overview contains network data."""
        response = client.get("/api/system/overview")
        data = response.json()
        assert "network" in data
        assert "bytes_sent" in data["network"]
        assert "bytes_recv" in data["network"]

    def test_overview_contains_disk_io(self, client):
        """Test that overview contains disk I/O data."""
        response = client.get("/api/system/overview")
        data = response.json()
        assert "disk_io" in data

    def test_cpu_percent_valid_range(self, client):
        """Test that CPU percent is in valid range."""
        response = client.get("/api/system/overview")
        data = response.json()
        cpu_percent = data["cpu"]["percent"]
        assert 0 <= cpu_percent <= 100

    def test_memory_values_consistent(self, client):
        """Test that memory values are logically consistent."""
        response = client.get("/api/system/overview")
        data = response.json()
        mem = data["memory"]
        assert mem["total"] >= mem["used"]
        assert mem["total"] >= mem["available"]


class TestSystemInfo:
    """Tests for /api/system/info endpoint."""

    def test_info_returns_200(self, client):
        """Test that info endpoint returns 200 OK."""
        response = client.get("/api/system/info")
        assert response.status_code == 200

    def test_info_contains_hostname(self, client):
        """Test that info contains hostname."""
        response = client.get("/api/system/info")
        data = response.json()
        assert "hostname" in data
        assert isinstance(data["hostname"], str)

    def test_info_contains_platform(self, client):
        """Test that info contains platform info."""
        response = client.get("/api/system/info")
        data = response.json()
        assert "platform" in data
        assert "platform_release" in data

    def test_info_contains_boot_time(self, client):
        """Test that info contains boot time."""
        response = client.get("/api/system/info")
        data = response.json()
        assert "boot_time" in data
        assert data["boot_time"] > 0

    def test_info_contains_gpu_flag(self, client):
        """Test that info contains GPU availability flag."""
        response = client.get("/api/system/info")
        data = response.json()
        assert "gpu_available" in data
        assert isinstance(data["gpu_available"], bool)
