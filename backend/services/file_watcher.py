"""
File system monitoring service using watchdog.

Monitors drives for file changes (create, modify, delete, move) and
streams events via callback for WebSocket broadcasting.
"""

import os
import threading
import time
import logging
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from queue import Queue, Empty

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
)

logger = logging.getLogger("SysMon")


# Directories to ignore for performance
IGNORED_DIRS = {
    "$Recycle.Bin",
    "System Volume Information",
    "$WinREAgent",
    "$Windows.~BT",
    "$Windows.~WS",
    "Windows.old",
    "ProgramData\\Microsoft\\Windows\\WER",
    "ProgramData\\Package Cache",
    "AppData\\Local\\Temp",
    "AppData\\Local\\Microsoft\\Windows\\INetCache",
    "AppData\\Local\\Microsoft\\Windows\\Explorer",
    "AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache",
    "AppData\\Local\\Mozilla\\Firefox\\Profiles",
    ".git",
    "node_modules",
    "__pycache__",
    # ".venv",
    # "venv",
}

# File extensions to ignore
IGNORED_EXTENSIONS = {
    # ".tmp",
    # ".temp",
    # ".log",
    ".etl",
    ".evtx",
    ".lock",
    ".lck",
    ".db-journal",
    ".db-wal",
}


@dataclass
class FileChangeEvent:
    """Represents a file system change event."""

    timestamp: str
    event_type: str  # 'new', 'modified', 'deleted', 'moved'
    path: str
    size: int
    is_directory: bool
    is_onedrive: bool
    old_path: Optional[str] = None  # For move events

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class FileChangeHandler(FileSystemEventHandler):
    """
    Handles file system events from watchdog observer.

    Filters out ignored directories/files and queues valid events.
    """

    def __init__(self, event_queue: Queue, drive: str):
        """
        Initialize the handler.

        Args:
            event_queue: Queue to put events into.
            drive: The drive being monitored (e.g., 'C:').
        """
        super().__init__()
        self.event_queue = event_queue
        self.drive = drive
        self._last_events: dict[str, float] = {}  # Debounce tracking
        self._debounce_seconds = 0.5

    def _should_ignore(self, path: str) -> bool:
        """
        Check if the path should be ignored.

        Args:
            path: The file/directory path.

        Returns:
            True if path should be ignored.
        """
        path_lower = path.lower()

        # Check ignored directories
        for ignored in IGNORED_DIRS:
            if ignored.lower() in path_lower:
                return True

        # Check ignored extensions
        ext = Path(path).suffix.lower()
        if ext in IGNORED_EXTENSIONS:
            return True

        return False

    def _is_debounced(self, path: str, event_type: str) -> bool:
        """
        Check if event should be debounced (too recent duplicate).

        Args:
            path: The file path.
            event_type: The type of event.

        Returns:
            True if event should be skipped.
        """
        key = f"{event_type}:{path}"
        now = time.time()

        if key in self._last_events:
            if now - self._last_events[key] < self._debounce_seconds:
                return True

        self._last_events[key] = now

        # Clean old entries periodically
        if len(self._last_events) > 1000:
            cutoff = now - self._debounce_seconds * 2
            self._last_events = {
                k: v for k, v in self._last_events.items() if v > cutoff
            }

        return False

    def _get_file_size(self, path: str) -> int:
        """
        Safely get file size.

        Args:
            path: The file path.

        Returns:
            File size in bytes, or 0 if unavailable.
        """
        try:
            return os.path.getsize(path)
        except (OSError, FileNotFoundError):
            return 0

    def _is_onedrive_path(self, path: str) -> bool:
        """
        Check if path is within OneDrive folder.

        Args:
            path: The file path.

        Returns:
            True if path is in OneDrive.
        """
        return "onedrive" in path.lower()

    def _create_event(
        self,
        event_type: str,
        path: str,
        is_directory: bool,
        old_path: Optional[str] = None,
    ) -> Optional[FileChangeEvent]:
        """
        Create a FileChangeEvent if valid.

        Args:
            event_type: Type of event.
            path: File/directory path.
            is_directory: Whether it's a directory.
            old_path: Previous path for move events.

        Returns:
            FileChangeEvent or None if should be ignored.
        """
        if self._should_ignore(path):
            return None

        if self._is_debounced(path, event_type):
            return None

        return FileChangeEvent(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            path=path,
            size=self._get_file_size(path) if event_type != "deleted" else 0,
            is_directory=is_directory,
            is_onedrive=self._is_onedrive_path(path),
            old_path=old_path,
        )

    def on_created(self, event):
        """Handle file/directory creation."""
        is_dir = isinstance(event, DirCreatedEvent)
        file_event = self._create_event("new", event.src_path, is_dir)
        if file_event:
            self.event_queue.put(file_event)

    def on_modified(self, event):
        """Handle file/directory modification."""
        # Skip directory modifications (too noisy)
        if isinstance(event, DirModifiedEvent):
            return

        file_event = self._create_event("modified", event.src_path, False)
        if file_event:
            self.event_queue.put(file_event)

    def on_deleted(self, event):
        """Handle file/directory deletion."""
        is_dir = isinstance(event, DirDeletedEvent)
        file_event = self._create_event("deleted", event.src_path, is_dir)
        if file_event:
            self.event_queue.put(file_event)

    def on_moved(self, event):
        """Handle file/directory move/rename."""
        is_dir = isinstance(event, DirMovedEvent)
        file_event = self._create_event(
            "moved", event.dest_path, is_dir, old_path=event.src_path
        )
        if file_event:
            self.event_queue.put(file_event)


class FileWatcherService:
    """
    Service for monitoring file system changes on drives.

    Manages watchdog observers and streams events via callback.
    """

    def __init__(self):
        """Initialize the file watcher service."""
        self._observers: dict[str, Observer] = {}
        self._event_queues: dict[str, Queue] = {}
        self._processor_threads: dict[str, threading.Thread] = {}
        self._running: dict[str, bool] = {}
        self._callbacks: list[Callable[[FileChangeEvent], None]] = []
        self._lock = threading.Lock()

    def register_callback(self, callback: Callable[[FileChangeEvent], None]) -> None:
        """
        Register a callback for file change events.

        Args:
            callback: Function to call with each FileChangeEvent.
        """
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[FileChangeEvent], None]) -> None:
        """
        Unregister a callback.

        Args:
            callback: The callback to remove.
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _process_events(self, drive: str) -> None:
        """
        Process events from queue and dispatch to callbacks.

        Args:
            drive: The drive being processed.
        """
        queue = self._event_queues.get(drive)
        if not queue:
            return

        while self._running.get(drive, False):
            try:
                event = queue.get(timeout=0.5)
                for callback in self._callbacks:
                    try:
                        callback(event)
                    except Exception as e:
                        logger.error(f"Error in file watcher callback: {e}")
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing file event: {e}")

    def start_monitoring(self, drive: str) -> bool:
        """
        Start monitoring a drive for file changes.

        Args:
            drive: Drive letter with colon (e.g., 'C:').

        Returns:
            True if monitoring started successfully.
        """
        drive = drive.upper().rstrip("\\")
        if not drive.endswith(":"):
            drive += ":"

        path = f"{drive}\\"

        if not os.path.exists(path):
            logger.error(f"Drive {drive} does not exist")
            return False

        with self._lock:
            if drive in self._observers:
                logger.info(f"Already monitoring {drive}")
                return True

            try:
                event_queue: Queue = Queue(maxsize=10000)
                handler = FileChangeHandler(event_queue, drive)
                observer = Observer()
                observer.schedule(handler, path, recursive=True)

                self._event_queues[drive] = event_queue
                self._observers[drive] = observer
                self._running[drive] = True

                # Start the observer
                observer.start()

                # Start event processor thread
                processor = threading.Thread(
                    target=self._process_events,
                    args=(drive,),
                    daemon=True,
                    name=f"FileWatcher-{drive}",
                )
                self._processor_threads[drive] = processor
                processor.start()

                logger.info(f"Started monitoring {drive}")
                return True

            except Exception as e:
                logger.error(f"Failed to start monitoring {drive}: {e}")
                self._cleanup_drive(drive)
                return False

    def stop_monitoring(self, drive: str) -> bool:
        """
        Stop monitoring a drive.

        Args:
            drive: Drive letter with colon (e.g., 'C:').

        Returns:
            True if monitoring stopped successfully.
        """
        drive = drive.upper().rstrip("\\")
        if not drive.endswith(":"):
            drive += ":"

        with self._lock:
            if drive not in self._observers:
                logger.info(f"Not monitoring {drive}")
                return True

            self._running[drive] = False
            self._cleanup_drive(drive)
            logger.info(f"Stopped monitoring {drive}")
            return True

    def _cleanup_drive(self, drive: str) -> None:
        """
        Clean up resources for a drive.

        Args:
            drive: The drive to clean up.
        """
        if drive in self._observers:
            try:
                self._observers[drive].stop()
                self._observers[drive].join(timeout=2)
            except Exception as e:
                logger.error(f"Error stopping observer for {drive}: {e}")
            del self._observers[drive]

        if drive in self._event_queues:
            del self._event_queues[drive]

        if drive in self._processor_threads:
            del self._processor_threads[drive]

        if drive in self._running:
            del self._running[drive]

    def get_status(self) -> dict:
        """
        Get current monitoring status.

        Returns:
            Dict with monitoring status for all drives.
        """
        with self._lock:
            return {
                "monitoring": list(self._observers.keys()),
                "active": {
                    drive: observer.is_alive()
                    for drive, observer in self._observers.items()
                },
            }

    def stop_all(self) -> None:
        """Stop monitoring all drives."""
        with self._lock:
            drives = list(self._observers.keys())

        for drive in drives:
            self.stop_monitoring(drive)

        logger.info("Stopped all file monitoring")


# Global singleton instance
file_watcher_service = FileWatcherService()
