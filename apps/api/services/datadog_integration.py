"""Datadog bidirectional integration — Part 12.

Continuum is the decision context layer on top of Datadog's operational layer.

Bidirectional flow:
  WRITE → Continuum posts decision events to Datadog so engineers see
          what architectural decisions were active during an incident.
  READ  → Continuum reads Datadog monitor alerts to detect when operational
          signals contradict a stored assumption (e.g. p99 latency spike
          contradicts a "< 100ms p99" assumption).

All Datadog calls are fire-and-forget (non-blocking) and fail silently so
the main ingestion pipeline is never blocked.

Configuration (via .env):
  DATADOG_API_KEY=...
  DATADOG_APP_KEY=...
  DATADOG_SITE=datadoghq.com         # or datadoghq.eu, etc.
  DATADOG_INTEGRATION_ENABLED=true
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional

import aiohttp

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

_DD_EVENT_URL = "https://api.{site}/api/v1/events"
_DD_MONITORS_URL = "https://api.{site}/api/v1/monitor"
_DD_METRICS_URL = "https://api.{site}/api/v1/series"
_REQUEST_TIMEOUT = 5  # seconds


@dataclass
class DatadogEvent:
    """A Datadog event posted from Continuum."""
    title: str
    text: str
    tags: list[str] = field(default_factory=list)
    alert_type: str = "info"        # info | warning | error | success
    priority: str = "normal"        # normal | low
    source_type_name: str = "Continuum"


@dataclass
class DatadogMonitorAlert:
    """A Datadog monitor alert (anomaly) that may contradict a decision assumption."""
    monitor_id: int
    monitor_name: str
    status: str                     # Alert | Warn | No Data | OK
    message: str
    triggered_at: Optional[datetime]
    affected_entities: list[str]    # Tags / host names relevant to the alert


class DatadogClient:
    """Async Datadog API client used by the integration service."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.get_datadog_api_key()
        self._app_key = settings.get_datadog_app_key()
        self._site = settings.datadog_site
        self._enabled = settings.datadog_integration_enabled

    def _headers(self) -> dict[str, str]:
        return {
            "DD-API-KEY": self._api_key,
            "DD-APPLICATION-KEY": self._app_key,
            "Content-Type": "application/json",
        }

    def _base_url(self, template: str) -> str:
        return template.format(site=self._site)

    async def post_event(self, event: DatadogEvent) -> bool:
        """POST a single event to the Datadog Events v1 API.

        Returns True on success.  Fails silently (returns False) on error.
        """
        if not self._enabled or not self._api_key:
            return False

        payload = {
            "title": event.title,
            "text": event.text,
            "tags": event.tags,
            "alert_type": event.alert_type,
            "priority": event.priority,
            "source_type_name": event.source_type_name,
        }

        url = self._base_url(_DD_EVENT_URL)
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)
            ) as session:
                async with session.post(url, json=payload, headers=self._headers()) as resp:
                    if resp.status in (200, 202):
                        logger.debug(f"Datadog event posted: {event.title}")
                        return True
                    logger.warning(
                        f"Datadog event POST failed: {resp.status} for '{event.title}'"
                    )
        except Exception as e:
            logger.debug(f"Datadog post_event error: {e}")
        return False

    async def get_alerting_monitors(
        self,
        tags: Optional[list[str]] = None,
    ) -> list[DatadogMonitorAlert]:
        """Fetch currently alerting Datadog monitors.

        Args:
            tags: Optional list of tags to filter monitors (e.g. ["service:api"])

        Returns list of DatadogMonitorAlert for monitors in Alert or Warn state.
        """
        if not self._enabled or not self._api_key:
            return []

        params: dict = {"monitor_tags": ",".join(tags) if tags else ""}

        url = self._base_url(_DD_MONITORS_URL)
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)
            ) as session:
                async with session.get(
                    url, params=params, headers=self._headers()
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()

            alerts: list[DatadogMonitorAlert] = []
            for monitor in data:
                state = monitor.get("overall_state", "")
                if state not in ("Alert", "Warn"):
                    continue

                # Parse triggered_at from the monitor status
                triggered_at: Optional[datetime] = None
                status_data = monitor.get("state", {}).get("groups", {})
                for group_data in status_data.values():
                    ts = group_data.get("last_triggered_ts")
                    if ts:
                        try:
                            triggered_at = datetime.fromtimestamp(ts, UTC)
                        except Exception:
                            pass
                        break

                # Extract affected entity names from monitor tags
                monitor_tags: list[str] = monitor.get("tags", [])
                host_tags = [t.split(":", 1)[1] for t in monitor_tags if ":" in t]

                alerts.append(DatadogMonitorAlert(
                    monitor_id=monitor.get("id", 0),
                    monitor_name=monitor.get("name", "Unknown monitor"),
                    status=state,
                    message=monitor.get("message", "")[:500],
                    triggered_at=triggered_at,
                    affected_entities=host_tags,
                ))

            return alerts

        except Exception as e:
            logger.debug(f"Datadog get_alerting_monitors error: {e}")
            return []


# ---------------------------------------------------------------------------
# Integration service
# ---------------------------------------------------------------------------

class DatadogIntegration:
    """Bidirectional Datadog integration for Continuum.

    WRITE operations:
    - post_decision_event()      — Post a new decision as Datadog event
    - post_contradiction_event() — Post when two decisions contradict each other

    READ operations:
    - check_assumption_violations() — Compare active alerts vs decision assumptions
    """

    def __init__(self) -> None:
        self._client = DatadogClient()

    # ------------------------------------------------------------------
    # WRITE: Continuum → Datadog
    # ------------------------------------------------------------------

    async def post_decision_event(
        self,
        decision_id: str,
        trigger: str,
        decision_text: str,
        project_name: str,
        scope: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> bool:
        """Post a new decision as a Datadog event (async, fire-and-forget).

        This lets engineers see Continuum decision markers overlaid on
        Datadog dashboards and incident timelines.
        """
        scope_label = scope or "unknown"
        event_tags = [
            "source:continuum",
            f"project:{project_name}",
            f"scope:{scope_label}",
        ] + (tags or [])

        # Truncate long decision text for the event body
        body = f"""**Decision:** {decision_text[:500]}

**Trigger:** {trigger[:300]}

**Scope:** {scope_label} | **Project:** {project_name}
[View in Continuum](/decisions/{decision_id})"""

        event = DatadogEvent(
            title=f"[Continuum] {trigger[:80]}",
            text=body,
            tags=event_tags,
            alert_type="info",
            priority="normal" if scope_label not in ("strategic", "architectural") else "normal",
        )
        return await self._client.post_event(event)

    async def post_contradiction_event(
        self,
        decision_a_id: str,
        decision_b_id: str,
        trigger_a: str,
        trigger_b: str,
        project_name: str,
    ) -> bool:
        """Post a contradiction detection as a Datadog warning event."""
        event = DatadogEvent(
            title=f"[Continuum] Contradiction detected in {project_name}",
            text=(
                f"Two decisions in project **{project_name}** appear to contradict:\n\n"
                f"- **Decision A:** {trigger_a[:150]}\n"
                f"- **Decision B:** {trigger_b[:150]}\n\n"
                f"[View Decision A](/decisions/{decision_a_id}) | "
                f"[View Decision B](/decisions/{decision_b_id})"
            ),
            tags=["source:continuum", f"project:{project_name}", "type:contradiction"],
            alert_type="warning",
        )
        return await self._client.post_event(event)

    # ------------------------------------------------------------------
    # READ: Datadog → Continuum assumption check
    # ------------------------------------------------------------------

    async def check_assumption_violations(
        self,
        assumptions: list[str],
        project_name: str,
    ) -> list[dict]:
        """Check whether any active Datadog alerts violate stored assumptions.

        Returns a list of violation dicts: {assumption, monitor_name, status, message}.
        """
        alerts = await self._client.get_alerting_monitors(
            tags=[f"project:{project_name}"] if project_name else None
        )

        if not alerts or not assumptions:
            return []

        violations: list[dict] = []

        for assumption in assumptions:
            assumption_lower = assumption.lower()
            for alert in alerts:
                alert_text = (alert.monitor_name + " " + alert.message).lower()

                # Simple keyword overlap: if the assumption and alert share
                # meaningful tokens, flag as potential violation
                assumption_words = {
                    w for w in assumption_lower.split()
                    if len(w) > 4 and w not in {"which", "where", "while", "their", "about"}
                }
                overlap = sum(1 for w in assumption_words if w in alert_text)

                if overlap >= 2 or (len(assumption_words) == 1 and overlap == 1):
                    violations.append({
                        "assumption": assumption,
                        "monitor_id": alert.monitor_id,
                        "monitor_name": alert.monitor_name,
                        "status": alert.status,
                        "message": alert.message[:300],
                        "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
                    })

        return violations


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_integration: Optional[DatadogIntegration] = None


def get_datadog_integration() -> DatadogIntegration:
    global _integration
    if _integration is None:
        _integration = DatadogIntegration()
    return _integration
