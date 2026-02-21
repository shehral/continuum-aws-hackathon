"""Entity resolution service with multi-stage matching pipeline and caching (SD-011).

Entity resolution is user-scoped - it only considers entities
connected to the user's decisions when finding duplicates and matches.

Fuzzy Matching Threshold Design Decision (KG-P2-2: Now configurable):
The default 85% threshold was chosen to balance precision and recall:
- 90%+ would miss common variations (e.g., "PostgreSQL" vs "Postgres")
- 80% or below would create too many false positives
- 85% catches most variations while maintaining quality

Thresholds are now configurable via environment variables:
- FUZZY_MATCH_THRESHOLD: For string fuzzy matching (default: 0.85)
- EMBEDDING_SIMILARITY_THRESHOLD: For vector similarity (default: 0.90)

Higher thresholds = more false negatives (duplicates created)
Lower thresholds = more false positives (incorrect merges)

SD-011: Entity lookup caching
- Redis caching with 5-minute TTL for entity lookups
- Cache invalidation on entity create/update/delete
- User-scoped caching for multi-tenant support
"""

from typing import Optional
from uuid import uuid4

from neo4j.exceptions import ClientError, DatabaseError
from rapidfuzz import fuzz

from config import get_settings
from models.ontology import (
    CANONICAL_NAMES,
    ResolvedEntity,
    get_canonical_name,
    normalize_entity_name,
)
from services.embeddings import get_embedding_service
from services.entity_cache import get_entity_cache
from utils.logging import get_logger
from utils.vectors import cosine_similarity

logger = get_logger(__name__)

# Configuration constants
FUZZY_MATCH_LIMIT = 500  # Maximum entities to load for fuzzy matching
FUZZY_MATCH_BATCH_SIZE = 100  # Batch size for paginated loading


class EntityResolver:
    """Multi-stage entity resolution pipeline with caching (SD-011).

    Resolution is user-scoped - only matches against entities
    connected to the user's decisions.

    Resolution stages (in order):
    1. Cache lookup - Check Redis cache first (SD-011)
    2. Exact match - Case-insensitive lookup in Neo4j
    3. Canonical lookup - Map aliases to canonical names
    4. Alias search - Check entity aliases field
    5. Fulltext prefix search - Neo4j fulltext index for fuzzy candidates
    6. Fuzzy match - rapidfuzz with configurable threshold (default 85%)
    7. Embedding similarity - Cosine similarity with configurable threshold (default 0.9)
    8. Create new - If no match found

    Performance Considerations:
    - Stage 1 (cache) is O(1) with Redis
    - Stages 2-4 use Neo4j indexes and are O(log n) or O(1)
    - Stage 5 (fuzzy) loads candidates in batches with LIMIT to prevent OOM
    - Stage 6 (embedding) uses vector index when available

    Threshold Configuration (KG-P2-2):
    Thresholds are loaded from settings and can be configured via environment:
    - fuzzy_match_threshold: 0.0-1.0 (multiplied by 100 for rapidfuzz)
    - embedding_similarity_threshold: 0.0-1.0 (cosine similarity)
    """

    def __init__(self, neo4j_session, user_id: str = "anonymous"):
        self.session = neo4j_session
        self.user_id = user_id
        self.embedding_service = get_embedding_service()
        self.cache = get_entity_cache()  # SD-011: Entity cache

        # Load configurable thresholds from settings (KG-P2-2)
        settings = get_settings()
        # Convert 0-1 scale to 0-100 for rapidfuzz (global defaults)
        self._global_fuzzy_threshold = int(settings.fuzzy_match_threshold * 100)
        self._global_embedding_threshold = settings.embedding_similarity_threshold
        # Backward-compat aliases (used in non-typed code paths)
        self.fuzzy_threshold = self._global_fuzzy_threshold
        self.embedding_threshold = self._global_embedding_threshold

        # Part 3c: Load per-entity-type thresholds (higher precision for file entities,
        # higher recall for concept entities).
        try:
            from services.code_resolver import TYPE_RESOLUTION_THRESHOLDS
            self._type_thresholds = TYPE_RESOLUTION_THRESHOLDS
        except ImportError:
            self._type_thresholds = {}

        logger.debug(
            f"EntityResolver initialized: fuzzy_threshold={self.fuzzy_threshold}%, "
            f"embedding_threshold={self.embedding_threshold}"
        )

    def _get_thresholds(self, entity_type: str) -> tuple[int, float]:
        """Return (fuzzy_threshold_0_100, embedding_threshold_0_1) for entity_type.

        Part 3c: Type-aware thresholds — file entities require high precision,
        concept entities allow higher recall.
        """
        if entity_type in self._type_thresholds:
            t = self._type_thresholds[entity_type]
            fuzzy = int(t.get("fuzzy", self._global_fuzzy_threshold / 100) * 100)
            embed = t.get("embedding", self._global_embedding_threshold)
            return fuzzy, embed
        return self._global_fuzzy_threshold, self._global_embedding_threshold

    async def resolve(self, name: str, entity_type: str) -> ResolvedEntity:
        """Resolve an entity name to an existing entity or create a new one.

        Resolution is scoped to user's entities first, then global entities.
        Uses Redis cache to speed up repeated lookups (SD-011).

        Args:
            name: The entity name to resolve
            entity_type: The type of entity (technology, concept, etc.)

        Returns:
            ResolvedEntity with match details
        """
        normalized_name = normalize_entity_name(name)

        # Stage 1: Check cache first (SD-011)
        cached = await self.cache.get_by_exact_name(self.user_id, normalized_name)
        if cached is not None:
            # Cache hit - could be an entity or None (negative cache)
            if cached:
                return ResolvedEntity(
                    id=cached["id"],
                    name=cached["name"],
                    type=cached["type"],
                    is_new=False,
                    match_method="cached",
                    confidence=1.0,
                )
            # Negative cache hit - no entity with this name exists
            # Continue to check other resolution methods

        # Stage 2: Exact match (case-insensitive) - user's entities first
        existing = await self._find_by_exact_match(normalized_name)
        if existing:
            # Cache the result (SD-011)
            await self.cache.set_by_exact_name(self.user_id, normalized_name, existing)
            return ResolvedEntity(
                id=existing["id"],
                name=existing["name"],
                type=existing["type"],
                is_new=False,
                match_method="exact",
                confidence=1.0,
            )

        # Stage 3: Canonical lookup
        canonical = get_canonical_name(name)
        if canonical.lower() != normalized_name:
            existing = await self._find_by_exact_match(canonical.lower())
            if existing:
                # Cache both the canonical and original name (SD-011)
                await self.cache.set_by_exact_name(
                    self.user_id, normalized_name, existing
                )
                await self.cache.set_by_exact_name(
                    self.user_id, canonical.lower(), existing
                )
                return ResolvedEntity(
                    id=existing["id"],
                    name=existing["name"],
                    type=existing["type"],
                    is_new=False,
                    match_method="canonical",
                    confidence=0.95,
                    canonical_name=canonical,
                )

        # Stage 4: Alias search
        existing = await self._find_by_alias(normalized_name)
        if existing:
            # Cache the alias lookup (SD-011)
            await self.cache.set_by_alias(self.user_id, normalized_name, existing)
            return ResolvedEntity(
                id=existing["id"],
                name=existing["name"],
                type=existing["type"],
                is_new=False,
                match_method="alias",
                confidence=0.92,
            )

        # Resolve per-type thresholds for stages 5 and 6 (Part 3c)
        fuzzy_t, embed_t = self._get_thresholds(entity_type)

        # Stage 5: Fulltext prefix search + Fuzzy match
        # Use Neo4j fulltext index to get candidates, then apply fuzzy matching
        fuzzy_result = await self._find_by_fuzzy_with_fulltext(
            normalized_name, fuzzy_threshold=fuzzy_t
        )
        if fuzzy_result:
            # Cache the fuzzy match result (SD-011)
            await self.cache.set_by_exact_name(
                self.user_id, normalized_name, fuzzy_result
            )
            return ResolvedEntity(
                id=fuzzy_result["id"],
                name=fuzzy_result["name"],
                type=fuzzy_result["type"],
                is_new=False,
                match_method="fuzzy",
                confidence=fuzzy_result["score"] / 100.0,
            )

        # Stage 6: Embedding similarity
        try:
            embedding = await self.embedding_service.embed_text(
                f"{entity_type}: {name}", input_type="passage"
            )
            similar = await self._find_by_embedding_similarity(
                embedding, threshold=embed_t
            )
            if similar:
                # Cache the embedding match result (SD-011)
                await self.cache.set_by_exact_name(
                    self.user_id, normalized_name, similar
                )
                return ResolvedEntity(
                    id=similar["id"],
                    name=similar["name"],
                    type=similar["type"],
                    is_new=False,
                    match_method="embedding",
                    confidence=similar["similarity"],
                )
        except (TimeoutError, ConnectionError) as e:
            logger.warning(f"Embedding service connection failed: {e}")
        except (ClientError, DatabaseError) as e:
            logger.warning(f"Database error during embedding similarity: {e}")

        # Stage 7: Create new entity
        # Cache negative result to prevent repeated lookups (SD-011)
        await self.cache.set_by_exact_name(self.user_id, normalized_name, None)

        final_name = canonical if canonical.lower() != normalized_name else name
        return ResolvedEntity(
            id=str(uuid4()),
            name=final_name,
            type=entity_type,
            is_new=True,
            match_method="new",
            confidence=1.0,
            aliases=[name] if final_name != name else [],
        )

    async def resolve_batch(self, entities: list[dict]) -> list[ResolvedEntity]:
        """Resolve multiple entities, returning resolved versions.

        Args:
            entities: List of dicts with 'name' and 'type' keys

        Returns:
            List of ResolvedEntity objects
        """
        resolved = []
        seen_names = {}  # Track resolved names to avoid duplicates within batch

        for entity in entities:
            name = entity.get("name", "")
            entity_type = entity.get("type", "concept")
            normalized = normalize_entity_name(name)

            # Check if we've already resolved this name in this batch
            if normalized in seen_names:
                resolved.append(seen_names[normalized])
                continue

            result = await self.resolve(name, entity_type)
            seen_names[normalized] = result

            # Also track canonical form
            canonical = get_canonical_name(name)
            if canonical.lower() != normalized:
                seen_names[canonical.lower()] = result

            resolved.append(result)

        return resolved

    async def _find_by_exact_match(self, normalized_name: str) -> Optional[dict]:
        """Find entity by exact case-insensitive name match.

        Prefers user's entities but falls back to global entities.
        """
        # First try user's entities
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND toLower(e.name) = $name
            RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type
            LIMIT 1
            """,
            name=normalized_name,
            user_id=self.user_id,
        )
        record = await result.single()
        if record:
            return dict(record)

        # Fall back to any entity (for cases like entity creation during decision save)
        result = await self.session.run(
            """
            MATCH (e:Entity)
            WHERE toLower(e.name) = $name
            RETURN e.id AS id, e.name AS name, e.type AS type
            LIMIT 1
            """,
            name=normalized_name,
        )
        record = await result.single()
        return dict(record) if record else None

    async def _find_by_alias(self, normalized_name: str) -> Optional[dict]:
        """Find entity by alias, preferring user's entities."""
        # First try user's entities
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND ANY(alias IN COALESCE(e.aliases, []) WHERE toLower(alias) = $name)
            RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type
            LIMIT 1
            """,
            name=normalized_name,
            user_id=self.user_id,
        )
        record = await result.single()
        if record:
            return dict(record)

        # Fall back to any entity
        result = await self.session.run(
            """
            MATCH (e:Entity)
            WHERE ANY(alias IN COALESCE(e.aliases, []) WHERE toLower(alias) = $name)
            RETURN e.id AS id, e.name AS name, e.type AS type
            LIMIT 1
            """,
            name=normalized_name,
        )
        record = await result.single()
        return dict(record) if record else None

    async def _find_by_fuzzy_with_fulltext(
        self,
        normalized_name: str,
        fuzzy_threshold: Optional[int] = None,
    ) -> Optional[dict]:
        """Find entity using fulltext index for candidates, then fuzzy match.

        This is more efficient than loading all entities:
        1. Use fulltext index to find candidates with similar prefixes/tokens
        2. Apply fuzzy matching only to candidates
        3. Fall back to batched loading if fulltext fails

        Args:
            normalized_name: The normalised entity name to match.
            fuzzy_threshold: rapidfuzz score threshold (0-100). When None,
                uses the global default (``self.fuzzy_threshold``). Pass a
                per-type value from ``_get_thresholds()`` for type-aware
                precision/recall trade-offs (Part 3c).

        Returns dict with id, name, type, score or None.
        """
        effective_threshold = fuzzy_threshold if fuzzy_threshold is not None else self.fuzzy_threshold

        # Try fulltext search first to get candidates
        try:
            # Search for entities with similar names using fulltext index
            # Use wildcard search for prefix matching
            search_term = f"{normalized_name}*"

            # First try user's entities via fulltext
            result = await self.session.run(
                """
                CALL db.index.fulltext.queryNodes('entity_fulltext', $search_term)
                YIELD node, score AS fulltext_score
                MATCH (d:DecisionTrace)-[:INVOLVES]->(node)
                WHERE d.user_id = $user_id OR d.user_id IS NULL
                RETURN DISTINCT node.id AS id, node.name AS name, node.type AS type
                LIMIT $limit
                """,
                search_term=search_term,
                user_id=self.user_id,
                limit=FUZZY_MATCH_LIMIT,
            )
            candidates = [dict(r) async for r in result]

            # Also try without fulltext for token-based matching
            if not candidates:
                # Try direct fuzzy on limited set
                candidates = await self._get_entity_names_batched()

            # Apply fuzzy matching to candidates
            best_match = None
            best_score = 0

            for entity in candidates:
                score = fuzz.ratio(normalized_name, entity["name"].lower())
                if score >= effective_threshold and score > best_score:
                    best_score = score
                    best_match = entity

            if best_match:
                return {**best_match, "score": best_score}

            return None

        except (ClientError, DatabaseError) as e:
            # Fulltext index may not exist, fall back to batched loading
            logger.debug(f"Fulltext search failed (index may not exist): {e}")
            return await self._find_by_fuzzy_batched(
                normalized_name, fuzzy_threshold=effective_threshold
            )

    async def _find_by_fuzzy_batched(
        self,
        normalized_name: str,
        fuzzy_threshold: Optional[int] = None,
    ) -> Optional[dict]:
        """Fallback: Find entity by fuzzy matching with batched loading.

        Loads entities in batches to prevent memory issues at scale.

        Args:
            normalized_name: The normalised entity name to match.
            fuzzy_threshold: rapidfuzz score threshold (0-100). Defaults to
                ``self.fuzzy_threshold`` (global setting) when not provided.
                Pass a per-type value from ``_get_thresholds()`` for
                type-aware precision/recall (Part 3c).
        """
        effective_threshold = fuzzy_threshold if fuzzy_threshold is not None else self.fuzzy_threshold

        best_match = None
        best_score = 0
        offset = 0

        while offset < FUZZY_MATCH_LIMIT:
            # Get user's entities in batches
            result = await self.session.run(
                """
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                WHERE d.user_id = $user_id OR d.user_id IS NULL
                RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type
                SKIP $offset
                LIMIT $batch_size
                """,
                user_id=self.user_id,
                offset=offset,
                batch_size=FUZZY_MATCH_BATCH_SIZE,
            )

            batch = [dict(r) async for r in result]
            if not batch:
                break

            for entity in batch:
                score = fuzz.ratio(normalized_name, entity["name"].lower())
                if score >= effective_threshold and score > best_score:
                    best_score = score
                    best_match = entity

            offset += FUZZY_MATCH_BATCH_SIZE

        # If no user entities matched, try global entities with limit
        if not best_match:
            result = await self.session.run(
                """
                MATCH (e:Entity)
                RETURN e.id AS id, e.name AS name, e.type AS type
                LIMIT $limit
                """,
                limit=FUZZY_MATCH_LIMIT,
            )

            async for record in result:
                entity = dict(record)
                score = fuzz.ratio(normalized_name, entity["name"].lower())
                if score >= effective_threshold and score > best_score:
                    best_score = score
                    best_match = entity

        if best_match:
            return {**best_match, "score": best_score}
        return None

    async def _get_entity_names_batched(self) -> list[dict]:
        """Get entity names with batched loading and LIMIT.

        Returns user's entities first with a reasonable limit to prevent OOM.
        """
        # Get user's entities with limit
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE d.user_id = $user_id OR d.user_id IS NULL
            RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type
            LIMIT $limit
            """,
            user_id=self.user_id,
            limit=FUZZY_MATCH_LIMIT,
        )
        user_entities = [dict(record) async for record in result]

        # If we have user entities, use those for fuzzy matching
        if user_entities:
            return user_entities

        # Fall back to all entities if user has none (with limit)
        result = await self.session.run(
            """
            MATCH (e:Entity)
            RETURN e.id AS id, e.name AS name, e.type AS type
            LIMIT $limit
            """,
            limit=FUZZY_MATCH_LIMIT,
        )
        return [dict(record) async for record in result]

    async def _get_all_entity_names(self) -> list[dict]:
        """Get all entity names for fuzzy matching.

        DEPRECATED: Use _get_entity_names_batched() or _find_by_fuzzy_with_fulltext() instead.
        This method is kept for backward compatibility but now applies LIMIT.

        Returns user's entities first, then global entities.
        """
        logger.warning(
            "_get_all_entity_names is deprecated. Use _find_by_fuzzy_with_fulltext instead."
        )
        return await self._get_entity_names_batched()

    async def _find_by_embedding_similarity(
        self, embedding: list[float], threshold: float
    ) -> Optional[dict]:
        """Find entity by embedding similarity, preferring user's entities."""
        # Try user's entities first with GDS
        try:
            result = await self.session.run(
                """
                MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
                WHERE (d.user_id = $user_id OR d.user_id IS NULL)
                AND e.embedding IS NOT NULL
                WITH DISTINCT e, gds.similarity.cosine(e.embedding, $embedding) AS similarity
                WHERE similarity > $threshold
                RETURN e.id AS id, e.name AS name, e.type AS type, similarity
                ORDER BY similarity DESC
                LIMIT 1
                """,
                embedding=embedding,
                threshold=threshold,
                user_id=self.user_id,
            )
            record = await result.single()
            if record:
                return dict(record)
        except (ClientError, DatabaseError):
            # Fall back to manual calculation (GDS not installed)
            return await self._find_by_embedding_similarity_manual(embedding, threshold)

        # Fall back to all entities
        try:
            result = await self.session.run(
                """
                MATCH (e:Entity)
                WHERE e.embedding IS NOT NULL
                WITH e, gds.similarity.cosine(e.embedding, $embedding) AS similarity
                WHERE similarity > $threshold
                RETURN e.id AS id, e.name AS name, e.type AS type, similarity
                ORDER BY similarity DESC
                LIMIT 1
                """,
                embedding=embedding,
                threshold=threshold,
            )
            record = await result.single()
            return dict(record) if record else None
        except (ClientError, DatabaseError):
            return await self._find_by_embedding_similarity_manual(embedding, threshold)

    async def _find_by_embedding_similarity_manual(
        self, embedding: list[float], threshold: float
    ) -> Optional[dict]:
        """Fallback: Find entity by embedding similarity without GDS.

        Prefers user's entities. Now uses LIMIT to prevent OOM.
        """
        # Try user's entities first (with limit)
        result = await self.session.run(
            """
            MATCH (d:DecisionTrace)-[:INVOLVES]->(e:Entity)
            WHERE (d.user_id = $user_id OR d.user_id IS NULL)
            AND e.embedding IS NOT NULL
            RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type, e.embedding AS embedding
            LIMIT $limit
            """,
            user_id=self.user_id,
            limit=FUZZY_MATCH_LIMIT,
        )

        best_match = None
        best_similarity = threshold

        async for record in result:
            other_embedding = record["embedding"]
            similarity = cosine_similarity(embedding, other_embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = {
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "similarity": similarity,
                }

        if best_match:
            return best_match

        # Fall back to all entities (with limit)
        result = await self.session.run(
            """
            MATCH (e:Entity)
            WHERE e.embedding IS NOT NULL
            RETURN e.id AS id, e.name AS name, e.type AS type, e.embedding AS embedding
            LIMIT $limit
            """,
            limit=FUZZY_MATCH_LIMIT,
        )

        async for record in result:
            other_embedding = record["embedding"]
            similarity = cosine_similarity(embedding, other_embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = {
                    "id": record["id"],
                    "name": record["name"],
                    "type": record["type"],
                    "similarity": similarity,
                }

        return best_match

    async def merge_duplicate_entities(self) -> dict:
        """Find and merge duplicate entities based on fuzzy matching.

        Only merges entities connected to the user's decisions.
        Returns statistics about merged entities.

        Uses batched loading to prevent memory issues at scale.
        """
        all_entities = await self._get_entity_names_batched()
        merged_count = 0
        merge_groups = []

        # Find potential duplicates
        processed = set()
        for i, entity in enumerate(all_entities):
            if entity["id"] in processed:
                continue

            group = [entity]
            processed.add(entity["id"])

            for other in all_entities[i + 1 :]:
                if other["id"] in processed:
                    continue

                score = fuzz.ratio(entity["name"].lower(), other["name"].lower())
                if score >= self.fuzzy_threshold:
                    group.append(other)
                    processed.add(other["id"])

            if len(group) > 1:
                merge_groups.append(group)

        # Merge each group
        for group in merge_groups:
            # Keep the entity with the canonical name or the first one
            canonical_entity = None
            for entity in group:
                if entity["name"] in CANONICAL_NAMES.values():
                    canonical_entity = entity
                    break

            primary = canonical_entity or group[0]
            others = [e for e in group if e["id"] != primary["id"]]

            for other in others:
                await self._merge_entities(primary["id"], other["id"])
                merged_count += 1

                # Invalidate cache for merged entity (SD-011)
                await self.cache.invalidate_entity(
                    self.user_id, other["id"], other.get("name")
                )

        # Invalidate cache for all affected entities (SD-011)
        if merge_groups:
            await self.cache.invalidate_user_cache(self.user_id)

        return {
            "groups_found": len(merge_groups),
            "entities_merged": merged_count,
        }

    async def _merge_entities(self, primary_id: str, secondary_id: str):
        """Merge secondary entity into primary, transferring all relationships."""
        # Step 1: Transfer INVOLVES relationships
        await self.session.run(
            """
            MATCH (primary:Entity {id: $primary_id})
            MATCH (secondary:Entity {id: $secondary_id})
            OPTIONAL MATCH (d:DecisionTrace)-[r:INVOLVES]->(secondary)
            WITH primary, secondary, collect(DISTINCT d) AS decisions
            FOREACH (d IN decisions |
                MERGE (d)-[:INVOLVES]->(primary)
            )
            """,
            primary_id=primary_id,
            secondary_id=secondary_id,
        )

        # Step 2: Transfer each relationship type separately (Cypher limitation)
        for rel_type in [
            "IS_A",
            "PART_OF",
            "RELATED_TO",
            "DEPENDS_ON",
            "ALTERNATIVE_TO",
        ]:
            # Outgoing relationships
            await self.session.run(
                f"""
                MATCH (primary:Entity {{id: $primary_id}})
                MATCH (secondary:Entity {{id: $secondary_id}})
                OPTIONAL MATCH (secondary)-[r:{rel_type}]->(other:Entity)
                WHERE other <> primary
                WITH primary, collect(DISTINCT other) AS targets
                FOREACH (t IN targets |
                    MERGE (primary)-[:{rel_type}]->(t)
                )
                """,
                primary_id=primary_id,
                secondary_id=secondary_id,
            )
            # Incoming relationships
            await self.session.run(
                f"""
                MATCH (primary:Entity {{id: $primary_id}})
                MATCH (secondary:Entity {{id: $secondary_id}})
                OPTIONAL MATCH (other:Entity)-[r:{rel_type}]->(secondary)
                WHERE other <> primary
                WITH primary, collect(DISTINCT other) AS sources
                FOREACH (s IN sources |
                    MERGE (s)-[:{rel_type}]->(primary)
                )
                """,
                primary_id=primary_id,
                secondary_id=secondary_id,
            )

        # Step 3: Add secondary name as alias and delete secondary
        await self.session.run(
            """
            MATCH (primary:Entity {id: $primary_id})
            MATCH (secondary:Entity {id: $secondary_id})
            SET primary.aliases = COALESCE(primary.aliases, []) + secondary.name
            DETACH DELETE secondary
            """,
            primary_id=primary_id,
            secondary_id=secondary_id,
        )

    async def add_alias(self, entity_id: str, alias: str):
        """Add an alias to an entity."""
        await self.session.run(
            """
            MATCH (e:Entity {id: $id})
            SET e.aliases = COALESCE(e.aliases, []) + $alias
            """,
            id=entity_id,
            alias=alias,
        )
        # Invalidate cache for this entity (SD-011)
        await self.cache.invalidate_entity(self.user_id, entity_id)


# Factory function
def get_entity_resolver(neo4j_session, user_id: str = "anonymous") -> EntityResolver:
    """Create an EntityResolver instance with the given Neo4j session."""
    return EntityResolver(neo4j_session, user_id=user_id)
