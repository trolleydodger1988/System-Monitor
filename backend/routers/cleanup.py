"""
Cleanup utilities router for temp file management.

Provides /api/cleanup/* endpoints.
"""

from fastapi import APIRouter

from services.cleanup_service import clear_temp_files
from config import logger

router = APIRouter(prefix="/api/cleanup", tags=["cleanup"])


@router.post("/temp-files")
def cleanup_temp_files():
    """
    Clear temporary files from common Windows temp directories.

    Returns:
        dict: Results of the cleanup operation.
    """
    try:
        results = clear_temp_files()
        logger.info(
            f"Temp cleanup completed: {results['total_deleted']} files, "
            f"{results['total_size_freed']} bytes freed"
        )
        return results
    except Exception as e:
        error_msg = f"Temp file cleanup failed: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "total_deleted": 0,
            "total_size_freed": 0,
            "directories_processed": 0,
            "errors": [error_msg],
            "details": [],
        }
