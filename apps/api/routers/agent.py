"""Agent Context API — structured knowledge graph access for AI agents.

Provides 5 endpoints for AI agents (Claude Code, Cursor, etc.) to query
and contribute to the architectural knowledge graph:

1. GET  /summary         — High-level project overview for bootstrapping
2. POST /context         — Focused context query with hybrid search
3. GET  /context/{name}  — Everything about a specific entity
4. POST /check           — Prior art check before making a decision
5. POST /remember        — Record an agent-made decision

All endpoints are user-scoped via JWT auth.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models.schemas import (
    AgentCheckRequest,
    AgentCheckResponse,
    AgentContextRequest,
    AgentContextResponse,
    AgentEntityContextResponse,
    AgentRememberRequest,
    AgentRememberResponse,
    AgentSummaryResponse,
)
from routers.auth import get_current_user_id, require_auth
from services.agent_context import AgentContextService
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/summary", response_model=AgentSummaryResponse)
async def get_summary(
    project: Optional[str] = Query(None, description="Filter by project name"),
    user_id: str = Depends(get_current_user_id),
):
    """Get high-level architectural overview for bootstrapping agent context.

    Returns key technologies, top decisions, unresolved contradictions,
    and knowledge gaps. Cached for 120 seconds.
    """
    try:
        service = AgentContextService(user_id=user_id)
        return await service.get_summary(project_filter=project)
    except Exception as e:
        logger.error(f"Error in agent summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate summary")


@router.post("/context", response_model=AgentContextResponse)
async def get_context(
    request: AgentContextRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Get focused context package for a natural language query.

    Uses hybrid search (lexical + semantic) to find relevant decisions,
    then expands the subgraph with entities and evolution chains.
    Supports markdown rendering for direct LLM consumption.
    """
    try:
        service = AgentContextService(user_id=user_id)
        return await service.get_context(
            query=request.query,
            max_decisions=request.max_decisions,
            max_tokens=request.max_tokens,
            include_evolution=request.include_evolution,
            include_entities=request.include_entities,
            fmt=request.format,
            project_filter=request.project_filter,
        )
    except Exception as e:
        logger.error(f"Error in agent context query: {e}")
        raise HTTPException(status_code=500, detail="Failed to get context")


@router.get("/context/{entity_name}", response_model=AgentEntityContextResponse)
async def get_entity_context(
    entity_name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get everything about a specific technology/concept.

    Resolves the entity name (handles aliases and canonical names),
    then returns all decisions involving it, related entities,
    timeline, and current status.
    """
    if not entity_name or len(entity_name) > 500:
        raise HTTPException(status_code=400, detail="Entity name must be 1-500 characters")

    try:
        service = AgentContextService(user_id=user_id)
        return await service.get_entity_context(entity_name)
    except Exception as e:
        logger.error(f"Error in entity context for '{entity_name}': {e}")
        raise HTTPException(status_code=500, detail="Failed to get entity context")


@router.post("/check", response_model=AgentCheckResponse)
async def check_prior_art(
    request: AgentCheckRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Check prior art before making a decision.

    Finds similar decisions via hybrid search, surfaces superseded
    decisions (abandoned patterns), flags contradictions, and returns
    a recommendation: proceed / review_similar / resolve_contradiction.

    Always returns fresh results (no caching).
    """
    try:
        service = AgentContextService(user_id=user_id)
        return await service.check_prior_art(
            proposed_decision=request.proposed_decision,
            context=request.context,
            entities=request.entities,
            threshold=request.threshold,
        )
    except Exception as e:
        logger.error(f"Error in prior art check: {e}")
        raise HTTPException(status_code=500, detail="Failed to check prior art")


@router.post("/remember", response_model=AgentRememberResponse)
async def remember_decision(
    request: AgentRememberRequest,
    user_id: str = Depends(require_auth),
):
    """Record an agent-made decision with provenance tracking.

    Saves the decision to the knowledge graph, extracts entities,
    finds similar existing decisions, and identifies potential
    supersedes/contradicts relationships.

    Requires authentication. Invalidates agent caches for the user.
    """
    try:
        service = AgentContextService(user_id=user_id)
        return await service.remember_decision(
            trigger=request.trigger,
            context=request.context,
            options=request.options,
            decision=request.decision,
            rationale=request.rationale,
            confidence=request.confidence,
            entities=request.entities,
            agent_name=request.agent_name,
            project_name=request.project_name,
        )
    except Exception as e:
        logger.error(f"Error recording agent decision: {e}")
        raise HTTPException(status_code=500, detail="Failed to record decision")
