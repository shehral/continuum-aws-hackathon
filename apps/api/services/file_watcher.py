"""File watcher service for monitoring Claude Code logs."""

import asyncio
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from utils.logging import get_logger

logger = get_logger(__name__)


class ClaudeLogHandler(FileSystemEventHandler):
    """Handle file system events for Claude log files."""

    def __init__(self, callback: Callable[[str], None]):
        """Initialize with a callback for new/modified files.

        Args:
            callback: Function to call with file path when JSONL file changes
        """
        self.callback = callback
        self._debounce_tasks: dict[str, asyncio.Task] = {}
        self._debounce_delay = 2.0  # Wait 2 seconds after last write

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return
        if event.src_path.endswith(".jsonl"):
            self._schedule_callback(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        if event.src_path.endswith(".jsonl"):
            self._schedule_callback(event.src_path)

    def _schedule_callback(self, file_path: str) -> None:
        """Schedule a debounced callback for the file."""
        # Cancel any existing task for this file
        if file_path in self._debounce_tasks:
            self._debounce_tasks[file_path].cancel()

        # Schedule new callback
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(self._debounced_callback(file_path))
            self._debounce_tasks[file_path] = task
        except RuntimeError:
            # No event loop running, call directly
            self.callback(file_path)

    async def _debounced_callback(self, file_path: str) -> None:
        """Wait for debounce delay then call the callback."""
        try:
            await asyncio.sleep(self._debounce_delay)
            self.callback(file_path)
        except asyncio.CancelledError:
            pass
        finally:
            self._debounce_tasks.pop(file_path, None)


class FileWatcherService:
    """Service for watching Claude Code log directories."""

    def __init__(self):
        self._observer: Optional[Observer] = None
        self._is_running = False
        self._watched_files: set[str] = set()
        self._on_change_callback: Optional[Callable[[str], None]] = None

    @property
    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._is_running

    def start(
        self,
        logs_path: str,
        on_change: Callable[[str], None],
    ) -> bool:
        """Start watching the logs directory.

        Args:
            logs_path: Path to Claude logs directory (e.g., ~/.claude/projects)
            on_change: Callback function when a file changes

        Returns:
            True if started successfully, False otherwise
        """
        if self._is_running:
            logger.warning("File watcher is already running")
            return False

        path = Path(logs_path).expanduser()
        if not path.exists():
            logger.error(f"Logs path does not exist: {path}")
            return False

        self._on_change_callback = on_change
        handler = ClaudeLogHandler(self._handle_file_change)

        self._observer = Observer()
        self._observer.schedule(handler, str(path), recursive=True)
        self._observer.start()
        self._is_running = True

        logger.info(f"Started watching: {path}")
        return True

    def stop(self) -> bool:
        """Stop the file watcher.

        Returns:
            True if stopped successfully, False if wasn't running
        """
        if not self._is_running or not self._observer:
            logger.warning("File watcher is not running")
            return False

        self._observer.stop()
        self._observer.join(timeout=5.0)
        self._observer = None
        self._is_running = False
        self._watched_files.clear()

        logger.info("Stopped file watcher")
        return True

    def _handle_file_change(self, file_path: str) -> None:
        """Handle a file change event."""
        logger.info(f"File changed: {file_path}")

        if self._on_change_callback:
            try:
                self._on_change_callback(file_path)
            except Exception as e:
                logger.error(f"Error in file change callback: {e}")


# Singleton instance
_watcher_service: Optional[FileWatcherService] = None


def get_file_watcher() -> FileWatcherService:
    """Get the file watcher service singleton."""
    global _watcher_service
    if _watcher_service is None:
        _watcher_service = FileWatcherService()
    return _watcher_service
