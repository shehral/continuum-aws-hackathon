"""Batch LLM processing for efficient entity and decision extraction (KG-P1-4).

Optimizes LLM usage by:
- Batching multiple texts into single LLM calls where possible
- Parallel processing of independent extraction tasks
- Smart chunking to stay within token limits
- Caching and deduplication of identical texts
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from config import get_settings
from services.extractor import (
    LLMResponseCache,
    get_extractor,
)
from services.llm import get_llm_client
from services.parser import parse_claude_log
from utils.json_extraction import extract_json_from_response
from utils.logging import get_logger

logger = get_logger(__name__)


# Batch processing configuration
DEFAULT_MAX_CONCURRENT = 3  # Respect rate limits
DEFAULT_MAX_TEXTS_PER_PROMPT = 5  # Texts per batched prompt
MAX_TOKENS_PER_BATCH = 8000  # Token limit for batched prompts
CHARS_PER_TOKEN_ESTIMATE = 4  # Rough estimate


@dataclass
class BatchItem:
    """Single item in a batch processing job."""

    id: str
    text: str
    source: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None
    processing_time_ms: int = 0


@dataclass
class BatchResult:
    """Result of a batch processing job."""

    batch_id: str
    total_items: int
    successful: int
    failed: int
    items: list[BatchItem]
    processing_time_ms: int
    started_at: datetime
    completed_at: datetime


# Batched entity extraction prompt
BATCH_ENTITY_PROMPT = """Extract technical entities from EACH of the following texts.
Return a JSON object with text numbers as keys.

## Entity Types
- technology: Tools, languages, frameworks, databases (PostgreSQL, React, Python)
- concept: Abstract ideas, methodologies (microservices, REST API, caching)
- pattern: Design patterns (singleton, repository pattern, CQRS)
- system: Software systems, services (authentication system, payment gateway)
- person: People mentioned
- organization: Companies, teams

## Example Output
{{
  "1": {{"entities": [{{"name": "React", "type": "technology", "confidence": 0.95}}]}},
  "2": {{"entities": [{{"name": "PostgreSQL", "type": "technology", "confidence": 0.95}}]}}
}}

## Texts to Process
{texts_block}

Return ONLY valid JSON with numbered keys matching the text numbers."""


class BatchProcessor:
    """Batch processor for efficient LLM operations (KG-P1-4).

    Provides batching strategies to reduce API overhead:
    1. Multi-text entity extraction in single prompt
    2. Parallel processing with rate limit awareness
    3. Automatic chunking for large batches
    """

    def __init__(
        self,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        max_texts_per_prompt: int = DEFAULT_MAX_TEXTS_PER_PROMPT,
    ):
        """Initialize batch processor.

        Args:
            max_concurrent: Maximum concurrent LLM calls
            max_texts_per_prompt: Maximum texts to combine in single prompt
        """
        self.max_concurrent = max_concurrent
        self.max_texts_per_prompt = max_texts_per_prompt
        self.llm = get_llm_client()
        self.cache = LLMResponseCache()
        self.settings = get_settings()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text."""
        return len(text) // CHARS_PER_TOKEN_ESTIMATE + 1

    def _create_text_batches(
        self, texts: list[str], max_tokens: int = MAX_TOKENS_PER_BATCH
    ) -> list[list[tuple[int, str]]]:
        """Split texts into batches respecting token limits.

        Args:
            texts: List of texts to batch
            max_tokens: Maximum tokens per batch

        Returns:
            List of batches, each containing (index, text) tuples
        """
        batches = []
        current_batch = []
        current_tokens = 0

        for idx, text in enumerate(texts):
            text_tokens = self._estimate_tokens(text)

            # Check if adding this text would exceed limits
            would_exceed_size = len(current_batch) >= self.max_texts_per_prompt
            would_exceed_tokens = current_tokens + text_tokens > max_tokens

            if current_batch and (would_exceed_size or would_exceed_tokens):
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0

            # Handle oversized texts - process individually
            if text_tokens > max_tokens:
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_tokens = 0
                batches.append([(idx, text)])
                continue

            current_batch.append((idx, text))
            current_tokens += text_tokens

        if current_batch:
            batches.append(current_batch)

        return batches

    def _format_texts_block(self, batch: list[tuple[int, str]]) -> str:
        """Format a batch of texts for the prompt."""
        lines = []
        for idx, text in batch:
            # Truncate very long texts and use 1-based indexing
            truncated = text[:1000] if len(text) > 1000 else text
            lines.append(f'Text {idx + 1}: "{truncated}"')
        return "\n".join(lines)

    async def extract_entities_batch(
        self,
        texts: list[str],
        bypass_cache: bool = False,
    ) -> list[list[dict]]:
        """Extract entities from multiple texts efficiently.

        Uses batched LLM calls to reduce API requests.

        Args:
            texts: List of texts to extract entities from
            bypass_cache: If True, skip cache lookup

        Returns:
            List of entity lists, one per input text
        """
        if not texts:
            return []

        results: list[list[dict]] = [[] for _ in texts]
        texts_to_process: list[tuple[int, str]] = []
        cached_count = 0

        # Check cache first
        for idx, text in enumerate(texts):
            if not bypass_cache:
                cached = await self.cache.get(text, "entities")
                if cached is not None:
                    results[idx] = cached
                    cached_count += 1
                    continue
            texts_to_process.append((idx, text))

        if cached_count > 0:
            logger.debug(f"Batch entity extraction: {cached_count} cache hits")

        if not texts_to_process:
            return results

        # Create batches
        batches = self._create_text_batches([t for _, t in texts_to_process])
        original_indices = [idx for idx, _ in texts_to_process]

        logger.info(
            f"Batch entity extraction: {len(texts_to_process)} texts in {len(batches)} batches"
        )

        # Process each batch
        extractor = get_extractor()

        async def process_batch(
            batch: list[tuple[int, str]],
        ) -> list[tuple[int, list[dict]]]:
            """Process a single batch with rate limiting."""
            async with self._semaphore:
                batch_results = []

                # Single text - use standard extraction
                if len(batch) == 1:
                    local_idx, text = batch[0]
                    entities = await extractor.extract_entities(text, bypass_cache=True)
                    await self.cache.set(text, "entities", entities)
                    return [(local_idx, entities)]

                # Multiple texts - use batch prompt
                texts_block = self._format_texts_block(batch)
                prompt = BATCH_ENTITY_PROMPT.format(texts_block=texts_block)

                try:
                    response = await self.llm.generate(prompt, temperature=0.3)
                    parsed = extract_json_from_response(response)

                    if parsed is None:
                        # Fallback to individual processing
                        for local_idx, text in batch:
                            entities = await extractor.extract_entities(
                                text, bypass_cache=True
                            )
                            await self.cache.set(text, "entities", entities)
                            batch_results.append((local_idx, entities))
                        return batch_results

                    # Parse batch response
                    for local_idx, text in batch:
                        key = str(local_idx + 1)  # 1-based in prompt
                        if key in parsed:
                            entry = parsed[key]
                            entities = (
                                entry.get("entities", [])
                                if isinstance(entry, dict)
                                else []
                            )
                        else:
                            entities = []
                        await self.cache.set(text, "entities", entities)
                        batch_results.append((local_idx, entities))

                except Exception as e:
                    logger.error(f"Batch entity extraction failed: {e}")
                    # Fallback to individual processing
                    for local_idx, text in batch:
                        try:
                            entities = await extractor.extract_entities(
                                text, bypass_cache=True
                            )
                            await self.cache.set(text, "entities", entities)
                        except Exception:
                            entities = []
                        batch_results.append((local_idx, entities))

                return batch_results

        # Process all batches
        all_batch_results = await asyncio.gather(
            *[process_batch(batch) for batch in batches], return_exceptions=True
        )

        # Collect results
        for batch_result in all_batch_results:
            if isinstance(batch_result, Exception):
                logger.error(f"Batch processing failed: {batch_result}")
                continue
            for local_idx, entities in batch_result:
                original_idx = original_indices[local_idx]
                results[original_idx] = entities

        return results

    async def process_log_files_batch(
        self,
        file_paths: list[str],
        user_id: str = "anonymous",
        save_to_graph: bool = True,
    ) -> BatchResult:
        """Process multiple Claude log files in batch.

        Args:
            file_paths: List of log file paths
            user_id: User ID for multi-tenant isolation
            save_to_graph: Whether to save extracted decisions to graph

        Returns:
            BatchResult with processing statistics
        """
        batch_id = str(uuid4())
        started_at = datetime.now(UTC)
        items: list[BatchItem] = []

        # Create batch items
        for file_path in file_paths:
            items.append(
                BatchItem(
                    id=str(uuid4()),
                    text="",  # Will be populated after parsing
                    source=file_path,
                )
            )

        # Process files
        extractor = get_extractor()

        async def process_file(item: BatchItem) -> None:
            """Process a single log file."""
            file_path = item.source
            start_time = datetime.now(UTC)

            async with self._semaphore:
                try:
                    # Parse the log file
                    conversations = parse_claude_log(file_path)
                    if not conversations:
                        item.result = {
                            "decisions": [],
                            "message": "No conversations found",
                        }
                        return

                    # Process the first conversation (most recent)
                    conversation = conversations[0]
                    item.text = conversation.get_full_text()[:500]  # Preview

                    # Extract decisions
                    decisions = await extractor.extract_decisions(conversation)

                    saved_ids = []
                    if save_to_graph and decisions:
                        for decision in decisions:
                            decision_id = await extractor.save_decision(
                                decision,
                                source="claude_logs",
                                user_id=user_id,
                            )
                            saved_ids.append(decision_id)

                    item.result = {
                        "decisions": [
                            {
                                "trigger": d.trigger[:100],
                                "confidence": d.confidence,
                            }
                            for d in decisions
                        ],
                        "saved_ids": saved_ids,
                        "file_path": file_path,
                    }

                    item.processing_time_ms = int(
                        (datetime.now(UTC) - start_time).total_seconds() * 1000
                    )

                except Exception as e:
                    item.error = str(e)
                    logger.error(f"Log file processing failed for {file_path}: {e}")

        await asyncio.gather(*[process_file(item) for item in items])

        completed_at = datetime.now(UTC)
        processing_time = int((completed_at - started_at).total_seconds() * 1000)

        successful = sum(1 for item in items if item.result is not None)
        failed = sum(1 for item in items if item.error is not None)

        # Calculate total decisions extracted
        total_decisions = sum(
            len(item.result.get("decisions", [])) for item in items if item.result
        )

        logger.info(
            "Batch log processing complete",
            extra={
                "batch_id": batch_id,
                "total_items": len(items),
                "successful": successful,
                "failed": failed,
                "total_decisions": total_decisions,
                "processing_time_ms": processing_time,
            },
        )

        return BatchResult(
            batch_id=batch_id,
            total_items=len(items),
            successful=successful,
            failed=failed,
            items=items,
            processing_time_ms=processing_time,
            started_at=started_at,
            completed_at=completed_at,
        )


# Singleton instance
_batch_processor: Optional[BatchProcessor] = None


def get_batch_processor(
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    max_texts_per_prompt: int = DEFAULT_MAX_TEXTS_PER_PROMPT,
) -> BatchProcessor:
    """Get or create the batch processor singleton (KG-P1-4).

    Args:
        max_concurrent: Maximum concurrent LLM calls
        max_texts_per_prompt: Maximum texts to combine in single prompt

    Returns:
        BatchProcessor instance
    """
    global _batch_processor
    if _batch_processor is None:
        _batch_processor = BatchProcessor(
            max_concurrent=max_concurrent,
            max_texts_per_prompt=max_texts_per_prompt,
        )
    return _batch_processor
