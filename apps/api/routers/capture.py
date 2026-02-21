"""Capture session endpoints with user isolation and WebSocket security.

All capture sessions are isolated by user. Users can only access their own sessions.
Anonymous users can create and access sessions, but their data is ephemeral and
not linked to any authenticated account.

SEC-012: WebSocket input validation and rate limiting.
SEC-009: Per-user rate limiting for LLM calls.
SD-010: Batch message storage for improved performance.
"""

import time
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.interview import InterviewAgent
from db.postgres import get_db
from models.postgres import CaptureMessage, CaptureSession, SessionStatus
from models.schemas import (
    CaptureMessage as CaptureMessageSchema,
)
from models.schemas import (
    CaptureSession as CaptureSessionSchema,
)
from models.schemas import (
    Entity,
)
from routers.auth import get_current_user_id
from services.message_queue import get_message_queue_manager
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# SEC-012: WebSocket security constants
MAX_MESSAGE_SIZE = 10000  # 10KB max message size
MAX_HISTORY_SIZE = 50  # Maximum messages in history
MAX_MESSAGES_PER_MINUTE = 20  # Rate limit for WebSocket messages
WEBSOCKET_RATE_WINDOW = 60  # Window in seconds


class WebSocketRateLimiter:
    """Simple in-memory rate limiter for WebSocket messages (SEC-012).

    Uses a sliding window to limit messages per session.
    """

    def __init__(
        self,
        max_messages: int = MAX_MESSAGES_PER_MINUTE,
        window: int = WEBSOCKET_RATE_WINDOW,
    ):
        self.max_messages = max_messages
        self.window = window
        self.timestamps: list[float] = []

    def check(self) -> bool:
        """Check if a message can be sent. Returns True if allowed."""
        now = time.time()
        window_start = now - self.window

        # Remove old timestamps
        self.timestamps = [t for t in self.timestamps if t > window_start]

        if len(self.timestamps) >= self.max_messages:
            return False

        self.timestamps.append(now)
        return True

    def get_retry_after(self) -> float:
        """Get seconds until the oldest message expires from the window."""
        if not self.timestamps:
            return 0
        now = time.time()
        oldest = min(self.timestamps)
        return max(0, oldest + self.window - now)


def validate_websocket_message(data: Any) -> tuple[bool, str]:
    """Validate WebSocket message format and size (SEC-012).

    Args:
        data: The parsed JSON data from the WebSocket

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check if data is a dict
    if not isinstance(data, dict):
        return False, "Message must be a JSON object"

    # Check for required 'content' field
    if "content" not in data:
        return False, "Message must contain 'content' field"

    content = data.get("content", "")

    # Check if content is a string
    if not isinstance(content, str):
        return False, "'content' must be a string"

    # Check message size
    if len(content) > MAX_MESSAGE_SIZE:
        return False, f"Message exceeds maximum size of {MAX_MESSAGE_SIZE} characters"

    # Check for empty content
    if not content.strip():
        return False, "Message content cannot be empty"

    return True, ""


async def _verify_session_ownership(
    db: AsyncSession,
    session_id: str,
    user_id: str,
) -> CaptureSession:
    """Verify the user owns the session and return it.

    Args:
        db: Database session
        session_id: The session ID to check
        user_id: The user ID who should own the session

    Returns:
        The CaptureSession if found and owned by user

    Raises:
        HTTPException 404 if session not found or not owned by user
    """
    result = await db.execute(
        select(CaptureSession).where(
            CaptureSession.id == session_id,
            CaptureSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        # Don't reveal whether session exists but belongs to another user
        # Always return generic "not found" for security
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@router.post("/sessions", response_model=CaptureSessionSchema)
async def start_capture_session(
    project_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Start a new capture session.

    Creates a new capture session linked to the current user.
    Anonymous users can create sessions, but they won't persist across auth.
    """
    session = CaptureSession(
        id=str(uuid4()),
        user_id=user_id,
        status=SessionStatus.ACTIVE,
        project_name=project_name,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(f"Created capture session {session.id} for user")

    return CaptureSessionSchema(
        id=session.id,
        status=session.status.value,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[],
    )


@router.get("/sessions/{session_id}", response_model=CaptureSessionSchema)
async def get_capture_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Get a capture session by ID.

    Users can only access their own sessions. Returns 404 if session
    doesn't exist or belongs to another user.
    """
    session = await _verify_session_ownership(db, session_id, user_id)

    # Get messages
    result = await db.execute(
        select(CaptureMessage)
        .where(CaptureMessage.session_id == session_id)
        .order_by(CaptureMessage.timestamp)
    )
    messages = result.scalars().all()

    return CaptureSessionSchema(
        id=session.id,
        status=session.status.value,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            CaptureMessageSchema(
                id=m.id,
                role=m.role,
                content=m.content,
                timestamp=m.timestamp,
                extracted_entities=[Entity(**e) for e in (m.extracted_entities or [])],
            )
            for m in messages
        ],
    )


@router.post("/sessions/{session_id}/messages", response_model=CaptureMessageSchema)
async def send_capture_message(
    session_id: str,
    content: dict,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Send a message in a capture session and get AI response.

    Users can only send messages to their own sessions.
    SD-010: Messages are batched for improved database performance.
    """
    # Verify session ownership and get session
    session = await _verify_session_ownership(db, session_id, user_id)

    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Session is not active")

    # Get message queue manager (SD-010)
    queue_manager = get_message_queue_manager()

    # Save user message via batch queue (SD-010)
    await queue_manager.add_message(
        db=db,
        session_id=session_id,
        role="user",
        content=content.get("content", ""),
    )

    # Get conversation history
    result = await db.execute(
        select(CaptureMessage)
        .where(CaptureMessage.session_id == session_id)
        .order_by(CaptureMessage.timestamp)
    )
    history = result.scalars().all()

    # Generate AI response using interview agent with per-user rate limiting (SEC-009)
    interview_agent = InterviewAgent(user_id=user_id)
    response_content, extracted_entities = await interview_agent.process_message(
        user_message=content.get("content", ""),
        history=[{"role": m.role, "content": m.content} for m in history],
    )

    # Save AI response via batch queue (SD-010)
    ai_message_id = await queue_manager.add_message(
        db=db,
        session_id=session_id,
        role="assistant",
        content=response_content,
        extracted_entities=[e.model_dump() for e in extracted_entities],
    )

    return CaptureMessageSchema(
        id=ai_message_id,
        role="assistant",
        content=response_content,
        timestamp=datetime.now(UTC),
        extracted_entities=extracted_entities,
    )


@router.post("/sessions/{session_id}/complete", response_model=CaptureSessionSchema)
async def complete_capture_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Complete a capture session and save the decision to the graph.

    Users can only complete their own sessions. The resulting decision
    will be linked to their user ID for multi-tenant isolation.
    SD-010: Flushes any pending messages before completing.
    """
    # Verify session ownership
    session = await _verify_session_ownership(db, session_id, user_id)

    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Session is not active")

    # Flush any pending messages (SD-010)
    queue_manager = get_message_queue_manager()
    await queue_manager.flush_session(db, session_id)

    # Update session status
    session.status = SessionStatus.COMPLETED
    session.completed_at = datetime.now(UTC)

    # Get all messages
    result = await db.execute(
        select(CaptureMessage)
        .where(CaptureMessage.session_id == session_id)
        .order_by(CaptureMessage.timestamp)
    )
    messages = result.scalars().all()

    # Extract decision from messages and save to Neo4j with per-user rate limiting (SEC-009)
    interview_agent = InterviewAgent(user_id=user_id)
    history = [{"role": m.role, "content": m.content} for m in messages]

    decision_data = await interview_agent.synthesize_decision(history)
    logger.debug(f"Synthesized decision for session {session_id}")

    if decision_data and decision_data.get("trigger"):
        from models.schemas import DecisionCreate
        from services.extractor import DecisionExtractor

        extractor = DecisionExtractor()
        decision = DecisionCreate(
            trigger=decision_data.get("trigger", ""),
            context=decision_data.get("context", ""),
            options=decision_data.get("options", []),
            decision=decision_data.get("decision", ""),
            rationale=decision_data.get("rationale", ""),
            confidence=decision_data.get("confidence", 0.8),
            source="interview",  # Tag as human-captured via interview
            project_name=session.project_name,
        )
        # Pass user_id for multi-tenant isolation and project_name
        decision_id = await extractor.save_decision(
            decision,
            source="interview",
            user_id=user_id,
            project_name=session.project_name
        )
        logger.info(
            f"Decision saved with ID: {decision_id} for session {session_id} (source: interview)"
        )
    else:
        logger.warning(
            f"No valid decision to save for session {session_id} - missing trigger or empty data"
        )

    await db.commit()
    await db.refresh(session)

    # Clean up the session queue (SD-010)
    await queue_manager.remove_session(db, session_id)

    return CaptureSessionSchema(
        id=session.id,
        status=session.status.value,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            CaptureMessageSchema(
                id=m.id,
                role=m.role,
                content=m.content,
                timestamp=m.timestamp,
                extracted_entities=[Entity(**e) for e in (m.extracted_entities or [])],
            )
            for m in messages
        ],
    )


@router.websocket("/sessions/{session_id}/ws")
async def capture_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time capture sessions with input validation (SEC-012).

    Security features:
    - Message size validation (max 10KB)
    - Message format validation
    - Rate limiting (max 20 messages/minute)
    - History size limit (max 50 messages)

    Note: WebSocket authentication is complex and typically requires
    passing tokens in the initial connection or first message.
    For now, this endpoint operates without strict user verification,
    but the session_id itself provides some isolation.

    TODO: Implement WebSocket authentication via:
    - Query parameter token: ws://host/sessions/{id}/ws?token=...
    - First message authentication handshake
    - Cookie-based authentication if same-origin
    """
    await websocket.accept()

    # SEC-009: Use anonymous user_id for WebSocket (until auth is implemented)
    # TODO: Extract user_id from WebSocket query params or first message
    user_id = "anonymous"

    interview_agent = InterviewAgent(user_id=user_id)
    history: list[dict] = []
    rate_limiter = WebSocketRateLimiter()

    try:
        while True:
            try:
                # Receive and parse message
                data = await websocket.receive_json()
            except Exception as parse_error:
                logger.warning(f"WebSocket parse error: {type(parse_error).__name__}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": "Invalid JSON format",
                        "code": "INVALID_JSON",
                    }
                )
                continue

            # SEC-012: Validate message format and size
            is_valid, error_message = validate_websocket_message(data)
            if not is_valid:
                logger.warning(f"WebSocket validation failed: {error_message}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": error_message,
                        "code": "VALIDATION_ERROR",
                    }
                )
                continue

            # SEC-012: Check rate limit
            if not rate_limiter.check():
                retry_after = rate_limiter.get_retry_after()
                logger.warning(
                    f"WebSocket rate limit exceeded for session {session_id}"
                )
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": f"Rate limit exceeded. Please wait {retry_after:.0f} seconds.",
                        "code": "RATE_LIMITED",
                        "retry_after": retry_after,
                    }
                )
                continue

            user_message = data.get("content", "")

            # SEC-012: Enforce history size limit
            if len(history) >= MAX_HISTORY_SIZE:
                # Trim oldest messages, keeping recent context
                history = history[-(MAX_HISTORY_SIZE - 2) :]
                logger.info(
                    f"Trimmed history for session {session_id} (exceeded {MAX_HISTORY_SIZE} messages)"
                )

            # Stream response
            full_response = ""
            try:
                async for chunk, entities in interview_agent.stream_response(
                    user_message, history
                ):
                    full_response += chunk
                    await websocket.send_json(
                        {
                            "type": "chunk",
                            "content": chunk,
                            "entities": [e.model_dump() for e in entities],
                        }
                    )
            except Exception as llm_error:
                logger.error(f"LLM error in WebSocket: {type(llm_error).__name__}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": "Failed to generate response. Please try again.",
                        "code": "LLM_ERROR",
                    }
                )
                continue

            # Send completion
            await websocket.send_json({"type": "complete"})

            # Update history
            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": full_response})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(
            f"WebSocket error for session {session_id}: {type(e).__name__}: {e}"
        )
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass  # Connection may already be closed
