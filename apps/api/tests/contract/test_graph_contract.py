"""Contract Tests for Graph API.

QA-P2-2: Tests that /api/graph responses match expected schema.
"""

import pytest
from pydantic import ValidationError

from tests.contract.schemas import (
    GraphDataSchema,
    GraphEdgeSchema,
    GraphNodeSchema,
    GraphStatsSchema,
    HybridSearchResultSchema,
    PaginatedGraphDataSchema,
    PaginationMetaSchema,
    SimilarDecisionSchema,
    ValidationIssueSchema,
    ValidationSummarySchema,
)


class TestGraphContract:
    """Contract tests for /api/graph endpoints."""

    def test_graph_node_decision_schema(self):
        """Test that decision node data passes schema validation."""
        valid_node = {
            "id": "decision-123",
            "type": "decision",
            "label": "Choose database",
            "has_embedding": True,
            "data": {
                "trigger": "Need database",
                "context": "Building app",
                "options": ["A", "B"],
                "decision": "A",
                "rationale": "Better fit",
                "confidence": 0.9,
                "created_at": "2026-01-30T12:00:00Z",
                "source": "manual",
            },
        }

        schema = GraphNodeSchema(**valid_node)
        assert schema.id == "decision-123"
        assert schema.type == "decision"
        assert schema.has_embedding is True

    def test_graph_node_entity_schema(self):
        """Test that entity node data passes schema validation."""
        valid_node = {
            "id": "entity-456",
            "type": "entity",
            "label": "PostgreSQL",
            "has_embedding": False,
            "data": {
                "name": "PostgreSQL",
                "type": "technology",
                "aliases": ["postgres", "pg"],
            },
        }

        schema = GraphNodeSchema(**valid_node)
        assert schema.id == "entity-456"
        assert schema.type == "entity"
        assert schema.has_embedding is False

    def test_graph_edge_schema(self):
        """Test that edge data passes schema validation."""
        valid_edge = {
            "id": "edge-1",
            "source": "decision-123",
            "target": "entity-456",
            "relationship": "INVOLVES",
            "weight": 0.95,
        }

        schema = GraphEdgeSchema(**valid_edge)
        assert schema.id == "edge-1"
        assert schema.relationship == "INVOLVES"
        assert schema.weight == 0.95

    def test_graph_edge_weight_optional(self):
        """Test that edge weight is optional."""
        edge_without_weight = {
            "id": "edge-1",
            "source": "node-1",
            "target": "node-2",
            "relationship": "RELATED_TO",
        }

        schema = GraphEdgeSchema(**edge_without_weight)
        assert schema.weight is None

    def test_graph_edge_weight_validation(self):
        """Test that edge weight must be 0.0-1.0."""
        invalid_edge = {
            "id": "edge-1",
            "source": "node-1",
            "target": "node-2",
            "relationship": "SIMILAR_TO",
            "weight": 1.5,  # Invalid
        }

        with pytest.raises(ValidationError):
            GraphEdgeSchema(**invalid_edge)

    def test_pagination_meta_schema(self):
        """Test that pagination metadata passes validation."""
        valid_pagination = {
            "page": 1,
            "page_size": 100,
            "total_count": 250,
            "total_pages": 3,
            "has_more": True,
        }

        schema = PaginationMetaSchema(**valid_pagination)
        assert schema.page == 1
        assert schema.total_pages == 3
        assert schema.has_more is True

    def test_pagination_page_minimum(self):
        """Test that page must be >= 1."""
        invalid_pagination = {
            "page": 0,  # Invalid
            "page_size": 100,
            "total_count": 100,
            "total_pages": 1,
            "has_more": False,
        }

        with pytest.raises(ValidationError):
            PaginationMetaSchema(**invalid_pagination)

    def test_pagination_page_size_maximum(self):
        """Test that page_size has maximum of 500."""
        invalid_pagination = {
            "page": 1,
            "page_size": 1000,  # Invalid - exceeds 500
            "total_count": 100,
            "total_pages": 1,
            "has_more": False,
        }

        with pytest.raises(ValidationError):
            PaginationMetaSchema(**invalid_pagination)

    def test_paginated_graph_data_schema(self):
        """Test that paginated graph response passes validation."""
        valid_response = {
            "nodes": [
                {
                    "id": "node-1",
                    "type": "decision",
                    "label": "Test",
                    "has_embedding": True,
                    "data": {"trigger": "Test"},
                },
            ],
            "edges": [
                {
                    "id": "edge-1",
                    "source": "node-1",
                    "target": "node-2",
                    "relationship": "INVOLVES",
                    "weight": 0.8,
                },
            ],
            "pagination": {
                "page": 1,
                "page_size": 100,
                "total_count": 50,
                "total_pages": 1,
                "has_more": False,
            },
        }

        schema = PaginatedGraphDataSchema(**valid_response)
        assert len(schema.nodes) == 1
        assert len(schema.edges) == 1
        assert schema.pagination.total_count == 50

    def test_graph_data_schema(self):
        """Test that non-paginated graph response passes validation."""
        valid_response = {
            "nodes": [
                {
                    "id": "node-1",
                    "type": "decision",
                    "label": "Test",
                    "has_embedding": False,
                    "data": {},
                },
                {
                    "id": "node-2",
                    "type": "entity",
                    "label": "PostgreSQL",
                    "has_embedding": True,
                    "data": {"name": "PostgreSQL", "type": "technology"},
                },
            ],
            "edges": [],
        }

        schema = GraphDataSchema(**valid_response)
        assert len(schema.nodes) == 2
        assert len(schema.edges) == 0

    def test_graph_stats_schema(self):
        """Test that graph stats response passes validation."""
        valid_stats = {
            "decisions": {
                "total": 100,
                "with_embeddings": 95,
            },
            "entities": {
                "total": 250,
                "with_embeddings": 200,
            },
            "relationships": 500,
        }

        schema = GraphStatsSchema(**valid_stats)
        assert schema.decisions["total"] == 100
        assert schema.entities["with_embeddings"] == 200
        assert schema.relationships == 500

    def test_validation_summary_schema(self):
        """Test that validation response passes schema validation."""
        valid_summary = {
            "total_issues": 3,
            "by_severity": {
                "error": 1,
                "warning": 2,
                "info": 0,
            },
            "by_type": {
                "circular_dependency": 1,
                "orphan_entity": 2,
            },
            "issues": [
                {
                    "type": "circular_dependency",
                    "severity": "error",
                    "message": "Circular dependency detected: A -> B -> A",
                    "affected_nodes": ["node-a", "node-b"],
                    "suggested_action": "Remove one of the edges",
                    "details": {"cycle": ["A", "B", "A"]},
                },
                {
                    "type": "orphan_entity",
                    "severity": "warning",
                    "message": "Entity has no connections",
                    "affected_nodes": ["orphan-1"],
                },
            ],
        }

        schema = ValidationSummarySchema(**valid_summary)
        assert schema.total_issues == 3
        assert len(schema.issues) == 2
        assert schema.issues[0].severity == "error"

    def test_validation_issue_optional_fields(self):
        """Test that validation issue optional fields work."""
        minimal_issue = {
            "type": "missing_embedding",
            "severity": "info",
            "message": "Node has no embedding",
            "affected_nodes": ["node-1"],
        }

        schema = ValidationIssueSchema(**minimal_issue)
        assert schema.suggested_action is None
        assert schema.details is None

    def test_hybrid_search_result_schema(self):
        """Test that hybrid search result passes validation."""
        valid_result = {
            "id": "decision-123",
            "type": "decision",
            "label": "Database selection",
            "lexical_score": 0.8,
            "semantic_score": 0.9,
            "combined_score": 0.87,
            "data": {
                "trigger": "Need database",
                "decision": "PostgreSQL",
            },
            "matched_fields": ["trigger", "decision"],
        }

        schema = HybridSearchResultSchema(**valid_result)
        assert schema.combined_score == 0.87
        assert len(schema.matched_fields) == 2

    def test_hybrid_search_scores_validation(self):
        """Test that search scores must be 0.0-1.0."""
        invalid_result = {
            "id": "test",
            "type": "decision",
            "label": "Test",
            "lexical_score": 1.5,  # Invalid
            "semantic_score": 0.5,
            "combined_score": 0.7,
            "data": {},
        }

        with pytest.raises(ValidationError):
            HybridSearchResultSchema(**invalid_result)

    def test_similar_decision_schema(self):
        """Test that similar decision result passes validation."""
        valid_result = {
            "id": "decision-456",
            "trigger": "Choose caching strategy",
            "decision": "Use Redis",
            "similarity": 0.85,
            "shared_entities": ["Redis", "Cache"],
        }

        schema = SimilarDecisionSchema(**valid_result)
        assert schema.similarity == 0.85
        assert len(schema.shared_entities) == 2

    def test_similar_decision_empty_shared_entities(self):
        """Test that empty shared_entities list is valid."""
        valid_result = {
            "id": "decision-789",
            "trigger": "Unrelated decision",
            "decision": "Something else",
            "similarity": 0.5,
        }

        schema = SimilarDecisionSchema(**valid_result)
        assert schema.shared_entities == []

    def test_graph_node_requires_id(self):
        """Test that graph node requires id field."""
        missing_id = {
            "type": "decision",
            "label": "Test",
            "has_embedding": True,
            "data": {},
        }

        with pytest.raises(ValidationError):
            GraphNodeSchema(**missing_id)

    def test_graph_edge_requires_relationship(self):
        """Test that graph edge requires relationship field."""
        missing_relationship = {
            "id": "edge-1",
            "source": "node-1",
            "target": "node-2",
        }

        with pytest.raises(ValidationError):
            GraphEdgeSchema(**missing_relationship)

    def test_valid_relationship_types(self):
        """Test that all valid relationship types are accepted."""
        valid_relationships = [
            "INVOLVES",
            "SIMILAR_TO",
            "SUPERSEDES",
            "INFLUENCED_BY",
            "CONTRADICTS",
            "IS_A",
            "PART_OF",
            "RELATED_TO",
            "DEPENDS_ON",
            "ALTERNATIVE_TO",
        ]

        base_edge = {
            "id": "edge-1",
            "source": "node-1",
            "target": "node-2",
        }

        for rel_type in valid_relationships:
            edge = {**base_edge, "relationship": rel_type}
            schema = GraphEdgeSchema(**edge)
            assert schema.relationship == rel_type
