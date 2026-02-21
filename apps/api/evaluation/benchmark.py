"""Evaluation harness for running benchmarks on decision extraction (RQ1)."""

from typing import Any

from services.extractor import DecisionExtractor
from services.parser import Conversation
from utils.logging import get_logger

from evaluation.metrics import (
    calculate_completeness,
    calculate_exact_match,
    calculate_f1_score,
    calculate_precision,
    calculate_recall,
)

logger = get_logger(__name__)


class EvaluationResults:
    """Results from evaluation run."""

    def __init__(self):
        self.precision: float = 0.0
        self.recall: float = 0.0
        self.f1_score: float = 0.0
        self.avg_completeness: float = 0.0
        self.exact_match_rate: float = 0.0
        self.total_extracted: int = 0
        self.total_ground_truth: int = 0
        self.metrics_by_decision_type: dict[str, dict[str, float]] = {}


class EvaluationHarness:
    """Evaluation harness for decision extraction quality (RQ1).
    
    Runs benchmarks on decision extraction pipeline and calculates:
    - Precision (>0.80 target)
    - Recall (>0.70 target)
    - F1 Score
    - Completeness (% of fields filled >20 chars)
    - Exact Match (verbatim text match, CogCanvas metric)
    """

    def __init__(self):
        self.extractor = DecisionExtractor()

    async def evaluate_extraction(
        self,
        conversations: list[Conversation],
        ground_truth: list[dict[str, Any]],
    ) -> EvaluationResults:
        """Evaluate extraction quality on conversations with ground truth.
        
        Args:
            conversations: List of conversations to extract from
            ground_truth: List of ground truth annotations
                        Format: [{"conversation_id": str, "decisions": [dict, ...]}, ...]
        
        Returns:
            EvaluationResults with all metrics
        """
        results = EvaluationResults()
        
        # Extract decisions from all conversations
        all_extracted = []
        all_ground_truth = []
        
        for conv in conversations:
            try:
                extracted = await self.extractor.extract_decisions(conv)
                all_extracted.extend([d.model_dump() for d in extracted])
            except Exception as e:
                logger.error(f"Failed to extract from conversation: {e}")
        
        # Collect ground truth decisions
        for gt_entry in ground_truth:
            all_ground_truth.extend(gt_entry.get("decisions", []))
        
        results.total_extracted = len(all_extracted)
        results.total_ground_truth = len(all_ground_truth)
        
        # Calculate metrics
        results.precision = calculate_precision(all_extracted, all_ground_truth)
        results.recall = calculate_recall(all_extracted, all_ground_truth)
        results.f1_score = calculate_f1_score(results.precision, results.recall)
        
        # Calculate average completeness
        if all_extracted:
            completeness_scores = [
                calculate_completeness(d) for d in all_extracted
            ]
            results.avg_completeness = sum(completeness_scores) / len(completeness_scores)
        
        # Calculate exact match rate (if verbatim fields available)
        if all_extracted and all_ground_truth:
            exact_matches = 0
            total_verbatim = 0
            for extracted in all_extracted:
                verbatim_decision = extracted.get("verbatim_decision")
                if verbatim_decision:
                    total_verbatim += 1
                    for gt in all_ground_truth:
                        gt_verbatim = gt.get("verbatim_decision")
                        if gt_verbatim and calculate_exact_match(verbatim_decision, gt_verbatim):
                            exact_matches += 1
                            break
            
            if total_verbatim > 0:
                results.exact_match_rate = exact_matches / total_verbatim
        
        return results

    async def evaluate_retrieval(
        self,
        queries: list[str],
        expected_results: list[list[str]],
    ) -> dict[str, float]:
        """Evaluate retrieval quality (for search/RAG evaluation).
        
        Args:
            queries: List of search queries
            expected_results: List of expected result IDs for each query
            
        Returns:
            Dict with retrieval metrics (precision@k, recall@k, NDCG@k)
        """
        # Placeholder for retrieval evaluation
        # Would integrate with search service
        return {
            "precision@5": 0.0,
            "recall@5": 0.0,
            "ndcg@5": 0.0,
        }
