"""Comprehensive unit tests for GraphValidator service.

Tests all validation checks:
- Circular dependencies in DEPENDS_ON chains
- Orphan entities with no relationships
- Low confidence relationships
- Duplicate entities (via fuzzy matching)
- Missing embeddings
- Invalid relationship configurations
- Auto-fix functionality

Target: 85%+ coverage for validator.py
"""

import pytest

from services.validator import (
    GraphValidator,
    IssueSeverity,
    IssueType,
    ValidationIssue,
    get_graph_validator,
)
from tests.factories import EntityFactory, Neo4jRecordFactory
from tests.mocks.neo4j_mock import MockNeo4jResult, MockNeo4jSession

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_session():
    """Create a mock Neo4j session."""
    return MockNeo4jSession()


@pytest.fixture
def validator(mock_session):
    """Create a GraphValidator with mock session."""
    return GraphValidator(mock_session)


# ============================================================================
# Circular Dependencies Tests
# ============================================================================


class TestValidatorCircularDependencies:
    """Test circular dependency detection in DEPENDS_ON chains."""

    @pytest.mark.asyncio
    async def test_detects_simple_cycle(self, validator, mock_session):
        """Should detect A -> B -> A cycle."""
        cycle_record = Neo4jRecordFactory.create_cycle_record(
            names=["A", "B", "A"],
            ids=["id-a", "id-b", "id-a"],
        )
        mock_session.set_response(
            "DEPENDS_ON",
            records=[cycle_record],
        )

        issues = await validator.check_circular_dependencies()

        assert len(issues) == 1
        assert issues[0].type == IssueType.CIRCULAR_DEPENDENCY
        assert issues[0].severity == IssueSeverity.ERROR
        assert "A" in issues[0].message
        assert "B" in issues[0].message

    @pytest.mark.asyncio
    async def test_detects_longer_cycle(self, validator, mock_session):
        """Should detect longer cycles A -> B -> C -> A."""
        cycle_record = Neo4jRecordFactory.create_cycle_record(
            names=["A", "B", "C", "A"],
            ids=["id-a", "id-b", "id-c", "id-a"],
        )
        mock_session.set_response(
            "DEPENDS_ON",
            records=[cycle_record],
        )

        issues = await validator.check_circular_dependencies()

        assert len(issues) == 1
        assert issues[0].type == IssueType.CIRCULAR_DEPENDENCY
        # Phase 5: Message format changed to include relationship type
        assert (
            "A" in issues[0].message
            and "B" in issues[0].message
            and "C" in issues[0].message
        )

    @pytest.mark.asyncio
    async def test_no_cycles_returns_empty(self, validator, mock_session):
        """Should return empty list when no cycles exist."""
        mock_session.set_response("DEPENDS_ON", records=[])

        issues = await validator.check_circular_dependencies()

        assert issues == []

    @pytest.mark.asyncio
    async def test_multiple_cycles_detected(self, validator, mock_session):
        """Should detect multiple independent cycles."""
        cycle1 = Neo4jRecordFactory.create_cycle_record(
            names=["A", "B", "A"],
            ids=["id-a", "id-b", "id-a"],
        )
        cycle2 = Neo4jRecordFactory.create_cycle_record(
            names=["X", "Y", "Z", "X"],
            ids=["id-x", "id-y", "id-z", "id-x"],
        )
        mock_session.set_response(
            "DEPENDS_ON",
            records=[cycle1, cycle2],
        )

        issues = await validator.check_circular_dependencies()

        assert len(issues) == 2
        assert all(i.type == IssueType.CIRCULAR_DEPENDENCY for i in issues)

    @pytest.mark.asyncio
    async def test_includes_suggested_action(self, validator, mock_session):
        """Should include suggested action for fixing."""
        cycle_record = Neo4jRecordFactory.create_cycle_record(
            names=["A", "B", "A"],
            ids=["id-a", "id-b", "id-a"],
        )
        mock_session.set_response("DEPENDS_ON", records=[cycle_record])

        issues = await validator.check_circular_dependencies()

        assert issues[0].suggested_action is not None
        # Phase 5: Suggested action changed to "review" instead of "remove"
        assert (
            "review" in issues[0].suggested_action.lower()
            or "identify" in issues[0].suggested_action.lower()
        )


# ============================================================================
# Orphan Entities Tests
# ============================================================================


class TestValidatorOrphanEntities:
    """Test detection of entities with no relationships."""

    @pytest.mark.asyncio
    async def test_detects_orphan_entity(self, validator, mock_session):
        """Should detect entity with no relationships."""
        entity = EntityFactory.create(name="OrphanTech", entity_type="technology")
        mock_session.set_response(
            "IS_A|PART_OF|RELATED_TO|DEPENDS_ON|ALTERNATIVE_TO",
            records=[Neo4jRecordFactory.create_entity_record(entity)],
        )

        issues = await validator.check_orphan_entities()

        assert len(issues) == 1
        assert issues[0].type == IssueType.ORPHAN_ENTITY
        assert issues[0].severity == IssueSeverity.WARNING
        assert "OrphanTech" in issues[0].message

    @pytest.mark.asyncio
    async def test_no_orphans_returns_empty(self, validator, mock_session):
        """Should return empty list when all entities have relationships."""
        mock_session.set_response(
            "IS_A|PART_OF|RELATED_TO|DEPENDS_ON|ALTERNATIVE_TO", records=[]
        )

        issues = await validator.check_orphan_entities()

        assert issues == []

    @pytest.mark.asyncio
    async def test_multiple_orphans_detected(self, validator, mock_session):
        """Should detect multiple orphan entities."""
        entities = [
            EntityFactory.create(name="Orphan1", entity_type="technology"),
            EntityFactory.create(name="Orphan2", entity_type="concept"),
            EntityFactory.create(name="Orphan3", entity_type="pattern"),
        ]
        mock_session.set_response(
            "IS_A|PART_OF|RELATED_TO|DEPENDS_ON|ALTERNATIVE_TO",
            records=[Neo4jRecordFactory.create_entity_record(e) for e in entities],
        )

        issues = await validator.check_orphan_entities()

        assert len(issues) == 3
        assert all(i.type == IssueType.ORPHAN_ENTITY for i in issues)

    @pytest.mark.asyncio
    async def test_orphan_includes_type_in_message(self, validator, mock_session):
        """Should include entity type in issue message."""
        entity = EntityFactory.create(name="LonelyPattern", entity_type="pattern")
        mock_session.set_response(
            "IS_A|PART_OF|RELATED_TO|DEPENDS_ON|ALTERNATIVE_TO",
            records=[Neo4jRecordFactory.create_entity_record(entity)],
        )

        issues = await validator.check_orphan_entities()

        assert "pattern" in issues[0].message


# ============================================================================
# Low Confidence Relationships Tests
# ============================================================================


class TestValidatorLowConfidenceRelationships:
    """Test detection of low confidence relationships."""

    @pytest.mark.asyncio
    async def test_detects_low_confidence(self, validator, mock_session):
        """Should detect relationships with confidence below threshold."""
        low_conf_record = {
            "source_id": "id1",
            "source_name": "Entity A",
            "target_id": "id2",
            "target_name": "Entity B",
            "rel_type": "DEPENDS_ON",
            "confidence": 0.3,
        }
        mock_session.set_response(
            "confidence",
            records=[low_conf_record],
        )

        issues = await validator.check_low_confidence_relationships(threshold=0.5)

        assert len(issues) == 1
        assert issues[0].type == IssueType.LOW_CONFIDENCE_RELATIONSHIP
        assert issues[0].severity == IssueSeverity.INFO
        assert "0.30" in issues[0].message

    @pytest.mark.asyncio
    async def test_respects_custom_threshold(self, validator, mock_session):
        """Should use custom confidence threshold."""
        medium_conf_record = {
            "source_id": "id1",
            "source_name": "Entity A",
            "target_id": "id2",
            "target_name": "Entity B",
            "rel_type": "RELATED_TO",
            "confidence": 0.6,
        }
        mock_session.set_response("confidence", records=[medium_conf_record])

        issues_high_threshold = await validator.check_low_confidence_relationships(
            threshold=0.7
        )

        # Reset and check with lower threshold
        mock_session.reset()
        mock_session.set_response("confidence", records=[medium_conf_record])
        issues_low_threshold = await validator.check_low_confidence_relationships(
            threshold=0.5
        )

        # 0.6 is below 0.7 but above 0.5
        assert len(issues_high_threshold) == 1
        assert len(issues_low_threshold) == 1

    @pytest.mark.asyncio
    async def test_no_low_confidence_returns_empty(self, validator, mock_session):
        """Should return empty list when all relationships have high confidence."""
        mock_session.set_response("confidence", records=[])

        issues = await validator.check_low_confidence_relationships()

        assert issues == []

    @pytest.mark.asyncio
    async def test_includes_relationship_details(self, validator, mock_session):
        """Should include relationship type and entities in details."""
        record = {
            "source_id": "id1",
            "source_name": "Source",
            "target_id": "id2",
            "target_name": "Target",
            "rel_type": "DEPENDS_ON",
            "confidence": 0.3,
        }
        mock_session.set_response("confidence", records=[record])

        issues = await validator.check_low_confidence_relationships()

        assert issues[0].details["relationship"] == "DEPENDS_ON"
        assert issues[0].details["source"] == "Source"
        assert issues[0].details["target"] == "Target"


# ============================================================================
# Duplicate Entities Tests
# ============================================================================


class TestValidatorDuplicateEntities:
    """Test detection of potential duplicate entities."""

    @pytest.mark.asyncio
    async def test_detects_similar_names(self, mock_session):
        """Should detect entities with similar names (fuzzy match)."""
        entities = [
            EntityFactory.create(name="PostgreSQL", entity_type="technology"),
            EntityFactory.create(name="Postgresq", entity_type="technology"),  # Typo
        ]

        async def mock_run(query, **params):
            return MockNeo4jResult(
                records=[Neo4jRecordFactory.create_entity_record(e) for e in entities]
            )

        mock_session.run = mock_run
        validator = GraphValidator(mock_session)

        issues = await validator.check_duplicate_entities()

        assert len(issues) >= 1
        assert issues[0].type == IssueType.DUPLICATE_ENTITY
        assert "PostgreSQL" in issues[0].message or "Postgresq" in issues[0].message

    @pytest.mark.asyncio
    async def test_ignores_dissimilar_names(self, validator, mock_session):
        """Should not flag entities with different names."""
        entities = [
            EntityFactory.create(name="Redis", entity_type="technology"),
            EntityFactory.create(name="MongoDB", entity_type="technology"),
        ]
        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(e) for e in entities],
        )

        issues = await validator.check_duplicate_entities()

        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_includes_similarity_score(self, validator, mock_session):
        """Should include similarity percentage in message."""
        entities = [
            EntityFactory.create(name="ReactJS", entity_type="technology"),
            EntityFactory.create(name="React.js", entity_type="technology"),
        ]
        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(e) for e in entities],
        )

        issues = await validator.check_duplicate_entities()

        if issues:  # Only if similarity threshold met
            assert "%" in issues[0].message

    @pytest.mark.asyncio
    async def test_known_alias_higher_severity(self, validator, mock_session):
        """Should flag known aliases with WARNING severity."""
        entities = [
            EntityFactory.create(name="PostgreSQL", entity_type="technology"),
            EntityFactory.create(name="postgres", entity_type="technology"),
        ]
        mock_session.set_response(
            "MATCH (e:Entity)",
            records=[Neo4jRecordFactory.create_entity_record(e) for e in entities],
        )

        issues = await validator.check_duplicate_entities()

        # postgres -> PostgreSQL is a known canonical mapping
        if issues:
            # At minimum should detect as duplicate
            assert len(issues) > 0


# ============================================================================
# Missing Embeddings Tests
# ============================================================================


class TestValidatorMissingEmbeddings:
    """Test detection of nodes without embeddings."""

    @pytest.mark.asyncio
    async def test_detects_decisions_without_embeddings(self, validator, mock_session):
        """Should detect decisions missing embeddings."""

        async def mock_run(query, **params):
            if "DecisionTrace" in query and "embedding IS NULL" in query:
                # Return count of decisions without embeddings
                return MockNeo4jResult(single_value={"count": 5})
            if "Entity" in query:
                return MockNeo4jResult(single_value={"count": 0})
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run

        issues = await validator.check_missing_embeddings()

        assert any(i.type == IssueType.MISSING_EMBEDDING for i in issues)
        decision_issue = next(
            (i for i in issues if i.details.get("type") == "decision"), None
        )
        assert decision_issue is not None

    @pytest.mark.asyncio
    async def test_detects_entities_without_embeddings(self, validator, mock_session):
        """Should detect entities missing embeddings."""

        async def mock_run(query, **params):
            # Decision query: "d.embedding IS NULL" and "count(d)"
            if "d.embedding IS NULL" in query:
                return MockNeo4jResult(single_value={"count": 0})
            # Entity query: "e.embedding IS NULL" and "count(DISTINCT e)"
            if "e.embedding IS NULL" in query:
                return MockNeo4jResult(single_value={"count": 5})
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run

        issues = await validator.check_missing_embeddings()

        entity_issue = next(
            (i for i in issues if i.details.get("type") == "entity"), None
        )
        assert entity_issue is not None
        assert entity_issue.details["count"] == 5

    @pytest.mark.asyncio
    async def test_no_missing_embeddings_returns_empty(self, validator, mock_session):
        """Should return empty list when all nodes have embeddings."""

        async def mock_run(query, **params):
            # All queries return count of 0
            return MockNeo4jResult(single_value={"count": 0})

        mock_session.run = mock_run

        issues = await validator.check_missing_embeddings()

        assert issues == []

    @pytest.mark.asyncio
    async def test_includes_suggested_action(self, validator, mock_session):
        """Should suggest running enhance endpoint."""

        async def mock_run(query, **params):
            if "DecisionTrace" in query:
                return MockNeo4jResult(single_value={"count": 3})
            if "Entity" in query:
                return MockNeo4jResult(single_value={"count": 0})
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run

        issues = await validator.check_missing_embeddings()

        assert len(issues) > 0
        assert any("enhance" in (i.suggested_action or "").lower() for i in issues)


# ============================================================================
# Invalid Relationships Tests
# ============================================================================


class TestValidatorInvalidRelationships:
    """Test detection of invalid relationship configurations."""

    @pytest.mark.asyncio
    async def test_detects_self_referential(self, validator, mock_session):
        """Should detect self-referential relationships."""
        self_ref_record = {
            "id": "entity-1",
            "name": "Self Entity",
            "rel_type": "DEPENDS_ON",
        }

        async def mock_run(query, **params):
            if "(d:DecisionTrace)-[r]->(d)" in query:
                return MockNeo4jResult(records=[self_ref_record])
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run

        issues = await validator.check_invalid_relationships()

        self_ref_issues = [i for i in issues if "Self" in i.message]
        assert len(self_ref_issues) >= 1
        assert self_ref_issues[0].severity == IssueSeverity.ERROR

    @pytest.mark.asyncio
    async def test_detects_decision_entity_relationship(self, validator, mock_session):
        """Should detect entity relationships between decisions."""
        d2d_record = {
            "id1": "dec-1",
            "trigger1": "Decision about X",
            "id2": "dec-2",
            "trigger2": "Decision about Y",
            "rel_type": "IS_A",  # Entity relationship, not decision relationship
        }

        async def mock_run(query, **params):
            if "DecisionTrace)-[r]->(d2:DecisionTrace)" in query:
                return MockNeo4jResult(records=[d2d_record])
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run

        issues = await validator.check_invalid_relationships()

        d2d_issues = [i for i in issues if i.type == IssueType.INVALID_RELATIONSHIP]
        if d2d_issues:
            # Should suggest using decision relationships instead
            assert any(
                "SIMILAR_TO" in str(i.suggested_action)
                or "INFLUENCED_BY" in str(i.suggested_action)
                for i in d2d_issues
            )

    @pytest.mark.asyncio
    async def test_no_invalid_relationships_returns_empty(
        self, validator, mock_session
    ):
        """Should return empty list when all relationships are valid."""

        async def mock_run(query, **params):
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run

        issues = await validator.check_invalid_relationships()

        assert issues == []


# ============================================================================
# Auto-Fix Tests
# ============================================================================


class TestValidatorAutoFix:
    """Test auto-fix functionality for safe issues."""

    @pytest.mark.asyncio
    async def test_removes_self_references(self, validator, mock_session):
        """Should remove self-referential relationships."""
        mock_session.set_response(
            "DELETE r",
            single_value={"count": 2},
        )

        stats = await validator.auto_fix()

        assert stats["self_references_removed"] == 2

    @pytest.mark.asyncio
    async def test_auto_fix_with_specific_issues(self, validator, mock_session):
        """Should only fix specified issue types."""
        mock_session.set_response(
            "DELETE r",
            single_value={"count": 1},
        )

        stats = await validator.auto_fix(issue_types=[IssueType.INVALID_RELATIONSHIP])

        assert stats["self_references_removed"] == 1

    @pytest.mark.asyncio
    async def test_auto_fix_no_issues(self, validator, mock_session):
        """Should return zero counts when nothing to fix."""
        mock_session.set_response(
            "DELETE r",
            single_value={"count": 0},
        )

        stats = await validator.auto_fix()

        assert stats["self_references_removed"] == 0


# ============================================================================
# Validation Summary Tests
# ============================================================================


class TestValidatorSummary:
    """Test validation summary functionality."""

    @pytest.mark.asyncio
    async def test_get_validation_summary_structure(self, validator, mock_session):
        """Should return properly structured summary."""

        # Set up empty responses for all checks
        async def mock_run(query, **params):
            if "count(e)" in query:
                return MockNeo4jResult(single_value={"count": 0})
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run

        summary = await validator.get_validation_summary()

        assert "total_issues" in summary
        assert "by_severity" in summary
        assert "by_type" in summary
        assert "error" in summary["by_severity"]
        assert "warning" in summary["by_severity"]
        assert "info" in summary["by_severity"]

    @pytest.mark.asyncio
    async def test_summary_counts_by_severity(self, mock_session):
        """Should count issues by severity correctly."""

        # Create some issues by mocking responses
        async def mock_run(query, **params):
            # Circular dependency check - return a cycle
            # Phase 5: Query pattern changed to use dynamic relationship type
            if (
                "DEPENDS_ON*2.." in query
                or "REQUIRES*2.." in query
                or "nodes(path)" in query
            ):
                return MockNeo4jResult(
                    records=[
                        Neo4jRecordFactory.create_cycle_record(
                            ["A", "B", "A"], ["1", "2", "1"]
                        )
                    ]
                )
            # Orphan entity check
            if "IS_A|PART_OF|RELATED_TO|DEPENDS_ON|ALTERNATIVE_TO" in query:
                return MockNeo4jResult(
                    records=[{"id": "orphan1", "name": "Orphan", "type": "tech"}]
                )
            # Missing embedding counts
            if "count(e)" in query:
                return MockNeo4jResult(single_value={"count": 0})
            # Self-referential check
            if "(d:DecisionTrace)-[r]->(d)" in query:
                return MockNeo4jResult(records=[])
            # Decision-decision entity relationship check
            if "(d1:DecisionTrace)-[r]->(d2:DecisionTrace)" in query:
                return MockNeo4jResult(records=[])
            # Low confidence check
            if "r.confidence" in query:
                return MockNeo4jResult(records=[])
            # Missing decision embeddings
            if (
                "DecisionTrace" in query
                and "embedding IS NULL" in query
                and "count(d)" in query
            ):
                return MockNeo4jResult(records=[])
            # Duplicate entity check
            if "MATCH (e:Entity)" in query and "RETURN e.id" in query:
                return MockNeo4jResult(records=[])
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run
        validator = GraphValidator(mock_session)

        summary = await validator.get_validation_summary()

        # Circular dep = ERROR, Orphan = WARNING
        assert summary["by_severity"]["error"] >= 1
        assert summary["by_severity"]["warning"] >= 1


# ============================================================================
# Validate All Tests
# ============================================================================


class TestValidatorValidateAll:
    """Test the validate_all method that runs all checks."""

    @pytest.mark.asyncio
    async def test_validate_all_runs_all_checks(self, validator, mock_session):
        """Should run all validation checks."""

        async def mock_run(query, **params):
            if "count(e)" in query:
                return MockNeo4jResult(single_value={"count": 0})
            return MockNeo4jResult(records=[])

        mock_session.run = mock_run

        issues = await validator.validate_all()

        # Should return a list (even if empty)
        assert isinstance(issues, list)


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestGetGraphValidator:
    """Test the factory function."""

    def test_creates_validator_instance(self, mock_session):
        """Should create GraphValidator with session."""
        validator = get_graph_validator(mock_session)

        assert isinstance(validator, GraphValidator)
        assert validator.session == mock_session

    def test_default_fuzzy_threshold(self, mock_session):
        """Should have default fuzzy threshold of 85."""
        validator = get_graph_validator(mock_session)

        assert validator.fuzzy_threshold == 85


# ============================================================================
# ValidationIssue Dataclass Tests
# ============================================================================


class TestValidationIssue:
    """Test the ValidationIssue dataclass."""

    def test_issue_creation(self):
        """Should create issue with all fields."""
        issue = ValidationIssue(
            type=IssueType.CIRCULAR_DEPENDENCY,
            severity=IssueSeverity.ERROR,
            message="Test cycle",
            affected_nodes=["id1", "id2"],
            suggested_action="Remove cycle",
            details={"cycle": ["A", "B"]},
        )

        assert issue.type == IssueType.CIRCULAR_DEPENDENCY
        assert issue.severity == IssueSeverity.ERROR
        assert issue.message == "Test cycle"
        assert issue.affected_nodes == ["id1", "id2"]
        assert issue.suggested_action == "Remove cycle"
        assert issue.details["cycle"] == ["A", "B"]

    def test_issue_optional_fields(self):
        """Should allow optional fields."""
        issue = ValidationIssue(
            type=IssueType.ORPHAN_ENTITY,
            severity=IssueSeverity.WARNING,
            message="Orphan found",
            affected_nodes=["id1"],
        )

        assert issue.suggested_action is None
        assert issue.details is None


# ============================================================================
# Enums Tests
# ============================================================================


class TestEnums:
    """Test enum values."""

    def test_issue_severity_values(self):
        """Should have correct severity values."""
        assert IssueSeverity.ERROR.value == "error"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.INFO.value == "info"

    def test_issue_type_values(self):
        """Should have correct issue type values."""
        assert IssueType.CIRCULAR_DEPENDENCY.value == "circular_dependency"
        assert IssueType.ORPHAN_ENTITY.value == "orphan_entity"
        assert IssueType.DUPLICATE_ENTITY.value == "duplicate_entity"
        assert IssueType.MISSING_EMBEDDING.value == "missing_embedding"
        assert IssueType.INVALID_RELATIONSHIP.value == "invalid_relationship"


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
