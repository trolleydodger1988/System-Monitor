"""
File monitoring router for real-time file change tracking.

Provides endpoints to start/stop monitoring drives and get status.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.file_watcher import file_watcher_service

router = APIRouter(prefix="/api/file-monitor", tags=["file-monitor"])


class DriveRequest(BaseModel):
    """Request model for drive operations."""

    drive: str


@router.post("/start")
def start_monitoring(request: DriveRequest):
    """
    Start monitoring a drive for file changes.

    Args:
        request: Contains the drive letter to monitor.

    Returns:
        dict: Success status and drive being monitored.

    Raises:
        HTTPException: If monitoring fails to start.
    """
    drive = request.drive.upper()

    if file_watcher_service.start_monitoring(drive):
        return {"status": "started", "drive": drive}
    else:
        raise HTTPException(
            status_code=500, detail=f"Failed to start monitoring {drive}"
        )


@router.post("/stop")
def stop_monitoring(request: DriveRequest):
    """
    Stop monitoring a drive.

    Args:
        request: Contains the drive letter to stop monitoring.

    Returns:
        dict: Success status and drive that was stopped.
    """
    drive = request.drive.upper()
    file_watcher_service.stop_monitoring(drive)
    return {"status": "stopped", "drive": drive}


@router.get("/status")
def get_status():
    """
    Get current file monitoring status.

    Returns:
        dict: Status of all monitored drives.
    """
    return file_watcher_service.get_status()
