"""
Tests for process management endpoints.

Tests /api/processes and related process control endpoints.
"""

import os
import pytest


class TestProcessList:
    """Tests for /api/processes endpoint."""

    def test_processes_returns_200(self, client):
        """Test that processes endpoint returns 200 OK."""
        response = client.get("/api/processes")
        assert response.status_code == 200

    def test_processes_returns_list(self, client):
        """Test that processes returns a list."""
        response = client.get("/api/processes")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0  # Should always have some processes

    def test_process_structure(self, client):
        """Test that processes have expected structure."""
        response = client.get("/api/processes")
        data = response.json()

        proc = data[0]
        assert "pid" in proc
        assert "name" in proc
        assert "cpu_percent" in proc
        assert "memory_percent" in proc

    def test_processes_sort_by_cpu(self, client):
        """Test sorting processes by CPU percent."""
        response = client.get("/api/processes?sort=cpu_percent&order=desc")
        assert response.status_code == 200
        data = response.json()

        # Verify descending order (allow for None values)
        cpu_values = [p.get("cpu_percent", 0) or 0 for p in data[:10]]
        assert cpu_values == sorted(cpu_values, reverse=True)

    def test_processes_sort_by_memory(self, client):
        """Test sorting processes by memory percent."""
        response = client.get("/api/processes?sort=memory_percent&order=desc")
        assert response.status_code == 200
        data = response.json()

        mem_values = [p.get("memory_percent", 0) or 0 for p in data[:10]]
        assert mem_values == sorted(mem_values, reverse=True)

    def test_processes_sort_by_name(self, client):
        """Test sorting processes by name."""
        response = client.get("/api/processes?sort=name&order=asc")
        assert response.status_code == 200
        data = response.json()

        names = [(p.get("name") or "").lower() for p in data[:10]]
        assert names == sorted(names)

    def test_cpu_percent_capped(self, client):
        """Test that CPU percent values are capped at 100."""
        response = client.get("/api/processes")
        data = response.json()

        for proc in data:
            cpu = proc.get("cpu_percent")
            if cpu is not None:
                assert cpu <= 100


class TestProcessControl:
    """Tests for process control endpoints (kill, suspend, resume)."""

    def test_kill_nonexistent_process(self, client):
        """Test killing a non-existent process returns failure."""
        response = client.post("/api/processes/999999999/kill")
        data = response.json()
        assert data["success"] is False

    def test_suspend_nonexistent_process(self, client):
        """Test suspending a non-existent process returns failure."""
        response = client.post("/api/processes/999999999/suspend")
        data = response.json()
        assert data["success"] is False

    def test_resume_nonexistent_process(self, client):
        """Test resuming a non-existent process returns failure."""
        response = client.post("/api/processes/999999999/resume")
        data = response.json()
        assert data["success"] is False

    # Note: Not testing actual kill/suspend/resume on real processes
    # as that could destabilize the test environment
