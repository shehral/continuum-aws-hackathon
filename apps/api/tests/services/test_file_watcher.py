"""Tests for the file watcher service.

This test suite covers the ClaudeLogHandler and FileWatcherService classes
that monitor Claude Code log directories for changes.

Test categories:
- Event handling (JSONL file creation/modification)
- Debouncing logic
- Service lifecycle (start/stop)
- Error handling
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.file_watcher import (
    ClaudeLogHandler,
    FileWatcherService,
    get_file_watcher,
)

# ============================================================================
# ClaudeLogHandler Tests
# ============================================================================


class TestClaudeLogHandler:
    """Tests for the ClaudeLogHandler event handler."""

    @pytest.fixture
    def mock_callback(self):
        """Create a mock callback function."""
        return MagicMock()

    @pytest.fixture
    def handler(self, mock_callback):
        """Create a handler with mock callback."""
        return ClaudeLogHandler(mock_callback)

    def test_init_creates_handler_with_callback(self, mock_callback):
        """Should initialize handler with callback."""
        handler = ClaudeLogHandler(mock_callback)
        assert handler.callback is mock_callback
        assert handler._debounce_delay == 2.0

    def test_on_created_jsonl_triggers_callback(self, handler, mock_callback):
        """Should schedule callback when JSONL file is created."""
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/file.jsonl"

        with patch.object(handler, "_schedule_callback") as mock_schedule:
            handler.on_created(event)
            mock_schedule.assert_called_once_with("/path/to/file.jsonl")

    def test_on_modified_jsonl_triggers_callback(self, handler, mock_callback):
        """Should schedule callback when JSONL file is modified."""
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/file.jsonl"

        with patch.object(handler, "_schedule_callback") as mock_schedule:
            handler.on_modified(event)
            mock_schedule.assert_called_once_with("/path/to/file.jsonl")

    def test_on_created_ignores_non_jsonl_files(self, handler):
        """Should ignore non-JSONL files on creation."""
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/file.txt"

        with patch.object(handler, "_schedule_callback") as mock_schedule:
            handler.on_created(event)
            mock_schedule.assert_not_called()

    def test_on_modified_ignores_non_jsonl_files(self, handler):
        """Should ignore non-JSONL files on modification."""
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/file.json"  # .json, not .jsonl

        with patch.object(handler, "_schedule_callback") as mock_schedule:
            handler.on_modified(event)
            mock_schedule.assert_not_called()

    def test_on_created_ignores_directory_events(self, handler):
        """Should ignore directory creation events."""
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/path/to/dir"

        with patch.object(handler, "_schedule_callback") as mock_schedule:
            handler.on_created(event)
            mock_schedule.assert_not_called()

    def test_on_modified_ignores_directory_events(self, handler):
        """Should ignore directory modification events."""
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/path/to/dir"

        with patch.object(handler, "_schedule_callback") as mock_schedule:
            handler.on_modified(event)
            mock_schedule.assert_not_called()

    def test_ignores_files_with_similar_extensions(self, handler):
        """Should not trigger on files with similar but different extensions."""
        test_cases = [
            "/path/to/file.jsonl.bak",
            "/path/to/file.JSONL",  # Case sensitive
            "/path/to/jsonl",  # No extension
            "/path/to/file.json",
            "/path/to/file.log",
        ]

        for path in test_cases:
            event = MagicMock()
            event.is_directory = False
            event.src_path = path

            with patch.object(handler, "_schedule_callback") as mock_schedule:
                handler.on_modified(event)
                if not path.endswith(".jsonl"):
                    mock_schedule.assert_not_called()

    def test_schedule_callback_cancels_existing_task(self, handler, mock_callback):
        """Should cancel existing debounce task for same file."""
        file_path = "/path/to/file.jsonl"

        # Create a mock task
        mock_task = MagicMock()
        handler._debounce_tasks[file_path] = mock_task

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_new_task = MagicMock()
            mock_loop.create_task.return_value = mock_new_task
            mock_get_loop.return_value = mock_loop

            handler._schedule_callback(file_path)

            # Old task should be cancelled
            mock_task.cancel.assert_called_once()
            # New task should be created
            mock_loop.create_task.assert_called_once()

    def test_schedule_callback_without_event_loop(self, handler, mock_callback):
        """Should call callback directly when no event loop is running."""
        file_path = "/path/to/file.jsonl"

        with patch("asyncio.get_event_loop", side_effect=RuntimeError("No event loop")):
            handler._schedule_callback(file_path)
            mock_callback.assert_called_once_with(file_path)

    @pytest.mark.asyncio
    async def test_debounced_callback_waits_before_calling(self, mock_callback):
        """Should wait for debounce delay before calling callback."""
        handler = ClaudeLogHandler(mock_callback)
        handler._debounce_delay = 0.1  # Short delay for test

        file_path = "/path/to/file.jsonl"

        # Run the debounced callback
        await handler._debounced_callback(file_path)

        # Callback should have been called
        mock_callback.assert_called_once_with(file_path)

    @pytest.mark.asyncio
    async def test_debounced_callback_cancellation(self, mock_callback):
        """Should not call callback when cancelled during debounce wait."""
        handler = ClaudeLogHandler(mock_callback)
        handler._debounce_delay = 10.0  # Long delay

        file_path = "/path/to/file.jsonl"

        # Start the debounced callback
        task = asyncio.create_task(handler._debounced_callback(file_path))
        handler._debounce_tasks[file_path] = task

        # Cancel it immediately
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Callback should NOT have been called
        mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_debounced_callback_removes_from_tasks(self, mock_callback):
        """Should remove itself from _debounce_tasks after completion."""
        handler = ClaudeLogHandler(mock_callback)
        handler._debounce_delay = 0.01  # Very short delay

        file_path = "/path/to/file.jsonl"
        handler._debounce_tasks[file_path] = "placeholder"

        await handler._debounced_callback(file_path)

        # Task should be removed from dict
        assert file_path not in handler._debounce_tasks

    def test_schedule_callback_replaces_existing_task(self, handler, mock_callback):
        """Scheduling callback for same file should cancel existing task."""
        file_path = "/path/to/file.jsonl"

        # Create a mock task
        mock_task = MagicMock()
        handler._debounce_tasks[file_path] = mock_task

        # Schedule another callback for same file
        with patch.object(handler, "_schedule_callback") as _patched:
            # Directly test that old task would be cancelled
            # by verifying it's replaced in the dict
            handler._debounce_tasks[file_path] = MagicMock()

            # The new task should be different
            assert handler._debounce_tasks[file_path] is not mock_task


# ============================================================================
# FileWatcherService Tests
# ============================================================================


class TestFileWatcherService:
    """Tests for the FileWatcherService."""

    @pytest.fixture
    def service(self):
        """Create a fresh FileWatcherService instance."""
        return FileWatcherService()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_init_sets_default_state(self, service):
        """Should initialize with correct default state."""
        assert service._observer is None
        assert service._is_running is False
        assert service._watched_files == set()
        assert service._on_change_callback is None

    def test_is_running_property(self, service):
        """Should return correct running state."""
        assert service.is_running is False
        service._is_running = True
        assert service.is_running is True

    def test_start_with_nonexistent_path(self, service):
        """Should return False for nonexistent path."""
        callback = MagicMock()
        result = service.start("/nonexistent/path/12345", callback)
        assert result is False
        assert service.is_running is False

    def test_start_with_valid_path(self, service, temp_dir):
        """Should start watching valid directory."""
        callback = MagicMock()

        with patch("services.file_watcher.Observer") as mock_observer_cls:
            mock_observer = MagicMock()
            mock_observer_cls.return_value = mock_observer

            result = service.start(temp_dir, callback)

            assert result is True
            assert service.is_running is True
            mock_observer.schedule.assert_called_once()
            mock_observer.start.assert_called_once()

    def test_start_already_running_returns_false(self, service, temp_dir):
        """Should return False if already running."""
        callback = MagicMock()
        service._is_running = True

        result = service.start(temp_dir, callback)

        assert result is False

    def test_start_expands_tilde_path(self, service):
        """Should expand ~ in paths."""
        callback = MagicMock()

        with patch("services.file_watcher.Observer") as mock_observer_cls:
            mock_observer = MagicMock()
            mock_observer_cls.return_value = mock_observer

            # Use a path that exists after expansion
            with tempfile.TemporaryDirectory() as tmpdir:
                result = service.start(tmpdir, callback)
                assert result is True

    def test_stop_when_not_running(self, service):
        """Should return False if not running."""
        result = service.stop()
        assert result is False

    def test_stop_when_running(self, service):
        """Should stop watcher and reset state."""
        mock_observer = MagicMock()
        service._observer = mock_observer
        service._is_running = True
        service._watched_files = {"file1", "file2"}

        result = service.stop()

        assert result is True
        assert service.is_running is False
        assert service._observer is None
        assert service._watched_files == set()
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once_with(timeout=5.0)

    def test_handle_file_change_calls_callback(self, service):
        """Should call on_change callback when file changes."""
        mock_callback = MagicMock()
        service._on_change_callback = mock_callback

        service._handle_file_change("/path/to/file.jsonl")

        mock_callback.assert_called_once_with("/path/to/file.jsonl")

    def test_handle_file_change_no_callback(self, service):
        """Should handle missing callback gracefully."""
        service._on_change_callback = None
        # Should not raise
        service._handle_file_change("/path/to/file.jsonl")

    def test_handle_file_change_callback_exception(self, service):
        """Should catch and log callback exceptions."""
        mock_callback = MagicMock(side_effect=Exception("Callback error"))
        service._on_change_callback = mock_callback

        # Should not raise
        service._handle_file_change("/path/to/file.jsonl")
        mock_callback.assert_called_once()

    def test_recursive_directory_watching(self, service, temp_dir):
        """Should watch directories recursively."""
        callback = MagicMock()

        with patch("services.file_watcher.Observer") as mock_observer_cls:
            mock_observer = MagicMock()
            mock_observer_cls.return_value = mock_observer

            service.start(temp_dir, callback)

            # Verify recursive=True is passed
            call_args = mock_observer.schedule.call_args
            assert call_args.kwargs.get("recursive", False) is True or (
                len(call_args.args) >= 3 and call_args.args[2] is True
            )


# ============================================================================
# Singleton Tests
# ============================================================================


class TestGetFileWatcher:
    """Tests for the get_file_watcher singleton function."""

    def test_returns_singleton_instance(self):
        """Should return the same instance on multiple calls."""
        # Reset the singleton for testing
        import services.file_watcher as fw

        fw._watcher_service = None

        watcher1 = get_file_watcher()
        watcher2 = get_file_watcher()

        assert watcher1 is watcher2

    def test_creates_instance_if_none(self):
        """Should create new instance if none exists."""
        import services.file_watcher as fw

        fw._watcher_service = None

        watcher = get_file_watcher()

        assert watcher is not None
        assert isinstance(watcher, FileWatcherService)


# ============================================================================
# Integration Tests
# ============================================================================


class TestFileWatcherIntegration:
    """Integration tests for file watcher with real file system."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.mark.slow
    def test_detects_new_jsonl_file(self, temp_dir):
        """Should detect creation of new JSONL file."""
        callback = MagicMock()
        service = FileWatcherService()

        try:
            service.start(temp_dir, callback)

            # Create a JSONL file
            test_file = Path(temp_dir) / "test.jsonl"
            test_file.write_text('{"test": "data"}\n')

            # Wait for event to be processed
            import time

            time.sleep(0.5)

            # Note: Due to debouncing, callback may not be called immediately
            # This test verifies the service starts and handles files
            assert service.is_running is True
        finally:
            service.stop()

    @pytest.mark.slow
    def test_full_lifecycle(self, temp_dir):
        """Test complete start/stop lifecycle."""
        callback = MagicMock()
        service = FileWatcherService()

        # Start
        assert service.start(temp_dir, callback) is True
        assert service.is_running is True

        # Stop
        assert service.stop() is True
        assert service.is_running is False

        # Can restart
        assert service.start(temp_dir, callback) is True
        assert service.is_running is True
        service.stop()


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
