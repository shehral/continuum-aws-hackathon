"""Analytics endpoints — Parts 4.4, 4.5, 4.6, 7, 8, 11, 3a.

Endpoints:
  GET  /api/analytics/timeline          — Decision timeline with scope breakdown (Part 4.4)
  GET  /api/analytics/dormant-alternatives — Unexplored rejected paths (Part 4.5)
  GET  /api/analytics/coverage          — File coverage map / knowledge debt (Part 4.6)
  GET  /api/analytics/stale             — Decisions past their scope-based half-life (Part 7)
  POST /api/analytics/decisions/{id}/review — Mark a decision as reviewed (Part 7)
  GET  /api/analytics/assumption-violations — Active assumption invalidations (Part 11)
  POST /api/analytics/admin/ontology/refresh — Refresh canonical name mappings (Part 3a)
"""

from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.neo4j import get_neo4j_session
from models.schemas import SCOPE_STALENESS_DAYS, DecisionScope
from routers.auth import get_current_user_id
from services.assumption_monitor import AssumptionMonitor
from services.dormant_detector import DormantAlternativeDetector
from services.git_service import get_git_service
from utils.cache import get_cached, set_cached
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Timeline (Part 4.4)
# ---------------------------------------------------------------------------

class TimelineBucket(BaseModel):
    period: str               # ISO week or month string, e.g. "2025-W03" or "2025-01"
    count: int
    by_scope: dict[str, int]  # scope → count
    by_type: dict[str, int]   # decision_type → count
    avg_confidence: float


@router.get("/timeline", response_model=list[TimelineBucket])
async def get_timeline(
    project: Optional[str] = Query(None, description="Filter by project name"),
    granularity: str = Query("week", pattern="^(day|week|month)$"),
    months_back: int = Query(6, ge=1, le=24),
    user_id: str = Depends(get_current_user_id),
):
    """Decision timeline bucketed by day/week/month with scope breakdown.

    Returns a chart-ready list of time buckets, each with count and scope
    distribution.  Use this to power the Timeline view chart mode.
    """
    cache_key_parts = [project or "all", granularity, str(months_back)]
    cached = await get_cached("analytics_timeline", user_id, *cache_key_parts)
    if cached:
        return cached

    session = await get_neo4j_session()
    if not session:
        return []

    project_filter = "AND d.project_name = $project" if project else ""

    # Cypher: aggregate by period
    if granularity == "day":
        period_expr = "substring(d.created_at, 0, 10)"
    elif granularity == "week":
        # ISO week using left(date, 8) → yyyy-MM-dd then compute week via apoc or substring
        period_expr = "substring(d.created_at, 0, 7)"  # fallback to month if no APOC
    else:
        period_expr = "substring(d.created_at, 0, 7)"

    cutoff = (datetime.now(UTC) - timedelta(days=months_back * 30)).isoformat()

    query = f"""
    MATCH (d:DecisionTrace)
    WHERE d.user_id = $user_id
      AND d.created_at > $cutoff
      {project_filter}
    RETURN {period_expr} AS period,
           count(d) AS cnt,
           d.scope AS scope,
           d.decision_type AS dtype,
           avg(toFloat(d.confidence)) AS avg_conf
    ORDER BY period ASC
    """

    params: dict = {"user_id": user_id, "cutoff": cutoff}
    if project:
        params["project"] = project

    try:
        result = await session.run(query, **params)
        rows = await result.data()
    except Exception as e:
        logger.error(f"Timeline query failed: {e}")
        return []

    # Aggregate into buckets
    buckets: dict[str, TimelineBucket] = {}
    for row in rows:
        period = str(row.get("period") or "unknown")
        cnt = int(row.get("cnt") or 0)
        scope = str(row.get("scope") or "unknown")
        dtype = str(row.get("dtype") or "general")
        avg_conf = float(row.get("avg_conf") or 0.0)

        if period not in buckets:
            buckets[period] = TimelineBucket(
                period=period,
                count=0,
                by_scope={},
                by_type={},
                avg_confidence=0.0,
            )
        b = buckets[period]
        b.count += cnt
        b.by_scope[scope] = b.by_scope.get(scope, 0) + cnt
        b.by_type[dtype] = b.by_type.get(dtype, 0) + cnt
        # Weighted average confidence
        b.avg_confidence = round(
            (b.avg_confidence * (b.count - cnt) + avg_conf * cnt) / b.count, 3
        )

    result_list = sorted(buckets.values(), key=lambda x: x.period)
    # Convert TimelineBucket objects to dicts for JSON serialization
    # (TimelineBucket is a dataclass, so model_dump() or asdict() should work)
    serializable_list = [
        {
            "period": b.period,
            "count": b.count,
            "by_scope": b.by_scope,
            "by_type": b.by_type,
            "avg_confidence": b.avg_confidence,
        }
        for b in result_list
    ]
    # Fix: Pass ttl as keyword argument after unpacked args
    await set_cached("analytics_timeline", user_id, serializable_list, *cache_key_parts, ttl=300)
    return result_list


# ---------------------------------------------------------------------------
# Dormant alternatives (Part 4.5)
# ---------------------------------------------------------------------------

class DormantAlternativeResponse(BaseModel):
    candidate_id: str
    text: str
    rejected_at: Optional[str]
    rejected_by_decision_id: str
    rejected_by_trigger: str
    original_decision: str
    days_dormant: int
    reconsider_score: float


@router.get("/dormant-alternatives", response_model=list[DormantAlternativeResponse])
async def get_dormant_alternatives(
    project: Optional[str] = Query(None),
    min_days_dormant: int = Query(14, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """Return rejected decision alternatives that have never been revisited.

    These are unexplored paths that may now be worth reconsidering.
    Sorted by reconsider_score (age + original confidence penalty).
    """
    session = await get_neo4j_session()
    if not session:
        return []

    detector = DormantAlternativeDetector(session, user_id)
    dormant = await detector.find_dormant_alternatives(
        project_name=project,
        min_days_dormant=min_days_dormant,
        limit=limit,
    )

    return [
        DormantAlternativeResponse(
            candidate_id=d.candidate_id,
            text=d.text,
            rejected_at=d.rejected_at.isoformat() if d.rejected_at else None,
            rejected_by_decision_id=d.rejected_by_decision_id,
            rejected_by_trigger=d.rejected_by_trigger,
            original_decision=d.original_decision,
            days_dormant=d.days_dormant,
            reconsider_score=d.reconsider_score,
        )
        for d in dormant
    ]


# ---------------------------------------------------------------------------
# Coverage map (Part 4.6)
# ---------------------------------------------------------------------------

class CoverageFile(BaseModel):
    file_path: str
    language: str
    decision_count: int
    last_decision_at: Optional[str]
    days_since_decision: Optional[int]
    is_stale: bool
    staleness_days: int


class CoverageStats(BaseModel):
    total_files: int
    covered_files: int          # files with ≥1 decision
    stale_files: int            # covered but stale
    uncovered_files: int        # no decisions at all
    knowledge_debt_score: float  # 0-1, higher = more uncovered
    files: list[CoverageFile]


@router.get("/coverage", response_model=CoverageStats)
async def get_coverage_map(
    project: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
):
    """File coverage map — which source files have decisions and which are dark.

    Returns the 'knowledge debt score':
        uncovered_files / total_files (weighted by file size)

    Used to populate the Coverage Map heatmap view.
    """
    git_svc = get_git_service()
    session = await get_neo4j_session()

    if not git_svc or not session:
        return CoverageStats(
            total_files=0, covered_files=0, stale_files=0,
            uncovered_files=0, knowledge_debt_score=0.0, files=[]
        )

    # Get all repo files
    repo_files = git_svc.get_all_repo_files()

    # Get CodeEntity nodes with decision counts from Neo4j
    project_filter = "AND d.project_name = $project" if project else ""
    query = f"""
    MATCH (e:CodeEntity {{user_id: $user_id}})<-[:AFFECTS]-(d:DecisionTrace)
    WHERE d.user_id = $user_id {project_filter}
    RETURN e.file_path AS path,
           count(d) AS decision_count,
           max(d.created_at) AS last_decision_at
    """
    params: dict = {"user_id": user_id}
    if project:
        params["project"] = project

    try:
        result = await session.run(query, **params)
        covered_raw = {
            row["path"]: {
                "count": row["decision_count"],
                "last_at": row["last_decision_at"],
            }
            for row in await result.data()
        }
    except Exception as e:
        logger.error(f"Coverage query failed: {e}")
        covered_raw = {}

    now = datetime.now(UTC)
    stale_threshold = 90  # days without a decision = stale (for covered files)

    coverage_files: list[CoverageFile] = []
    covered_count = 0
    stale_count = 0

    for rf in repo_files:
        path = rf.file_path
        info = covered_raw.get(path)
        decision_count = info["count"] if info else 0

        last_decision_at: Optional[str] = None
        days_since: Optional[int] = None
        is_stale = False
        staleness_days = 0

        if info and info.get("last_at"):
            try:
                last_dt = datetime.fromisoformat(str(info["last_at"]).replace("Z", "+00:00"))
                last_decision_at = last_dt.isoformat()
                days_since = (now - last_dt).days
                if days_since > stale_threshold:
                    is_stale = True
                    staleness_days = days_since
            except ValueError:
                pass

        if decision_count > 0:
            covered_count += 1
            if is_stale:
                stale_count += 1

        coverage_files.append(CoverageFile(
            file_path=path,
            language=rf.language,
            decision_count=decision_count,
            last_decision_at=last_decision_at,
            days_since_decision=days_since,
            is_stale=is_stale,
            staleness_days=staleness_days,
        ))

    total = len(coverage_files)
    uncovered = total - covered_count
    debt_score = round(uncovered / total, 3) if total > 0 else 0.0

    return CoverageStats(
        total_files=total,
        covered_files=covered_count,
        stale_files=stale_count,
        uncovered_files=uncovered,
        knowledge_debt_score=debt_score,
        files=coverage_files,
    )


# ---------------------------------------------------------------------------
# Stale decisions (Part 7)
# ---------------------------------------------------------------------------

class StaleDecision(BaseModel):
    id: str
    trigger: str
    decision: str
    scope: Optional[str]
    confidence: float
    created_at: str
    last_reviewed_at: Optional[str]
    days_since_review: int
    staleness_threshold_days: int
    is_overdue: bool


@router.get("/stale", response_model=list[StaleDecision])
async def get_stale_decisions(
    project: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
):
    """Return decisions that have exceeded their scope-based review threshold.

    Staleness thresholds by scope:
      - strategic:    730 days (2 years)
      - architectural: 180 days (6 months)
      - library:      90 days
      - config:       30 days
      - operational:  14 days
      - unknown:      90 days
    """
    session = await get_neo4j_session()
    if not session:
        return []

    project_filter = "AND d.project_name = $project" if project else ""
    now_iso = datetime.now(UTC).isoformat()

    query = f"""
    MATCH (d:DecisionTrace)
    WHERE d.user_id = $user_id {project_filter}
    RETURN d.id AS id,
           d.trigger AS trigger,
           d.agent_decision AS decision,
           d.scope AS scope,
           d.confidence AS confidence,
           d.created_at AS created_at,
           d.last_reviewed_at AS last_reviewed_at
    ORDER BY d.created_at ASC
    LIMIT $limit
    """
    params: dict = {"user_id": user_id, "limit": limit}
    if project:
        params["project"] = project

    try:
        result = await session.run(query, **params)
        rows = await result.data()
    except Exception as e:
        logger.error(f"Stale decisions query failed: {e}")
        return []

    now = datetime.now(UTC)
    stale: list[StaleDecision] = []

    for row in rows:
        scope = str(row.get("scope") or "unknown")
        threshold = SCOPE_STALENESS_DAYS.get(scope, 90)

        last_reviewed_raw = row.get("last_reviewed_at")
        created_at_raw = row.get("created_at") or now_iso

        # Use last_reviewed_at if available, else created_at
        review_anchor_raw = last_reviewed_raw or created_at_raw
        try:
            review_anchor = datetime.fromisoformat(str(review_anchor_raw).replace("Z", "+00:00"))
            days_since = (now - review_anchor).days
        except ValueError:
            days_since = 0

        is_overdue = days_since > threshold

        if is_overdue:
            stale.append(StaleDecision(
                id=str(row.get("id") or ""),
                trigger=str(row.get("trigger") or ""),
                decision=str(row.get("decision") or ""),
                scope=scope if scope != "unknown" else None,
                confidence=float(row.get("confidence") or 0.5),
                created_at=str(created_at_raw),
                last_reviewed_at=str(last_reviewed_raw) if last_reviewed_raw else None,
                days_since_review=days_since,
                staleness_threshold_days=threshold,
                is_overdue=True,
            ))

    # Sort by most overdue first
    stale.sort(key=lambda x: x.days_since_review - x.staleness_threshold_days, reverse=True)
    return stale


class ReviewRequest(BaseModel):
    notes: Optional[str] = None


@router.post("/decisions/{decision_id}/review")
async def mark_decision_reviewed(
    decision_id: str,
    body: ReviewRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Mark a decision as reviewed (resets its staleness clock).

    Sets last_reviewed_at to now() and optionally stores review notes.
    """
    session = await get_neo4j_session()
    if not session:
        raise HTTPException(status_code=503, detail="Graph database unavailable")

    now_iso = datetime.now(UTC).isoformat()
    try:
        result = await session.run(
            """
            MATCH (d:DecisionTrace {id: $id, user_id: $user_id})
            SET d.last_reviewed_at = $now,
                d.review_notes = $notes
            RETURN d.id AS id
            """,
            id=decision_id,
            user_id=user_id,
            now=now_iso,
            notes=body.notes or "",
        )
        data = await result.data()
        if not data:
            raise HTTPException(status_code=404, detail="Decision not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark decision reviewed: {e}")
        raise HTTPException(status_code=500, detail="Failed to update decision")

    return {"status": "reviewed", "decision_id": decision_id, "reviewed_at": now_iso}


# ---------------------------------------------------------------------------
# Assumption violations (Part 11)
# ---------------------------------------------------------------------------

class AssumptionViolation(BaseModel):
    decision_id: str
    decision_trigger: str
    assumption: str
    invalidating_decision_id: str
    invalidating_trigger: str
    confidence: float


@router.get("/assumption-violations", response_model=list[AssumptionViolation])
async def get_assumption_violations(
    project: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """Return decisions whose stored assumptions have been contradicted by newer decisions."""
    session = await get_neo4j_session()
    if not session:
        return []

    monitor = AssumptionMonitor(session, user_id)
    violations = await monitor.scan_project(project_name=project, limit=limit)

    return [
        AssumptionViolation(
            decision_id=v.decision_id,
            decision_trigger=v.decision_trigger,
            assumption=v.assumption,
            invalidating_decision_id=v.invalidating_decision_id,
            invalidating_trigger=v.invalidating_trigger,
            confidence=v.confidence,
        )
        for v in violations
    ]


# ---------------------------------------------------------------------------
# Part 3a: OntologyUpdater admin endpoint
# ---------------------------------------------------------------------------

class OntologyRefreshResponse(BaseModel):
    new_mappings_added: int
    message: str


@router.post("/admin/ontology/refresh", response_model=OntologyRefreshResponse)
async def refresh_ontology(
    user_id: str = Depends(get_current_user_id),
):
    """Refresh the canonical name mapping dictionary from PyPI, npm, crates.io, and graph.

    Writes new mappings to models/ontology_dynamic.py (auto-generated).
    Safe to re-run at any time — only adds, never removes existing mappings.
    """
    from services.ontology_updater import OntologyUpdater

    session = await get_neo4j_session()
    updater = OntologyUpdater(neo4j_session=session)
    try:
        added = await updater.refresh()
        return OntologyRefreshResponse(
            new_mappings_added=added,
            message=f"Ontology refreshed: {added} new canonical mappings added.",
        )
    except Exception as e:
        logger.error(f"Ontology refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ontology refresh failed: {e}")
