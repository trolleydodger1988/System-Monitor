"""
Storage/disk monitoring router for partitions and I/O statistics.

Provides /api/disks/* and /api/disk-io endpoints.
"""

import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.disk_monitor import get_disks, get_disk_io

router = APIRouter(prefix="/api", tags=["storage"])


class OpenFolderRequest(BaseModel):
    """Request model for opening a folder in File Explorer."""

    path: str


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


@router.post("/open-folder")
def open_folder(request: OpenFolderRequest):
    """
    Open a folder in Windows File Explorer.

    Args:
        request (OpenFolderRequest): Contains the path to open.

    Returns:
        dict: Success status message.

    Raises:
        HTTPException: If the path doesn't exist or isn't a directory.
    """
    folder_path = Path(request.path)

    if not folder_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Path does not exist: {request.path}"
        )

    if not folder_path.is_dir():
        # If it's a file, open the parent folder
        folder_path = folder_path.parent

    try:
        subprocess.Popen(f'explorer "{folder_path}"', shell=True)
        return {"status": "success", "path": str(folder_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {str(e)}")
