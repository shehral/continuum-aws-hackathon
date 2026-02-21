"""Git integration endpoints — Parts 4.2, 6, 10.

Endpoints:
  POST /api/git/commit          — Link a git commit to decisions (Part 6)
  GET  /api/git/pr-context      — Decision context for a PR (Part 10)
  GET  /api/git/files           — All repo files with metadata (Part 4.6)
  GET  /api/git/stale-files     — Files not modified in threshold_days (Part 4.6)
"""

from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from config import get_settings
from db.neo4j import get_neo4j_session
from routers.auth import get_current_user_id
from services.git_service import (
    CommitInfo,
    create_affects_edge,
    create_commit_node,
    create_implemented_by_edge,
    create_touches_edges,
    get_git_service,
)
from utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/git/commit — link a commit to decisions (Part 6)
# ---------------------------------------------------------------------------

class CommitLinkRequest(BaseModel):
    """Payload sent by the post-commit git hook."""
    sha: str
    message: str
    author_email: str
    committed_at: str           # ISO-8601
    files_changed: list[str]
    project_name: Optional[str] = None
    session_timestamp: Optional[str] = None  # When the Claude session started


class CommitLinkResponse(BaseModel):
    sha: str
    linked_decisions: int
    created_touches: int


@router.post("/commit", response_model=CommitLinkResponse)
async def link_commit(
    body: CommitLinkRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Accept a git commit and link it to nearby decisions via file overlap.

    Called by the post-commit hook (tools/continuum-post-commit.sh).
    Creates:
    - CommitNode in Neo4j
    - IMPLEMENTED_BY edges (Decision → CommitNode)
    - TOUCHES edges (CommitNode → CodeEntity)
    """
    session = await get_neo4j_session()
    if not session:
        raise HTTPException(status_code=503, detail="Graph database unavailable")

    settings = get_settings()

    # Parse committed_at
    try:
        committed_at = datetime.fromisoformat(body.committed_at.replace("Z", "+00:00"))
    except ValueError:
        committed_at = datetime.now(UTC)

    # Build CommitInfo
    commit = CommitInfo(
        sha=body.sha,
        short_sha=body.sha[:7],
        message=body.message,
        author_name="",
        author_email=body.author_email,
        committed_at=committed_at,
        files_changed=body.files_changed,
    )

    # Create CommitNode
    await create_commit_node(session, commit, user_id)

    # Create TOUCHES edges
    await create_touches_edges(session, body.sha, body.files_changed, user_id)

    # Find decisions to link via file overlap
    window_start: Optional[datetime] = None
    if body.session_timestamp:
        try:
            session_ts = datetime.fromisoformat(body.session_timestamp.replace("Z", "+00:00"))
            window_start = session_ts - timedelta(hours=2)
        except ValueError:
            pass

    if window_start is None:
        window_start = committed_at - timedelta(hours=settings.git_commit_link_window_hours)

    # Query decisions from the session window that touch the same files
    project_filter = "AND d.project_name = $project" if body.project_name else ""
    query = f"""
    MATCH (d:DecisionTrace)-[:AFFECTS]->(e:CodeEntity)
    WHERE d.user_id = $user_id
      AND d.created_at >= $window_start
      AND d.created_at <= $committed_at
      AND e.file_path IN $files
      {project_filter}
    RETURN DISTINCT d.id AS id, count(e) AS overlap_count
    ORDER BY overlap_count DESC
    LIMIT 20
    """
    params: dict = {
        "user_id": user_id,
        "window_start": window_start.isoformat(),
        "committed_at": committed_at.isoformat(),
        "files": body.files_changed,
    }
    if body.project_name:
        params["project"] = body.project_name

    linked = 0
    try:
        result = await session.run(query, **params)
        rows = await result.data()

        for row in rows:
            decision_id = row.get("id")
            overlap = int(row.get("overlap_count") or 0)
            if decision_id and overlap > 0:
                # Score = overlap / len(files_changed) (simple jaccard numerator)
                score = overlap / len(body.files_changed) if body.files_changed else 0.0
                if score >= settings.git_commit_link_score_threshold:
                    await create_implemented_by_edge(session, decision_id, body.sha, score)
                    linked += 1
    except Exception as e:
        logger.error(f"Commit link query failed: {e}")

    return CommitLinkResponse(
        sha=body.sha,
        linked_decisions=linked,
        created_touches=len(body.files_changed),
    )


# ---------------------------------------------------------------------------
# GET /api/git/pr-context — decision context for PR (Part 10)
# ---------------------------------------------------------------------------

class PRDecision(BaseModel):
    id: str
    trigger: str
    decision: str
    scope: Optional[str]
    confidence: float
    created_at: str
    file_path: str  # The file that links this decision to the PR


class PRContextResponse(BaseModel):
    pr_files: list[str]
    relevant_decisions: list[PRDecision]
    contradictions: list[dict]
    stale_decisions: list[str]  # decision IDs that are past their staleness threshold


@router.get("/pr-context", response_model=PRContextResponse)
async def get_pr_context(
    files: str = Query(..., description="Comma-separated list of files changed in the PR"),
    project: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
):
    """Return all Continuum decisions relevant to a set of changed files.

    Used by the GitHub Actions workflow (tools/continuum-pr-check.yml) to
    inject decision context into PR descriptions and CI comments.
    """
    session = await get_neo4j_session()
    if not session:
        return PRContextResponse(
            pr_files=[], relevant_decisions=[], contradictions=[], stale_decisions=[]
        )

    file_list = [f.strip() for f in files.split(",") if f.strip()]
    if not file_list:
        raise HTTPException(status_code=400, detail="files parameter is required")

    project_filter = "AND d.project_name = $project" if project else ""

    # Find decisions that affect any of the PR's files
    query = f"""
    MATCH (d:DecisionTrace)-[r:AFFECTS]->(e:CodeEntity)
    WHERE d.user_id = $user_id
      AND e.file_path IN $files
      {project_filter}
    RETURN d.id AS id,
           d.trigger AS trigger,
           d.agent_decision AS decision,
           d.scope AS scope,
           d.confidence AS confidence,
           d.created_at AS created_at,
           e.file_path AS file_path
    ORDER BY d.created_at DESC
    LIMIT 50
    """
    params: dict = {"user_id": user_id, "files": file_list}
    if project:
        params["project"] = project

    try:
        result = await session.run(query, **params)
        rows = await result.data()
    except Exception as e:
        logger.error(f"PR context query failed: {e}")
        return PRContextResponse(
            pr_files=file_list, relevant_decisions=[], contradictions=[], stale_decisions=[]
        )

    decisions = [
        PRDecision(
            id=str(row.get("id") or ""),
            trigger=str(row.get("trigger") or ""),
            decision=str(row.get("decision") or ""),
            scope=str(row.get("scope")) if row.get("scope") else None,
            confidence=float(row.get("confidence") or 0.5),
            created_at=str(row.get("created_at") or ""),
            file_path=str(row.get("file_path") or ""),
        )
        for row in rows
    ]

    # Find contradictions among the relevant decisions
    decision_ids = [d.id for d in decisions]
    contradictions: list[dict] = []
    if decision_ids:
        try:
            contra_result = await session.run(
                """
                MATCH (a:DecisionTrace)-[:CONTRADICTS]->(b:DecisionTrace)
                WHERE a.id IN $ids AND b.id IN $ids
                RETURN a.id AS a_id, a.trigger AS a_trigger,
                       b.id AS b_id, b.trigger AS b_trigger
                """,
                ids=decision_ids,
            )
            contradictions = await contra_result.data()
        except Exception:
            pass

    # Flag stale decisions (scope-based threshold)
    from models.schemas import SCOPE_STALENESS_DAYS
    now = datetime.now(UTC)
    stale_ids: list[str] = []
    for d in decisions:
        scope = d.scope or "unknown"
        threshold = SCOPE_STALENESS_DAYS.get(scope, 90)
        try:
            created = datetime.fromisoformat(d.created_at.replace("Z", "+00:00"))
            if (now - created).days > threshold:
                stale_ids.append(d.id)
        except ValueError:
            pass

    return PRContextResponse(
        pr_files=file_list,
        relevant_decisions=decisions,
        contradictions=[
            {
                "a_id": row.get("a_id"),
                "a_trigger": row.get("a_trigger"),
                "b_id": row.get("b_id"),
                "b_trigger": row.get("b_trigger"),
            }
            for row in contradictions
        ],
        stale_decisions=stale_ids,
    )


# ---------------------------------------------------------------------------
# GET /api/git/files — repo file tree (Part 4.6)
# ---------------------------------------------------------------------------

class RepoFileResponse(BaseModel):
    file_path: str
    language: str
    size_bytes: int
    last_modified: Optional[str]


@router.get("/files", response_model=list[RepoFileResponse])
async def get_repo_files(
    user_id: str = Depends(get_current_user_id),
):
    """Return all tracked files in the configured repository."""
    git_svc = get_git_service()
    if not git_svc:
        return []

    files = git_svc.get_all_repo_files()
    return [
        RepoFileResponse(
            file_path=f.file_path,
            language=f.language,
            size_bytes=f.size_bytes,
            last_modified=f.last_modified.isoformat() if f.last_modified else None,
        )
        for f in files
    ]


# ---------------------------------------------------------------------------
# GET /api/git/stale-files (Part 4.6)
# ---------------------------------------------------------------------------

class StaleFileResponse(BaseModel):
    file_path: str
    last_modified: str
    days_since_modified: int


@router.get("/stale-files", response_model=list[StaleFileResponse])
async def get_stale_files(
    threshold_days: int = Query(90, ge=1, le=1825),
    user_id: str = Depends(get_current_user_id),
):
    """Return files not modified in the last threshold_days (default 90)."""
    git_svc = get_git_service()
    if not git_svc:
        return []

    stale = git_svc.get_stale_files(threshold_days=threshold_days)
    return [
        StaleFileResponse(
            file_path=s.file_path,
            last_modified=s.last_modified.isoformat(),
            days_since_modified=s.days_since_modified,
        )
        for s in stale
    ]
