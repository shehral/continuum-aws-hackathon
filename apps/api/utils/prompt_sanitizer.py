"""Prompt injection defense utilities (ML-P1-1).

This module provides functions to detect and neutralize prompt injection attempts
before sending user input to LLMs. Implements defense-in-depth with multiple layers:

1. Pattern-based detection for known injection techniques
2. Structural analysis for suspicious formatting
3. Input transformation to neutralize threats
4. Confidence scoring for risk assessment

References:
- OWASP LLM Top 10: LLM01 Prompt Injection
- Anthropic prompt injection guidelines
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

from utils.logging import get_logger

logger = get_logger(__name__)


class InjectionRiskLevel(str, Enum):
    """Risk levels for detected prompt injection attempts."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SanitizationResult:
    """Result of prompt sanitization analysis."""

    original_text: str
    sanitized_text: str
    risk_level: InjectionRiskLevel
    detected_patterns: List[str]
    confidence: float  # 0.0 to 1.0
    was_modified: bool


# =============================================================================
# Pattern Definitions for Prompt Injection Detection
# =============================================================================

# System prompt override attempts
SYSTEM_PROMPT_PATTERNS = [
    # Direct override attempts
    (
        r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?|guidelines?)",
        "system_override",
    ),
    (
        r"\b(?:new|actual|real)\s+(?:system\s+)?(?:instructions?|prompt)\s*[:\-]",
        "system_override",
    ),
    (r"\byou\s+are\s+(?:now|actually)\s+(?:a|an)\b", "role_hijack"),
    (r"\bact\s+as\s+(?:if\s+)?(?:you\s+(?:are|were)\s+)?(?:a|an|the)\b", "role_hijack"),
    (r"\bpretend\s+(?:you\s+are|to\s+be)\b", "role_hijack"),
    (r"\bfrom\s+now\s+on\b.*\byou\s+(?:will|must|should)\b", "behavior_override"),
    # Instruction boundary attacks
    (r"###\s*(?:system|instruction|prompt)", "boundary_attack"),
    (r"\[(?:SYSTEM|INST|INSTRUCTION)\]", "boundary_attack"),
    (r"<(?:system|instruction|prompt)>", "boundary_attack"),
    (r"(?:^|\n)(?:System|Assistant|Human):", "role_injection"),
    # Jailbreak techniques
    (r"\bDAN\s*(?:mode|prompt)?\b", "jailbreak"),
    (r"\bdev(?:eloper)?\s+mode\b", "jailbreak"),
    (r"\bunrestricted\s+mode\b", "jailbreak"),
    (r"\bno\s+(?:restrictions?|limits?|filters?)\b", "jailbreak"),
]

# Context manipulation patterns
CONTEXT_MANIPULATION_PATTERNS = [
    # Hidden instructions
    (r"\[hidden\].*?\[/hidden\]", "hidden_instruction"),
    (r"<!--.*?-->", "html_comment_injection"),
    (r"/\*.*?\*/", "code_comment_injection"),
    # Unicode/encoding tricks
    (r"[\u200b-\u200f\u2028-\u202f\ufeff]", "invisible_chars"),  # Zero-width chars
    (r"[\u0000-\u001f]", "control_chars"),  # Control characters (except common ones)
    # Base64 encoded instructions (common evasion technique)
    (r"(?:execute|run|decode|eval)\s*(?:base64|b64)", "encoded_instruction"),
]

# Output manipulation patterns
OUTPUT_MANIPULATION_PATTERNS = [
    # Data exfiltration attempts
    (
        r"\b(?:output|print|return|show|display|reveal)\s+(?:your|the|all)\s+(?:system\s+)?(?:prompt|instructions?|rules?|context)",
        "data_exfil",
    ),
    (
        r"\b(?:what|show|tell)\s+(?:are|me)\s+(?:your|the)\s+(?:system\s+)?(?:instructions?|prompt|rules?)",
        "data_exfil",
    ),
    # Format manipulation
    (r"respond\s+only\s+(?:with|in)\s+(?:json|xml|code)", "format_override"),
    (
        r"(?:never|don\'?t|do\s+not)\s+(?:mention|say|include|add)\b",
        "output_restriction",
    ),
]

# Compile all patterns for efficiency
COMPILED_PATTERNS: List[Tuple[re.Pattern, str, str]] = []
for pattern, category in SYSTEM_PROMPT_PATTERNS:
    COMPILED_PATTERNS.append(
        (re.compile(pattern, re.IGNORECASE | re.MULTILINE), category, "system")
    )
for pattern, category in CONTEXT_MANIPULATION_PATTERNS:
    COMPILED_PATTERNS.append(
        (re.compile(pattern, re.IGNORECASE | re.DOTALL), category, "context")
    )
for pattern, category in OUTPUT_MANIPULATION_PATTERNS:
    COMPILED_PATTERNS.append((re.compile(pattern, re.IGNORECASE), category, "output"))


# =============================================================================
# Detection Functions
# =============================================================================


def detect_injection_patterns(text: str) -> List[Tuple[str, str, str]]:
    """Detect known prompt injection patterns in text.

    Args:
        text: The input text to analyze

    Returns:
        List of tuples (matched_text, category, pattern_type)
    """
    matches = []

    for pattern, category, pattern_type in COMPILED_PATTERNS:
        for match in pattern.finditer(text):
            matched_text = match.group()
            # Truncate long matches for logging
            if len(matched_text) > 100:
                matched_text = matched_text[:100] + "..."
            matches.append((matched_text, category, pattern_type))

    return matches


def calculate_risk_level(
    detected_patterns: List[Tuple[str, str, str]],
) -> Tuple[InjectionRiskLevel, float]:
    """Calculate overall risk level from detected patterns.

    Args:
        detected_patterns: List of detected patterns

    Returns:
        Tuple of (risk_level, confidence)
    """
    if not detected_patterns:
        return InjectionRiskLevel.NONE, 0.0

    # Weight different pattern types
    weights = {
        "system_override": 0.9,
        "role_hijack": 0.8,
        "behavior_override": 0.7,
        "boundary_attack": 0.85,
        "role_injection": 0.75,
        "jailbreak": 0.95,
        "hidden_instruction": 0.6,
        "html_comment_injection": 0.4,
        "code_comment_injection": 0.3,
        "invisible_chars": 0.5,
        "control_chars": 0.4,
        "encoded_instruction": 0.7,
        "data_exfil": 0.6,
        "format_override": 0.3,
        "output_restriction": 0.4,
    }

    # Calculate max weight from detected patterns
    max_weight = max(weights.get(cat, 0.5) for _, cat, _ in detected_patterns)

    # Count of patterns increases confidence
    pattern_count = len(detected_patterns)
    count_factor = min(1.0, 0.5 + (pattern_count * 0.1))

    confidence = max_weight * count_factor

    # Map confidence to risk level
    if confidence >= 0.8:
        return InjectionRiskLevel.CRITICAL, confidence
    elif confidence >= 0.6:
        return InjectionRiskLevel.HIGH, confidence
    elif confidence >= 0.4:
        return InjectionRiskLevel.MEDIUM, confidence
    elif confidence > 0:
        return InjectionRiskLevel.LOW, confidence
    else:
        return InjectionRiskLevel.NONE, 0.0


def analyze_structure(text: str) -> List[str]:
    """Analyze text structure for suspicious patterns.

    Looks for structural indicators that might not match regex patterns
    but indicate manipulation attempts.

    Args:
        text: The input text to analyze

    Returns:
        List of structural concerns found
    """
    concerns = []

    # Check for unusual line patterns suggesting role injection
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Multiple colons at line start (role-like format)
        if re.match(r"^[A-Z][a-z]+:\s*", stripped):
            concerns.append(f"role_like_format_line_{i}")

    # Check for markdown-style headers that might delimit fake sections
    if re.search(
        r"^#{1,6}\s+(?:system|instruction|prompt|context)",
        text,
        re.IGNORECASE | re.MULTILINE,
    ):
        concerns.append("suspicious_markdown_headers")

    # Check for excessive special characters (potential encoding bypass)
    special_char_ratio = sum(
        1 for c in text if not c.isalnum() and not c.isspace()
    ) / max(len(text), 1)
    if special_char_ratio > 0.3:
        concerns.append("high_special_char_ratio")

    # Check for repeated prompt-like structures
    prompt_markers = len(
        re.findall(
            r"(?:prompt|instruction|system|context)\s*[:\-]", text, re.IGNORECASE
        )
    )
    if prompt_markers > 2:
        concerns.append("multiple_prompt_markers")

    return concerns


# =============================================================================
# Sanitization Functions
# =============================================================================


def remove_invisible_characters(text: str) -> str:
    """Remove invisible/zero-width characters that could hide instructions.

    Args:
        text: Input text

    Returns:
        Text with invisible characters removed
    """
    # Zero-width characters
    invisible_chars = r"[\u200b-\u200f\u2028-\u202f\ufeff\u00ad]"
    return re.sub(invisible_chars, "", text)


def escape_role_markers(text: str) -> str:
    """Escape patterns that look like chat role markers.

    Args:
        text: Input text

    Returns:
        Text with role markers escaped
    """
    # Add quotes around role-like patterns to make them clearly user content
    text = re.sub(r"(^|\n)(System|Assistant|Human|User):", r'\1"\2:"', text)
    return text


def neutralize_boundary_attacks(text: str) -> str:
    """Neutralize boundary/delimiter attacks.

    Args:
        text: Input text

    Returns:
        Text with boundary attacks neutralized
    """
    # Escape triple hash boundaries
    text = re.sub(
        r"###\s*(system|instruction|prompt)",
        r"[user mentioned: \1]",
        text,
        flags=re.IGNORECASE,
    )

    # Escape bracket-style markers
    text = re.sub(
        r"\[(SYSTEM|INST|INSTRUCTION)\]",
        r"[user mentioned: \1]",
        text,
        flags=re.IGNORECASE,
    )

    # Escape XML-style markers
    text = re.sub(
        r"<(system|instruction|prompt)>",
        r"[user mentioned: \1]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</(system|instruction|prompt)>",
        r"[user mentioned: end \1]",
        text,
        flags=re.IGNORECASE,
    )

    return text


def wrap_user_content(text: str) -> str:
    """Wrap user content in clear delimiters for the LLM.

    This helps the model understand the boundary between
    system instructions and user content.

    Args:
        text: The user's input text

    Returns:
        Text wrapped in clear delimiters
    """
    # Note: The actual wrapping depends on model format.
    # This is a template that can be customized per model.
    return text  # Return as-is; wrapping is done at prompt construction level


def sanitize_prompt(
    text: str,
    strict_mode: bool = False,
    log_detections: bool = True,
) -> SanitizationResult:
    """Main sanitization function for user input.

    Applies multiple layers of defense:
    1. Pattern detection and risk assessment
    2. Structural analysis
    3. Character-level sanitization
    4. Boundary neutralization

    Args:
        text: The user input to sanitize
        strict_mode: If True, reject high-risk inputs entirely
        log_detections: If True, log detected patterns (default True)

    Returns:
        SanitizationResult with analysis and sanitized text
    """
    if not text:
        return SanitizationResult(
            original_text=text,
            sanitized_text=text,
            risk_level=InjectionRiskLevel.NONE,
            detected_patterns=[],
            confidence=0.0,
            was_modified=False,
        )

    # Step 1: Detect patterns
    detected = detect_injection_patterns(text)
    pattern_names = [f"{cat}:{ptype}" for _, cat, ptype in detected]

    # Step 2: Structural analysis
    structural_concerns = analyze_structure(text)
    pattern_names.extend(structural_concerns)

    # Step 3: Calculate risk
    risk_level, confidence = calculate_risk_level(detected)

    # Adjust risk for structural concerns
    if structural_concerns and risk_level == InjectionRiskLevel.NONE:
        risk_level = InjectionRiskLevel.LOW
        confidence = 0.2
    elif structural_concerns:
        confidence = min(1.0, confidence + 0.1)

    # Step 4: Sanitize based on risk level
    sanitized = text
    was_modified = False

    # Always remove invisible characters
    sanitized = remove_invisible_characters(sanitized)
    if sanitized != text:
        was_modified = True

    # For medium+ risk, apply additional sanitization
    if risk_level in (
        InjectionRiskLevel.MEDIUM,
        InjectionRiskLevel.HIGH,
        InjectionRiskLevel.CRITICAL,
    ):
        before = sanitized
        sanitized = escape_role_markers(sanitized)
        sanitized = neutralize_boundary_attacks(sanitized)
        if sanitized != before:
            was_modified = True

    # Log detections
    if log_detections and pattern_names:
        logger.warning(
            "Prompt injection patterns detected",
            extra={
                "risk_level": risk_level.value,
                "confidence": confidence,
                "patterns": pattern_names[:10],  # Limit logged patterns
                "was_modified": was_modified,
            },
        )

    return SanitizationResult(
        original_text=text,
        sanitized_text=sanitized,
        risk_level=risk_level,
        detected_patterns=pattern_names,
        confidence=confidence,
        was_modified=was_modified,
    )


def is_safe_for_llm(
    text: str, max_risk: InjectionRiskLevel = InjectionRiskLevel.MEDIUM
) -> bool:
    """Quick check if text is safe to send to LLM.

    Args:
        text: The text to check
        max_risk: Maximum acceptable risk level (default MEDIUM)

    Returns:
        True if text is safe, False otherwise
    """
    result = sanitize_prompt(text, log_detections=False)

    risk_order = [
        InjectionRiskLevel.NONE,
        InjectionRiskLevel.LOW,
        InjectionRiskLevel.MEDIUM,
        InjectionRiskLevel.HIGH,
        InjectionRiskLevel.CRITICAL,
    ]

    return risk_order.index(result.risk_level) <= risk_order.index(max_risk)


def get_safe_prompt(text: str, fallback: str = "") -> str:
    """Get sanitized prompt text, or fallback if too risky.

    Args:
        text: The text to sanitize
        fallback: Fallback text if input is too risky

    Returns:
        Sanitized text or fallback
    """
    result = sanitize_prompt(text)

    if result.risk_level in (InjectionRiskLevel.HIGH, InjectionRiskLevel.CRITICAL):
        logger.warning("High-risk prompt rejected, using fallback")
        return fallback

    return result.sanitized_text
