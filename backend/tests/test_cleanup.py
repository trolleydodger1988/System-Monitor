"""
Tests for cleanup endpoints.

Tests /api/cleanup/temp-files endpoint.
"""

import pytest


class TestCleanup:
    """Tests for /api/cleanup/temp-files endpoint."""

    def test_cleanup_returns_200(self, client):
        """Test that cleanup endpoint returns 200 OK."""
        # Note: This actually cleans temp files - use with caution in CI
        response = client.post("/api/cleanup/temp-files")
        assert response.status_code == 200

    def test_cleanup_response_structure(self, client):
        """Test that cleanup response has expected structure."""
        response = client.post("/api/cleanup/temp-files")
        data = response.json()

        assert "success" in data
        assert "total_deleted" in data
        assert "total_size_freed" in data
        assert "directories_processed" in data
        assert "errors" in data
        assert "details" in data

    def test_cleanup_values_valid(self, client):
        """Test that cleanup values are logically valid."""
        response = client.post("/api/cleanup/temp-files")
        data = response.json()

        assert isinstance(data["success"], bool)
        assert data["total_deleted"] >= 0
        assert data["total_size_freed"] >= 0
        assert data["directories_processed"] >= 0
        assert isinstance(data["errors"], list)
        assert isinstance(data["details"], list)
