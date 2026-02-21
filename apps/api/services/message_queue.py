"""Message batch queue for capture sessions (SD-010).

Batches message inserts instead of individual writes to reduce database load.
The queue flushes when either:
- N messages are queued (configurable via MESSAGE_BATCH_SIZE)
- Timeout expires (configurable via MESSAGE_BATCH_TIMEOUT)

Features:
- Async-safe with locks for concurrent access
- Automatic flush on timeout
- Graceful degradation on errors
- Session-scoped batching
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.postgres import CaptureMessage
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class QueuedMessage:
    """A message waiting to be persisted."""

    id: str
    session_id: str
    role: str
    content: str
    timestamp: datetime
    extracted_entities: list[dict] | None = None


@dataclass
class SessionMessageQueue:
    """Per-session message queue with batch flushing (SD-010).

    Queues messages for a single capture session and flushes them
    in batches to reduce database round trips.
    """

    session_id: str
    messages: list[QueuedMessage] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _flush_task: asyncio.Task | None = field(default=None, repr=False)
    _settings: Any = field(default=None, repr=False)

    def __post_init__(self):
        self._settings = get_settings()

    async def add_message(
        self,
        db: AsyncSession,
        role: str,
        content: str,
        extracted_entities: list[dict] | None = None,
    ) -> str:
        """Add a message to the queue.

        Args:
            db: Database session for flushing
            role: Message role ('user' or 'assistant')
            content: Message content
            extracted_entities: Optional extracted entities

        Returns:
            Message ID
        """
        message_id = str(uuid4())
        message = QueuedMessage(
            id=message_id,
            session_id=self.session_id,
            role=role,
            content=content,
            timestamp=datetime.now(UTC),
            extracted_entities=extracted_entities,
        )

        async with self._lock:
            self.messages.append(message)
            queue_size = len(self.messages)

            # Check if we should flush
            if queue_size >= self._settings.message_batch_size:
                logger.debug(
                    f"Session {self.session_id}: Queue reached batch size "
                    f"({queue_size}), flushing"
                )
                await self._flush(db)
            else:
                # Start or reset the timeout task
                self._schedule_flush(db)

        return message_id

    def _schedule_flush(self, db: AsyncSession):
        """Schedule a flush after timeout (SD-010)."""
        # Cancel existing task if any
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()

        # Create new flush task
        async def delayed_flush():
            try:
                await asyncio.sleep(self._settings.message_batch_timeout)
                async with self._lock:
                    if self.messages:  # Only flush if there are messages
                        logger.debug(
                            f"Session {self.session_id}: Timeout flush "
                            f"({len(self.messages)} messages)"
                        )
                        await self._flush(db)
            except asyncio.CancelledError:
                pass  # Normal cancellation
            except Exception as e:
                logger.error(f"Error in delayed flush: {e}")

        self._flush_task = asyncio.create_task(delayed_flush())

    async def _flush(self, db: AsyncSession):
        """Flush all queued messages to the database (SD-010).

        Must be called while holding the lock.
        """
        if not self.messages:
            return

        messages_to_flush = self.messages.copy()
        self.messages.clear()

        # Cancel any pending flush task
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            self._flush_task = None

        try:
            # Batch insert all messages
            db_messages = [
                CaptureMessage(
                    id=msg.id,
                    session_id=msg.session_id,
                    role=msg.role,
                    content=msg.content,
                    timestamp=msg.timestamp,
                    extracted_entities=msg.extracted_entities,
                )
                for msg in messages_to_flush
            ]

            db.add_all(db_messages)
            await db.commit()

            logger.info(
                f"Session {self.session_id}: Flushed {len(db_messages)} messages"
            )

        except Exception as e:
            logger.error(f"Session {self.session_id}: Failed to flush messages: {e}")
            # Re-queue the messages on failure
            self.messages = messages_to_flush + self.messages
            raise

    async def flush_all(self, db: AsyncSession):
        """Force flush all messages immediately.

        Called when a session ends or on explicit request.
        """
        async with self._lock:
            if self.messages:
                logger.debug(
                    f"Session {self.session_id}: Force flushing "
                    f"{len(self.messages)} messages"
                )
                await self._flush(db)

    @property
    def pending_count(self) -> int:
        """Number of messages waiting to be flushed."""
        return len(self.messages)


class MessageQueueManager:
    """Manages message queues for all active capture sessions (SD-010).

    Provides session-scoped batching with automatic cleanup.
    """

    def __init__(self):
        self._queues: dict[str, SessionMessageQueue] = {}
        self._lock = asyncio.Lock()

    async def get_queue(self, session_id: str) -> SessionMessageQueue:
        """Get or create a queue for a session."""
        async with self._lock:
            if session_id not in self._queues:
                self._queues[session_id] = SessionMessageQueue(session_id=session_id)
            return self._queues[session_id]

    async def add_message(
        self,
        db: AsyncSession,
        session_id: str,
        role: str,
        content: str,
        extracted_entities: list[dict] | None = None,
    ) -> str:
        """Add a message to the session's queue.

        Args:
            db: Database session for flushing
            session_id: Capture session ID
            role: Message role ('user' or 'assistant')
            content: Message content
            extracted_entities: Optional extracted entities

        Returns:
            Message ID
        """
        queue = await self.get_queue(session_id)
        return await queue.add_message(db, role, content, extracted_entities)

    async def flush_session(self, db: AsyncSession, session_id: str):
        """Flush all pending messages for a session.

        Called when a session is completed or closed.
        """
        async with self._lock:
            if session_id in self._queues:
                queue = self._queues[session_id]
                await queue.flush_all(db)

    async def remove_session(self, db: AsyncSession, session_id: str):
        """Flush and remove a session's queue.

        Called when a session is completed or closed.
        """
        async with self._lock:
            if session_id in self._queues:
                queue = self._queues.pop(session_id)
                await queue.flush_all(db)
                logger.debug(f"Removed queue for session {session_id}")

    async def flush_all(self, db: AsyncSession):
        """Flush all pending messages across all sessions.

        Useful for graceful shutdown.
        """
        async with self._lock:
            for session_id, queue in self._queues.items():
                try:
                    await queue.flush_all(db)
                except Exception as e:
                    logger.error(f"Error flushing session {session_id}: {e}")

    def get_stats(self) -> dict:
        """Get queue statistics."""
        total_pending = sum(q.pending_count for q in self._queues.values())
        return {
            "active_sessions": len(self._queues),
            "total_pending_messages": total_pending,
            "sessions": {sid: q.pending_count for sid, q in self._queues.items()},
        }


# Singleton instance
_message_queue_manager: MessageQueueManager | None = None


def get_message_queue_manager() -> MessageQueueManager:
    """Get the message queue manager singleton."""
    global _message_queue_manager
    if _message_queue_manager is None:
        _message_queue_manager = MessageQueueManager()
    return _message_queue_manager
