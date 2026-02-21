"""Transaction coordinator for cross-database operations (SD-001).

Implements the Saga pattern for coordinating transactions across PostgreSQL and Neo4j.
This ensures data consistency when operations need to modify both databases atomically.

Design:
- Each saga step has an execute and compensate action
- If any step fails, previous steps are compensated in reverse order
- Compensation failures are logged but don't block the rollback
- Provides audit logging for all saga executions

Usage:
    coordinator = TransactionCoordinator()
    saga = DecisionCreationSaga(coordinator)
    result = await saga.execute(decision_data)
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Generic, TypeVar
from uuid import uuid4

from utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class SagaStatus(Enum):
    """Status of a saga execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass
class SagaStep:
    """A single step in a saga with execute and compensate actions.

    Args:
        name: Human-readable name for the step (used in logging)
        execute: Async function that performs the step's action
        compensate: Async function that undoes the step's action (for rollback)
        retry_count: Number of times to retry on transient failures (default: 2)
    """

    name: str
    execute: Callable[..., Coroutine[Any, Any, Any]]
    compensate: Callable[..., Coroutine[Any, Any, None]]
    retry_count: int = 2


@dataclass
class SagaContext:
    """Context passed between saga steps, accumulating results.

    Attributes:
        saga_id: Unique identifier for this saga execution
        started_at: When the saga started
        status: Current status of the saga
        results: Dict of step_name -> result from each completed step
        current_step: Index of the currently executing step
        error: Exception that caused the saga to fail (if any)
    """

    saga_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: SagaStatus = SagaStatus.PENDING
    results: dict[str, Any] = field(default_factory=dict)
    current_step: int = 0
    error: Exception | None = None


class TransactionCoordinator:
    """Coordinates saga execution across multiple databases (SD-001).

    The coordinator manages the lifecycle of saga executions:
    1. Executes steps in sequence
    2. Tracks completed steps
    3. Compensates on failure (reverse order)
    4. Logs all operations for audit

    Example:
        coordinator = TransactionCoordinator()

        steps = [
            SagaStep(
                name="create_postgres_decision",
                execute=create_in_postgres,
                compensate=delete_from_postgres,
            ),
            SagaStep(
                name="create_neo4j_node",
                execute=create_in_neo4j,
                compensate=delete_from_neo4j,
            ),
        ]

        result = await coordinator.execute_saga(steps, initial_data)
    """

    def __init__(self):
        self._active_sagas: dict[str, SagaContext] = {}

    async def execute_saga(
        self,
        steps: list[SagaStep],
        initial_data: dict[str, Any],
    ) -> tuple[SagaContext, Any]:
        """Execute a saga with the given steps.

        Args:
            steps: List of SagaStep objects to execute in order
            initial_data: Initial data to pass to the first step

        Returns:
            Tuple of (SagaContext, final_result)

        Raises:
            Exception: If the saga fails and compensation completes
        """
        context = SagaContext()
        context.status = SagaStatus.IN_PROGRESS
        self._active_sagas[context.saga_id] = context

        logger.info(
            f"Starting saga {context.saga_id}",
            extra={
                "saga_id": context.saga_id,
                "step_count": len(steps),
                "steps": [s.name for s in steps],
            },
        )

        completed_steps: list[tuple[SagaStep, Any]] = []
        current_data = initial_data

        try:
            for i, step in enumerate(steps):
                context.current_step = i

                logger.debug(
                    f"Executing saga step: {step.name}",
                    extra={
                        "saga_id": context.saga_id,
                        "step": step.name,
                        "step_index": i,
                    },
                )

                # Execute step with retry logic
                result = await self._execute_with_retry(
                    step.execute,
                    current_data,
                    context,
                    step.retry_count,
                    step.name,
                )

                context.results[step.name] = result
                completed_steps.append((step, result))

                # Pass result to next step
                if isinstance(result, dict):
                    current_data = {**current_data, **result}
                else:
                    current_data = {**current_data, f"{step.name}_result": result}

                logger.debug(
                    f"Completed saga step: {step.name}",
                    extra={
                        "saga_id": context.saga_id,
                        "step": step.name,
                    },
                )

            # All steps completed successfully
            context.status = SagaStatus.COMPLETED
            logger.info(
                f"Saga {context.saga_id} completed successfully",
                extra={
                    "saga_id": context.saga_id,
                    "duration_ms": (
                        datetime.now(UTC) - context.started_at
                    ).total_seconds()
                    * 1000,
                },
            )

            return context, current_data

        except Exception as e:
            context.error = e
            context.status = SagaStatus.COMPENSATING

            logger.error(
                f"Saga {context.saga_id} failed at step {steps[context.current_step].name}: {e}",
                extra={
                    "saga_id": context.saga_id,
                    "failed_step": steps[context.current_step].name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

            # Compensate completed steps in reverse order
            await self._compensate(completed_steps, context)

            raise

        finally:
            # Clean up active saga tracking
            self._active_sagas.pop(context.saga_id, None)

    async def _execute_with_retry(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        data: dict[str, Any],
        context: SagaContext,
        max_retries: int,
        step_name: str,
    ) -> Any:
        """Execute a function with retry logic.

        Args:
            func: Async function to execute
            data: Data to pass to the function
            context: Saga context
            max_retries: Maximum number of retries
            step_name: Name of the step (for logging)

        Returns:
            Result of the function

        Raises:
            Exception: If all retries are exhausted
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return await func(data, context)
            except Exception as e:
                last_error = e

                if attempt < max_retries:
                    delay = 0.5 * (2**attempt)  # Exponential backoff
                    logger.warning(
                        f"Saga step {step_name} failed, retrying in {delay}s",
                        extra={
                            "saga_id": context.saga_id,
                            "step": step_name,
                            "attempt": attempt + 1,
                            "max_retries": max_retries + 1,
                            "error": str(e),
                        },
                    )
                    await asyncio.sleep(delay)

        raise last_error  # type: ignore

    async def _compensate(
        self,
        completed_steps: list[tuple[SagaStep, Any]],
        context: SagaContext,
    ) -> None:
        """Compensate completed steps in reverse order.

        Args:
            completed_steps: List of (step, result) tuples to compensate
            context: Saga context
        """
        logger.info(
            f"Starting compensation for saga {context.saga_id}",
            extra={
                "saga_id": context.saga_id,
                "steps_to_compensate": len(completed_steps),
            },
        )

        compensation_errors: list[tuple[str, Exception]] = []

        for step, result in reversed(completed_steps):
            try:
                logger.debug(
                    f"Compensating step: {step.name}",
                    extra={
                        "saga_id": context.saga_id,
                        "step": step.name,
                    },
                )

                await step.compensate(result, context)

                logger.debug(
                    f"Compensation successful: {step.name}",
                    extra={
                        "saga_id": context.saga_id,
                        "step": step.name,
                    },
                )

            except Exception as e:
                # Log but continue compensating other steps
                compensation_errors.append((step.name, e))
                logger.error(
                    f"Compensation failed for step {step.name}: {e}",
                    extra={
                        "saga_id": context.saga_id,
                        "step": step.name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

        if compensation_errors:
            context.status = SagaStatus.FAILED
            logger.error(
                f"Saga {context.saga_id} compensation incomplete",
                extra={
                    "saga_id": context.saga_id,
                    "failed_compensations": [name for name, _ in compensation_errors],
                },
            )
        else:
            context.status = SagaStatus.COMPENSATED
            logger.info(
                f"Saga {context.saga_id} fully compensated",
                extra={"saga_id": context.saga_id},
            )


class BaseSaga(ABC, Generic[T]):
    """Base class for defining domain-specific sagas.

    Subclasses should define the saga steps and implement
    the execute method with proper typing.
    """

    def __init__(self, coordinator: TransactionCoordinator):
        self.coordinator = coordinator

    @abstractmethod
    def _build_steps(self) -> list[SagaStep]:
        """Build the list of saga steps.

        Returns:
            List of SagaStep objects defining the saga
        """
        pass

    @abstractmethod
    async def execute(self, data: T) -> Any:
        """Execute the saga with the given data.

        Args:
            data: Domain-specific input data

        Returns:
            Domain-specific result
        """
        pass


class DecisionCreationSaga(BaseSaga[dict]):
    """Saga for creating a decision in both PostgreSQL and Neo4j (SD-001).

    Steps:
    1. Create decision in PostgreSQL (source of truth for metadata)
    2. Create decision node in Neo4j (for graph relationships)
    3. Create entity links in Neo4j (connects decision to entities)
    4. Generate embeddings (async, no compensation needed)

    If any step fails, previous steps are rolled back.
    """

    def _build_steps(self) -> list[SagaStep]:
        return [
            SagaStep(
                name="create_postgres_decision",
                execute=self._create_postgres_decision,
                compensate=self._delete_postgres_decision,
            ),
            SagaStep(
                name="create_neo4j_decision",
                execute=self._create_neo4j_decision,
                compensate=self._delete_neo4j_decision,
            ),
            SagaStep(
                name="create_entity_links",
                execute=self._create_entity_links,
                compensate=self._delete_entity_links,
            ),
        ]

    async def execute(self, decision_data: dict) -> dict:
        """Create a decision across both databases.

        Args:
            decision_data: Decision data including:
                - trigger: What prompted the decision
                - context: Background information
                - options: List of alternatives considered
                - decision: What was chosen
                - rationale: Why it was chosen
                - entities: List of related entity IDs

        Returns:
            Dict with decision_id and created timestamps
        """
        steps = self._build_steps()
        context, result = await self.coordinator.execute_saga(steps, decision_data)
        return result

    async def _create_postgres_decision(self, data: dict, context: SagaContext) -> dict:
        """Create decision record in PostgreSQL."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from models.decision import Decision as DecisionModel

        from db.postgres import async_session_maker

        async with async_session_maker() as session:
            decision_id = str(uuid4())
            decision = DecisionModel(
                id=decision_id,
                trigger=data.get("trigger", ""),
                context=data.get("context", ""),
                options=data.get("options", []),
                decision=data.get("decision", ""),
                rationale=data.get("rationale", ""),
                confidence=data.get("confidence", 0.5),
                source=data.get("source", "manual"),
                created_at=datetime.now(UTC),
            )
            session.add(decision)
            await session.commit()

            return {"decision_id": decision_id, "postgres_created": True}

    async def _delete_postgres_decision(
        self, result: dict, context: SagaContext
    ) -> None:
        """Compensate: Delete decision from PostgreSQL."""
        from models.decision import Decision as DecisionModel
        from sqlalchemy import delete

        from db.postgres import async_session_maker

        decision_id = result.get("decision_id")
        if not decision_id:
            return

        async with async_session_maker() as session:
            await session.execute(
                delete(DecisionModel).where(DecisionModel.id == decision_id)
            )
            await session.commit()

    async def _create_neo4j_decision(self, data: dict, context: SagaContext) -> dict:
        """Create decision node in Neo4j."""
        from db.neo4j import get_neo4j_session

        decision_id = data.get("decision_id")

        async with get_neo4j_session() as session:
            result = await session.run(
                """
                CREATE (d:Decision {
                    id: $id,
                    trigger: $trigger,
                    decision: $decision,
                    confidence: $confidence,
                    source: $source,
                    created_at: datetime()
                })
                RETURN d.id as id
                """,
                id=decision_id,
                trigger=data.get("trigger", ""),
                decision=data.get("decision", ""),
                confidence=data.get("confidence", 0.5),
                source=data.get("source", "manual"),
            )
            record = await result.single()

            return {"neo4j_node_id": record["id"] if record else None}

    async def _delete_neo4j_decision(self, result: dict, context: SagaContext) -> None:
        """Compensate: Delete decision node from Neo4j."""
        from db.neo4j import get_neo4j_session

        decision_id = context.results.get("create_postgres_decision", {}).get(
            "decision_id"
        )
        if not decision_id:
            return

        async with get_neo4j_session() as session:
            await session.run(
                "MATCH (d:Decision {id: $id}) DETACH DELETE d",
                id=decision_id,
            )

    async def _create_entity_links(self, data: dict, context: SagaContext) -> dict:
        """Create relationships between decision and entities in Neo4j."""
        from db.neo4j import get_neo4j_session

        decision_id = data.get("decision_id")
        entity_ids = data.get("entities", [])

        if not entity_ids:
            return {"linked_entities": []}

        linked = []
        async with get_neo4j_session() as session:
            for entity_id in entity_ids:
                result = await session.run(
                    """
                    MATCH (d:Decision {id: $decision_id})
                    MATCH (e:Entity {id: $entity_id})
                    MERGE (d)-[r:INVOLVES]->(e)
                    RETURN e.id as entity_id
                    """,
                    decision_id=decision_id,
                    entity_id=entity_id,
                )
                record = await result.single()
                if record:
                    linked.append(record["entity_id"])

        return {"linked_entities": linked}

    async def _delete_entity_links(self, result: dict, context: SagaContext) -> None:
        """Compensate: Remove entity links from Neo4j."""
        from db.neo4j import get_neo4j_session

        decision_id = context.results.get("create_postgres_decision", {}).get(
            "decision_id"
        )
        if not decision_id:
            return

        async with get_neo4j_session() as session:
            await session.run(
                "MATCH (d:Decision {id: $id})-[r:INVOLVES]->() DELETE r",
                id=decision_id,
            )


# Convenience function for creating decisions with saga coordination
async def create_decision_with_saga(decision_data: dict) -> dict:
    """Create a decision using saga-coordinated transactions (SD-001).

    This is the recommended way to create decisions when you need
    guaranteed consistency across PostgreSQL and Neo4j.

    Args:
        decision_data: Decision data dict

    Returns:
        Dict with decision_id and metadata

    Raises:
        Exception: If creation fails (previous steps will be compensated)
    """
    coordinator = TransactionCoordinator()
    saga = DecisionCreationSaga(coordinator)
    return await saga.execute(decision_data)
