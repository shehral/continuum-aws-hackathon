"""Pydantic schemas with input validation (SEC-005 compliant)."""

import re
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# SEC-005: UUID pattern for ID validation
UUID_PATTERN = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.IGNORECASE
)

# SEC-005: Valid relationship types (whitelist)
VALID_RELATIONSHIP_TYPES = frozenset(
    {
        # Decision -> Entity
        "INVOLVES",
        # Decision -> Decision
        "SIMILAR_TO",
        "SUPERSEDES",
        "INFLUENCED_BY",
        "CONTRADICTS",
        # Temporal relationships (RQ1.3: Temporal reasoning)
        "FOLLOWS",  # Decision B follows Decision A (happens after in conversation)
        "PRECEDES",  # Decision A precedes Decision B (happens before in conversation)
        # Entity -> Entity
        "IS_A",
        "PART_OF",
        "RELATED_TO",
        "DEPENDS_ON",
        "ALTERNATIVE_TO",
        # KG-P2-1: Extended entity relationships
        "ENABLES",
        "PREVENTS",
        "REQUIRES",
        "REFINES",
        # Codebase connectivity (Part 4.1, 4.2, 4.3)
        "AFFECTS",          # Decision -> CodeEntity
        "IMPLEMENTED_BY",   # Decision -> CommitNode
        "TOUCHES",          # CommitNode -> CodeEntity
        "REJECTED_BY",      # CandidateDecision -> DecisionTrace
        "ALTERNATIVE_TO",   # CandidateDecision -> CandidateDecision (already in set)
    }
)


# ---------------------------------------------------------------------------
# Decision scope taxonomy (Part 4.7)
# ---------------------------------------------------------------------------

class DecisionScope(str, Enum):
    """Hierarchical scope of a decision, determining its expected half-life.

    Used for:
    - Graph visual layering (strategic at top, operational at bottom)
    - Staleness thresholds (SCOPE_STALENESS_DAYS)
    - Timeline breakdown by scope
    """
    STRATEGIC = "strategic"         # Monolith vs microservices — years half-life
    ARCHITECTURAL = "architectural" # Which framework, DB schema — months
    LIBRARY = "library"             # Which npm/pip package — weeks/months
    CONFIG = "config"               # Timeout values, rate limits — days/weeks
    OPERATIONAL = "operational"     # Deployment config, env vars — hours/days


# Staleness threshold (days) per scope level
SCOPE_STALENESS_DAYS: dict[str, int] = {
    DecisionScope.STRATEGIC: 730,       # 2 years
    DecisionScope.ARCHITECTURAL: 180,   # 6 months
    DecisionScope.LIBRARY: 90,          # 3 months
    DecisionScope.CONFIG: 30,           # 1 month
    DecisionScope.OPERATIONAL: 14,      # 2 weeks
}


# Rationale provenance — who/what provided the rationale
class RationaleAuthor(str, Enum):
    """Source of the rationale field.

    Tracks fidelity:
    - thinking  = extracted from Claude's thinking block (highest fidelity)
    - user      = verbatim from user role message
    - assistant = inferred from assistant response text (lowest fidelity)
    """
    THINKING = "thinking"
    USER = "user"
    ASSISTANT = "assistant"


def validate_uuid(value: str, field_name: str = "id") -> str:
    """Validate that a string is a valid UUID format (SEC-005)."""
    if not UUID_PATTERN.match(value):
        raise ValueError(f"{field_name} must be a valid UUID format")
    return value.lower()  # Normalize to lowercase


# Entity schemas
class EntityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    type: str = Field(
        ..., min_length=1, max_length=50
    )  # concept, system, person, technology, pattern


class Entity(EntityBase):
    id: Optional[str] = Field(
        None, max_length=36
    )  # Optional for creation, always present in response


# Decision source types
class DecisionSource:
    CLAUDE_LOGS = "claude_logs"  # Extracted from Claude Code conversation logs
    INTERVIEW = "interview"  # Captured via AI-guided interview
    MANUAL = "manual"  # Manually entered by user
    UNKNOWN = "unknown"  # Legacy or untagged decisions


# Verbatim grounding (CogCanvas-inspired) - stores exact text quotes with offsets
class TextSpan(BaseModel):
    """Represents a verbatim text span from the original conversation."""
    text: str = Field(..., description="Exact verbatim text from conversation")
    start_char: int = Field(..., ge=0, description="Character offset start in conversation")
    end_char: int = Field(..., ge=0, description="Character offset end in conversation")
    turn_index: int = Field(..., ge=0, description="Which conversation turn (0-indexed)")


# Decision schemas
class DecisionBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    trigger: str = Field(..., min_length=1, max_length=5000)
    context: str = Field(..., min_length=1, max_length=10000)
    options: list[str] = Field(..., min_length=1, max_length=50)
    agent_decision: str = Field(
        ..., min_length=1, max_length=5000,
        alias="decision", serialization_alias="agent_decision",
    )
    agent_rationale: str = Field(
        ..., min_length=1, max_length=10000,
        alias="rationale", serialization_alias="agent_rationale",
    )
    human_decision: Optional[str] = Field(None, max_length=5000)
    human_rationale: Optional[str] = Field(None, max_length=10000)

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        """Validate each option string."""
        if not v:
            raise ValueError("At least one option is required")
        validated = []
        for opt in v:
            if not opt or len(opt) > 1000:
                raise ValueError("Each option must be 1-1000 characters")
            validated.append(opt.strip())
        return validated


class Decision(DecisionBase):
    id: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: datetime
    entities: list[Entity]
    source: str = DecisionSource.UNKNOWN  # Where this decision came from
    project_name: Optional[str] = None  # Project this decision belongs to

    # Verbatim grounding fields (CogCanvas-inspired, RQ1 enhancement)
    verbatim_quote: Optional[str] = Field(None, description="Exact verbatim quote from conversation")
    verbatim_start_char: Optional[int] = Field(None, ge=0, description="Character offset start")
    verbatim_end_char: Optional[int] = Field(None, ge=0, description="Character offset end")
    turn_index: Optional[int] = Field(None, ge=0, description="Conversation turn index")

    # Scope taxonomy (Part 4.7)
    scope: Optional[DecisionScope] = Field(
        None,
        description="Hierarchical scope level that determines half-life and graph layering",
    )

    # Rationale provenance (Part 2c)
    raw_rationale: Optional[str] = Field(
        None,
        max_length=50000,
        description="Raw thinking block text used as rationale source (highest fidelity)",
    )
    rationale_author: Optional[RationaleAuthor] = Field(
        None,
        description="Who/what provided the rationale: thinking block, user, or assistant",
    )

    # Decision freshness (Part 7)
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit assumptions this decision relies on",
    )
    last_reviewed_at: Optional[datetime] = Field(
        None,
        description="When this decision was last explicitly reviewed by a developer",
    )


class DecisionCreate(DecisionBase):
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    source: str = DecisionSource.UNKNOWN
    project_name: Optional[str] = Field(None, max_length=200)

    # Verbatim grounding fields (CogCanvas-inspired, RQ1 enhancement)
    verbatim_trigger: Optional[str] = Field(None, description="Exact verbatim quote for trigger")
    verbatim_decision: Optional[str] = Field(None, description="Exact verbatim quote for decision")
    verbatim_rationale: Optional[str] = Field(None, description="Exact verbatim quote for rationale")
    trigger_span: Optional[TextSpan] = Field(None, description="Text span for trigger in conversation")
    decision_span: Optional[TextSpan] = Field(None, description="Text span for decision in conversation")
    rationale_span: Optional[TextSpan] = Field(None, description="Text span for rationale in conversation")
    turn_index: Optional[int] = Field(None, ge=0, description="Conversation turn index where decision was made")

    # Scope taxonomy (Part 4.7)
    scope: Optional[DecisionScope] = Field(
        None,
        description="Hierarchical scope level — extracted by LLM, determines half-life",
    )

    # Rationale provenance (Part 2c)
    raw_rationale: Optional[str] = Field(
        None,
        max_length=50000,
        description="Raw thinking block text from which rationale was extracted",
    )
    rationale_author: Optional[RationaleAuthor] = Field(
        None,
        description="Who provided the rationale: thinking, user, or assistant",
    )

    # Decision freshness (Part 7)
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit assumptions this decision relies on (extracted by LLM)",
    )


class DecisionUpdate(BaseModel):
    """Schema for updating a decision.

    All fields are optional - only provided fields will be updated.
    Entity management is handled separately via entity linking endpoints.
    """

    model_config = ConfigDict(populate_by_name=True)

    trigger: Optional[str] = Field(None, min_length=1, max_length=5000)
    context: Optional[str] = Field(None, min_length=1, max_length=10000)
    options: Optional[list[str]] = Field(None, min_length=1, max_length=50)
    agent_decision: Optional[str] = Field(
        None, min_length=1, max_length=5000, alias="decision",
    )
    agent_rationale: Optional[str] = Field(
        None, min_length=1, max_length=10000, alias="rationale",
    )
    human_decision: Optional[str] = Field(None, max_length=5000)
    human_rationale: Optional[str] = Field(None, max_length=10000)
    
    # Verbatim grounding fields (optional updates)
    verbatim_quote: Optional[str] = Field(None, max_length=10000)
    verbatim_start_char: Optional[int] = Field(None, ge=0)
    verbatim_end_char: Optional[int] = Field(None, ge=0)
    turn_index: Optional[int] = Field(None, ge=0)

    # Scope + freshness updates
    scope: Optional[DecisionScope] = None
    assumptions: Optional[list[str]] = Field(None, description="Updated assumptions list")
    last_reviewed_at: Optional[datetime] = Field(
        None,
        description="Set to now() when developer explicitly reviews this decision",
    )

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str] | None) -> list[str] | None:
        """Validate each option string if provided."""
        if v is None:
            return None
        if not v:
            raise ValueError("At least one option is required when updating options")
        validated = []
        for opt in v:
            if not opt or len(opt) > 1000:
                raise ValueError("Each option must be 1-1000 characters")
            validated.append(opt.strip())
        return validated


# Graph schemas
class GraphNode(BaseModel):
    id: str
    type: str  # decision, entity
    label: str
    data: dict
    has_embedding: bool = False


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship: str
    weight: Optional[float] = Field(None, ge=0.0, le=1.0)  # Confidence/similarity score


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# Enhanced relationship types
class RelationshipType:
    # Decision -> Entity
    INVOLVES = "INVOLVES"

    # Decision -> Decision
    SIMILAR_TO = "SIMILAR_TO"
    SUPERSEDES = "SUPERSEDES"
    INFLUENCED_BY = "INFLUENCED_BY"
    CONTRADICTS = "CONTRADICTS"

    # Entity -> Entity
    IS_A = "IS_A"
    PART_OF = "PART_OF"
    RELATED_TO = "RELATED_TO"
    DEPENDS_ON = "DEPENDS_ON"

    # Codebase connectivity (Part 4.1 / 4.2 / 4.3)
    AFFECTS = "AFFECTS"             # Decision/CommitNode -> CodeEntity
    IMPLEMENTED_BY = "IMPLEMENTED_BY"  # Decision -> CommitNode
    TOUCHES = "TOUCHES"             # CommitNode -> CodeEntity
    REJECTED_BY = "REJECTED_BY"     # CandidateDecision -> DecisionTrace


# Semantic search schemas
class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=100)
    threshold: float = Field(0.5, ge=0.0, le=1.0)
    include_entities: bool = True


class SimilarDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    trigger: str
    agent_decision: str = Field(alias="decision", serialization_alias="agent_decision")
    similarity: float = Field(..., ge=0.0, le=1.0)
    shared_entities: list[str] = []


class EntityRelationship(BaseModel):
    source_id: str
    source_name: str
    target_id: str
    target_name: str
    relationship: str
    confidence: float = Field(1.0, ge=0.0, le=1.0)


# Capture session schemas
class CaptureMessageBase(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=50000)


class CaptureMessage(CaptureMessageBase):
    id: str
    timestamp: datetime
    extracted_entities: Optional[list[Entity]] = None


class CaptureSessionBase(BaseModel):
    status: str = Field("active", pattern=r"^(active|completed|cancelled)$")


class CaptureSession(CaptureSessionBase):
    id: str
    created_at: datetime
    updated_at: datetime
    messages: list[CaptureMessage] = []


# Dashboard schemas
class DashboardStats(BaseModel):
    total_decisions: int = Field(..., ge=0)
    total_entities: int = Field(..., ge=0)
    total_sessions: int = Field(..., ge=0)
    needs_review: int = Field(0, ge=0)
    recent_decisions: list[Decision]


# Ingestion schemas
class IngestionStatus(BaseModel):
    is_watching: bool
    last_run: Optional[datetime]
    files_processed: int = Field(..., ge=0)


class IngestionResult(BaseModel):
    status: str
    processed: int = Field(..., ge=0)
    decisions_extracted: int = Field(..., ge=0)


# Search schemas
class SearchResult(BaseModel):
    type: str  # decision, entity
    id: str
    label: str
    score: float = Field(..., ge=0.0, le=1.0)
    data: dict


# Entity linking schemas (SEC-005: Hardened with validation)
class LinkEntityRequest(BaseModel):
    """Request to link an entity to a decision.

    SEC-005: All fields are validated to prevent injection and ensure data integrity.
    """

    decision_id: str = Field(
        ..., min_length=36, max_length=36, description="UUID of the decision to link to"
    )
    entity_id: str = Field(
        ..., min_length=36, max_length=36, description="UUID of the entity to link"
    )
    relationship: str = Field(
        default="INVOLVES", max_length=50, description="Type of relationship"
    )

    @field_validator("decision_id")
    @classmethod
    def validate_decision_id(cls, v: str) -> str:
        """Validate decision_id is a proper UUID (SEC-005)."""
        return validate_uuid(v, "decision_id")

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, v: str) -> str:
        """Validate entity_id is a proper UUID (SEC-005)."""
        return validate_uuid(v, "entity_id")

    @field_validator("relationship")
    @classmethod
    def validate_relationship(cls, v: str) -> str:
        """Validate relationship is in the allowed list (SEC-005)."""
        v_upper = v.upper()
        if v_upper not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Invalid relationship type: '{v}'. "
                f"Allowed types: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}"
            )
        return v_upper


class SuggestEntitiesRequest(BaseModel):
    """Request to get entity suggestions from text."""

    text: str = Field(..., min_length=1, max_length=10000)


# Hybrid search schemas (KG-P1-3)
class HybridSearchRequest(BaseModel):
    """Request for hybrid search combining lexical and semantic search.

    Hybrid search combines:
    - Lexical search (fulltext index) - good for exact matches and keywords
    - Semantic search (vector similarity) - good for meaning and concepts
    - Graph expansion (optional) - expands via relationships for better recall

    Final score = alpha * lexical_score + (1 - alpha) * semantic_score
    """

    query: str = Field(..., min_length=1, max_length=2000, description="Search query")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    threshold: float = Field(
        0.3, ge=0.0, le=1.0, description="Minimum combined score threshold"
    )
    alpha: float = Field(
        0.3,
        ge=0.0,
        le=1.0,
        description="Weight for lexical score (0.3 = 30% lexical, 70% semantic)",
    )
    include_entities: bool = Field(
        True, description="Include entities in search results"
    )
    search_decisions: bool = Field(True, description="Search decision nodes")
    search_entities: bool = Field(True, description="Search entity nodes")
    graph_depth: int = Field(
        0, ge=0, le=2, description="Graph expansion depth (0=none, 1=1-hop, 2=2-hop)"
    )


class HybridSearchResult(BaseModel):
    """Result from hybrid search with score breakdown."""

    id: str
    type: str  # "decision" or "entity"
    label: str
    lexical_score: float = Field(..., ge=0.0, le=1.0)
    semantic_score: float = Field(..., ge=0.0, le=1.0)
    combined_score: float = Field(..., ge=0.0, le=1.0)
    data: dict
    matched_fields: list[str] = Field(
        default_factory=list, description="Fields that matched lexically"
    )


# Graph Pagination schemas (SD-003)
class PaginationMeta(BaseModel):
    """Pagination metadata for paginated responses."""

    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, le=500, description="Number of items per page")
    total_count: int = Field(..., ge=0, description="Total number of items")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    has_more: bool = Field(..., description="Whether there are more pages")


class PaginatedGraphData(BaseModel):
    """Paginated graph data response.

    Returns decisions first in pages. Entities connected to the returned
    decisions are included. For large graphs, use lazy loading via
    /graph/nodes/{node_id}/neighbors endpoint.
    """

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    pagination: PaginationMeta


class NeighborNode(BaseModel):
    """A neighbor node with its connecting relationship."""

    node: GraphNode
    relationship: str
    direction: str = Field(
        ...,
        pattern=r"^(incoming|outgoing)$",
        description="Direction relative to source node",
    )
    weight: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Relationship weight/score"
    )


class NeighborsResponse(BaseModel):
    """Response for neighbor nodes of a given node."""

    source_node_id: str
    neighbors: list[NeighborNode]
    total_count: int = Field(..., ge=0, description="Total number of neighbors")


# =============================================================================
# Agent Context API schemas
# =============================================================================


class AgentContextRequest(BaseModel):
    """Request for focused context query from the knowledge graph."""

    query: str = Field(..., min_length=1, max_length=2000, description="Natural language query")
    max_decisions: int = Field(10, ge=1, le=50, description="Max decisions to return")
    max_tokens: int = Field(4000, ge=500, le=16000, description="Approx token budget for response")
    include_evolution: bool = Field(True, description="Include SUPERSEDES/CONTRADICTS chains")
    include_entities: bool = Field(True, description="Include related entities")
    format: Literal["json", "markdown"] = Field("json", description="Response format")
    project_filter: Optional[str] = Field(None, max_length=200, description="Filter by project")


class AgentDecisionSummary(BaseModel):
    """Compact decision representation for agent consumption."""

    id: str
    trigger: str
    decision: str
    rationale: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: Optional[str] = None
    source: Optional[str] = None
    relevance_score: float = Field(0.0, ge=0.0, le=1.0, description="How relevant to the query")
    is_current: bool = Field(True, description="False if superseded by another decision")
    entities: list[str] = Field(default_factory=list)


class AgentEntitySummary(BaseModel):
    """Compact entity representation for agent consumption."""

    name: str
    type: str
    decision_count: int = Field(0, ge=0)
    related_entities: list[str] = Field(default_factory=list)


class EvolutionChain(BaseModel):
    """A chain of decisions showing how a topic evolved."""

    chain_type: Literal["supersedes", "contradicts"]
    decisions: list[AgentDecisionSummary]
    reasoning: Optional[str] = None


class AgentContextResponse(BaseModel):
    """Focused context package for agent consumption."""

    query: str
    decisions: list[AgentDecisionSummary]
    entities: list[AgentEntitySummary] = Field(default_factory=list)
    evolution_chains: list[EvolutionChain] = Field(default_factory=list)
    contradictions: list[dict] = Field(default_factory=list, description="Unresolved contradictions")
    total_decisions_searched: int = 0
    markdown: Optional[str] = Field(None, description="Markdown rendering if format=markdown")


class AgentEntityContextResponse(BaseModel):
    """Everything about a specific entity for agent consumption."""

    name: str
    type: str
    aliases: list[str] = Field(default_factory=list)
    decisions: list[AgentDecisionSummary]
    related_entities: list[AgentEntitySummary] = Field(default_factory=list)
    timeline: list[dict] = Field(default_factory=list, description="Chronological decision history")
    current_status: Optional[str] = Field(None, description="Whether actively used or superseded")


class AgentCheckRequest(BaseModel):
    """Request to check prior art before making a decision."""

    proposed_decision: str = Field(..., min_length=1, max_length=5000)
    context: str = Field("", max_length=10000)
    entities: list[str] = Field(default_factory=list, max_length=20)
    threshold: float = Field(0.5, ge=0.0, le=1.0, description="Similarity threshold")


class AbandonedPattern(BaseModel):
    """A decision that was tried and superseded."""

    original_decision: AgentDecisionSummary
    superseded_by: AgentDecisionSummary
    reasoning: Optional[str] = None


class AgentCheckResponse(BaseModel):
    """Prior art check results."""

    proposed_decision: str
    similar_decisions: list[AgentDecisionSummary]
    abandoned_patterns: list[AbandonedPattern] = Field(default_factory=list)
    contradictions: list[AgentDecisionSummary] = Field(default_factory=list)
    recommendation: Literal["proceed", "review_similar", "resolve_contradiction"]
    recommendation_reason: str


class AgentRememberRequest(BaseModel):
    """Request to record an agent-made decision."""

    model_config = ConfigDict(populate_by_name=True)

    trigger: str = Field(..., min_length=1, max_length=5000)
    context: str = Field(..., min_length=1, max_length=10000)
    options: list[str] = Field(..., min_length=1, max_length=50)
    decision: str = Field(..., min_length=1, max_length=5000)
    rationale: str = Field(..., min_length=1, max_length=10000)
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    entities: list[str] = Field(default_factory=list, max_length=30, description="Known entity names")
    agent_name: str = Field("unknown-agent", max_length=100)
    project_name: Optional[str] = Field(None, max_length=200)

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one option is required")
        return [opt.strip() for opt in v if opt and len(opt) <= 1000]


class AgentRememberResponse(BaseModel):
    """Response after recording an agent decision."""

    decision_id: str
    entities_extracted: list[str]
    similar_existing: list[AgentDecisionSummary] = Field(default_factory=list)
    potential_supersedes: list[str] = Field(default_factory=list, description="IDs of possibly superseded decisions")
    potential_contradicts: list[str] = Field(default_factory=list, description="IDs of possibly contradicting decisions")


class AgentSummaryResponse(BaseModel):
    """High-level architectural overview for agent bootstrapping."""

    total_decisions: int = 0
    total_entities: int = 0
    top_technologies: list[AgentEntitySummary] = Field(default_factory=list)
    top_decisions: list[AgentDecisionSummary] = Field(default_factory=list)
    unresolved_contradictions: list[dict] = Field(default_factory=list)
    knowledge_gaps: list[dict] = Field(default_factory=list, description="Areas with few decisions")
    project_name: Optional[str] = None
