"""
Storage/disk monitoring router for partitions and I/O statistics.

Provides /api/disks/* and /api/disk-io endpoints.
"""

from fastapi import APIRouter

from services.disk_monitor import get_disks, get_disk_io

router = APIRouter(prefix="/api", tags=["storage"])


@router.get("/disks/partitions")
def disks():
    """
    Get disk partition information.

    Returns:
        list: List of disk partition dicts.
    """
    return get_disks()


@router.get("/disk-io")
def disk_io():
    """
    Get disk I/O statistics with read/write speeds per disk.

    Returns:
        dict: Dictionary mapping disk names to their I/O stats.
    """
    return get_disk_io()
