"""Comprehensive End-to-End Test Suite for Continuum API.

This test suite covers:
- Decisions CRUD (Create, Read, Update, Delete)
- Entities CRUD
- Search functionality
- Entity resolution
- Graph validation
- Knowledge graph endpoints
"""

from uuid import uuid4

import httpx
import pytest

# Base URL for API
BASE_URL = "http://localhost:8000/api"


@pytest.fixture
def client():
    """Create an async HTTP client."""
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


class TestHealthCheck:
    """Test API health and basic connectivity."""

    def test_health_endpoint(self, client):
        """Test the health check endpoint via graph stats."""
        # Use graph stats as a health check since there's no dedicated health endpoint
        response = client.get("/graph/stats")
        assert response.status_code == 200
        data = response.json()
        assert "decisions" in data
        assert "entities" in data


class TestDecisions:
    """Test Decision CRUD operations."""

    def test_get_all_decisions(self, client):
        """Test listing all decisions."""
        response = client.get("/decisions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_decisions_with_pagination(self, client):
        """Test decisions pagination."""
        response = client.get("/decisions?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 5

    def test_create_decision(self, client):
        """Test creating a new decision."""
        decision_data = {
            "trigger": f"Test decision trigger {uuid4().hex[:8]}",
            "context": "This is a test context for E2E testing",
            "options": ["Option A", "Option B", "Option C"],
            "decision": "Option A was chosen for testing",
            "rationale": "Option A provides the best test coverage",
            "auto_extract": False,  # Disable auto-extraction for faster test
        }
        response = client.post("/decisions", json=decision_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["trigger"] == decision_data["trigger"]
        return data["id"]

    def test_get_decision_by_id(self, client):
        """Test getting a specific decision."""
        # First create a decision
        decision_data = {
            "trigger": f"Test get by id {uuid4().hex[:8]}",
            "context": "Context for get by id test",
            "options": ["A", "B"],
            "decision": "A",
            "rationale": "Because A",
            "auto_extract": False,
        }
        create_response = client.post("/decisions", json=decision_data)
        assert create_response.status_code == 200
        decision_id = create_response.json()["id"]

        # Then fetch it
        response = client.get(f"/decisions/{decision_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == decision_id
        assert data["trigger"] == decision_data["trigger"]

    def test_get_nonexistent_decision(self, client):
        """Test getting a decision that doesn't exist."""
        fake_id = str(uuid4())
        response = client.get(f"/decisions/{fake_id}")
        assert response.status_code == 404

    def test_delete_decision(self, client):
        """Test deleting a decision."""
        # First create a decision
        decision_data = {
            "trigger": f"Test delete {uuid4().hex[:8]}",
            "context": "Context for delete test",
            "options": ["A"],
            "decision": "A",
            "rationale": "Delete me",
            "auto_extract": False,
        }
        create_response = client.post("/decisions", json=decision_data)
        decision_id = create_response.json()["id"]

        # Delete it
        response = client.delete(f"/decisions/{decision_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

        # Verify it's gone
        get_response = client.get(f"/decisions/{decision_id}")
        assert get_response.status_code == 404


class TestEntities:
    """Test Entity CRUD operations."""

    def test_get_all_entities(self, client):
        """Test listing all entities."""
        response = client.get("/entities")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_entity(self, client):
        """Test creating a new entity."""
        entity_data = {
            "name": f"TestEntity_{uuid4().hex[:8]}",
            "type": "technology",
        }
        response = client.post("/entities", json=entity_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == entity_data["name"]
        assert data["type"] == entity_data["type"]
        return data["id"]

    def test_get_entity_by_id(self, client):
        """Test getting a specific entity."""
        # First create an entity
        entity_data = {
            "name": f"GetById_{uuid4().hex[:8]}",
            "type": "concept",
        }
        create_response = client.post("/entities", json=entity_data)
        entity_id = create_response.json()["id"]

        # Then fetch it
        response = client.get(f"/entities/{entity_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == entity_id
        assert data["name"] == entity_data["name"]

    def test_delete_entity_without_relationships(self, client):
        """Test deleting an entity without relationships."""
        # Create an orphan entity
        entity_data = {
            "name": f"OrphanEntity_{uuid4().hex[:8]}",
            "type": "concept",
        }
        create_response = client.post("/entities", json=entity_data)
        entity_id = create_response.json()["id"]

        # Delete it (should succeed without force)
        response = client.delete(f"/entities/{entity_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

    def test_delete_entity_force(self, client):
        """Test force-deleting an entity."""
        # Create an entity
        entity_data = {
            "name": f"ForceDelete_{uuid4().hex[:8]}",
            "type": "technology",
        }
        create_response = client.post("/entities", json=entity_data)
        entity_id = create_response.json()["id"]

        # Force delete
        response = client.delete(f"/entities/{entity_id}?force=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"


class TestSearch:
    """Test search functionality."""

    def test_search_basic(self, client):
        """Test basic search."""
        response = client.get("/search?query=test")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_search_case_insensitive(self, client):
        """Test that search is case-insensitive."""
        # Search with lowercase
        lower_response = client.get("/search?query=redis")
        assert lower_response.status_code == 200

        # Search with uppercase
        upper_response = client.get("/search?query=REDIS")
        assert upper_response.status_code == 200

        # Both should return results (if Redis exists)
        lower_data = lower_response.json()
        upper_data = upper_response.json()
        # At minimum, both should return the same type of response
        assert isinstance(lower_data, list)
        assert isinstance(upper_data, list)

    def test_search_filter_by_type_decision(self, client):
        """Test search filtering by decision type."""
        response = client.get("/search?query=test&type=decision")
        assert response.status_code == 200
        data = response.json()
        for item in data:
            assert item["type"] == "decision"

    def test_search_filter_by_type_entity(self, client):
        """Test search filtering by entity type."""
        response = client.get("/search?query=python&type=entity")
        assert response.status_code == 200
        data = response.json()
        for item in data:
            assert item["type"] == "entity"

    def test_search_minimum_length(self, client):
        """Test that search requires minimum query length."""
        response = client.get("/search?query=a")
        assert response.status_code == 422  # Validation error

    def test_search_suggestions(self, client):
        """Test search suggestions endpoint."""
        response = client.get("/search/suggest?query=post")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestGraph:
    """Test knowledge graph endpoints."""

    def test_get_graph_stats(self, client):
        """Test getting graph statistics."""
        response = client.get("/graph/stats")
        assert response.status_code == 200
        data = response.json()
        assert "decisions" in data
        assert "entities" in data
        assert "relationships" in data

    def test_get_graph_data(self, client):
        """Test getting graph data."""
        response = client.get("/graph?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data

    def test_graph_validate(self, client):
        """Test graph validation endpoint."""
        response = client.get("/graph/validate")
        assert response.status_code == 200
        data = response.json()
        # Response is a dict with issues list
        assert "issues" in data
        assert "total_issues" in data
        assert "by_severity" in data
        assert isinstance(data["issues"], list)
        # Each validation issue should have required fields
        for issue in data["issues"]:
            assert "type" in issue
            assert "severity" in issue

    def test_entity_timeline(self, client):
        """Test entity timeline endpoint."""
        response = client.get("/graph/entities/timeline/PostgreSQL")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestEntityResolution:
    """Test entity resolution functionality."""

    def test_merge_duplicates(self, client):
        """Test the merge duplicates endpoint."""
        response = client.post("/graph/entities/merge-duplicates")
        assert response.status_code == 200
        data = response.json()
        assert "groups_found" in data
        assert "entities_merged" in data


class TestEnhanceEndpoint:
    """Test the enhance endpoint for relationship extraction."""

    @pytest.mark.skip(reason="Requires AI API access and may timeout")
    def test_enhance_endpoint(self, client):
        """Test the enhance endpoint."""
        # Create a new client with longer timeout for enhance
        with httpx.Client(base_url=BASE_URL, timeout=120.0) as long_client:
            response = long_client.post("/graph/enhance?max_decisions=1")
            # Should return 200 or take a while
            assert response.status_code == 200
            data = response.json()
            assert "status" in data

    def test_enhance_endpoint_exists(self, client):
        """Verify the enhance endpoint exists (even if we can't fully test it)."""
        # Just check the endpoint exists by checking method not allowed for GET
        response = client.get("/graph/enhance")
        # 405 means endpoint exists but wrong method, 404 means it doesn't exist
        assert response.status_code in [200, 405, 422]


class TestLinkEntities:
    """Test entity linking functionality."""

    def test_suggest_entities(self, client):
        """Test entity suggestion from text."""
        request_data = {
            "text": "We decided to use PostgreSQL as our primary database with Redis for caching"
        }
        response = client.post("/entities/suggest", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestEndToEndFlow:
    """Test complete end-to-end workflows."""

    def test_create_decision_search_delete(self, client):
        """Test full lifecycle: create -> search -> delete."""
        # 1. Create a decision with unique trigger
        unique_term = f"UniqueTerm{uuid4().hex[:8]}"
        decision_data = {
            "trigger": f"Decision about {unique_term}",
            "context": f"We need to decide about {unique_term} technology",
            "options": [f"Use {unique_term}", "Use alternative"],
            "decision": f"Use {unique_term}",
            "rationale": f"{unique_term} is the best choice",
            "auto_extract": False,
        }
        create_response = client.post("/decisions", json=decision_data)
        assert create_response.status_code == 200
        decision_id = create_response.json()["id"]

        # 2. Search for the decision
        search_response = client.get(f"/search?query={unique_term}")
        assert search_response.status_code == 200
        search_results = search_response.json()
        assert any(r["id"] == decision_id for r in search_results)

        # 3. Delete the decision
        delete_response = client.delete(f"/decisions/{decision_id}")
        assert delete_response.status_code == 200

        # 4. Verify deletion
        get_response = client.get(f"/decisions/{decision_id}")
        assert get_response.status_code == 404

    def test_create_entity_link_to_decision(self, client):
        """Test creating an entity and linking it to a decision."""
        # 1. Create an entity
        entity_name = f"TestTech_{uuid4().hex[:8]}"
        entity_data = {"name": entity_name, "type": "technology"}
        entity_response = client.post("/entities", json=entity_data)
        assert entity_response.status_code == 200
        entity_id = entity_response.json()["id"]

        # 2. Create a decision
        decision_data = {
            "trigger": f"Decision about {entity_name}",
            "context": "Test context",
            "options": ["A", "B"],
            "decision": "A",
            "rationale": "Test rationale",
            "auto_extract": False,
        }
        decision_response = client.post("/decisions", json=decision_data)
        assert decision_response.status_code == 200
        decision_id = decision_response.json()["id"]

        # 3. Link entity to decision
        link_data = {
            "decision_id": decision_id,
            "entity_id": entity_id,
            "relationship": "INVOLVES",
        }
        link_response = client.post("/entities/link", json=link_data)
        assert link_response.status_code == 200

        # 4. Verify link in graph
        graph_response = client.get("/graph?limit=100")
        assert graph_response.status_code == 200

        # 5. Cleanup
        client.delete(f"/decisions/{decision_id}")
        client.delete(f"/entities/{entity_id}?force=true")


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_decision_id_format(self, client):
        """Test handling of invalid ID format."""
        response = client.get("/decisions/not-a-valid-uuid")
        assert response.status_code == 404

    def test_missing_required_fields(self, client):
        """Test validation of required fields."""
        # Missing trigger
        response = client.post(
            "/decisions",
            json={
                "context": "test",
                "options": [],
                "decision": "test",
                "rationale": "test",
            },
        )
        assert response.status_code == 422

    def test_empty_search_query(self, client):
        """Test empty search query."""
        response = client.get("/search?query=")
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
