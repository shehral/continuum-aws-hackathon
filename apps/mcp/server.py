"""Continuum MCP Server — knowledge graph tools for AI agents.

Wraps the 5 Agent Context API endpoints as MCP tools that Claude Code
(and any MCP-compatible agent) discovers automatically via .mcp.json.

Architecture:
    Claude Code --stdio--> MCP Server --httpx--> FastAPI Backend
                                                    |
                                              Neo4j / Redis / PG

No business logic here — just HTTP client translation.
All logging goes to stderr (stdout is reserved for JSON-RPC).
"""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

API_URL = os.environ.get("CONTINUUM_API_URL", "http://localhost:8000")
API_TOKEN = os.environ.get("CONTINUUM_API_TOKEN", "")
REQUEST_TIMEOUT = 30.0

mcp = FastMCP(
    name="continuum",
    instructions=(
        "Continuum knowledge graph tools. Use continuum_summary at session start, "
        "continuum_search before coding, continuum_check before deciding, "
        "continuum_remember after making architectural decisions, "
        "and continuum_explain to understand why a file or feature is the way it is."
    ),
)


def _log(msg: str) -> None:
    """Log to stderr — stdout is reserved for MCP JSON-RPC."""
    print(f"[continuum-mcp] {msg}", file=sys.stderr)


async def _api_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
) -> dict:
    """Make an HTTP request to the Continuum FastAPI backend.

    Handles three error cases, all raised as RuntimeError so the MCP SDK
    surfaces them as tool error responses to the agent.
    """
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    url = f"{API_URL}{path}"
    _log(f"{method} {url}")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.request(
                method, url, headers=headers, params=params, json=json_body
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        raise RuntimeError(
            "Cannot connect to Continuum API at {url}. "
            "Is the backend running? Start with: pnpm dev:api".format(url=API_URL)
        )
    except httpx.HTTPStatusError as e:
        detail = "Unknown error"
        try:
            body = e.response.json()
            detail = body.get("detail", str(body))
        except Exception:
            detail = e.response.text[:500]
        raise RuntimeError(f"Continuum API error {e.response.status_code}: {detail}")
    except httpx.TimeoutException:
        raise RuntimeError(f"Request to Continuum API timed out after {REQUEST_TIMEOUT}s")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def continuum_summary(project: str = "") -> str:
    """Get high-level architectural overview for bootstrapping session context.

    Returns top technologies, recent decisions, unresolved contradictions,
    knowledge gaps, dormant alternatives, stale decisions, and scope breakdown.
    Call this at the start of a session to understand the project's
    architectural landscape and spot decisions that need review.

    Args:
        project: Optional project name to filter by.
    """
    params: dict = {}
    if project:
        params["project"] = project

    # Fetch core summary
    data = await _api_request("GET", "/api/agent/summary", params=params or None)

    # Enrich with dormant alternatives (top 3)
    try:
        dormant_params: dict = {"min_days_dormant": 14, "limit": 3}
        if project:
            dormant_params["project"] = project
        dormant = await _api_request(
            "GET", "/api/analytics/dormant-alternatives", params=dormant_params
        )
        if dormant:
            data["dormant_alternatives"] = dormant
    except Exception:
        pass

    # Enrich with stale decisions (top 5)
    try:
        stale_params: dict = {"limit": 5}
        if project:
            stale_params["project"] = project
        stale = await _api_request(
            "GET", "/api/analytics/stale", params=stale_params
        )
        if stale:
            data["stale_decisions"] = stale
    except Exception:
        pass

    return json.dumps(data, indent=2)


@mcp.tool()
async def continuum_search(
    query: str,
    max_decisions: int = 10,
    include_evolution: bool = True,
    include_entities: bool = True,
    project: str = "",
) -> str:
    """Search the knowledge graph for decisions matching a natural language query.

    Uses hybrid search (lexical + semantic) to find relevant architectural
    decisions, then expands with entity and evolution context.

    Args:
        query: Natural language search query (e.g. "database migration strategy").
        max_decisions: Maximum number of decisions to return (1-50).
        include_evolution: Include SUPERSEDES/CONTRADICTS chains.
        include_entities: Include related entities for each decision.
        project: Optional project name to filter by.
    """
    body: dict = {
        "query": query,
        "max_decisions": max_decisions,
        "include_evolution": include_evolution,
        "include_entities": include_entities,
        "format": "json",
    }
    if project:
        body["project_filter"] = project

    data = await _api_request("POST", "/api/agent/context", json_body=body)
    return json.dumps(data, indent=2)


@mcp.tool()
async def continuum_entity(entity_name: str) -> str:
    """Get everything about a specific technology, pattern, or concept.

    Returns all decisions involving this entity, related entities,
    timeline, and current status. Handles aliases and canonical names
    (e.g. "postgres" resolves to "PostgreSQL").

    Args:
        entity_name: Name of the entity to look up (e.g. "React", "PostgreSQL", "Node.js").
    """
    encoded = quote(entity_name, safe="")
    data = await _api_request("GET", f"/api/agent/context/{encoded}")
    return json.dumps(data, indent=2)


@mcp.tool()
async def continuum_check(
    proposed_decision: str,
    context: str = "",
    entities: list[str] | None = None,
    threshold: float = 0.5,
) -> str:
    """Check prior art before making a significant architectural decision.

    IMPORTANT: Always call this BEFORE making a significant architectural
    decision. It surfaces similar past decisions, abandoned patterns that
    were tried and superseded, and contradictions that need resolution.

    Returns a recommendation: "proceed", "review_similar", or
    "resolve_contradiction".

    Args:
        proposed_decision: Description of the decision you're about to make.
        context: Additional context about why this decision is being considered.
        entities: Known entity names involved (e.g. ["React", "Next.js"]).
        threshold: Similarity threshold for finding related decisions (0.0-1.0).
    """
    body: dict = {
        "proposed_decision": proposed_decision,
        "context": context,
        "entities": entities or [],
        "threshold": threshold,
    }
    data = await _api_request("POST", "/api/agent/check", json_body=body)
    return json.dumps(data, indent=2)


@mcp.tool()
async def continuum_remember(
    trigger: str,
    context: str,
    options: list[str],
    decision: str,
    rationale: str,
    confidence: float = 0.8,
    entities: list[str] | None = None,
    agent_name: str = "claude-code",
    project_name: str = "",
) -> str:
    """Record an architectural decision to the knowledge graph.

    Saves the decision with full provenance tracking, extracts entities,
    finds similar existing decisions, and identifies potential
    supersedes/contradicts relationships.

    Requires authentication (CONTINUUM_API_TOKEN must be set).

    Args:
        trigger: What prompted this decision.
        context: Background information and constraints.
        options: Alternatives that were considered.
        decision: What was chosen.
        rationale: Why this option was chosen over the alternatives.
        confidence: Confidence level (0.0-1.0, default 0.8).
        entities: Known entity names involved (e.g. ["React", "PostgreSQL"]).
        agent_name: Name of the agent making this decision.
        project_name: Optional project name to associate with.
    """
    body: dict = {
        "trigger": trigger,
        "context": context,
        "options": options,
        "decision": decision,
        "rationale": rationale,
        "confidence": confidence,
        "entities": entities or [],
        "agent_name": agent_name,
    }
    if project_name:
        body["project_name"] = project_name

    data = await _api_request("POST", "/api/agent/remember", json_body=body)
    return json.dumps(data, indent=2)


@mcp.tool()
async def continuum_explain(
    file_path: str = "",
    entity_name: str = "",
    decision_id: str = "",
    project: str = "",
) -> str:
    """Explain WHY a file, entity, or decision is the way it is.

    Provides decision provenance: which decisions led to this design,
    what alternatives were rejected, what assumptions underlie it, and
    whether any of those assumptions have been invalidated.

    Call this when you open a file and want to understand its design history
    before making changes to it.

    Args:
        file_path:   Relative file path to explain (e.g. "apps/api/services/extractor.py").
        entity_name: Technology or concept to explain (e.g. "Neo4j", "FastAPI").
        decision_id: Specific decision UUID to get deep provenance for.
        project:     Optional project filter.

    Provide exactly one of file_path, entity_name, or decision_id.
    """
    if not any([file_path, entity_name, decision_id]):
        return json.dumps({
            "error": "Provide one of: file_path, entity_name, or decision_id"
        })

    explanation: dict = {
        "query": file_path or entity_name or decision_id,
        "type": "file" if file_path else ("entity" if entity_name else "decision"),
        "decisions": [],
        "rejected_alternatives": [],
        "assumptions": [],
        "invalidated_assumptions": [],
        "stale": False,
    }

    params: dict = {}
    if project:
        params["project"] = project

    # 1. Find relevant decisions
    if file_path:
        # Look up decisions that AFFECT this file
        try:
            encoded = quote(file_path, safe="")
            resp = await _api_request(
                "GET",
                f"/api/git/pr-context",
                params={"files": file_path, **({"project": project} if project else {})},
            )
            explanation["decisions"] = resp.get("relevant_decisions", [])
            explanation["stale_ids"] = resp.get("stale_decisions", [])
        except Exception as e:
            _log(f"continuum_explain file lookup error: {e}")

    elif entity_name:
        # Use existing entity context endpoint
        try:
            encoded = quote(entity_name, safe="")
            resp = await _api_request("GET", f"/api/agent/context/{encoded}")
            explanation["decisions"] = resp.get("decisions", [])
            explanation["entity_info"] = resp.get("entity", {})
        except Exception as e:
            _log(f"continuum_explain entity lookup error: {e}")

    elif decision_id:
        # Direct decision lookup with provenance
        try:
            resp = await _api_request("GET", f"/api/decisions/{decision_id}")
            explanation["decisions"] = [resp] if resp else []
        except Exception as e:
            _log(f"continuum_explain decision lookup error: {e}")

    # 2. Enrich with dormant alternatives for the found decisions
    if explanation["decisions"] and len(explanation["decisions"]) <= 5:
        try:
            dormant_params: dict = {"min_days_dormant": 1, "limit": 10}
            if project:
                dormant_params["project"] = project
            dormant = await _api_request(
                "GET", "/api/analytics/dormant-alternatives", params=dormant_params
            )
            # Filter to alternatives related to the found decisions
            found_ids = {d.get("id") or d.get("rejected_by_decision_id") for d in explanation["decisions"]}
            explanation["rejected_alternatives"] = [
                d for d in (dormant or [])
                if d.get("rejected_by_decision_id") in found_ids
            ]
        except Exception:
            pass

    # 3. Check for assumption violations
    if explanation["decisions"]:
        try:
            violations_params: dict = {"limit": 10}
            if project:
                violations_params["project"] = project
            violations = await _api_request(
                "GET", "/api/analytics/assumption-violations", params=violations_params
            )
            found_ids2 = {d.get("id") for d in explanation["decisions"]}
            explanation["invalidated_assumptions"] = [
                v for v in (violations or [])
                if v.get("decision_id") in found_ids2
            ]
        except Exception:
            pass

    return json.dumps(explanation, indent=2)


if __name__ == "__main__":
    _log(f"Starting Continuum MCP server (API: {API_URL})")
    mcp.run(transport="stdio")
