"""Tests for the capture router."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestStartCaptureSession:
    """Tests for POST /sessions endpoint."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        # Mock refresh to set timestamp fields
        async def mock_refresh(obj):
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = datetime.now(UTC)
            if not hasattr(obj, "updated_at") or obj.updated_at is None:
                obj.updated_at = datetime.now(UTC)

        session.refresh = mock_refresh
        return session

    @pytest.mark.asyncio
    async def test_start_session_creates_new_session(self, mock_db_session):
        """Should create a new capture session."""
        with patch("routers.capture.get_db", return_value=mock_db_session):
            from routers.capture import start_capture_session

            result = await start_capture_session(
                db=mock_db_session, user_id="test-user"
            )

            assert result.id is not None
            assert result.status == "active"
            mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_session_uses_anonymous_user(self, mock_db_session):
        """Should use anonymous user when no auth provided."""
        with patch("routers.capture.get_db", return_value=mock_db_session):
            from routers.capture import start_capture_session

            result = await start_capture_session(
                db=mock_db_session, user_id="anonymous"
            )

            assert result.id is not None


class TestGetCaptureSession:
    """Tests for GET /sessions/{session_id} endpoint."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_session_found(self, mock_db_session):
        """Should return session when found."""
        session_id = str(uuid4())

        # Mock session query
        mock_session_obj = MagicMock()
        mock_session_obj.id = session_id
        mock_session_obj.status = MagicMock()
        mock_session_obj.status.value = "active"
        mock_session_obj.created_at = datetime.now(UTC)
        mock_session_obj.updated_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_session_obj)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock messages query
        mock_messages_result = MagicMock()
        mock_messages_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_result
            else:
                return mock_messages_result

        mock_db_session.execute = mock_execute

        with patch("routers.capture.get_db", return_value=mock_db_session):
            from routers.capture import get_capture_session

            result = await get_capture_session(session_id, db=mock_db_session)

            assert result.id == session_id
            assert result.status == "active"

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, mock_db_session):
        """Should raise 404 when session not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("routers.capture.get_db", return_value=mock_db_session):
            from fastapi import HTTPException

            from routers.capture import get_capture_session

            with pytest.raises(HTTPException) as exc_info:
                await get_capture_session("nonexistent-id", db=mock_db_session)
            assert exc_info.value.status_code == 404


class TestSendCaptureMessage:
    """Tests for POST /sessions/{session_id}/messages endpoint."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_send_message_to_active_session(self, mock_db_session):
        """Should process message and return AI response."""
        session_id = str(uuid4())

        # Mock active session
        from models.postgres import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = session_id
        mock_session_obj.status = SessionStatus.ACTIVE

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none = MagicMock(
            return_value=mock_session_obj
        )

        mock_messages_result = MagicMock()
        mock_messages_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_session_result
            else:
                return mock_messages_result

        mock_db_session.execute = mock_execute

        # Mock AI message creation
        mock_ai_message = MagicMock()
        mock_ai_message.id = str(uuid4())
        mock_ai_message.role = "assistant"
        mock_ai_message.content = "AI response"
        mock_ai_message.timestamp = datetime.now(UTC)
        mock_ai_message.extracted_entities = []

        async def mock_refresh(obj):
            if hasattr(obj, "content"):
                obj.id = mock_ai_message.id
                obj.role = mock_ai_message.role
                obj.content = mock_ai_message.content
                obj.timestamp = mock_ai_message.timestamp
                obj.extracted_entities = mock_ai_message.extracted_entities

        mock_db_session.refresh = mock_refresh

        mock_interview_agent = MagicMock()
        mock_interview_agent.process_message = AsyncMock(
            return_value=("AI response", [])
        )

        with (
            patch("routers.capture.get_db", return_value=mock_db_session),
            patch("routers.capture.InterviewAgent", return_value=mock_interview_agent),
        ):
            from routers.capture import send_capture_message

            result = await send_capture_message(
                session_id, {"content": "User message"}, db=mock_db_session
            )

            assert result.role == "assistant"
            assert result.content == "AI response"

    @pytest.mark.asyncio
    async def test_send_message_to_inactive_session(self, mock_db_session):
        """Should reject message to inactive session."""
        session_id = str(uuid4())

        from models.postgres import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = session_id
        mock_session_obj.status = SessionStatus.COMPLETED

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_session_obj)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("routers.capture.get_db", return_value=mock_db_session):
            from fastapi import HTTPException

            from routers.capture import send_capture_message

            with pytest.raises(HTTPException) as exc_info:
                await send_capture_message(
                    session_id, {"content": "test"}, db=mock_db_session
                )
            assert exc_info.value.status_code == 400


class TestCompleteCaptureSession:
    """Tests for POST /sessions/{session_id}/complete endpoint."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_complete_session_success(self, mock_db_session):
        """Should complete session and save decision."""
        session_id = str(uuid4())

        from models.postgres import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = session_id
        mock_session_obj.status = SessionStatus.ACTIVE
        mock_session_obj.created_at = datetime.now(UTC)
        mock_session_obj.updated_at = datetime.now(UTC)

        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none = MagicMock(
            return_value=mock_session_obj
        )

        # Mock messages
        mock_message = MagicMock()
        mock_message.id = str(uuid4())
        mock_message.role = "user"
        mock_message.content = "Test message"
        mock_message.timestamp = datetime.now(UTC)
        mock_message.extracted_entities = []

        mock_messages_result = MagicMock()
        mock_messages_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[mock_message]))
        )

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_session_result
            else:
                return mock_messages_result

        mock_db_session.execute = mock_execute

        mock_interview_agent = MagicMock()
        mock_interview_agent.synthesize_decision = AsyncMock(
            return_value={
                "trigger": "Test trigger",
                "context": "Test context",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Because",
                "confidence": 0.9,
            }
        )

        mock_extractor = MagicMock()
        mock_extractor.save_decision = AsyncMock(return_value="decision-id")

        with (
            patch("routers.capture.get_db", return_value=mock_db_session),
            patch("routers.capture.InterviewAgent", return_value=mock_interview_agent),
            patch("services.extractor.DecisionExtractor", return_value=mock_extractor),
        ):
            from routers.capture import complete_capture_session

            result = await complete_capture_session(session_id, db=mock_db_session)

            assert result.status == "completed"
            mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_complete_already_completed_session(self, mock_db_session):
        """Should reject completing already completed session."""
        session_id = str(uuid4())

        from models.postgres import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = session_id
        mock_session_obj.status = SessionStatus.COMPLETED

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_session_obj)
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with patch("routers.capture.get_db", return_value=mock_db_session):
            from fastapi import HTTPException

            from routers.capture import complete_capture_session

            with pytest.raises(HTTPException) as exc_info:
                await complete_capture_session(session_id, db=mock_db_session)
            assert exc_info.value.status_code == 400
