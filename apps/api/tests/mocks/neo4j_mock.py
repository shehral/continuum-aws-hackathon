"""Mock Neo4j session for unit testing.

Provides a controllable mock that simulates Neo4j async session behavior
without requiring a running database.
"""

from typing import Optional


class MockNeo4jResult:
    """Mock Neo4j query result that supports async iteration."""

    def __init__(self, records: list[dict] = None, single_value: dict = None):
        self._records = records or []
        self._single_value = single_value
        self._index = 0

    async def single(self) -> Optional[dict]:
        """Return single record or None."""
        return self._single_value

    def __aiter__(self):
        """Return async iterator."""
        self._index = 0
        return self

    async def __anext__(self) -> dict:
        """Get next record."""
        if self._index >= len(self._records):
            raise StopAsyncIteration
        record = self._records[self._index]
        self._index += 1
        return record


class MockNeo4jSession:
    """Mock Neo4j async session for testing.

    Allows configuring different responses for different query patterns.
    """

    def __init__(self):
        self._query_responses: dict[str, MockNeo4jResult] = {}
        self._default_result = MockNeo4jResult()
        self._run_calls: list[tuple[str, dict]] = []

    def set_response(
        self,
        query_pattern: str,
        records: list[dict] = None,
        single_value: dict = None,
    ):
        """Configure response for queries containing the pattern.

        Args:
            query_pattern: String pattern to match in query
            records: List of records to return for iteration
            single_value: Value to return from .single()
        """
        self._query_responses[query_pattern] = MockNeo4jResult(
            records=records,
            single_value=single_value,
        )

    def set_default_response(
        self,
        records: list[dict] = None,
        single_value: dict = None,
    ):
        """Set the default response for unmatched queries."""
        self._default_result = MockNeo4jResult(
            records=records,
            single_value=single_value,
        )

    async def run(self, query: str, **params) -> MockNeo4jResult:
        """Execute a mock query.

        Records the call for verification and returns configured response.
        """
        self._run_calls.append((query, params))

        # Find matching response
        for pattern, result in self._query_responses.items():
            if pattern.lower() in query.lower():
                # Return a fresh copy to allow multiple iterations
                return MockNeo4jResult(
                    records=result._records.copy(),
                    single_value=result._single_value,
                )

        return MockNeo4jResult(
            records=self._default_result._records.copy(),
            single_value=self._default_result._single_value,
        )

    def get_calls(self) -> list[tuple[str, dict]]:
        """Get all recorded query calls."""
        return self._run_calls.copy()

    def get_call_count(self) -> int:
        """Get number of queries executed."""
        return len(self._run_calls)

    def reset(self):
        """Reset all state."""
        self._query_responses.clear()
        self._run_calls.clear()
        self._default_result = MockNeo4jResult()

    def assert_query_contains(self, pattern: str) -> bool:
        """Assert that at least one query contained the pattern."""
        for query, _ in self._run_calls:
            if pattern.lower() in query.lower():
                return True
        return False


def create_mock_session_with_entities(entities: list[dict]) -> MockNeo4jSession:
    """Create a session pre-configured with entity data.

    Args:
        entities: List of entity dicts with id, name, type fields

    Returns:
        MockNeo4jSession configured for entity queries
    """
    session = MockNeo4jSession()

    # Configure responses for common entity queries
    session.set_response(
        "MATCH (e:Entity)",
        records=entities,
    )

    # Configure exact match lookups
    for entity in entities:
        name_lower = entity["name"].lower()
        session.set_response(
            f"toLower(e.name) = '{name_lower}'",
            single_value=entity,
        )

    return session


def create_mock_session_with_decisions(decisions: list[dict]) -> MockNeo4jSession:
    """Create a session pre-configured with decision data.

    Args:
        decisions: List of decision dicts

    Returns:
        MockNeo4jSession configured for decision queries
    """
    session = MockNeo4jSession()

    session.set_response(
        "MATCH (d:DecisionTrace)",
        records=decisions,
    )

    for decision in decisions:
        session.set_response(
            f"id: '{decision['id']}'",
            single_value=decision,
        )

    return session
