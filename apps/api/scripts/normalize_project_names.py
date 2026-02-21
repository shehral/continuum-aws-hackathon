"""Normalize all project_name fields in Neo4j to lowercase for consistency."""
import asyncio
from db.neo4j import get_neo4j_session, init_neo4j
from utils.logging import get_logger

logger = get_logger(__name__)


async def normalize_project_names():
    """Update all DecisionTrace nodes to have lowercase project names."""
    # Initialize Neo4j driver
    await init_neo4j()

    session = await get_neo4j_session()
    
    async with session:
        # Get all decisions with project names
        result = await session.run(
            """
            MATCH (d:DecisionTrace)
            WHERE d.project_name IS NOT NULL
            RETURN d.id as id, d.project_name as old_name
            """
        )
        
        updates = []
        async for record in result:
            old_name = record["old_name"]
            new_name = old_name.lower()
            if old_name != new_name:
                updates.append((record["id"], old_name, new_name))
        
        logger.info(f"Found {len(updates)} decisions to normalize")
        
        # Update each decision
        for decision_id, old_name, new_name in updates:
            await session.run(
                """
                MATCH (d:DecisionTrace {id: $id})
                SET d.project_name = $new_name
                """,
                id=decision_id,
                new_name=new_name,
            )
            logger.info(f"Updated {decision_id}: '{old_name}' -> '{new_name}'")
        
        logger.info(f"Normalized {len(updates)} project names")
        return len(updates)


if __name__ == "__main__":
    count = asyncio.run(normalize_project_names())
    print(f"✓ Normalized {count} project names to lowercase")
