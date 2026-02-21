"""Notifications endpoints — Part 8.

Endpoints:
  GET    /api/notifications              — List notifications (unread-first)
  POST   /api/notifications/read-all     — Mark all notifications as read
  POST   /api/notifications/{id}/read    — Mark a single notification as read
  GET    /api/notifications/unread-count — Count of unread notifications
  WebSocket /ws/notifications            — Real-time push channel

The WebSocket channel delivers notification payloads in real-time whenever:
  - A cross-user contradiction is detected
  - An assumption is flagged as invalidated
  - A stale decision is surfaced
  - A dormant alternative is flagged

All endpoints are user-scoped (user_id from JWT auth).

PostgreSQL schema (run once in migrations):
    CREATE TABLE IF NOT EXISTS notifications (
        id          UUID PRIMARY KEY,
        user_id     TEXT NOT NULL,
        type        TEXT NOT NULL,
        title       TEXT NOT NULL,
        body        TEXT NOT NULL,
        payload     JSONB DEFAULT '{}',
        read        BOOLEAN DEFAULT false,
        created_at  TIMESTAMPTZ DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
        ON notifications (user_id, read, created_at DESC);
"""

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from routers.auth import get_current_user_id
from services.notifications import (
    NotificationService,
    get_notification_service,
    register_ws,
    unregister_ws,
)
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    body: str
    payload: dict
    read: bool
    created_at: str


class UnreadCountResponse(BaseModel):
    count: int


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    unread_only: bool = True,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    """Return notifications for the current user.

    Set unread_only=false to include previously read notifications.
    """
    svc = get_notification_service()
    if unread_only:
        rows = await svc.get_unread(user_id, limit=limit)
    else:
        rows = await svc.get_all(user_id, limit=limit)

    return [
        NotificationResponse(
            id=str(r.get("id", "")),
            type=str(r.get("type", "")),
            title=str(r.get("title", "")),
            body=str(r.get("body", "")),
            payload=r.get("payload") or {},
            read=bool(r.get("read", False)),
            created_at=str(r.get("created_at", "")),
        )
        for r in rows
    ]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user_id: str = Depends(get_current_user_id),
):
    """Return the count of unread notifications for the badge indicator."""
    svc = get_notification_service()
    rows = await svc.get_unread(user_id, limit=200)
    return UnreadCountResponse(count=len(rows))


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Mark a single notification as read."""
    svc = get_notification_service()
    ok = await svc.mark_read(notification_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(
    user_id: str = Depends(get_current_user_id),
):
    """Mark all notifications as read for the current user."""
    svc = get_notification_service()
    count = await svc.mark_all_read(user_id)
    return {"ok": True, "marked_read": count}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def notifications_ws(
    websocket: WebSocket,
    token: str = "",
):
    """Real-time notification channel.

    Connect with: ws://HOST/ws/notifications?token=<JWT>

    The server sends JSON notification objects as they are created:
    {
        "id": "...",
        "type": "contradiction",
        "title": "...",
        "body": "...",
        "payload": {...},
        "read": false,
        "created_at": "..."
    }

    Clients should reconnect with exponential back-off on disconnect.
    """
    # Authenticate via query-param token (headers not available in WS handshake).
    # Re-uses the same JWT decoding logic as get_current_user_id by constructing
    # a fake Authorization header value.
    from routers.auth import get_current_user_id
    user_id = await get_current_user_id(
        authorization=f"Bearer {token}" if token else None
    )
    if user_id == "anonymous":
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    await register_ws(user_id, websocket)
    logger.info(f"WebSocket connected for user {user_id}")

    # Send any unread notifications immediately on connect
    svc = get_notification_service()
    unread = await svc.get_unread(user_id, limit=20)
    for notif in reversed(unread):  # oldest first
        try:
            await websocket.send_json(notif)
        except Exception:
            break

    # Keep alive: wait for close or ping
    try:
        while True:
            # Receive messages from client (ping/ack or graceful close)
            data = await websocket.receive_text()
            # Support client-side ack: {"ack": "notification_id"}
            try:
                import json as _json
                msg = _json.loads(data)
                if msg.get("ack"):
                    await svc.mark_read(msg["ack"], user_id)
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await unregister_ws(user_id, websocket)
        logger.info(f"WebSocket disconnected for user {user_id}")
