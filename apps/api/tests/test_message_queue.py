"""Tests for the message batch queue (SD-010)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.message_queue import (
    MessageQueueManager,
    QueuedMessage,
    SessionMessageQueue,
    get_message_queue_manager,
)


class TestQueuedMessage:
    """Test the QueuedMessage dataclass."""

    def test_create_queued_message(self):
        """Should create a queued message with all fields."""
        msg = QueuedMessage(
            id="msg-123",
            session_id="session-456",
            role="user",
            content="Hello",
            timestamp=datetime.now(UTC),
            extracted_entities=[{"name": "test", "type": "concept"}],
        )

        assert msg.id == "msg-123"
        assert msg.session_id == "session-456"
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert len(msg.extracted_entities) == 1

    def test_default_extracted_entities(self):
        """Should default extracted_entities to None."""
        msg = QueuedMessage(
            id="msg-123",
            session_id="session-456",
            role="user",
            content="Hello",
            timestamp=datetime.now(UTC),
        )

        assert msg.extracted_entities is None


class TestSessionMessageQueue:
    """Test the per-session message queue."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.add_all = MagicMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with batch config."""
        settings = MagicMock()
        settings.message_batch_size = 3
        settings.message_batch_timeout = 2.0
        return settings

    @pytest.mark.asyncio
    async def test_add_message_returns_id(self, mock_db_session, mock_settings):
        """Should return a message ID when adding a message."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            queue = SessionMessageQueue(session_id="session-123")
            message_id = await queue.add_message(mock_db_session, "user", "Hello")

            assert message_id is not None
            assert len(message_id) > 0

    @pytest.mark.asyncio
    async def test_add_message_queues_message(self, mock_db_session, mock_settings):
        """Should queue message without immediate flush."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            queue = SessionMessageQueue(session_id="session-123")
            await queue.add_message(mock_db_session, "user", "Hello")

            assert queue.pending_count == 1
            # Should not have committed yet (batch size is 3)
            mock_db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_message_flushes_at_batch_size(
        self, mock_db_session, mock_settings
    ):
        """Should flush when batch size is reached."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            queue = SessionMessageQueue(session_id="session-123")

            # Add 3 messages (batch_size is 3)
            await queue.add_message(mock_db_session, "user", "Message 1")
            await queue.add_message(mock_db_session, "assistant", "Message 2")
            await queue.add_message(mock_db_session, "user", "Message 3")

            # Should have flushed
            mock_db_session.add_all.assert_called_once()
            mock_db_session.commit.assert_called_once()
            assert queue.pending_count == 0

    @pytest.mark.asyncio
    async def test_flush_all_forces_flush(self, mock_db_session, mock_settings):
        """Should flush all messages immediately."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            queue = SessionMessageQueue(session_id="session-123")

            await queue.add_message(mock_db_session, "user", "Message 1")
            await queue.add_message(mock_db_session, "assistant", "Message 2")

            assert queue.pending_count == 2

            await queue.flush_all(mock_db_session)

            mock_db_session.add_all.assert_called_once()
            mock_db_session.commit.assert_called_once()
            assert queue.pending_count == 0

    @pytest.mark.asyncio
    async def test_flush_all_on_empty_queue(self, mock_db_session, mock_settings):
        """Should handle flush on empty queue gracefully."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            queue = SessionMessageQueue(session_id="session-123")

            await queue.flush_all(mock_db_session)

            mock_db_session.add_all.assert_not_called()
            mock_db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_includes_extracted_entities(
        self, mock_db_session, mock_settings
    ):
        """Should include extracted entities when flushing."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            queue = SessionMessageQueue(session_id="session-123")

            entities = [{"name": "PostgreSQL", "type": "technology"}]
            await queue.add_message(mock_db_session, "assistant", "Response", entities)

            await queue.flush_all(mock_db_session)

            # Check that add_all was called with a message containing entities
            call_args = mock_db_session.add_all.call_args
            messages = call_args[0][0]
            assert len(messages) == 1
            assert messages[0].extracted_entities == entities


class TestMessageQueueManager:
    """Test the message queue manager."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.add_all = MagicMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with batch config."""
        settings = MagicMock()
        settings.message_batch_size = 5
        settings.message_batch_timeout = 2.0
        return settings

    @pytest.mark.asyncio
    async def test_get_queue_creates_new_queue(self, mock_settings):
        """Should create a new queue for a session."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            manager = MessageQueueManager()
            queue = await manager.get_queue("session-123")

            assert queue is not None
            assert queue.session_id == "session-123"

    @pytest.mark.asyncio
    async def test_get_queue_returns_same_queue(self, mock_settings):
        """Should return the same queue for the same session."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            manager = MessageQueueManager()
            queue1 = await manager.get_queue("session-123")
            queue2 = await manager.get_queue("session-123")

            assert queue1 is queue2

    @pytest.mark.asyncio
    async def test_add_message(self, mock_db_session, mock_settings):
        """Should add message via queue manager."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            manager = MessageQueueManager()
            message_id = await manager.add_message(
                mock_db_session, "session-123", "user", "Hello"
            )

            assert message_id is not None
            stats = manager.get_stats()
            assert stats["active_sessions"] == 1
            assert stats["total_pending_messages"] == 1

    @pytest.mark.asyncio
    async def test_flush_session(self, mock_db_session, mock_settings):
        """Should flush a specific session's queue."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            manager = MessageQueueManager()
            await manager.add_message(mock_db_session, "session-123", "user", "Hello")
            await manager.add_message(mock_db_session, "session-456", "user", "World")

            await manager.flush_session(mock_db_session, "session-123")

            stats = manager.get_stats()
            assert stats["sessions"]["session-123"] == 0
            assert stats["sessions"]["session-456"] == 1

    @pytest.mark.asyncio
    async def test_remove_session(self, mock_db_session, mock_settings):
        """Should remove a session's queue after flushing."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            manager = MessageQueueManager()
            await manager.add_message(mock_db_session, "session-123", "user", "Hello")

            await manager.remove_session(mock_db_session, "session-123")

            stats = manager.get_stats()
            assert stats["active_sessions"] == 0
            assert "session-123" not in stats["sessions"]

    @pytest.mark.asyncio
    async def test_flush_all(self, mock_db_session, mock_settings):
        """Should flush all sessions' queues."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            manager = MessageQueueManager()
            await manager.add_message(mock_db_session, "session-123", "user", "Hello")
            await manager.add_message(mock_db_session, "session-456", "user", "World")

            await manager.flush_all(mock_db_session)

            stats = manager.get_stats()
            assert stats["total_pending_messages"] == 0

    def test_get_stats(self, mock_settings):
        """Should return correct statistics."""
        with patch("services.message_queue.get_settings", return_value=mock_settings):
            manager = MessageQueueManager()
            stats = manager.get_stats()

            assert "active_sessions" in stats
            assert "total_pending_messages" in stats
            assert "sessions" in stats
            assert stats["active_sessions"] == 0
            assert stats["total_pending_messages"] == 0


class TestGetMessageQueueManager:
    """Test the singleton getter."""

    def test_returns_manager_instance(self):
        """Should return a MessageQueueManager instance."""
        manager = get_message_queue_manager()
        assert isinstance(manager, MessageQueueManager)

    def test_returns_same_instance(self):
        """Should return the same instance on subsequent calls."""
        manager1 = get_message_queue_manager()
        manager2 = get_message_queue_manager()
        assert manager1 is manager2


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
