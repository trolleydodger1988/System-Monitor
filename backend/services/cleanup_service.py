"""
Cleanup utilities service for temp file management.

This module provides functions to clear temporary files from the system.
"""

import shutil
from pathlib import Path
from typing import Dict, Any

from config import logger


def clear_temp_files() -> Dict[str, Any]:
    """
    Clear temporary files from common Windows temp directories.

    Returns:
        dict: Results of the cleanup operation including files deleted and errors.
    """
    # Get user profile dynamically
    user_profile = Path.home()

    temp_directories = [
        user_profile / "AppData" / "Local" / "Temp",
        Path("C:/Windows/Temp"),
        Path("C:/Temp"),
        user_profile / "AppData" / "Local" / "Microsoft" / "Windows" / "INetCache",
        user_profile / "AppData" / "Local" / "CrashDumps",
        user_profile / "AppData" / "Local" / "Microsoft" / "Windows" / "WebCache",
        user_profile
        / "AppData"
        / "Local"
        / "Google"
        / "Chrome"
        / "User Data"
        / "Default"
        / "Cache",
        user_profile
        / "AppData"
        / "Local"
        / "Microsoft"
        / "Edge"
        / "User Data"
        / "Default"
        / "Cache",
        user_profile / "AppData" / "Local" / "pip" / "cache",
        user_profile / "AppData" / "Roaming" / "Code" / "CachedExtensionVSIXs",
        Path("C:/Windows/SoftwareDistribution/Download"),
        # One Drive logs
        user_profile / "AppData" / "Local" / "Microsoft" / "OneDrive" / "logs",
    ]

    results = {
        "success": True,
        "total_deleted": 0,
        "total_size_freed": 0,
        "directories_processed": 0,
        "errors": [],
        "details": [],
    }

    for temp_dir in temp_directories:
        try:
            if not temp_dir.exists():
                results["details"].append(
                    {
                        "directory": str(temp_dir),
                        "status": "skipped",
                        "reason": "Directory does not exist",
                        "files_deleted": 0,
                        "size_freed": 0,
                    }
                )
                continue

            files_deleted = 0
            size_freed = 0

            # Get total size before cleanup
            for item in temp_dir.iterdir():
                try:
                    if item.is_file():
                        size_freed += item.stat().st_size
                        item.unlink()
                        files_deleted += 1
                    elif item.is_dir():
                        # Calculate directory size before removal
                        for sub_item in item.rglob("*"):
                            if sub_item.is_file():
                                try:
                                    size_freed += sub_item.stat().st_size
                                except (OSError, PermissionError):
                                    pass
                        shutil.rmtree(item, ignore_errors=True)
                        files_deleted += 1
                except (PermissionError, FileNotFoundError, OSError) as e:
                    # Some files might be in use, log but continue
                    results["errors"].append(f"Could not delete {item}: {str(e)}")

            results["details"].append(
                {
                    "directory": str(temp_dir),
                    "status": "completed",
                    "files_deleted": files_deleted,
                    "size_freed": size_freed,
                }
            )

            results["total_deleted"] += files_deleted
            results["total_size_freed"] += size_freed
            results["directories_processed"] += 1

        except Exception as e:
            error_msg = f"Error processing {temp_dir}: {str(e)}"
            results["errors"].append(error_msg)
            results["details"].append(
                {
                    "directory": str(temp_dir),
                    "status": "error",
                    "reason": str(e),
                    "files_deleted": 0,
                    "size_freed": 0,
                }
            )
            logger.error(error_msg)

    if results["errors"]:
        results["success"] = len(results["errors"]) < len(temp_directories)

    return results
