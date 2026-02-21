"""Migration: Rename decision/rationale → agent_decision/agent_rationale.

Idempotent — safe to run multiple times. If properties are already renamed,
the SET is a no-op (COALESCE falls through to the new name).

Usage:
    cd apps/api
    .venv/bin/python scripts/migrate_rationale.py
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import AsyncGraphDatabase


async def migrate():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4jpassword")

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async with driver.session() as session:
        # Step 1: Count decisions to migrate
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.decision IS NOT NULL AND d.agent_decision IS NULL
            RETURN count(d) as to_migrate
            """
        )
        record = await result.single()
        to_migrate = record["to_migrate"]
        print(f"Decisions to migrate: {to_migrate}")

        if to_migrate == 0:
            print("Nothing to migrate — already up to date.")
        else:
            # Step 2: Rename properties
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE d.decision IS NOT NULL AND d.agent_decision IS NULL
                SET d.agent_decision = d.decision,
                    d.agent_rationale = d.rationale
                REMOVE d.decision, d.rationale
                RETURN count(d) as migrated
                """
            )
            record = await result.single()
            print(f"Migrated: {record['migrated']} decisions")

        # Step 3: Drop old fulltext index and recreate with new property names
        try:
            await session.run("DROP INDEX decision_fulltext IF EXISTS")
            print("Dropped old decision_fulltext index")
        except Exception as e:
            print(f"Index drop skipped: {e}")

        try:
            await session.run(
                """
                CREATE FULLTEXT INDEX decision_fulltext IF NOT EXISTS
                FOR (d:DecisionTrace)
                ON EACH [d.trigger, d.context, d.agent_decision, d.agent_rationale]
                """
            )
            print("Created new decision_fulltext index with agent_decision/agent_rationale")
        except Exception as e:
            print(f"Index creation skipped: {e}")

        # Step 4: Report stats
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.human_rationale IS NULL
            RETURN count(d) as needs_review
            """
        )
        record = await result.single()
        print(f"Decisions needing human review: {record['needs_review']}")

    await driver.close()
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
