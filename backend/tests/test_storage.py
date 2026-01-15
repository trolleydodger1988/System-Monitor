"""
Tests for storage/disk endpoints.

Tests /api/disks/partitions and /api/disk-io endpoints.
"""

import pytest


class TestDiskPartitions:
    """Tests for /api/disks/partitions endpoint."""

    def test_partitions_returns_200(self, client):
        """Test that partitions endpoint returns 200 OK."""
        response = client.get("/api/disks/partitions")
        assert response.status_code == 200

    def test_partitions_returns_list(self, client):
        """Test that partitions returns a list."""
        response = client.get("/api/disks/partitions")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0  # Should have at least one disk

    def test_partition_structure(self, client):
        """Test that partitions have expected structure."""
        response = client.get("/api/disks/partitions")
        data = response.json()

        disk = data[0]
        assert "device" in disk
        assert "mountpoint" in disk
        assert "fstype" in disk
        assert "total" in disk
        assert "used" in disk
        assert "free" in disk
        assert "percent" in disk

    def test_partition_values_valid(self, client):
        """Test that partition values are logically valid."""
        response = client.get("/api/disks/partitions")
        data = response.json()

        for disk in data:
            assert disk["total"] >= disk["used"]
            assert disk["total"] >= disk["free"]
            assert 0 <= disk["percent"] <= 100


class TestDiskIO:
    """Tests for /api/disk-io endpoint."""

    def test_disk_io_returns_200(self, client):
        """Test that disk I/O endpoint returns 200 OK."""
        response = client.get("/api/disk-io")
        assert response.status_code == 200

    def test_disk_io_returns_dict(self, client):
        """Test that disk I/O returns a dictionary."""
        response = client.get("/api/disk-io")
        data = response.json()
        assert isinstance(data, dict)

    def test_disk_io_structure(self, client):
        """Test that disk I/O has expected structure per disk."""
        response = client.get("/api/disk-io")
        data = response.json()

        if len(data) > 0:
            disk_name = list(data.keys())[0]
            disk = data[disk_name]
            assert "read_bytes" in disk
            assert "write_bytes" in disk
            assert "read_count" in disk
            assert "write_count" in disk
            assert "read_speed" in disk
            assert "write_speed" in disk
            assert "read_iops" in disk
            assert "write_iops" in disk

    def test_disk_io_speeds_non_negative(self, client):
        """Test that disk I/O speeds are non-negative."""
        response = client.get("/api/disk-io")
        data = response.json()

        for disk_name, disk in data.items():
            assert disk["read_speed"] >= 0
            assert disk["write_speed"] >= 0
            assert disk["read_iops"] >= 0
            assert disk["write_iops"] >= 0
