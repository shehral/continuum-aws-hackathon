"""Tests for the ingest router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestListProjects:
    """Tests for GET /projects endpoint."""

    @pytest.mark.asyncio
    async def test_list_projects_returns_list(self):
        """Should return list of available projects."""
        mock_projects = [
            {"dir": "project-1", "name": "project1", "files": 5, "path": "/path/1"},
            {"dir": "project-2", "name": "project2", "files": 3, "path": "/path/2"},
        ]

        mock_parser = MagicMock()
        mock_parser.get_available_projects = MagicMock(return_value=mock_projects)

        with (
            patch("routers.ingest.ClaudeLogParser", return_value=mock_parser),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from routers.ingest import list_available_projects

            result = await list_available_projects()

            assert len(result) == 2
            assert result[0]["name"] == "project1"

    @pytest.mark.asyncio
    async def test_list_projects_empty(self):
        """Should return empty list when no projects."""
        mock_parser = MagicMock()
        mock_parser.get_available_projects = MagicMock(return_value=[])

        with (
            patch("routers.ingest.ClaudeLogParser", return_value=mock_parser),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from routers.ingest import list_available_projects

            result = await list_available_projects()

            assert result == []


class TestPreviewIngestion:
    """Tests for GET /preview endpoint."""

    @pytest.mark.asyncio
    async def test_preview_returns_conversations(self):
        """Should return preview of conversations."""
        mock_previews = [
            {
                "file": "/path/to/file.jsonl",
                "project": "project1",
                "messages": 10,
                "preview": "Sample preview...",
            }
        ]

        mock_parser = MagicMock()
        mock_parser.preview_logs = AsyncMock(return_value=mock_previews)

        with (
            patch("routers.ingest.ClaudeLogParser", return_value=mock_parser),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from routers.ingest import preview_ingestion

            result = await preview_ingestion(project=None, exclude=None, limit=10)

            assert result.total_conversations == 1
            assert len(result.previews) == 1

    @pytest.mark.asyncio
    async def test_preview_with_project_filter(self):
        """Should filter by project."""
        mock_parser = MagicMock()
        mock_parser.preview_logs = AsyncMock(return_value=[])

        with (
            patch("routers.ingest.ClaudeLogParser", return_value=mock_parser),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from routers.ingest import preview_ingestion

            await preview_ingestion(project="myproject", exclude=None, limit=10)

            # Verify filter was passed to parser
            call_args = mock_parser.preview_logs.call_args
            assert call_args[1]["project_filter"] == "myproject"

    @pytest.mark.asyncio
    async def test_preview_with_exclude_filter(self):
        """Should exclude specified projects."""
        mock_parser = MagicMock()
        mock_parser.preview_logs = AsyncMock(return_value=[])

        with (
            patch("routers.ingest.ClaudeLogParser", return_value=mock_parser),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from routers.ingest import preview_ingestion

            await preview_ingestion(project=None, exclude="proj1,proj2", limit=10)

            call_args = mock_parser.preview_logs.call_args
            assert call_args[1]["exclude_projects"] == ["proj1", "proj2"]


class TestTriggerIngestion:
    """Tests for POST /trigger endpoint."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_trigger_ingestion_success(self, mock_db_session):
        """Should process files and extract decisions."""
        mock_conversations = [MagicMock(messages=[{"role": "user", "content": "test"}])]

        async def mock_parse_all(*args, **kwargs):
            yield "/path/file.jsonl", mock_conversations

        mock_parser = MagicMock()
        mock_parser.parse_all_logs = mock_parse_all

        mock_extractor = MagicMock()
        mock_extractor.extract_decisions = AsyncMock(return_value=[{"id": "1"}])
        mock_extractor.save_decision = AsyncMock(return_value="decision-id")

        with (
            patch("routers.ingest.ClaudeLogParser", return_value=mock_parser),
            patch("routers.ingest.DecisionExtractor", return_value=mock_extractor),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from routers.ingest import trigger_ingestion

            result = await trigger_ingestion(
                project=None, exclude=None, db=mock_db_session
            )

            assert result.status == "completed"
            assert result.processed >= 1

    @pytest.mark.asyncio
    async def test_trigger_ingestion_with_filters(self, mock_db_session):
        """Should apply project filters during ingestion."""

        async def mock_parse_all(*args, **kwargs):
            return
            yield

        mock_parser = MagicMock()
        mock_parser.parse_all_logs = mock_parse_all

        with (
            patch("routers.ingest.ClaudeLogParser", return_value=mock_parser),
            patch("routers.ingest.DecisionExtractor"),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from routers.ingest import trigger_ingestion

            result = await trigger_ingestion(
                project="myproject", exclude="exclude1", db=mock_db_session
            )

            assert result.status == "completed"


class TestIngestionStatus:
    """Tests for GET /status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Should return current ingestion status."""
        from routers.ingest import get_ingestion_status

        result = await get_ingestion_status()

        assert hasattr(result, "is_watching")
        assert hasattr(result, "files_processed")


class TestWatchEndpoints:
    """Tests for POST /watch/start and /watch/stop endpoints."""

    @pytest.mark.asyncio
    async def test_start_watching(self):
        """Should start file watcher."""
        mock_watcher = MagicMock()
        mock_watcher.is_running = False
        mock_watcher.start = MagicMock(return_value=True)

        with (
            patch("routers.ingest.get_file_watcher", return_value=mock_watcher),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from fastapi import BackgroundTasks

            from routers.ingest import start_watching

            bg_tasks = BackgroundTasks()
            result = await start_watching(bg_tasks)

            assert result["status"] == "watching started"

    @pytest.mark.asyncio
    async def test_start_watching_already_running(self):
        """Should return already watching when watcher is running."""
        mock_watcher = MagicMock()
        mock_watcher.is_running = True

        with (
            patch("routers.ingest.get_file_watcher", return_value=mock_watcher),
            patch("routers.ingest.get_settings") as mock_settings,
        ):
            mock_settings.return_value.claude_logs_path = "/logs"

            from fastapi import BackgroundTasks

            from routers.ingest import start_watching

            bg_tasks = BackgroundTasks()
            result = await start_watching(bg_tasks)

            assert result["status"] == "already watching"

    @pytest.mark.asyncio
    async def test_stop_watching(self):
        """Should stop file watcher."""
        mock_watcher = MagicMock()
        mock_watcher.is_running = True
        mock_watcher.stop = MagicMock()

        with patch("routers.ingest.get_file_watcher", return_value=mock_watcher):
            from routers.ingest import stop_watching

            result = await stop_watching()

            assert result["status"] == "watching stopped"
            mock_watcher.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_watching_not_running(self):
        """Should return not watching when watcher isn't running."""
        mock_watcher = MagicMock()
        mock_watcher.is_running = False

        with patch("routers.ingest.get_file_watcher", return_value=mock_watcher):
            from routers.ingest import stop_watching

            result = await stop_watching()

            assert result["status"] == "not watching"
