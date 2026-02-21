"""Memory compression service for long conversations (Recall-inspired, Phase 5).

Compresses conversation context while preserving decision traces and critical constraints.
Useful when conversations exceed context window limits.
"""

from typing import Any, Optional

from config import get_settings
from services.llm_providers.nvidia import NvidiaLLMProvider
from utils.logging import get_logger

logger = get_logger(__name__)


class MemoryCompressor:
    """Compresses long conversations into semantic summaries while preserving decisions.
    
    Inspired by Recall (Claude Mem) - compresses context for future sessions.
    Preserves verbatim quotes for critical constraints (CogCanvas method).
    """
    
    def __init__(self):
        """Initialize memory compressor with LLM provider."""
        settings = get_settings()
        self.llm = NvidiaLLMProvider(model=settings.nvidia_model)
        self.compression_ratio_target = 0.3  # Target 30% of original size
    
    async def compress_conversation(
        self,
        conversation_text: str,
        decisions: list[dict],
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """Compress a conversation while preserving decision traces.
        
        Args:
            conversation_text: Full conversation text
            decisions: List of extracted decisions (to preserve verbatim)
            max_tokens: Maximum tokens for compressed output (optional)
            
        Returns:
            Dictionary with:
            - compressed_text: Compressed summary
            - preserved_decisions: Decisions with verbatim quotes preserved
            - compression_ratio: Original size / compressed size
            - token_estimate: Estimated token count
        """
        settings = get_settings()
        if max_tokens is None:
            max_tokens = settings.max_prompt_tokens // 2  # Use half of max for compressed
        
        # Extract verbatim quotes from decisions (critical constraints)
        verbatim_quotes = []
        for decision in decisions:
            if decision.get("verbatim_decision"):
                verbatim_quotes.append(decision["verbatim_decision"])
            if decision.get("verbatim_trigger"):
                verbatim_quotes.append(decision["verbatim_trigger"])
            if decision.get("verbatim_rationale"):
                verbatim_quotes.append(decision["verbatim_rationale"])
        
        # Build compression prompt
        compression_prompt = f"""Compress the following conversation into a concise summary while preserving:
1. All key decisions and their verbatim quotes (exact wording is critical)
2. Important constraints and requirements
3. Technical choices and rationale
4. Context needed for future sessions

CRITICAL: Preserve these exact verbatim quotes verbatim (do not paraphrase):
{chr(10).join(f"- {quote}" for quote in verbatim_quotes[:10])}

Conversation:
{conversation_text[:50000]}  # Limit input size

Compressed Summary:"""
        
        try:
            # Generate compressed summary
            compressed_text = await self.llm.generate(
                prompt=compression_prompt,
                temperature=0.2,  # Low temperature for factual compression
                max_tokens=max_tokens,
            )
            
            # Calculate compression metrics
            original_size = len(conversation_text)
            compressed_size = len(compressed_text)
            compression_ratio = compressed_size / original_size if original_size > 0 else 1.0
            
            # Estimate token count (rough: 1 token ≈ 4 characters)
            token_estimate = len(compressed_text) // 4
            
            logger.info(
                f"Compressed conversation: {original_size} -> {compressed_size} chars "
                f"(ratio: {compression_ratio:.2f}, ~{token_estimate} tokens)"
            )
            
            return {
                "compressed_text": compressed_text,
                "preserved_decisions": decisions,  # Decisions preserved as-is
                "compression_ratio": compression_ratio,
                "token_estimate": token_estimate,
                "original_size": original_size,
                "compressed_size": compressed_size,
            }
            
        except Exception as e:
            logger.error(f"Memory compression failed: {e}")
            # Fallback: return original with minimal compression
            return {
                "compressed_text": conversation_text[:max_tokens * 4],  # Rough token limit
                "preserved_decisions": decisions,
                "compression_ratio": 1.0,
                "token_estimate": len(conversation_text) // 4,
                "original_size": len(conversation_text),
                "compressed_size": len(conversation_text),
            }
    
    async def estimate_token_cost(
        self,
        original_text: str,
        compressed_text: str,
        cost_per_1k_tokens: float = 0.001,  # Example: $0.001 per 1k tokens
    ) -> dict[str, float]:
        """Estimate token cost savings from compression.
        
        Args:
            original_text: Original conversation text
            compressed_text: Compressed text
            cost_per_1k_tokens: Cost per 1000 tokens (default example)
            
        Returns:
            Dictionary with cost estimates
        """
        # Rough token estimation (1 token ≈ 4 characters)
        original_tokens = len(original_text) // 4
        compressed_tokens = len(compressed_text) // 4
        
        original_cost = (original_tokens / 1000) * cost_per_1k_tokens
        compressed_cost = (compressed_tokens / 1000) * cost_per_1k_tokens
        savings = original_cost - compressed_cost
        
        return {
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "original_cost": original_cost,
            "compressed_cost": compressed_cost,
            "savings": savings,
            "savings_percent": (savings / original_cost * 100) if original_cost > 0 else 0.0,
        }


# Global compressor instance
_compressor: Optional[MemoryCompressor] = None


def get_memory_compressor() -> MemoryCompressor:
    """Get or create global memory compressor instance."""
    global _compressor
    if _compressor is None:
        _compressor = MemoryCompressor()
    return _compressor
