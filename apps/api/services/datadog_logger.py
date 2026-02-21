"""Datadog logging integration for LLM observability.

Tracks LLM calls, token usage, latency, and costs for monitoring in Datadog.
Sends logs directly to Datadog HTTP API.
"""

import json
import time
from typing import Any, Optional

import httpx

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class DatadogLLMLogger:
    """Logger for LLM calls to Datadog with structured metrics."""

    # Cost per 1M tokens (approximate NVIDIA NIM pricing)
    COST_PER_1M_INPUT_TOKENS = 0.30
    COST_PER_1M_OUTPUT_TOKENS = 2.50

    @staticmethod
    async def send_to_datadog(log_data: dict) -> None:
        """Send log directly to Datadog HTTP API.
        
        Args:
            log_data: Structured log data to send
        """
        settings = get_settings()
        
        if not settings.datadog_integration_enabled:
            logger.debug("Datadog integration disabled, skipping log send")
            return
            
        if not settings.datadog_api_key:
            logger.warning("Datadog API key not configured, skipping log send")
            return
        
        try:
            url = f"https://http-intake.logs.{settings.datadog_site}/api/v2/logs"
            api_key = settings.datadog_api_key.get_secret_value()
            
            logger.info(f"[DATADOG] Attempting to send log to {url}")
            logger.info(f"[DATADOG] API key configured: {bool(api_key)}, length: {len(api_key) if api_key else 0}")
            
            headers = {
                "DD-API-KEY": api_key,
                "Content-Type": "application/json",
            }
            
            payload = {
                "ddsource": "continuum-api",
                "ddtags": "env:hackathon,service:continuum-llm",
                "hostname": "continuum-api",
                "message": log_data.get("log_message", "LLM call"),
                **log_data,
            }
            
            logger.info(f"[DATADOG] Payload size: {len(str(payload))} bytes")
            
            async with httpx.AsyncClient() as client:
                logger.info("[DATADOG] Sending HTTP POST request...")
                response = await client.post(url, json=[payload], headers=headers, timeout=10.0)
                logger.info(f"[DATADOG] Response status: {response.status_code}")
                logger.info(f"[DATADOG] Response body: {response.text[:200]}")
                
                if response.status_code not in (200, 202):
                    logger.warning(f"Failed to send log to Datadog: {response.status_code} - {response.text}")
                else:
                    logger.info(f"✅ Successfully sent log to Datadog: {response.status_code}")
        except httpx.TimeoutException as e:
            logger.error(f"[DATADOG] Timeout sending log to Datadog: {e}")
        except httpx.ConnectError as e:
            logger.error(f"[DATADOG] Connection error sending log to Datadog: {e}")
        except Exception as e:
            logger.error(f"[DATADOG] Error sending log to Datadog: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[DATADOG] Traceback: {traceback.format_exc()}")

    @staticmethod
    async def log_llm_call(
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency_ms: float,
        operation: str = "generate",
        streaming: bool = False,
        user_id: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
        **extra_context,
    ) -> None:
        """Log an LLM call with full observability metrics.

        Args:
            model: Model name (e.g., "nvidia/llama-3.3-nemotron-super-49b-v1.5")
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            total_tokens: Total tokens used
            latency_ms: Request latency in milliseconds
            operation: Operation type ("generate", "extract_decisions", "analyze", etc.)
            streaming: Whether this was a streaming request
            user_id: User ID if available
            success: Whether the call succeeded
            error: Error message if failed
            **extra_context: Additional context (e.g., decision_count, entity_count)
        """
        # Calculate cost
        input_cost = (prompt_tokens / 1_000_000) * DatadogLLMLogger.COST_PER_1M_INPUT_TOKENS
        output_cost = (completion_tokens / 1_000_000) * DatadogLLMLogger.COST_PER_1M_OUTPUT_TOKENS
        total_cost = input_cost + output_cost

        # Structured log for Datadog
        log_data = {
            "log_message": f"LLM call: {operation} ({'success' if success else 'failed'})",
            "llm.model": model,
            "llm.operation": operation,
            "llm.streaming": streaming,
            "llm.tokens.prompt": prompt_tokens,
            "llm.tokens.completion": completion_tokens,
            "llm.tokens.total": total_tokens,
            "llm.latency_ms": latency_ms,
            "llm.cost.input_usd": round(input_cost, 6),
            "llm.cost.output_usd": round(output_cost, 6),
            "llm.cost.total_usd": round(total_cost, 6),
            "llm.success": success,
            "timestamp": int(time.time() * 1000),  # milliseconds
        }

        if user_id:
            log_data["user_id"] = user_id

        if error:
            log_data["llm.error"] = error

        # Add extra context
        log_data.update(extra_context)

        # Log locally
        if success:
            logger.info("LLM call completed", extra=log_data)
        else:
            logger.error("LLM call failed", extra=log_data)
        
        # Send to Datadog
        await DatadogLLMLogger.send_to_datadog(log_data)

    @staticmethod
    async def log_extraction_batch(
        model: str,
        conversation_count: int,
        decisions_extracted: int,
        entities_found: int,
        total_tokens: int,
        total_latency_ms: float,
        user_id: Optional[str] = None,
    ) -> None:
        """Log a batch extraction operation.

        Args:
            model: Model name
            conversation_count: Number of conversations processed
            decisions_extracted: Total decisions extracted
            entities_found: Total entities found
            total_tokens: Total tokens used across all calls
            total_latency_ms: Total latency across all calls
            user_id: User ID if available
        """
        avg_latency = total_latency_ms / conversation_count if conversation_count > 0 else 0
        decisions_per_conversation = (
            decisions_extracted / conversation_count if conversation_count > 0 else 0
        )

        log_data = {
            "log_message": f"LLM extraction batch: {decisions_extracted} decisions from {conversation_count} conversations",
            "llm.operation": "extraction_batch",
            "llm.model": model,
            "batch.conversation_count": conversation_count,
            "batch.decisions_extracted": decisions_extracted,
            "batch.entities_found": entities_found,
            "batch.decisions_per_conversation": round(decisions_per_conversation, 2),
            "llm.tokens.total": total_tokens,
            "llm.latency_ms.total": total_latency_ms,
            "llm.latency_ms.avg": round(avg_latency, 2),
            "timestamp": int(time.time() * 1000),
        }

        if user_id:
            log_data["user_id"] = user_id

        logger.info("LLM extraction batch completed", extra=log_data)
        await DatadogLLMLogger.send_to_datadog(log_data)


class LLMCallTimer:
    """Context manager for timing LLM calls."""

    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000
