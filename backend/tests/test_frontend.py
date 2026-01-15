"""
Tests for frontend serving endpoints.

Tests /, /styles.css, /app.js, /favicon.ico endpoints.
"""

import pytest


class TestFrontendServing:
    """Tests for frontend static file serving."""

    def test_index_returns_200(self, client):
        """Test that root returns 200 OK."""
        response = client.get("/")
        assert response.status_code == 200

    def test_index_returns_html(self, client):
        """Test that root returns HTML content."""
        response = client.get("/")
        assert "text/html" in response.headers.get("content-type", "")

    def test_styles_returns_200(self, client):
        """Test that styles.css returns 200 OK."""
        response = client.get("/styles.css")
        assert response.status_code == 200

    def test_styles_returns_css(self, client):
        """Test that styles.css returns CSS content."""
        response = client.get("/styles.css")
        content_type = response.headers.get("content-type", "")
        assert "css" in content_type or "text/plain" in content_type

    def test_appjs_returns_200(self, client):
        """Test that app.js returns 200 OK."""
        response = client.get("/app.js")
        assert response.status_code == 200

    def test_appjs_returns_javascript(self, client):
        """Test that app.js returns JavaScript content."""
        response = client.get("/app.js")
        content_type = response.headers.get("content-type", "")
        assert "javascript" in content_type or "text/plain" in content_type
