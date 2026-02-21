"""Notification service — Part 8.

Stores in-app notifications in PostgreSQL and delivers them in real-time
via WebSocket.  Cross-user contradiction detection runs when a new decision
is saved into a project that has other users' decisions.

Architecture:
  PostgreSQL table `notifications`:
    id, user_id, type, title, body, payload (JSONB), read, created_at

  WebSocket registry (in-memory, per-process):
    {user_id → set of WebSocket connections}

  Cross-user contradiction scan:
    When user A saves decision D in project P, find all decisions from
    *other* users in P whose CONTRADICTS edge overlaps with D's entities.
    If found, create CONTRADICTS edge in Neo4j and notify both users.

Notification types:
  - contradiction      : Two decisions (possibly from different users) conflict
  - assumption_invalid : An assumption was detected as violated
  - stale_decision     : A decision has passed its scope staleness threshold
  - dormant_alternative: A dormant alternative worth revisiting was flagged
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional
from weakref import WeakSet

from fastapi import WebSocket
from utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# In-memory WebSocket registry
# ---------------------------------------------------------------------------

# Maps user_id → set of active WebSocket connections (weak refs handle GC)
_ws_registry: dict[str, set[WebSocket]] = {}
_registry_lock = asyncio.Lock()


async def register_ws(user_id: str, ws: WebSocket) -> None:
    """Register a WebSocket connection for a user."""
    async with _registry_lock:
        if user_id not in _ws_registry:
            _ws_registry[user_id] = set()
        _ws_registry[user_id].add(ws)
    logger.debug(f"WebSocket registered for user {user_id} ({len(_ws_registry[user_id])} connections)")


async def unregister_ws(user_id: str, ws: WebSocket) -> None:
    """Unregister a WebSocket connection (e.g. on disconnect)."""
    async with _registry_lock:
        if user_id in _ws_registry:
            _ws_registry[user_id].discard(ws)
            if not _ws_registry[user_id]:
                del _ws_registry[user_id]


async def push_to_user(user_id: str, payload: dict) -> int:
    """Push a JSON payload to all WebSocket connections for a user.

    Returns the number of connections successfully sent to.
    """
    async with _registry_lock:
        connections = list(_ws_registry.get(user_id, set()))

    if not connections:
        return 0

    sent = 0
    dead: list[WebSocket] = []
    for ws in connections:
        try:
            await ws.send_json(payload)
            sent += 1
        except Exception:
            dead.append(ws)

    # Clean up dead connections
    if dead:
        async with _registry_lock:
            for ws in dead:
                _ws_registry.get(user_id, set()).discard(ws)

    return sent


# ---------------------------------------------------------------------------
# Notification data model
# ---------------------------------------------------------------------------

@dataclass
class Notification:
    """A single notification stored in PostgreSQL and pushed via WebSocket."""
    user_id: str
    type: str                       # "contradiction" | "assumption_invalid" | "stale_decision" | "dormant_alternative"
    title: str
    body: str
    payload: dict = field(default_factory=dict)  # Structured data (decision IDs, etc.)
    id: Optional[str] = None
    read: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "payload": self.payload,
            "read": self.read,
            "created_at": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# NotificationService
# ---------------------------------------------------------------------------

class NotificationService:
    """Create and deliver notifications to users.

    Usage:
        svc = NotificationService()
        await svc.notify_contradiction(decision_a, decision_b, user_a, user_b, reason)
        await svc.get_unread(user_id)
        await svc.mark_read(notification_id, user_id)

    Persistence uses the shared SQLAlchemy AsyncSession (same engine as the rest
    of the app).  The raw asyncpg pool is no longer needed.
    """

    def __init__(self, pg_pool=None):
        # pg_pool parameter kept for backwards-compat call sites; not used.
        pass

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    async def _save(self, notif: Notification) -> str:
        """Persist notification to PostgreSQL via SQLAlchemy.  Returns the new ID."""
        import uuid
        from db.postgres import async_session_maker
        from models.postgres import Notification as NotificationModel

        notif_id = str(uuid.uuid4())
        if async_session_maker is None:
            return notif_id  # DB not initialised yet

        try:
            async with async_session_maker() as session:
                row = NotificationModel(
                    id=notif_id,
                    user_id=notif.user_id,
                    type=notif.type,
                    title=notif.title,
                    body=notif.body,
                    payload=notif.payload,
                    read=False,
                    created_at=notif.created_at,
                )
                session.add(row)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist notification: {e}")

        return notif_id

    async def get_unread(self, user_id: str, limit: int = 50) -> list[dict]:
        """Return unread notifications for a user (newest first)."""
        from sqlalchemy import select
        from db.postgres import async_session_maker
        from models.postgres import Notification as NotificationModel

        if async_session_maker is None:
            return []
        try:
            async with async_session_maker() as session:
                stmt = (
                    select(NotificationModel)
                    .where(NotificationModel.user_id == user_id, NotificationModel.read == False)  # noqa: E712
                    .order_by(NotificationModel.created_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
            return [
                {
                    "id": r.id, "type": r.type, "title": r.title,
                    "body": r.body, "payload": r.payload,
                    "read": r.read, "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to fetch notifications: {e}")
            return []

    async def get_all(self, user_id: str, limit: int = 100) -> list[dict]:
        """Return all notifications for a user (newest first)."""
        from sqlalchemy import select
        from db.postgres import async_session_maker
        from models.postgres import Notification as NotificationModel

        if async_session_maker is None:
            return []
        try:
            async with async_session_maker() as session:
                stmt = (
                    select(NotificationModel)
                    .where(NotificationModel.user_id == user_id)
                    .order_by(NotificationModel.created_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
            return [
                {
                    "id": r.id, "type": r.type, "title": r.title,
                    "body": r.body, "payload": r.payload,
                    "read": r.read, "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to fetch notifications: {e}")
            return []

    async def mark_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a single notification as read.  Returns True on success."""
        from sqlalchemy import update
        from db.postgres import async_session_maker
        from models.postgres import Notification as NotificationModel

        if async_session_maker is None:
            return False
        try:
            async with async_session_maker() as session:
                stmt = (
                    update(NotificationModel)
                    .where(NotificationModel.id == notification_id, NotificationModel.user_id == user_id)
                    .values(read=True)
                )
                result = await session.execute(stmt)
                await session.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.warning(f"Failed to mark notification read: {e}")
            return False

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user.  Returns count updated."""
        from sqlalchemy import update
        from db.postgres import async_session_maker
        from models.postgres import Notification as NotificationModel

        if async_session_maker is None:
            return 0
        try:
            async with async_session_maker() as session:
                stmt = (
                    update(NotificationModel)
                    .where(NotificationModel.user_id == user_id, NotificationModel.read == False)  # noqa: E712
                    .values(read=True)
                )
                result = await session.execute(stmt)
                await session.commit()
            return result.rowcount
        except Exception as e:
            logger.warning(f"Failed to mark all notifications read: {e}")
            return 0

    # ------------------------------------------------------------------
    # Notification creation helpers
    # ------------------------------------------------------------------

    async def _deliver(self, notif: Notification) -> None:
        """Persist + push a notification."""
        notif.id = await self._save(notif)
        # Fire-and-forget WebSocket push
        asyncio.ensure_future(push_to_user(notif.user_id, notif.to_dict()))

    async def notify_contradiction(
        self,
        decision_a: dict,
        decision_b: dict,
        user_a: str,
        user_b: str,
        contradiction_reason: str = "",
    ) -> None:
        """Notify both users when a cross-user contradiction is detected.

        Sends a notification to user_a (whose new decision triggered the scan)
        and to user_b (whose older decision is being contradicted).
        """
        a_trigger = str(decision_a.get("trigger", ""))[:80]
        b_trigger = str(decision_b.get("trigger", ""))[:80]
        a_id = str(decision_a.get("id", ""))
        b_id = str(decision_b.get("id", ""))

        # Notify user_a (the one who just saved a decision)
        notif_a = Notification(
            user_id=user_a,
            type="contradiction",
            title="Contradiction detected",
            body=(
                f"Your decision \"{a_trigger}\" contradicts an existing decision "
                f"\"{b_trigger}\" from another developer in this project."
            ),
            payload={
                "decision_a_id": a_id,
                "decision_b_id": b_id,
                "reason": contradiction_reason,
                "other_user": user_b,
            },
        )
        await self._deliver(notif_a)

        # Notify user_b (whose decision is contradicted)
        if user_b != user_a:
            notif_b = Notification(
                user_id=user_b,
                type="contradiction",
                title="Your decision may be contradicted",
                body=(
                    f"A new decision \"{a_trigger}\" was added that may contradict "
                    f"your decision \"{b_trigger}\"."
                ),
                payload={
                    "decision_a_id": a_id,
                    "decision_b_id": b_id,
                    "reason": contradiction_reason,
                    "other_user": user_a,
                },
            )
            await self._deliver(notif_b)

    async def notify_assumption_invalid(
        self,
        user_id: str,
        decision_id: str,
        decision_trigger: str,
        assumption: str,
        invalidating_decision_id: str,
        invalidating_trigger: str,
    ) -> None:
        """Notify user that a stored assumption may have been invalidated."""
        notif = Notification(
            user_id=user_id,
            type="assumption_invalid",
            title="Decision assumption may be outdated",
            body=(
                f"Your assumption \"{assumption[:100]}\" in decision "
                f"\"{decision_trigger[:60]}\" may be invalidated by a newer decision: "
                f"\"{invalidating_trigger[:60]}\"."
            ),
            payload={
                "decision_id": decision_id,
                "assumption": assumption,
                "invalidating_decision_id": invalidating_decision_id,
            },
        )
        await self._deliver(notif)

    async def notify_stale_decision(
        self,
        user_id: str,
        decision_id: str,
        decision_trigger: str,
        scope: str,
        days_old: int,
    ) -> None:
        """Notify user that a decision has passed its staleness threshold."""
        notif = Notification(
            user_id=user_id,
            type="stale_decision",
            title="Stale decision needs review",
            body=(
                f"Your {scope} decision \"{decision_trigger[:80]}\" is {days_old} days old "
                f"and may need to be reviewed or confirmed still relevant."
            ),
            payload={
                "decision_id": decision_id,
                "scope": scope,
                "days_old": days_old,
            },
        )
        await self._deliver(notif)

    async def notify_dormant_alternative(
        self,
        user_id: str,
        candidate_id: str,
        alternative_text: str,
        original_decision_trigger: str,
        days_dormant: int,
        reconsider_score: float,
    ) -> None:
        """Notify user about a dormant alternative worth revisiting."""
        notif = Notification(
            user_id=user_id,
            type="dormant_alternative",
            title="Unexplored alternative worth revisiting",
            body=(
                f"Alternative \"{alternative_text[:80]}\" from the decision "
                f"\"{original_decision_trigger[:60]}\" has been dormant for "
                f"{days_dormant} days and may now be viable."
            ),
            payload={
                "candidate_id": candidate_id,
                "reconsider_score": reconsider_score,
                "days_dormant": days_dormant,
            },
        )
        await self._deliver(notif)


# ---------------------------------------------------------------------------
# Cross-user contradiction scanner
# ---------------------------------------------------------------------------

class CrossUserContradictionScanner:
    """Scan for contradictions between decisions from different users in the same project.

    Called after a new decision is saved.  Finds decisions from *other* users
    in the same project, runs pairwise contradiction analysis, and stores
    CONTRADICTS edges + notifications.

    This is computationally bounded by:
    - Only comparing the newest N decisions from other users (limit=20)
    - Only running when project_name is set (multi-user project context)
    - Using the existing DecisionAnalyzer (LLM-based pairwise check)
    """

    def __init__(self, neo4j_session, notification_service: NotificationService):
        self.session = neo4j_session
        self.notif_svc = notification_service

    async def scan_after_save(
        self,
        new_decision_id: str,
        new_decision: dict,
        user_id: str,
        project_name: str,
    ) -> int:
        """Scan for cross-user contradictions after a decision is saved.

        Args:
            new_decision_id: ID of the just-saved decision
            new_decision:    Dict with trigger, agent_decision, agent_rationale
            user_id:         The user who saved the decision
            project_name:    The project to scan within

        Returns:
            Number of contradictions found and stored.
        """
        if not project_name:
            return 0

        # Find recent decisions from *other* users in the same project
        try:
            result = await self.session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE d.project_name = $project
                  AND d.user_id <> $user_id
                  AND d.user_id IS NOT NULL
                RETURN d.id AS id,
                       d.trigger AS trigger,
                       d.agent_decision AS agent_decision,
                       d.agent_rationale AS agent_rationale,
                       d.user_id AS user_id,
                       d.created_at AS created_at
                ORDER BY d.created_at DESC
                LIMIT 20
                """,
                project=project_name,
                user_id=user_id,
            )
            other_decisions = await result.data()
        except Exception as e:
            logger.warning(f"Cross-user contradiction scan query failed: {e}")
            return 0

        if not other_decisions:
            return 0

        # Run pairwise analysis
        from services.decision_analyzer import DecisionAnalyzer
        analyzer = DecisionAnalyzer(self.session, user_id)

        found = 0
        decision_a = {
            "id": new_decision_id,
            "trigger": new_decision.get("trigger", ""),
            "decision": new_decision.get("agent_decision", ""),
            "rationale": new_decision.get("agent_rationale", ""),
            "created_at": datetime.now(UTC).isoformat(),
        }

        for other in other_decisions:
            decision_b = {
                "id": str(other.get("id", "")),
                "trigger": str(other.get("trigger", "")),
                "decision": str(other.get("agent_decision", "")),
                "rationale": str(other.get("agent_rationale", "")),
                "created_at": str(other.get("created_at", "")),
            }
            other_user_id = str(other.get("user_id", ""))

            try:
                rel = await analyzer.analyze_decision_pair(decision_a, decision_b)
            except Exception as e:
                logger.debug(f"Pairwise analysis failed: {e}")
                continue

            if rel and rel.get("type") == "CONTRADICTS" and rel.get("confidence", 0) >= 0.6:
                # Store CONTRADICTS edge (cross-user — no user_id filter on the MERGE)
                try:
                    await self.session.run(
                        """
                        MATCH (a:DecisionTrace {id: $a_id})
                        MATCH (b:DecisionTrace {id: $b_id})
                        MERGE (a)-[r:CONTRADICTS]->(b)
                        SET r.confidence = $confidence,
                            r.reasoning = $reasoning,
                            r.cross_user = true,
                            r.detected_at = $now
                        """,
                        a_id=new_decision_id,
                        b_id=decision_b["id"],
                        confidence=rel["confidence"],
                        reasoning=rel.get("reasoning", "")[:500],
                        now=datetime.now(UTC).isoformat(),
                    )
                except Exception as e:
                    logger.warning(f"Failed to store CONTRADICTS edge: {e}")

                # Notify both users
                await self.notif_svc.notify_contradiction(
                    decision_a=decision_a,
                    decision_b=decision_b,
                    user_a=user_id,
                    user_b=other_user_id,
                    contradiction_reason=rel.get("reasoning", ""),
                )
                found += 1

        if found:
            logger.info(
                f"Cross-user contradiction scan: {found} contradictions found "
                f"for decision {new_decision_id} in project {project_name}"
            )

        return found


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_notification_service: Optional[NotificationService] = None


def get_notification_service(pg_pool=None) -> NotificationService:
    """Get or create the singleton NotificationService."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService(pg_pool)
    elif pg_pool is not None and _notification_service._pool is None:
        _notification_service._pool = pg_pool
    return _notification_service
