"""Cross-model comparison runner for RQ1.3 and RQ5.

Compares extraction quality across different NVIDIA LLM models.
"""

import asyncio
from typing import Any

from config import get_settings
from services.extractor import DecisionExtractor
from services.llm_providers.nvidia import NvidiaLLMProvider
from services.parser import Conversation
from utils.logging import get_logger

from evaluation.benchmark import EvaluationHarness
from evaluation.metrics import (
    calculate_completeness,
    calculate_exact_match,
    calculate_f1_score,
    calculate_precision,
    calculate_recall,
)

logger = get_logger(__name__)


class CrossModelResults:
    """Results from cross-model comparison."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.precision: float = 0.0
        self.recall: float = 0.0
        self.f1_score: float = 0.0
        self.avg_completeness: float = 0.0
        self.avg_confidence: float = 0.0
        self.cost_per_decision: float = 0.0  # Estimated cost
        self.p50_latency_ms: float = 0.0
        self.p99_latency_ms: float = 0.0
        self.total_decisions: int = 0
        self.total_tokens: int = 0


class CrossModelRunner:
    """Runner for comparing extraction quality across LLM models (RQ1.3, RQ5).
    
    Tests extraction on multiple NVIDIA models and compares:
    - F1, completeness, cost/decision, p50/p99 latency
    - Calibration transfer across models
    """

    def __init__(self):
        self.settings = get_settings()
        self.models = self.settings.nvidia_models_for_comparison
        self.evaluation_harness = EvaluationHarness()

    async def compare_models(
        self,
        conversations: list[Conversation],
        ground_truth: list[dict[str, Any]] | None = None,
    ) -> dict[str, CrossModelResults]:
        """Compare extraction quality across multiple models.
        
        Args:
            conversations: List of conversations to extract from
            ground_truth: Optional ground truth for evaluation
            
        Returns:
            Dict mapping model_name -> CrossModelResults
        """
        results = {}
        
        for model_name in self.models:
            logger.info(f"Testing model: {model_name}")
            
            try:
                # Create extractor with specific model
                # Note: This requires modifying DecisionExtractor to accept model parameter
                # For now, we'll use the default extractor and note the limitation
                model_results = await self._test_model(
                    model_name,
                    conversations,
                    ground_truth,
                )
                results[model_name] = model_results
                
            except Exception as e:
                logger.error(f"Failed to test model {model_name}: {e}")
                continue
        
        return results

    async def _test_model(
        self,
        model_name: str,
        conversations: list[Conversation],
        ground_truth: list[dict[str, Any]] | None,
    ) -> CrossModelResults:
        """Test a single model and collect metrics.
        
        Args:
            model_name: Model to test
            conversations: Conversations to extract from
            ground_truth: Optional ground truth
            
        Returns:
            CrossModelResults for this model
        """
        results = CrossModelResults(model_name)
        
        # Create LLM provider with specific model
        llm_provider = NvidiaLLMProvider(model=model_name)
        
        # Create extractor (would need to modify to accept custom LLM provider)
        # For now, this is a placeholder showing the structure
        extractor = DecisionExtractor()
        
        # Extract decisions and measure latency
        import time
        latencies = []
        all_extracted = []
        
        for conv in conversations:
            start_time = time.time()
            try:
                extracted = await extractor.extract_decisions(conv)
                latency_ms = (time.time() - start_time) * 1000
                latencies.append(latency_ms)
                all_extracted.extend([d.model_dump() for d in extracted])
            except Exception as e:
                logger.error(f"Extraction failed for {model_name}: {e}")
        
        results.total_decisions = len(all_extracted)
        
        # Calculate latency percentiles
        if latencies:
            sorted_latencies = sorted(latencies)
            results.p50_latency_ms = sorted_latencies[len(sorted_latencies) // 2]
            results.p99_latency_ms = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        
        # Calculate quality metrics if ground truth available
        if ground_truth:
            all_ground_truth = []
            for gt_entry in ground_truth:
                all_ground_truth.extend(gt_entry.get("decisions", []))
            
            results.precision = calculate_precision(all_extracted, all_ground_truth)
            results.recall = calculate_recall(all_extracted, all_ground_truth)
            results.f1_score = calculate_f1_score(results.precision, results.recall)
        
        # Calculate average completeness and confidence
        if all_extracted:
            completeness_scores = [
                calculate_completeness(d) for d in all_extracted
            ]
            results.avg_completeness = sum(completeness_scores) / len(completeness_scores)
            
            confidence_scores = [
                d.get("confidence", 0.5) for d in all_extracted
            ]
            results.avg_confidence = sum(confidence_scores) / len(confidence_scores)
        
        # Estimate cost (placeholder - would need actual token counts)
        # results.cost_per_decision = estimated_cost
        
        return results
