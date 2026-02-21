"""API Contract Test Schemas.

QA-P2-2: Pydantic schemas for validating API responses.
These schemas define the contract that clients depend on.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, RootModel


# Dashboard Stats Schema
class DashboardStatsSchema(BaseModel):
    """Expected schema for GET /api/dashboard/stats response."""

    total_decisions: int = Field(..., ge=0)
    total_entities: int = Field(..., ge=0)
    total_sessions: int = Field(..., ge=0)
    recent_decisions: list["DecisionSchema"]


# Entity Schema
class EntitySchema(BaseModel):
    """Expected schema for entity objects."""

    id: Optional[str] = None
    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)


# Decision Schema
class DecisionSchema(BaseModel):
    """Expected schema for decision objects."""

    id: str
    trigger: str
    context: str
    options: list[str]
    decision: str
    rationale: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: datetime
    entities: list[EntitySchema]
    source: str = "unknown"


class DecisionListSchema(RootModel[list[DecisionSchema]]):
    """Expected schema for GET /api/decisions response."""

    pass


# Graph Schemas
class GraphNodeSchema(BaseModel):
    """Expected schema for graph node objects."""

    id: str
    type: str  # "decision" or "entity"
    label: str
    data: dict[str, Any]
    has_embedding: bool = False


class GraphEdgeSchema(BaseModel):
    """Expected schema for graph edge objects."""

    id: str
    source: str
    target: str
    relationship: str
    weight: Optional[float] = Field(None, ge=0.0, le=1.0)


class PaginationMetaSchema(BaseModel):
    """Expected schema for pagination metadata."""

    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=500)
    total_count: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)
    has_more: bool


class PaginatedGraphDataSchema(BaseModel):
    """Expected schema for GET /api/graph response."""

    nodes: list[GraphNodeSchema]
    edges: list[GraphEdgeSchema]
    pagination: PaginationMetaSchema


class GraphDataSchema(BaseModel):
    """Expected schema for GET /api/graph/all response."""

    nodes: list[GraphNodeSchema]
    edges: list[GraphEdgeSchema]


# Search Schemas
class SimilarDecisionSchema(BaseModel):
    """Expected schema for similar decision results."""

    id: str
    trigger: str
    decision: str
    similarity: float = Field(..., ge=0.0, le=1.0)
    shared_entities: list[str] = []


class HybridSearchResultSchema(BaseModel):
    """Expected schema for hybrid search results."""

    id: str
    type: str
    label: str
    lexical_score: float = Field(..., ge=0.0, le=1.0)
    semantic_score: float = Field(..., ge=0.0, le=1.0)
    combined_score: float = Field(..., ge=0.0, le=1.0)
    data: dict[str, Any]
    matched_fields: list[str] = []


# Validation Schemas
class ValidationIssueSchema(BaseModel):
    """Expected schema for validation issue objects."""

    type: str
    severity: str  # "error", "warning", "info"
    message: str
    affected_nodes: list[str]
    suggested_action: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class ValidationSummarySchema(BaseModel):
    """Expected schema for GET /api/graph/validate response."""

    total_issues: int = Field(..., ge=0)
    by_severity: dict[str, int]
    by_type: dict[str, int]
    issues: list[ValidationIssueSchema]


# Graph Stats Schema
class GraphStatsSchema(BaseModel):
    """Expected schema for GET /api/graph/stats response."""

    decisions: dict[str, int]  # {total, with_embeddings}
    entities: dict[str, int]  # {total, with_embeddings}
    relationships: int


# Error Response Schema
class ErrorResponseSchema(BaseModel):
    """Expected schema for error responses."""

    detail: str


# Timeline Schemas
class TimelineEntrySchema(BaseModel):
    """Expected schema for timeline entries."""

    id: str
    trigger: str
    decision: str
    rationale: Optional[str] = None
    created_at: Optional[str] = None
    source: Optional[str] = None
    supersedes: list[str] = []
    conflicts_with: list[str] = []


# Capture Session Schemas
class CaptureMessageSchema(BaseModel):
    """Expected schema for capture messages."""

    id: str
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime
    extracted_entities: Optional[list[EntitySchema]] = None


class CaptureSessionSchema(BaseModel):
    """Expected schema for capture session objects."""

    id: str
    status: str  # "active", "completed", "cancelled"
    created_at: datetime
    updated_at: datetime
    messages: list[CaptureMessageSchema] = []


# Ingestion Schemas
class IngestionStatusSchema(BaseModel):
    """Expected schema for ingestion status."""

    is_watching: bool
    last_run: Optional[datetime] = None
    files_processed: int = Field(..., ge=0)


class IngestionResultSchema(BaseModel):
    """Expected schema for ingestion results."""

    status: str
    processed: int = Field(..., ge=0)
    decisions_extracted: int = Field(..., ge=0)
