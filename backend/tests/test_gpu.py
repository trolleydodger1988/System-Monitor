"""
Tests for GPU monitoring endpoint.

Tests /api/gpu endpoint with hardware-dependent skipping.
"""

import pytest
from tests.conftest import skip_no_gpu


class TestGPU:
    """Tests for /api/gpu endpoint."""

    def test_gpu_returns_200(self, client):
        """Test that GPU endpoint returns 200 OK (even with no GPU)."""
        response = client.get("/api/gpu")
        assert response.status_code == 200

    def test_gpu_returns_list(self, client):
        """Test that GPU endpoint returns a list."""
        response = client.get("/api/gpu")
        data = response.json()
        assert isinstance(data, list)

    @skip_no_gpu
    def test_gpu_has_expected_fields(self, client):
        """Test that GPU data contains expected fields when GPU is available."""
        response = client.get("/api/gpu")
        data = response.json()

        if len(data) > 0:
            gpu = data[0]
            assert "id" in gpu
            assert "name" in gpu
            assert "load" in gpu
            assert "memory_total" in gpu
            assert "memory_used" in gpu
            assert "type" in gpu

    @skip_no_gpu
    def test_gpu_load_valid_range(self, client):
        """Test that GPU load is in valid range."""
        response = client.get("/api/gpu")
        data = response.json()

        for gpu in data:
            if gpu.get("load") is not None:
                assert 0 <= gpu["load"] <= 100

    @skip_no_gpu
    def test_gpu_type_valid(self, client):
        """Test that GPU type is one of expected values."""
        response = client.get("/api/gpu")
        data = response.json()

        valid_types = {"nvidia", "intel", "amd", "other"}
        for gpu in data:
            assert gpu.get("type") in valid_types
