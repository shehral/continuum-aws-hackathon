"""Evaluation metrics for decision extraction quality (RQ1).

Targets from Research Mapping:
- Precision: >0.80 (80% of extracted decisions are valid)
- Recall: >0.70 (70% of actual decisions are extracted)
- Completeness: % of 5 trace fields filled >20 chars
"""

from typing import Any


def calculate_precision(
    extracted_decisions: list[dict],
    ground_truth_decisions: list[dict],
) -> float:
    """Calculate precision: % of extracted decisions that are valid.
    
    Args:
        extracted_decisions: List of extracted decision dicts
        ground_truth_decisions: List of ground truth decision dicts
        
    Returns:
        Precision score (0.0 to 1.0)
    """
    if not extracted_decisions:
        return 0.0
    
    # For now, simple matching by decision text
    # In full implementation, would use more sophisticated matching
    valid_count = 0
    for extracted in extracted_decisions:
        extracted_text = extracted.get("decision", "").lower()
        # Check if this matches any ground truth decision
        for gt in ground_truth_decisions:
            gt_text = gt.get("decision", "").lower()
            # Simple text similarity (would use better matching in production)
            if extracted_text in gt_text or gt_text in extracted_text:
                valid_count += 1
                break
    
    return valid_count / len(extracted_decisions)


def calculate_recall(
    extracted_decisions: list[dict],
    ground_truth_decisions: list[dict],
) -> float:
    """Calculate recall: % of actual decisions that were extracted.
    
    Args:
        extracted_decisions: List of extracted decision dicts
        ground_truth_decisions: List of ground truth decision dicts
        
    Returns:
        Recall score (0.0 to 1.0)
    """
    if not ground_truth_decisions:
        return 1.0 if not extracted_decisions else 0.0
    
    # Count how many ground truth decisions were found
    found_count = 0
    for gt in ground_truth_decisions:
        gt_text = gt.get("decision", "").lower()
        # Check if any extracted decision matches
        for extracted in extracted_decisions:
            extracted_text = extracted.get("decision", "").lower()
            if extracted_text in gt_text or gt_text in extracted_text:
                found_count += 1
                break
    
    return found_count / len(ground_truth_decisions)


def calculate_f1_score(precision: float, recall: float) -> float:
    """Calculate F1 score: harmonic mean of precision and recall.
    
    Args:
        precision: Precision score
        recall: Recall score
        
    Returns:
        F1 score (0.0 to 1.0)
    """
    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


def calculate_completeness(decision: dict, min_chars: int = 20) -> float:
    """Calculate completeness: % of 5 trace fields filled >min_chars.
    
    The 5 core fields are: trigger, context, options, decision, rationale.
    
    Args:
        decision: Decision dict with trace fields
        min_chars: Minimum characters to consider field "filled"
        
    Returns:
        Completeness score (0.0 to 1.0)
    """
    required_fields = ["trigger", "decision", "rationale", "context"]
    filled_count = 0
    
    for field in required_fields:
        value = decision.get(field, "")
        if isinstance(value, str) and len(value.strip()) >= min_chars:
            filled_count += 1
    
    # Check options (array field)
    options = decision.get("options", [])
    if options and any(len(str(opt).strip()) >= min_chars for opt in options):
        filled_count += 1
    
    return filled_count / 5.0


def calculate_exact_match(
    extracted_text: str,
    ground_truth_text: str,
) -> bool:
    """Calculate exact match: verbatim text match (CogCanvas metric).
    
    Args:
        extracted_text: Extracted verbatim text
        ground_truth_text: Ground truth verbatim text
        
    Returns:
        True if exact match (normalized whitespace), False otherwise
    """
    # Normalize whitespace for comparison
    extracted_norm = " ".join(extracted_text.split())
    gt_norm = " ".join(ground_truth_text.split())
    
    return extracted_norm.lower() == gt_norm.lower()
