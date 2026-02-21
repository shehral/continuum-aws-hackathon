"""Decision and entity extraction with embedding-based knowledge graph.

KG-P0-2: LLM response caching to avoid redundant API calls
KG-P0-3: Relationship type validation before storing
KG-QW-4: Extraction reasoning logging for debugging and quality analysis
ML-P2-2: Specialized prompt templates for different decision types
ML-P2-3: Post-processing confidence calibration based on extraction quality
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

import redis.asyncio as redis
from neo4j.exceptions import ClientError, DatabaseError

from config import get_settings
from db.neo4j import get_neo4j_session
from models.ontology import (
    ENTITY_ONLY_RELATIONSHIPS,
    get_canonical_name,
    validate_entity_relationship,
)
from models.provenance import (
    Provenance,
    SourceType,
    create_llm_provenance,
)
from models.schemas import DecisionCreate, Entity, TextSpan
from services.embeddings import get_embedding_service
from services.entity_resolver import EntityResolver
from services.llm import get_llm_client
from services.parser import Conversation
from utils.json_extraction import extract_json_from_response
from utils.logging import get_logger
from utils.vectors import cosine_similarity

# Lazy imports for services that may not be available in all environments
_dormant_detector_cls = None
_git_service_fn = None
_datadog_integration_fn = None


def _get_dormant_detector_cls():
    global _dormant_detector_cls
    if _dormant_detector_cls is None:
        try:
            from services.dormant_detector import DormantAlternativeDetector
            _dormant_detector_cls = DormantAlternativeDetector
        except ImportError:
            pass
    return _dormant_detector_cls


def _get_git_service():
    global _git_service_fn
    if _git_service_fn is None:
        try:
            from services.git_service import (
                get_git_service,
                create_code_entity_node,
                create_affects_edge,
            )
            _git_service_fn = (get_git_service, create_code_entity_node, create_affects_edge)
        except ImportError:
            pass
    return _git_service_fn


def _get_datadog_integration():
    global _datadog_integration_fn
    if _datadog_integration_fn is None:
        try:
            from services.datadog_integration import get_datadog_integration
            _datadog_integration_fn = get_datadog_integration
        except ImportError:
            pass
    return _datadog_integration_fn

logger = get_logger(__name__)

# Default values for missing decision fields (ML-QW-3)
DEFAULT_DECISION_FIELDS = {
    "confidence": 0.5,
    "context": "",
    "rationale": "",
    "options": [],
    "trigger": "Unknown trigger",
    "decision": "",
}


def apply_decision_defaults(decision_data: dict) -> dict:
    """Apply default values for missing or None decision fields (ML-QW-3).

    This ensures that incomplete decision data from LLM extraction
    or cached responses doesn't cause errors during processing.

    Args:
        decision_data: Raw decision dict from LLM or cache

    Returns:
        Decision dict with defaults applied for missing fields
    """
    result = {}
    for key, default_value in DEFAULT_DECISION_FIELDS.items():
        value = decision_data.get(key)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            result[key] = default_value
        elif isinstance(default_value, list) and not isinstance(value, list):
            # Handle case where options might be a string or other type
            result[key] = default_value
        else:
            result[key] = value
    # Preserve any extra fields not in defaults
    for key, value in decision_data.items():
        if key not in result:
            result[key] = value
    return result


# Exact trigger strings from the DECISION_EXTRACTION_PROMPT few-shot examples.
# If the LLM returns one of these triggers on a real conversation it has hallucinated
# an example rather than extracted a real decision — reject immediately.
KNOWN_EXAMPLE_TRIGGERS: frozenset[str] = frozenset({
    "need to select a database for the project",
    "need to choose frontend framework",
    "need to choose a styling approach",
    "need for better type safety in component",
})


def _is_valid_decision(d: dict) -> tuple[bool, str]:
    """Strict validation gate for extracted decisions before storage.

    Rejects garbage/empty decisions that pass the loose 'no decision field' check.
    Returns (is_valid, rejection_reason) so callers can log the reason.

    Criteria (all must pass):
    - trigger must not match a known few-shot example (hallucination guard)
    - decision field must be >= 10 chars (not empty or trivially short)
    - trigger must not be the default placeholder "Unknown trigger"
    - trigger must be non-empty after stripping
    - confidence must be >= 0.3 (minimum meaningful signal)
    - decision field must be non-empty after stripping
    """
    decision_text = d.get("decision", "").strip()
    trigger_text = d.get("trigger", "").strip()
    confidence = d.get("confidence", 0.0)

    # Hallucination guard — reject if trigger is verbatim from few-shot examples
    if trigger_text.lower() in KNOWN_EXAMPLE_TRIGGERS:
        return False, f"trigger matches known few-shot example (hallucination): '{trigger_text}'"

    if not decision_text:
        return False, "empty decision field"
    if len(decision_text) < 10:
        return False, f"decision too short ({len(decision_text)} chars): '{decision_text}'"
    if not trigger_text:
        return False, "empty trigger field"
    if trigger_text == "Unknown trigger":
        return False, "trigger is placeholder 'Unknown trigger'"
    if confidence < 0.3:
        return False, f"confidence too low ({confidence:.2f} < 0.3)"

    return True, ""


def _completeness_score(d: dict) -> float:
    """Compute completeness score for a decision dict (Part 14 — LightRAG gleaning).

    Returns fraction of the 5 core fields that have >= 20 characters of content.
    Used to decide whether a gleaning pass is warranted (threshold: < 0.6).
    """
    core_fields = ["trigger", "context", "options", "decision", "rationale"]
    filled = 0
    for field in core_fields:
        val = d.get(field, "")
        if isinstance(val, list):
            filled += 1 if any(len(str(v)) >= 5 for v in val) else 0
        elif isinstance(val, str) and len(val.strip()) >= 20:
            filled += 1
    return filled / len(core_fields)


# Few-shot decision extraction prompt with Chain-of-Thought reasoning
DECISION_EXTRACTION_PROMPT = """Analyze this conversation and extract any technical decisions made.

## What constitutes a decision?
A decision is a choice that affects the project direction, architecture, or implementation. This includes:
- **Explicit decisions**: "Should we use X or Y? Let's use X because..."
- **Implicit decisions**: "Let's use X for this" (even without stated alternatives)
- **Technical choices**: Framework selections, architecture patterns, tool adoptions
- **Implementation strategies**: How to solve a problem, approach to take

Each decision should have:
- A trigger (problem, requirement, or question that prompted it)
- Context (background information, constraints)
- Options (alternatives considered - can be just one if no alternatives mentioned)
- The actual decision (what was chosen)
- Rationale (why this choice was made)

## Examples

### Example 1: Single clear decision
Conversation:
"We need to pick a database. I looked at PostgreSQL and MongoDB. PostgreSQL seems better for our relational data needs and the team already knows SQL. Let's go with PostgreSQL."

Output:
```json
[
  {{
    "trigger": "Need to select a database for the project",
    "context": "Team has SQL experience, data is relational in nature",
    "options": ["PostgreSQL", "MongoDB"],
    "decision": "Use PostgreSQL as the primary database",
    "rationale": "Better fit for relational data and team already has SQL expertise",
    "confidence": 0.95,
    "scope": "architectural",
    "assumptions": ["team has existing SQL expertise", "data model is relational", "no need for horizontal write scaling initially"]
  }}
]
```

### Example 2: Multiple decisions in one conversation
Conversation:
"For the frontend, React makes sense since we're already using it elsewhere. For styling, I considered Tailwind vs CSS modules. Tailwind will speed up development, so let's use that."

Output:
```json
[
  {{
    "trigger": "Need to choose frontend framework",
    "context": "Team already using React in other projects",
    "options": ["React"],
    "decision": "Use React for the frontend",
    "rationale": "Consistency with existing projects and team familiarity",
    "confidence": 0.9,
    "scope": "library",
    "assumptions": ["team is already familiar with React", "React is used in other projects in the org"]
  }},
  {{
    "trigger": "Need to choose a styling approach",
    "context": "Building frontend with React",
    "options": ["Tailwind CSS", "CSS modules"],
    "decision": "Use Tailwind CSS for styling",
    "rationale": "Faster development velocity with utility classes",
    "confidence": 0.85,
    "scope": "library",
    "assumptions": []
  }}
]
```

### Example 3: Implicit decision (no alternatives stated)
Conversation:
"Let's add TypeScript to this component for better type safety. I'll update the imports and add interfaces."

Output:
```json
[
  {{
    "trigger": "Need for better type safety in component",
    "context": "Existing component lacks type checking",
    "options": ["TypeScript"],
    "decision": "Add TypeScript to the component",
    "rationale": "Improves type safety and code quality",
    "confidence": 0.85,
    "scope": "config",
    "assumptions": []
  }}
]
```

### Example 4: No decisions (just discussion)
Conversation:
"What do you think about microservices? I've heard they can be complex but offer good scalability. We should probably discuss this more with the team before deciding anything."

Output:
```json
[]
```

### Example 5: Document reading / research (no decisions made)
Conversation:
"I will start with giving you some context for you to read. Review and understand these papers about distributed systems and explain what you understood."

Output:
```json
[]
```

## Instructions
For each decision found, provide:
- trigger: What prompted the decision (be specific)
- context: Relevant background (constraints, requirements, team situation)
- options: Alternatives considered (can be just [chosen_option] if no alternatives mentioned)
- decision: What was decided (clear statement)
- rationale: Why this choice (extract reasoning from context, or "Not explicitly stated" if unclear)
- confidence: 0.0-1.0 (how clear/complete the decision is)
- verbatim_trigger: EXACT verbatim quote from conversation for trigger (preserve exact wording, including qualifiers like "everywhere")
- verbatim_decision: EXACT verbatim quote from conversation for decision
- verbatim_rationale: EXACT verbatim quote from conversation for rationale (if available)
- turn_index: Which conversation turn (0-indexed) this decision came from
- scope: One of: "strategic" (whole-system architecture, years half-life), "architectural" (framework/DB choice, months), "library" (package selection, weeks), "config" (tunable parameters, days), "operational" (deployment/env settings, hours)
- assumptions: List of explicit assumptions this decision relies on (e.g. ["single-tenant", "< 100 req/s", "team of 2"])

**Important**:
- Extract both explicit decisions (X vs Y) and implicit ones ("Let's use X")
- Implementation choices count as decisions (e.g., "I'll refactor this using pattern X")
- If only one option is mentioned, that's still a decision
- If no clear decisions are found, return an empty array []
- **VERBATIM PRESERVATION**: Always include exact quotes - preserve qualifiers like "everywhere", "always", "never" exactly as written
- **TURN TRACKING**: Count turns starting from 0 (first user message = turn 0, first assistant response = turn 1, etc.)
- **SCOPE**: Classify each decision's hierarchical scope (strategic > architectural > library > config > operational)
- **ASSUMPTIONS**: Extract explicit assumptions stated or implied by the decision context

## Conversation to analyze:
{conversation_text}

Return ONLY valid JSON, no markdown code blocks or explanation."""


# ML-P2-2: Decision Type Enumeration
class DecisionType:
    """Enumeration of decision types for specialized extraction (ML-P2-2)."""

    ARCHITECTURE = "architecture"
    TECHNOLOGY = "technology"
    PROCESS = "process"
    GENERAL = "general"


# ML-P2-2: Specialized prompt for architecture decisions
ARCHITECTURE_DECISION_PROMPT = """Analyze this conversation for ARCHITECTURE DECISIONS.

Focus on: system structure, scalability, communication patterns, tradeoffs.

## Example
Conversation: "We decided to start with a modular monolith given our small team."
Output:
```json
[{{"trigger": "Deciding on system architecture", "context": "Small team", "options": ["Microservices", "Monolith"], "decision": "Modular monolith", "rationale": "Reduced complexity for small team", "confidence": 0.9, "decision_type": "architecture"}}]
```

## Conversation to analyze:
{conversation_text}

Return ONLY valid JSON, no markdown code blocks or explanation."""


# ML-P2-2: Specialized prompt for technology choice decisions
TECHNOLOGY_DECISION_PROMPT = """Analyze this conversation for TECHNOLOGY CHOICE DECISIONS.

Focus on: tools, frameworks, alternatives considered, compatibility, team skills.

## Example
Conversation: "We chose PostgreSQL over MongoDB for ACID compliance."
Output:
```json
[{{"trigger": "Selecting database", "context": "Need ACID compliance", "options": ["PostgreSQL", "MongoDB"], "decision": "PostgreSQL", "rationale": "Better transactional support", "confidence": 0.95, "decision_type": "technology"}}]
```

## Conversation to analyze:
{conversation_text}

Return ONLY valid JSON, no markdown code blocks or explanation."""


# ML-P2-2: Specialized prompt for process decisions
PROCESS_DECISION_PROMPT = """Analyze this conversation for PROCESS and WORKFLOW DECISIONS.

Focus on: team workflows, deployment practices, quality assurance, collaboration.

## Example
Conversation: "We are implementing mandatory code reviews with CODEOWNERS."
Output:
```json
[{{"trigger": "Establishing code review practices", "context": "Need quality improvement", "options": ["Optional reviews", "Mandatory reviews"], "decision": "Mandatory reviews with CODEOWNERS", "rationale": "Ensures expert review", "confidence": 0.85, "decision_type": "process"}}]
```

## Conversation to analyze:
{conversation_text}

Return ONLY valid JSON, no markdown code blocks or explanation."""


# ML-P2-2: Map decision types to prompts
DECISION_TYPE_PROMPTS = {
    DecisionType.ARCHITECTURE: ARCHITECTURE_DECISION_PROMPT,
    DecisionType.TECHNOLOGY: TECHNOLOGY_DECISION_PROMPT,
    DecisionType.PROCESS: PROCESS_DECISION_PROMPT,
    DecisionType.GENERAL: None,  # Use default DECISION_EXTRACTION_PROMPT
}


# ML-P2-2: Keywords for auto-detecting decision type
DECISION_TYPE_KEYWORDS = {
    DecisionType.ARCHITECTURE: [
        "architecture",
        "microservice",
        "monolith",
        "distributed",
        "scalability",
        "api gateway",
        "event-driven",
        "message queue",
        "load balancer",
    ],
    DecisionType.TECHNOLOGY: [
        "framework",
        "library",
        "database",
        "postgres",
        "mongodb",
        "redis",
        "react",
        "vue",
        "python",
        "typescript",
        "aws",
        "docker",
    ],
    DecisionType.PROCESS: [
        "workflow",
        "process",
        "ci/cd",
        "deployment",
        "code review",
        "branching",
        "agile",
        "sprint",
        "release",
    ],
}


def detect_decision_type(text: str) -> str:
    """Auto-detect the decision type based on keywords in the text (ML-P2-2).
    
    DEPRECATED: Use detect_decision_type_llm() for better accuracy.
    Kept for backward compatibility and fallback.

    Args:
        text: The conversation or decision text to analyze

    Returns:
        The detected decision type string
    """
    text_lower = text.lower()
    scores = {dtype: 0 for dtype in DECISION_TYPE_KEYWORDS}

    for dtype, keywords in DECISION_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                scores[dtype] += 1

    max_score = max(scores.values())
    if max_score >= 2:  # Require at least 2 keyword matches
        for dtype, score in scores.items():
            if score == max_score:
                return dtype

    return DecisionType.GENERAL


# LLM-based decision type detection prompt
DECISION_TYPE_DETECTION_PROMPT = """Analyze this conversation and classify the PRIMARY type of decision being made.

Decision types:
- architecture: System structure, scalability, communication patterns, architectural tradeoffs
- technology: Tool/framework/library selection, technology choices, compatibility decisions
- process: Team workflows, deployment practices, quality assurance, collaboration processes
- general: Other types of decisions or unclear/mixed types

## Examples

Conversation: "We decided to use microservices architecture for better scalability."
Classification: architecture

Conversation: "Choosing PostgreSQL over MongoDB for ACID compliance."
Classification: technology

Conversation: "Implementing mandatory code reviews with CODEOWNERS."
Classification: process

Conversation: "We need to refactor this component for better maintainability."
Classification: general

## Conversation to analyze:
{conversation_text}

Return ONLY the decision type (one word: architecture, technology, process, or general), no explanation."""


async def detect_decision_type_llm(
    text: str, 
    llm_client=None,
    cache: "LLMResponseCache | None" = None,
    bypass_cache: bool = False,
) -> str:
    """Detect decision type using LLM for better accuracy (RQ1.1 enhancement).

    Args:
        text: The conversation or decision text to analyze
        llm_client: LLM client instance (if None, will get from get_llm_client())
        cache: LLM response cache instance (if None, will create new)
        bypass_cache: If True, skip cache lookup

    Returns:
        The detected decision type string (architecture, technology, process, or general)
    """
    from services.llm import get_llm_client
    
    if llm_client is None:
        llm_client = get_llm_client()
    
    if cache is None:
        cache = LLMResponseCache()
    
    # Truncate text if too long (keep first 2000 chars for type detection)
    truncated_text = text[:2000] if len(text) > 2000 else text
    
    # Check cache
    cache_key = f"decision_type:{truncated_text}"
    if not bypass_cache:
        cached = await cache.get(cache_key, "decision_type")
        if cached is not None:
            logger.debug(f"Using cached decision type: {cached}")
            return cached
    
    # Use LLM to detect type
    prompt = DECISION_TYPE_DETECTION_PROMPT.format(conversation_text=truncated_text)
    
    try:
        response = await llm_client.generate(
            prompt=prompt,
            temperature=0.3,
            max_tokens=200,  # Increased to handle potential thinking tags
            sanitize_input=False,  # Prompt is system-generated, safe
        )
        
        # Log raw response for debugging (before any processing)
        from utils.json_extraction import _log_raw_response
        _log_raw_response(response, "decision_type_detection")
        
        # Extract type from response (should be single word)
        # Response should already have thinking tags stripped by LLM client
        detected_type = response.strip().lower()
        
        # Additional cleanup: remove any remaining thinking tag artifacts
        detected_type = re.sub(r"^<[^>]*>", "", detected_type)
        detected_type = re.sub(r"<[^>]*>$", "", detected_type)
        detected_type = detected_type.strip()
        
        # Validate and normalize
        valid_types = {
            DecisionType.ARCHITECTURE,
            DecisionType.TECHNOLOGY,
            DecisionType.PROCESS,
            DecisionType.GENERAL,
        }
        
        if detected_type in valid_types:
            result = detected_type
        else:
            # Fallback to keyword-based if LLM returns invalid type
            logger.warning(f"LLM returned invalid decision type: {detected_type}, falling back to keyword detection")
            result = detect_decision_type(text)
        
        # Cache result
        await cache.set(cache_key, "decision_type", result)
        
        return result
        
    except Exception as e:
        logger.error(f"Error in LLM-based decision type detection: {e}, falling back to keyword detection")
        return detect_decision_type(text)


def calibrate_confidence(decision_data: dict) -> float:
    """Calibrate confidence score based on extraction completeness (ML-P2-3).
    
    DEPRECATED: Use calibrate_confidence_temperature() for modern calibration.
    Kept for backward compatibility and fallback.

    Adjusts the raw LLM confidence based on:
    - Completeness of extracted fields
    - Number of options/entities mentioned
    - Quality indicators in rationale

    Args:
        decision_data: The extracted decision dictionary

    Returns:
        Calibrated confidence score (0.0 to 1.0)
    """
    raw_confidence = decision_data.get("confidence", 0.5)
    calibrated = raw_confidence

    # Penalty for missing required fields
    required_fields = ["trigger", "decision", "rationale"]
    missing_required = sum(1 for f in required_fields if not decision_data.get(f))
    calibrated -= missing_required * 0.15

    # Bonus for having options (indicates careful consideration)
    options = decision_data.get("options", [])
    if len(options) >= 2:
        calibrated += 0.05
    if len(options) >= 3:
        calibrated += 0.03

    # Bonus for detailed rationale
    rationale = decision_data.get("rationale", "")
    rationale_words = len(rationale.split()) if rationale else 0
    if rationale_words >= 20:
        calibrated += 0.05
    elif rationale_words >= 10:
        calibrated += 0.02
    elif rationale_words < 5:
        calibrated -= 0.10

    # Bonus for having context
    context = decision_data.get("context", "")
    if context and len(context.split()) >= 5:
        calibrated += 0.03

    # Quality phrases bonus
    quality_phrases = [
        "because",
        "since",
        "due to",
        "trade-off",
        "benefit",
        "compared to",
    ]
    rationale_lower = rationale.lower()
    quality_matches = sum(1 for p in quality_phrases if p in rationale_lower)
    calibrated += min(quality_matches * 0.02, 0.08)

    return round(max(0.1, min(1.0, calibrated)), 3)


def calibrate_confidence_temperature(decision_data: dict, temperature: float = 1.5) -> float:
    """Calibrate confidence using Temperature Scaling (RQ1.2 enhancement).
    
    Temperature Scaling is a modern calibration technique that scales the confidence
    score using a temperature parameter T: calibrated = raw_confidence^(1/T)
    
    This method:
    - Requires no training data (unlike learned classifiers)
    - Is simple and interpretable
    - Works well for structured extraction tasks
    - Can be tuned on validation set if available
    
    Args:
        decision_data: The extracted decision dictionary
        temperature: Temperature parameter (default 1.5, higher = more conservative)
                    T=1.0 = no calibration, T>1.0 = lower confidence, T<1.0 = higher confidence
    
    Returns:
        Calibrated confidence score (0.0 to 1.0)
    """
    from config import get_settings
    
    settings = get_settings()
    temp = temperature if temperature != 1.5 else settings.confidence_calibration_temperature
    
    raw_confidence = decision_data.get("confidence", 0.5)
    
    # Temperature scaling: calibrated = raw^(1/T)
    # For T > 1, this reduces confidence (makes it more conservative)
    # For T < 1, this increases confidence (makes it more optimistic)
    if raw_confidence <= 0:
        return 0.0
    if raw_confidence >= 1.0:
        return 1.0
    
    calibrated = raw_confidence ** (1.0 / temp)
    
    # Apply completeness adjustment (light heuristic to account for missing fields)
    # This is optional - pure temperature scaling would skip this
    required_fields = ["trigger", "decision", "rationale"]
    missing_required = sum(1 for f in required_fields if not decision_data.get(f))
    if missing_required > 0:
        # Light penalty for missing fields (smaller than heuristic method)
        calibrated *= (1.0 - missing_required * 0.05)
    
    return round(max(0.0, min(1.0, calibrated)), 3)


def calibrate_confidence_composite(
    decision_data: dict,
    rationale_author: str | None = None,
    conversation_text: str = "",
) -> float:
    """Data-driven composite confidence calibration (Part 2e).

    Replaces temperature-scaling magic constant with observable signals:

        calibrated = raw * 0.4
                   + completeness_score * 0.3
                   + evidence_score * 0.2
                   + source_score * 0.1

    - ``completeness_score``: fraction of 5 fields with > 20 chars
    - ``evidence_score``: 1.0 if verbatim_quote found in source, 0.5 partial, 0.2 none
    - ``source_score``: 1.0 if rationale_author=='thinking', 0.85 'user', 0.6 'assistant'

    No ground-truth dataset required — all signals are computable from the
    extraction output alone.
    """
    raw_confidence = float(decision_data.get("confidence", 0.5))

    # 1. Completeness score — fraction of key fields with substantive content
    key_fields = ["trigger", "context", "options", "decision", "rationale"]
    filled = 0
    for field in key_fields:
        val = decision_data.get(field, "")
        if isinstance(val, list):
            if any(len(str(v)) > 5 for v in val):
                filled += 1
        elif isinstance(val, str) and len(val.strip()) > 20:
            filled += 1
    completeness_score = filled / len(key_fields)

    # 2. Evidence score — verbatim quote grounding in source text
    verbatim = (
        decision_data.get("verbatim_decision", "")
        or decision_data.get("verbatim_trigger", "")
        or ""
    )
    if verbatim and conversation_text:
        if verbatim.strip().lower() in conversation_text.lower():
            evidence_score = 1.0
        else:
            # Partial: check if at least 60% of words appear
            words = verbatim.split()
            if words:
                hits = sum(1 for w in words if w.lower() in conversation_text.lower())
                evidence_score = 0.5 if hits / len(words) >= 0.6 else 0.2
            else:
                evidence_score = 0.2
    else:
        # No verbatim quote provided — moderate penalty
        evidence_score = 0.35

    # 3. Source score — rationale provenance fidelity
    source_scores = {
        "thinking": 1.0,
        "user": 0.85,
        "assistant": 0.6,
        None: 0.6,
    }
    source_score = source_scores.get(rationale_author, 0.6)

    calibrated = (
        raw_confidence * 0.4
        + completeness_score * 0.3
        + evidence_score * 0.2
        + source_score * 0.1
    )

    return round(max(0.0, min(1.0, calibrated)), 3)


# ---------------------------------------------------------------------------
# Episode segmentation (Part 2b)
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass, field as _field


@_dataclass
class Episode:
    """A contiguous cluster of messages representing one decision arc.

    Arc labels:
    - setup         : problem statement / task definition
    - exploration   : reading files, running commands, gathering info
    - pivot         : change of approach after discovering a dead end
    - implementation: writing / editing code
    - verification  : running tests, inspecting output, confirming result
    """
    messages: list  # list[Message] from parser
    turn_start: int = 0
    arc_label: str = "unknown"

    @property
    def text_content(self) -> str:
        """Flat text representation (legacy format) for LLM prompts."""
        parts = []
        for msg in self.messages:
            role = getattr(msg, "role", "unknown")
            content = getattr(msg, "content", "")
            parts.append(f"{role}: {content}")
        return "\n\n".join(parts)

    @property
    def thinking_text(self) -> str:
        """Concatenated thinking blocks from all messages in this episode."""
        thinking_parts = [
            msg.thinking
            for msg in self.messages
            if getattr(msg, "thinking", None)
        ]
        return "\n\n".join(thinking_parts) if thinking_parts else ""

    @property
    def tool_file_paths(self) -> list[str]:
        """All file paths referenced by tool calls in this episode.

        Ground-truth file references (confidence 1.0) — used to create
        AFFECTS edges to CodeEntity nodes without fuzzy matching.
        """
        paths: list[str] = []
        for msg in self.messages:
            for tc in getattr(msg, "tool_calls", []):
                paths.extend(tc.file_paths)
        return list(set(paths))  # deduplicate


_EXPLORATION_TOOLS = {"Read", "Glob", "Grep", "Bash", "WebFetch", "WebSearch"}
_WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
_BOUNDARY_PHRASES = {
    "done", "looks good", "perfect", "let's move on", "next step",
    "lgtm", "approved", "thank you", "thanks", "great", "ship it",
}


def _is_episode_boundary(
    msg,
    next_msg,
    cluster_tool_names: list[str],
    episode_gap_minutes: float = 10.0,
) -> bool:
    """Heuristic to detect a natural episode boundary.

    Boundary signals:
    1. Write/Edit tool follows ≥2 Read/Bash calls → implementation after exploration
    2. Timestamp gap > episode_gap_minutes between this and next message
    3. User message after ≥3 assistant tool calls (natural conversational break)
    4. User message contains a "done / let's move on" phrase
    """
    # Signal 1: write tool after exploration cluster
    read_count = sum(1 for t in cluster_tool_names if t in _EXPLORATION_TOOLS)
    has_write = any(t in _WRITE_TOOLS for t in cluster_tool_names)
    if has_write and read_count >= 2:
        return True

    # Signal 2: timestamp gap
    if next_msg is not None:
        ts_self = getattr(msg, "timestamp", None)
        ts_next = getattr(next_msg, "timestamp", None)
        if ts_self and ts_next:
            try:
                from datetime import datetime
                fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
                def _parse(ts: str):
                    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                        try:
                            return datetime.strptime(ts, fmt)
                        except ValueError:
                            pass
                    return None
                t1, t2 = _parse(ts_self), _parse(ts_next)
                if t1 and t2:
                    gap_minutes = (t2 - t1).total_seconds() / 60
                    if gap_minutes > episode_gap_minutes:
                        return True
            except Exception:
                pass

    # Signal 3: user message after ≥3 assistant tool calls
    if getattr(msg, "role", "") == "user" and len(cluster_tool_names) >= 3:
        return True

    # Signal 4: boundary phrases in user message
    if getattr(msg, "role", "") == "user":
        content_lower = getattr(msg, "content", "").lower()
        if any(phrase in content_lower for phrase in _BOUNDARY_PHRASES):
            return True

    return False


def _classify_arc(messages: list) -> str:
    """Classify an episode's arc label from its tool call patterns."""
    tool_names: list[str] = []
    for msg in messages:
        for tc in getattr(msg, "tool_calls", []):
            tool_names.append(tc.name)

    has_write = any(t in _WRITE_TOOLS for t in tool_names)
    has_explore = any(t in _EXPLORATION_TOOLS for t in tool_names)

    # Heuristic classification
    if not tool_names:
        # Pure text exchange — likely setup or verification
        return "setup" if len(messages) <= 2 else "verification"
    if has_write and not has_explore:
        return "implementation"
    if has_write and has_explore:
        return "pivot"
    if has_explore and not has_write:
        return "exploration"
    return "unknown"


def segment_into_episodes(raw_messages: list, episode_gap_minutes: float = 10.0) -> list[Episode]:
    """Split a conversation's structured messages into decision episodes.

    Each episode is a contiguous cluster of messages focused on one
    decision arc (setup → explore → implement → verify).

    Extracting decisions per-episode rather than per-conversation:
    - Keeps context window small (better LLM accuracy)
    - Avoids mixing decisions from different arcs
    - Allows per-episode arc_label metadata on Decision nodes
    """
    if not raw_messages:
        return []

    episodes: list[Episode] = []
    current: list = []
    cluster_tools: list[str] = []
    turn_start = 0

    for i, msg in enumerate(raw_messages):
        current.append(msg)
        # Accumulate tool names from this message
        for tc in getattr(msg, "tool_calls", []):
            cluster_tools.append(tc.name)

        next_msg = raw_messages[i + 1] if i + 1 < len(raw_messages) else None

        if _is_episode_boundary(msg, next_msg, cluster_tools, episode_gap_minutes):
            if len(current) >= 2:
                ep = Episode(
                    messages=current[:],
                    turn_start=turn_start,
                    arc_label=_classify_arc(current),
                )
                episodes.append(ep)
            turn_start = i + 1
            current = []
            cluster_tools = []

    # Flush remaining
    if current:
        episodes.append(Episode(
            messages=current,
            turn_start=turn_start,
            arc_label=_classify_arc(current),
        ))

    # If segmentation produced no episodes (single short exchange), return one
    if not episodes and raw_messages:
        episodes = [Episode(
            messages=raw_messages,
            turn_start=0,
            arc_label=_classify_arc(raw_messages),
        )]

    return episodes


# ---------------------------------------------------------------------------
# Rationale provenance detection (Part 2c)
# ---------------------------------------------------------------------------

def _detect_rationale_author(decision_dict: dict, messages: list) -> str:
    """Determine who/what provided the rationale for this decision.

    Priority:
    1. 'thinking'  — any message in the episode has a thinking block
    2. 'user'      — rationale text appears verbatim in a user-role message
    3. 'assistant' — default (rationale inferred from assistant response)
    """
    from models.schemas import RationaleAuthor

    # Check for thinking blocks in the episode
    for msg in messages:
        if getattr(msg, "thinking", None):
            return RationaleAuthor.THINKING

    # Check if rationale appears in user messages
    rationale = decision_dict.get("rationale", "").strip().lower()
    if rationale and len(rationale) > 10:
        for msg in messages:
            if getattr(msg, "role", "") == "user":
                content = getattr(msg, "content", "").lower()
                # Simple containment check — enough for provenance signal
                if rationale[:50] in content:
                    return RationaleAuthor.USER

    return RationaleAuthor.ASSISTANT


# Few-shot entity extraction prompt with Chain-of-Thought reasoning
ENTITY_EXTRACTION_PROMPT = """Extract technical entities from this decision text.

## Entity Types
- technology: Specific tools, languages, frameworks, databases (e.g., PostgreSQL, React, Python)
- concept: Abstract ideas, principles, methodologies (e.g., microservices, REST API, caching)
- pattern: Design and architectural patterns (e.g., singleton, repository pattern, CQRS)
- system: Software systems, services, components (e.g., authentication system, payment gateway)
- person: People mentioned (team members, stakeholders)
- organization: Companies, teams, departments

## Examples

Input: "We chose React over Vue for the frontend"
Output:
{{
  "entities": [
    {{"name": "React", "type": "technology", "confidence": 0.95}},
    {{"name": "Vue", "type": "technology", "confidence": 0.95}},
    {{"name": "frontend", "type": "concept", "confidence": 0.85}}
  ],
  "reasoning": "React and Vue are frontend frameworks (technology). Frontend is the general concept being discussed."
}}

Input: "JWT tokens stored in Redis for session management"
Output:
{{
  "entities": [
    {{"name": "JWT", "type": "technology", "confidence": 0.95}},
    {{"name": "Redis", "type": "technology", "confidence": 0.95}},
    {{"name": "session management", "type": "concept", "confidence": 0.85}}
  ],
  "reasoning": "JWT is an authentication token standard (technology). Redis is a database (technology). Session management is the concept being implemented."
}}

Input: "Implementing the repository pattern with SQLAlchemy for data access"
Output:
{{
  "entities": [
    {{"name": "repository pattern", "type": "pattern", "confidence": 0.95}},
    {{"name": "SQLAlchemy", "type": "technology", "confidence": 0.95}},
    {{"name": "data access", "type": "concept", "confidence": 0.8}}
  ],
  "reasoning": "Repository pattern is a design pattern. SQLAlchemy is an ORM technology. Data access is the concept being addressed."
}}

## Decision Text
{decision_text}

Extract entities with your reasoning. Return ONLY valid JSON:
{{
  "entities": [{{"name": "string", "type": "entity_type", "confidence": 0.0-1.0}}, ...],
  "reasoning": "Brief explanation of your categorization"
}}"""


# Few-shot entity relationship extraction prompt
ENTITY_RELATIONSHIP_PROMPT = """Identify relationships between these entities.

## Relationship Types
- IS_A: X is a type/category of Y (e.g., "PostgreSQL IS_A Database")
- PART_OF: X is a component of Y (e.g., "React Flow PART_OF React ecosystem")
- DEPENDS_ON: X requires/depends on Y (e.g., "Next.js DEPENDS_ON React")
- RELATED_TO: X is generally related to Y (e.g., "FastAPI RELATED_TO Python")
- ALTERNATIVE_TO: X can be used instead of Y (e.g., "MongoDB ALTERNATIVE_TO PostgreSQL")

## Examples

Entities: ["React", "Vue", "frontend"]
Context: "We chose React over Vue for the frontend"
Output:
{{
  "relationships": [
    {{"from": "React", "to": "frontend", "type": "PART_OF", "confidence": 0.9}},
    {{"from": "Vue", "to": "frontend", "type": "PART_OF", "confidence": 0.9}},
    {{"from": "React", "to": "Vue", "type": "ALTERNATIVE_TO", "confidence": 0.95}}
  ],
  "reasoning": "React and Vue are both frontend frameworks (PART_OF frontend). They were considered as alternatives."
}}

Entities: ["PostgreSQL", "Redis", "caching", "database"]
Context: "Using PostgreSQL as the primary database with Redis for caching"
Output:
{{
  "relationships": [
    {{"from": "PostgreSQL", "to": "database", "type": "IS_A", "confidence": 0.95}},
    {{"from": "Redis", "to": "caching", "type": "PART_OF", "confidence": 0.9}},
    {{"from": "Redis", "to": "database", "type": "IS_A", "confidence": 0.85}}
  ],
  "reasoning": "PostgreSQL is a relational database. Redis is used for caching but is also a database (key-value store)."
}}

Entities: ["Next.js", "React", "TypeScript", "frontend"]
Context: "Building the frontend with Next.js and TypeScript"
Output:
{{
  "relationships": [
    {{"from": "Next.js", "to": "React", "type": "DEPENDS_ON", "confidence": 0.95}},
    {{"from": "Next.js", "to": "frontend", "type": "PART_OF", "confidence": 0.9}},
    {{"from": "TypeScript", "to": "frontend", "type": "PART_OF", "confidence": 0.85}}
  ],
  "reasoning": "Next.js is built on top of React (DEPENDS_ON). Both Next.js and TypeScript are part of the frontend stack."
}}

## Entities: {entities}
## Context: {context}

Identify relationships. Only include relationships you're confident about (>0.7 confidence).
Return ONLY valid JSON:
{{
  "relationships": [{{"from": "entity", "to": "entity", "type": "RELATIONSHIP_TYPE", "confidence": 0.0-1.0}}, ...],
  "reasoning": "Brief explanation"
}}"""


# Decision-to-decision relationship extraction prompt
DECISION_RELATIONSHIP_PROMPT = """Analyze if these two decisions have a significant relationship.

## Relationship Types
- SUPERSEDES: The newer decision explicitly replaces or changes the older decision
- CONTRADICTS: The decisions fundamentally conflict (choosing opposite approaches)

## Examples

Decision A (Jan 15): "Using PostgreSQL for the primary database"
Decision B (Mar 20): "Migrating to MongoDB for horizontal scaling needs"
Output:
{{
  "relationship": "SUPERSEDES",
  "confidence": 0.9,
  "reasoning": "Decision B explicitly changes the database choice from PostgreSQL to MongoDB, superseding Decision A."
}}

Decision A (Feb 1): "REST API for all client communication"
Decision B (Feb 15): "GraphQL for mobile app queries to reduce overfetching"
Output:
{{
  "relationship": null,
  "confidence": 0.0,
  "reasoning": "These decisions are complementary - GraphQL is added for mobile while REST remains for other clients."
}}

Decision A (Jan 10): "Monolithic architecture for faster initial development"
Decision B (Jun 1): "Breaking into microservices for better scaling"
Output:
{{
  "relationship": "SUPERSEDES",
  "confidence": 0.85,
  "reasoning": "Decision B transitions from the monolithic approach in Decision A to microservices."
}}

Decision A (Mar 1): "Using JWT for stateless authentication"
Decision B (Mar 5): "Using session cookies for authentication"
Output:
{{
  "relationship": "CONTRADICTS",
  "confidence": 0.9,
  "reasoning": "JWT (stateless) and session cookies (stateful) are conflicting authentication approaches."
}}

## Decision A ({decision_a_date}):
Trigger: {decision_a_trigger}
Decision: {decision_a_text}
Rationale: {decision_a_rationale}

## Decision B ({decision_b_date}):
Trigger: {decision_b_trigger}
Decision: {decision_b_text}
Rationale: {decision_b_rationale}

Analyze the relationship. Return ONLY valid JSON:
{{
  "relationship": "SUPERSEDES" | "CONTRADICTS" | null,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation"
}}"""


class LLMResponseCache:
    """Redis-based cache for LLM extraction responses (KG-P0-2).

    Caches LLM responses keyed by:
    - Hash of input text
    - Prompt template version
    - Extraction type (decision, entity, relationship)

    This avoids redundant API calls when reprocessing the same content.
    """

    def __init__(self):
        self._redis: redis.Redis | None = None
        self._settings = get_settings()

    async def _get_redis(self) -> redis.Redis | None:
        """Get or create Redis connection for caching."""
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    self._settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"LLM cache Redis connection failed: {e}")
                self._redis = None
        return self._redis

    def _get_cache_key(self, text: str, extraction_type: str) -> str:
        """Generate a cache key for the LLM response.

        Format: llm:{version}:{type}:{hash(text)}
        """
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        version = self._settings.llm_extraction_prompt_version
        return f"llm:{version}:{extraction_type}:{text_hash}"

    async def get(self, text: str, extraction_type: str) -> dict | list | str | None:
        """Get cached LLM response if available.
        
        Returns:
            Cached response (dict, list, or str) or None if not cached
        """
        if not self._settings.llm_cache_enabled:
            return None

        redis_client = await self._get_redis()
        if redis_client is None:
            return None

        try:
            cache_key = self._get_cache_key(text, extraction_type)
            cached = await redis_client.get(cache_key)
            if cached:
                logger.debug(f"LLM cache hit for {extraction_type}")
                # Try to parse as JSON first (for dict/list), fall back to string
                try:
                    return json.loads(cached)
                except json.JSONDecodeError:
                    # Return as string if not valid JSON
                    return cached
        except Exception as e:
            logger.warning(f"LLM cache read error: {e}")

        return None

    async def set(self, text: str, extraction_type: str, response: dict | list | str) -> None:
        """Cache an LLM response."""
        if not self._settings.llm_cache_enabled:
            return

        redis_client = await self._get_redis()
        if redis_client is None:
            return

        try:
            cache_key = self._get_cache_key(text, extraction_type)
            await redis_client.setex(
                cache_key,
                self._settings.llm_cache_ttl,
                json.dumps(response),
            )
            logger.debug(f"LLM cache set for {extraction_type}")
        except Exception as e:
            logger.warning(f"LLM cache write error: {e}")


class DecisionExtractor:
    """Extract decisions and entities from conversations using LLM.

    Enhanced with:
    - Few-shot Chain-of-Thought prompts for better extraction
    - Entity resolution to prevent duplicates
    - ALTERNATIVE_TO relationship detection
    - SUPERSEDES and CONTRADICTS relationship analysis
    - Embedding generation for semantic search
    - Multi-tenant user isolation via user_id
    - Robust JSON parsing for LLM responses
    - Configurable similarity threshold
    - LLM response caching (KG-P0-2)
    - Relationship type validation (KG-P0-3)
    """

    def __init__(self):
        self.llm = get_llm_client()
        self.embedding_service = get_embedding_service()
        self.cache = LLMResponseCache()
        settings = get_settings()
        self.similarity_threshold = settings.similarity_threshold
        self.high_confidence_threshold = settings.high_confidence_similarity_threshold
    
    def _find_text_span(
        self, 
        conversation: "Conversation",
        verbatim_text: str, 
        turn_index: int | None = None
    ) -> "TextSpan | None":
        """Find text span (character offsets) for verbatim text in conversation.
        
        Args:
            conversation: Conversation object with messages
            verbatim_text: Exact verbatim quote to find
            turn_index: Optional turn index hint from LLM
            
        Returns:
            TextSpan with offsets, or None if not found
        """
        from models.schemas import TextSpan
        from config import get_settings
        
        settings = get_settings()
        if not settings.verbatim_grounding_enabled or not verbatim_text:
            return None
        
        conversation_text = conversation.get_full_text()
        
        # Normalize whitespace for matching (preserve original for span)
        normalized_verbatim = " ".join(verbatim_text.split())
        normalized_conversation = " ".join(conversation_text.split())
        
        # Try to find verbatim text in conversation (case-insensitive search)
        verbatim_lower = normalized_verbatim.lower()
        conversation_lower = normalized_conversation.lower()
        
        start_idx = conversation_lower.find(verbatim_lower)
        if start_idx == -1:
            # Try partial match - find longest substring
            # For now, return None if exact match fails
            logger.debug(f"Could not find verbatim text in conversation: {verbatim_text[:50]}...")
            return None
        
        end_idx = start_idx + len(normalized_verbatim)
        
        # Map back to original character positions
        # Count characters in original text up to the match
        char_count = 0
        original_start = 0
        original_end = 0
        
        for i, char in enumerate(conversation_text):
            if char_count == start_idx:
                original_start = i
            if char_count == end_idx:
                original_end = i
                break
            if not char.isspace() or (i > 0 and not conversation_text[i-1].isspace()):
                char_count += 1
        
        if original_end == 0:
            original_end = len(conversation_text)
        
        # Calculate turn index if not provided
        if turn_index is None:
            # Count turns by iterating through messages
            # Each user+assistant pair = 1 turn
            turn_count = 0
            char_pos = 0
            for i, msg in enumerate(conversation.messages):
                msg_text = f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
                if original_start >= char_pos and original_start < char_pos + len(msg_text):
                    # Found the message containing the verbatim text
                    turn_count = i // 2  # Each turn = user + assistant
                    break
                char_pos += len(msg_text) + 2  # +2 for "\n\n"
            turn_index = turn_count
        
        return TextSpan(
            text=verbatim_text,
            start_char=original_start,
            end_char=original_end,
            turn_index=turn_index or 0,
        )

    async def _verify_decision(
        self,
        decision_dict: dict,
        source_text: str,
    ) -> tuple[bool, list[str], dict]:
        """Verify an extracted decision against the source text (Part 2d).

        Returns (is_valid, issues, corrected_fields).
        Only used when confidence < high_confidence_threshold to save LLM calls.
        """
        verify_prompt = f"""You are verifying a decision extracted from a conversation.

Source conversation (excerpt):
{source_text[:3000]}

Extracted decision:
{json.dumps(decision_dict, indent=2)}

Verify:
1. Does the decision text actually appear or be clearly inferable from the source? (yes/no)
2. Is this from the IMPLEMENTED path (not an abandoned/rejected alternative)? (yes/no)
3. Are the options[] actual alternatives considered, not just mentions? (yes/no)
4. What is the appropriate confidence (0.0-1.0) based on evidence?
5. Are there any corrections needed for trigger, decision, or rationale fields?

Respond as JSON:
{{"is_valid": true/false, "on_implemented_path": true/false, "issues": ["..."], "corrected_fields": {{}}, "evidence_confidence": 0.0-1.0}}"""

        try:
            response = await self.llm.generate(verify_prompt, temperature=0.1, sanitize_input=False)
            result = extract_json_from_response(response)
            if isinstance(result, dict):
                is_valid = result.get("is_valid", True) and result.get("on_implemented_path", True)
                issues = result.get("issues", [])
                corrected = result.get("corrected_fields", {})
                ev_conf = result.get("evidence_confidence", decision_dict.get("confidence", 0.5))
                # Update confidence with evidence signal
                if ev_conf:
                    decision_dict["evidence_confidence"] = float(ev_conf)
                return is_valid, issues, corrected
        except Exception as e:
            logger.debug(f"Verify pass failed: {e}")
        return True, [], {}

    async def extract_decisions(
        self,
        conversation: Conversation,
        bypass_cache: bool = False,
        decision_type: str | None = None,
    ) -> list[DecisionCreate]:
        """Extract decision traces from a conversation using few-shot CoT prompt.

        Enhanced pipeline (Parts 2b–2e):
        - Uses get_structured_text() which includes thinking blocks and tool calls
        - Applies composite confidence calibration (data-driven, no ground truth needed)
        - Attaches raw_rationale, rationale_author, scope, assumptions to each decision
        - Optionally runs verify/refine pass for low-confidence decisions (Part 2d)

        Args:
            conversation: The conversation to extract decisions from
            bypass_cache: If True, skip cache lookup and force fresh extraction
            decision_type: Optional decision type override (architecture, technology, process)
                          If None, auto-detects based on keywords (ML-P2-2)
        """
        # Use structured text (includes thinking blocks + tool calls) when available
        if conversation.raw_messages:
            conversation_text = conversation.get_structured_text()
        else:
            conversation_text = conversation.get_full_text()

        # Collect episode thinking text for raw_rationale (Part 2c)
        episode_thinking = "\n\n".join(
            msg.thinking
            for msg in conversation.raw_messages
            if getattr(msg, "thinking", None)
        )

        # Truncate conversation if it's too large for the prompt
        # Estimate tokens: ~4 chars per token, plus prompt template overhead
        settings = get_settings()
        max_prompt_tokens = settings.effective_max_prompt_tokens
        
        # Estimate prompt template size (DECISION_EXTRACTION_PROMPT + thinking section)
        prompt_template_size = len(DECISION_EXTRACTION_PROMPT) // 4  # rough token estimate
        thinking_section_size = len(episode_thinking) // 4 if episode_thinking else 0
        available_for_conversation = max_prompt_tokens - prompt_template_size - thinking_section_size - 1000  # safety margin
        
        # Estimate conversation tokens
        conversation_tokens = len(conversation_text) // 4
        
        if conversation_tokens > available_for_conversation:
            # Truncate: keep recent messages (most important for decisions)
            # Strategy: keep last N messages that fit, prioritizing recent content
            logger.warning(
                f"Conversation too large ({conversation_tokens} tokens), truncating to fit "
                f"within {available_for_conversation} tokens. Original length: {len(conversation_text)} chars"
            )
            
            # Calculate target length (leave some margin)
            target_chars = (available_for_conversation - 500) * 4  # chars, with margin
            
            if conversation.raw_messages:
                # For structured text, truncate by keeping recent messages
                # Keep messages from the end until we hit the limit
                truncated_parts = []
                current_length = 0
                
                # Process messages in reverse (most recent first)
                for msg in reversed(conversation.raw_messages):
                    header = f"[Turn {msg.turn_index} | {msg.role}]"
                    sections: list[str] = [header]
                    
                    if msg.thinking:
                        sections.append(f"<thinking>\n{msg.thinking}\n</thinking>")
                    
                    for tc in msg.tool_calls:
                        params = tc.params_summary()
                        tc_line = f"Tool: {tc.name}({params})" if params else f"Tool: {tc.name}()"
                        if tc.result is not None:
                            result_preview = tc.result[:500] + "…" if len(tc.result) > 500 else tc.result
                            sections.append(f"{tc_line}\nResult: {result_preview}")
                        else:
                            sections.append(tc_line)
                    
                    if msg.content:
                        sections.append(f"Response: {msg.content}")
                    
                    msg_text = "\n".join(sections)
                    msg_length = len(msg_text)
                    
                    if current_length + msg_length > target_chars:
                        # Add truncation notice
                        truncated_parts.insert(0, f"[TRUNCATED: {len(conversation.raw_messages) - len(truncated_parts)} earlier messages removed to fit token limit]")
                        break
                    
                    truncated_parts.insert(0, msg_text)
                    current_length += msg_length + 2  # +2 for "\n\n"
                
                conversation_text = "\n\n".join(truncated_parts)
            else:
                # For flat text, simple truncation from the end
                conversation_text = conversation_text[:target_chars]
                conversation_text += "\n\n[TRUNCATED: Earlier conversation removed to fit token limit]"
            
            logger.info(
                f"Truncated conversation to {len(conversation_text)} chars "
                f"(estimated {len(conversation_text) // 4} tokens)"
            )

        # ML-P2-2: Auto-detect decision type if not specified
        if decision_type is None:
            try:
                decision_type = await detect_decision_type_llm(
                    conversation.get_full_text(),  # use flat text for type detection
                    llm_client=self.llm,
                    cache=self.cache,
                    bypass_cache=bypass_cache,
                )
            except Exception as e:
                logger.warning(f"LLM-based decision type detection failed: {e}, falling back to keyword detection")
                decision_type = detect_decision_type(conversation.get_full_text())
        logger.debug(f"Using decision type: {decision_type}")

        # Check cache first (KG-P0-2)
        cache_key = f"{decision_type}:{conversation.get_full_text()}"
        if not bypass_cache:
            cached = await self.cache.get(cache_key, "decisions")
            if cached is not None:
                logger.info(f"Using cached decision extraction (type={decision_type})")
                # Include ALL fields that DecisionCreate supports so that extended
                # fields (scope, assumptions, rationale_author, raw_rationale, verbatim
                # fields, turn_index) are not silently dropped on cache hits.
                _CACHE_FIELDS = {
                    "trigger", "context", "options", "decision", "rationale", "confidence",
                    "scope", "assumptions", "rationale_author", "raw_rationale",
                    "verbatim_trigger", "verbatim_decision", "verbatim_rationale", "turn_index",
                }
                return [
                    DecisionCreate(
                        **{k: v for k, v in apply_decision_defaults(d).items() if k in _CACHE_FIELDS}
                    )
                    for d in cached
                    if apply_decision_defaults(d).get("decision")
                ]

        # Build prompt — inject thinking blocks as high-fidelity rationale signal
        thinking_section = ""
        if episode_thinking:
            thinking_section = f"\n<thinking_blocks>\n{episode_thinking[:4000]}\n</thinking_blocks>\nUse the above internal reasoning (if present) as ground truth for the rationale field.\n"

        # ML-P2-2: Select appropriate prompt based on decision type
        specialized_prompt = DECISION_TYPE_PROMPTS.get(decision_type)
        if specialized_prompt is not None:
            prompt = specialized_prompt.format(conversation_text=conversation_text) + thinking_section
        else:
            prompt = DECISION_EXTRACTION_PROMPT.format(
                conversation_text=conversation_text
            ) + thinking_section

        try:
            # Increase max_tokens for complete responses
            response = await self.llm.generate(
                prompt, 
                temperature=0.3, 
                sanitize_input=False,
                max_tokens=8192,  # Increased from default 4096 for longer responses
            )

            # Use robust JSON extraction with dict-to-list conversion
            decisions_data = extract_json_from_response(
                response, 
                context="decision_extraction",
                expect_list=True  # Convert single dict to list if needed
            )

            if decisions_data is None:
                logger.warning("Failed to parse decisions from LLM response")
                return []

            # Ensure we have a list (dict-to-list wrapper)
            # This is a safety net in case expect_list conversion didn't work
            if isinstance(decisions_data, dict):
                logger.warning(
                    f"extract_json_from_response returned dict despite expect_list=True. "
                    f"Converting manually. Response preview: {str(decisions_data)[:200]}"
                )
                decisions_data = [decisions_data]
            elif not isinstance(decisions_data, list):
                logger.error(
                    f"Unexpected type from extract_json_from_response: {type(decisions_data)}. "
                    f"Value: {decisions_data}. This should not happen."
                )
                return []
            
            if not isinstance(decisions_data, list):
                logger.warning(f"Expected list, got {type(decisions_data)}")
                return []

            # ---------------------------------------------------------------
            # Part 14: LightRAG gleaning — re-extract for incomplete decisions
            # ---------------------------------------------------------------
            # If initial extraction produced sparse results (< 60% fields filled),
            # run a focused "gleaning" pass to recover missed context.
            # Max 1 gleaning iteration (controlled by extraction_max_gleaning config).
            settings_for_gleaning = get_settings()
            max_gleaning = getattr(settings_for_gleaning, "extraction_max_gleaning", 1)
            if max_gleaning > 0 and decisions_data:
                incomplete = [
                    d for d in decisions_data
                    if _completeness_score(d) < 0.6
                ]
                if incomplete:
                    glean_prompt = (
                        f"Below is a partial decision extraction from a conversation. "
                        f"Several fields are missing or too short. "
                        f"Re-extract ONLY the missing fields for each decision.\n\n"
                        f"ORIGINAL CONVERSATION (excerpt):\n{conversation_text[:3000]}\n\n"
                        f"PARTIAL EXTRACTIONS:\n"
                        f"{json.dumps(incomplete, indent=2)[:2000]}\n\n"
                        f"For each partial decision, fill in any missing: context, options, "
                        f"rationale, scope, assumptions. Return a JSON list with the same "
                        f"indices, containing ONLY the filled-in fields (do not repeat "
                        f"already-complete fields). Return: [{{\"idx\": 0, \"context\": \"...\", ...}}]"
                    )
                    try:
                        glean_response = await self.llm.generate(
                            glean_prompt, temperature=0.2, sanitize_input=False
                        )
                        gleaned = extract_json_from_response(glean_response)
                        if isinstance(gleaned, list):
                            for patch in gleaned:
                                # Find corresponding decision by index or trigger match
                                idx = patch.pop("idx", None)
                                if idx is not None and 0 <= idx < len(decisions_data):
                                    for field_key, field_val in patch.items():
                                        if field_val and not decisions_data[idx].get(field_key):
                                            decisions_data[idx][field_key] = field_val
                            logger.debug(
                                f"Gleaning pass patched {len(gleaned)} incomplete decisions"
                            )
                    except Exception as e:
                        logger.debug(f"Gleaning pass failed (non-critical): {e}")

            # ---------------------------------------------------------------
            # Part 14: instructor-style retry — validate extraction output
            # ---------------------------------------------------------------
            # If any extracted decision fails our _is_valid_decision gate and
            # the confidence is > 0.3, attempt one targeted re-extraction.
            # This mirrors instructor's retry loop without requiring the library.
            retry_count = 0
            max_retries = 1
            for d in decisions_data:
                if retry_count >= max_retries:
                    break
                d_defaults = apply_decision_defaults(d)
                is_valid, rejection_reason = _is_valid_decision(d_defaults)
                if not is_valid and d.get("confidence", 0.5) >= 0.4:
                    # Targeted re-extraction for this specific decision
                    retry_prompt = (
                        f"The following decision extraction failed validation: {rejection_reason}\n\n"
                        f"Partial extraction:\n{json.dumps(d, indent=2)[:500]}\n\n"
                        f"Source conversation (excerpt):\n{conversation_text[:2000]}\n\n"
                        f"Please re-extract this single decision with all required fields "
                        f"(trigger min 10 chars, decision min 10 chars, confidence 0.3-1.0). "
                        f"Return a JSON object (not a list)."
                    )
                    try:
                        retry_response = await self.llm.generate(
                            retry_prompt, temperature=0.2, sanitize_input=False
                        )
                        retried = extract_json_from_response(retry_response)
                        if isinstance(retried, dict):
                            d.update({k: v for k, v in retried.items() if v})
                            retry_count += 1
                    except Exception as e:
                        logger.debug(f"Instructor retry failed (non-critical): {e}")

            # Part 2e: Composite confidence calibration (data-driven, no ground truth)
            settings = get_settings()

            # Determine rationale author for the whole conversation once
            # (thinking blocks apply to all decisions in this episode)
            episode_rationale_author = _detect_rationale_author(
                {},
                conversation.raw_messages,
            )

            for d in decisions_data:
                raw_confidence = d.get("confidence", 0.5)
                d["raw_confidence"] = raw_confidence

                if settings.confidence_calibration_method == "composite":
                    calibrated = calibrate_confidence_composite(
                        d,
                        rationale_author=episode_rationale_author,
                        conversation_text=conversation.get_full_text(),
                    )
                elif settings.confidence_calibration_method == "temperature":
                    calibrated = calibrate_confidence_temperature(d, settings.confidence_calibration_temperature)
                elif settings.confidence_calibration_method == "heuristic":
                    calibrated = calibrate_confidence(d)
                else:
                    # Default to composite (new default)
                    calibrated = calibrate_confidence_composite(
                        d,
                        rationale_author=episode_rationale_author,
                        conversation_text=conversation.get_full_text(),
                    )

                d["confidence"] = calibrated

            # Part 2d: Verify pass for low-confidence decisions
            # Run in parallel to minimise latency overhead
            # Use raw_confidence (pre-calibration) to decide which decisions need
            # verification — calibration can legitimately lower scores for sparse
            # decisions, and we don't want to verify every decision every run.
            import asyncio as _asyncio
            verify_tasks = []
            verify_indices = []
            for i, d in enumerate(decisions_data):
                # Check raw confidence if available, else fall back to calibrated
                check_confidence = d.get("raw_confidence", d.get("confidence", 0.5))
                if check_confidence < self.high_confidence_threshold:
                    verify_tasks.append(
                        self._verify_decision(d, conversation.get_full_text()[:4000])
                    )
                    verify_indices.append(i)

            if verify_tasks:
                verify_results = await _asyncio.gather(*verify_tasks, return_exceptions=True)
                for idx, result in zip(verify_indices, verify_results):
                    if isinstance(result, Exception):
                        continue
                    is_valid, issues, corrected = result
                    if not is_valid:
                        # Mark for rejection (keep it in list; validation gate will drop it)
                        decisions_data[idx]["confidence"] = 0.1
                        decisions_data[idx]["_verify_rejected"] = True
                        logger.debug(f"Decision rejected by verify pass: {issues}")
                    elif corrected:
                        decisions_data[idx].update(corrected)

            # Log extraction summary (KG-QW-4)
            if decisions_data:
                confidence_scores = [d.get("confidence", 0.5) for d in decisions_data]
                raw_scores = [d.get("raw_confidence", d.get("confidence", 0.5)) for d in decisions_data]
                avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
                avg_raw = sum(raw_scores) / len(raw_scores) if raw_scores else 0
                logger.info(
                    "Decision extraction completed",
                    extra={
                        "extraction_type": "decisions",
                        "decision_type": decision_type,
                        "count": len(decisions_data),
                        "avg_confidence": round(avg_confidence, 3),
                        "avg_raw_confidence": round(avg_raw, 3),
                        "calibration_delta": round(avg_confidence - avg_raw, 3),
                        "has_thinking": bool(episode_thinking),
                        "rationale_author": episode_rationale_author,
                        "confidence_range": {
                            "min": round(min(confidence_scores), 3) if confidence_scores else 0,
                            "max": round(max(confidence_scores), 3) if confidence_scores else 0,
                        },
                        "decisions_summary": [
                            {
                                "trigger_preview": d.get("trigger", "")[:50],
                                "confidence": d.get("confidence", 0.5),
                                "raw_confidence": d.get("raw_confidence", d.get("confidence", 0.5)),
                            }
                            for d in decisions_data[:5]
                        ],
                    },
                )

            # Apply defaults and build DecisionCreate objects
            decisions = []
            for d in decisions_data:
                decision_dict = apply_decision_defaults(d)

                # Strict validation gate
                is_valid, rejection_reason = _is_valid_decision(decision_dict)
                if not is_valid or decision_dict.get("_verify_rejected"):
                    logger.debug(
                        "Decision rejected by validation gate",
                        extra={
                            "rejection_reason": rejection_reason or "verify_pass",
                            "decision_preview": str(decision_dict.get("decision", ""))[:100],
                            "trigger_preview": str(decision_dict.get("trigger", ""))[:100],
                            "confidence": decision_dict.get("confidence", 0.0),
                        },
                    )
                    continue

                # Verbatim grounding (RQ1.2)
                verbatim_trigger = decision_dict.get("verbatim_trigger")
                verbatim_decision = decision_dict.get("verbatim_decision")
                verbatim_rationale = decision_dict.get("verbatim_rationale")
                turn_index = decision_dict.get("turn_index")

                trigger_span = None
                decision_span = None
                rationale_span = None

                if verbatim_trigger:
                    trigger_span = self._find_text_span(conversation, verbatim_trigger, turn_index)
                if verbatim_decision:
                    decision_span = self._find_text_span(conversation, verbatim_decision, turn_index)
                if verbatim_rationale:
                    rationale_span = self._find_text_span(conversation, verbatim_rationale, turn_index)

                # Per-decision rationale author (refines episode-level signal)
                per_decision_author = _detect_rationale_author(
                    decision_dict, conversation.raw_messages
                )

                # Create DecisionCreate with all new fields
                decision_create = DecisionCreate(
                    **{
                        k: v
                        for k, v in decision_dict.items()
                        if k in ("trigger", "context", "options", "decision", "rationale", "confidence")
                    },
                    verbatim_trigger=verbatim_trigger,
                    verbatim_decision=verbatim_decision,
                    verbatim_rationale=verbatim_rationale,
                    trigger_span=trigger_span,
                    decision_span=decision_span,
                    rationale_span=rationale_span,
                    turn_index=turn_index,
                    # New fields (Parts 2c, 4.7, 7)
                    raw_rationale=episode_thinking or None,
                    rationale_author=per_decision_author,
                    scope=decision_dict.get("scope") or None,
                    assumptions=decision_dict.get("assumptions", []),
                )
                # Attach ground-truth tool-call file paths (Part 4.1)
                # These bypass fuzzy matching — confidence 1.0 for AFFECTS edges.
                # Set as a private attribute (not a Pydantic field) so save_decision
                # can pick it up via getattr(decision, "_tool_file_paths", None).
                try:
                    # Collect all file paths from tool calls in the conversation
                    _tool_paths: list[str] = []
                    for raw_msg in conversation.raw_messages:
                        for tc in getattr(raw_msg, "tool_calls", []):
                            _tool_paths.extend(tc.file_paths)
                    if _tool_paths:
                        object.__setattr__(decision_create, "_tool_file_paths", list(set(_tool_paths)))
                except Exception:
                    pass  # Non-critical — gracefully skip if Pydantic rejects it

                decisions.append(decision_create)

            # Cache only the validated decisions (KG-P0-2).
            # Caching after validation ensures the cache never stores verify-rejected
            # or low-confidence entries that would be silently saved on a cache hit.
            if decisions:
                cacheable = [
                    {k: v for k, v in d.items() if k != "_verify_rejected"}
                    for d in decisions_data
                    if not d.get("_verify_rejected")
                    and _is_valid_decision(apply_decision_defaults(d))[0]
                ]
                await self.cache.set(cache_key, "decisions", cacheable)

            return decisions

        except (TimeoutError, ConnectionError) as e:
            logger.error(f"LLM connection error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error extracting decisions: {e}")
            return []

    async def extract_entities(
        self, text: str, bypass_cache: bool = False
    ) -> list[dict]:
        """Extract entities from text using few-shot CoT prompt.

        Args:
            text: The text to extract entities from
            bypass_cache: If True, skip cache lookup and force fresh extraction

        Returns list of dicts with name, type, and confidence.
        """
        # Check cache first (KG-P0-2)
        if not bypass_cache:
            cached = await self.cache.get(text, "entities")
            if cached is not None:
                logger.info("Using cached entity extraction")
                return cached

        prompt = ENTITY_EXTRACTION_PROMPT.format(decision_text=text)

        try:
            response = await self.llm.generate(prompt, temperature=0.3, sanitize_input=False)

            # Use robust JSON extraction
            result = extract_json_from_response(response)

            if result is None:
                logger.warning("Failed to parse entity extraction response")
                return []

            entities = result.get("entities", [])
            reasoning = result.get("reasoning", "")

            # Log extraction with structured data (KG-QW-4: Extraction reasoning logging)
            if entities:
                # Group entities by type for summary
                type_counts = {}
                confidence_by_type = {}
                for e in entities:
                    etype = e.get("type", "unknown")
                    type_counts[etype] = type_counts.get(etype, 0) + 1
                    if etype not in confidence_by_type:
                        confidence_by_type[etype] = []
                    confidence_by_type[etype].append(e.get("confidence", 0.8))

                avg_confidence_by_type = {
                    t: round(sum(scores) / len(scores), 3)
                    for t, scores in confidence_by_type.items()
                }

                logger.info(
                    "Entity extraction completed",
                    extra={
                        "extraction_type": "entities",
                        "count": len(entities),
                        "type_distribution": type_counts,
                        "avg_confidence_by_type": avg_confidence_by_type,
                        "entities": [
                            {
                                "name": e.get("name"),
                                "type": e.get("type"),
                                "confidence": e.get("confidence"),
                            }
                            for e in entities
                        ],
                        "llm_reasoning": reasoning[:500]
                        if reasoning
                        else None,  # Truncate for log size
                    },
                )
            else:
                logger.debug(
                    "No entities extracted from text",
                    extra={
                        "text_length": len(text),
                        "llm_reasoning": reasoning[:200] if reasoning else None,
                    },
                )

            # Cache the result (KG-P0-2)
            await self.cache.set(text, "entities", entities)

            return entities

        except (TimeoutError, ConnectionError) as e:
            logger.error(f"LLM connection error during entity extraction: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during entity extraction: {e}")
            return []

    async def extract_entity_relationships(
        self, entities: list[Entity], context: str = "", bypass_cache: bool = False
    ) -> list[dict]:
        """Extract relationships between entities using few-shot CoT prompt.

        Includes relationship type validation (KG-P0-3).
        """
        if len(entities) < 2:
            return []

        import json as json_module

        entity_names = [
            e.name if hasattr(e, "name") else e.get("name", "") for e in entities
        ]

        # Build entity type lookup for validation
        entity_types = {}
        for e in entities:
            name = e.name if hasattr(e, "name") else e.get("name", "")
            etype = e.type if hasattr(e, "type") else e.get("type", "concept")
            entity_types[name.lower()] = etype

        # Cache key includes entities and context
        cache_text = f"{json_module.dumps(sorted(entity_names))}|{context}"

        # Check cache first (KG-P0-2)
        if not bypass_cache:
            cached = await self.cache.get(cache_text, "relationships")
            if cached is not None:
                logger.info("Using cached relationship extraction")
                return cached

        prompt = ENTITY_RELATIONSHIP_PROMPT.format(
            entities=json_module.dumps(entity_names),
            context=context or "General technical discussion",
        )

        try:
            response = await self.llm.generate(prompt, temperature=0.3, sanitize_input=False)

            # Use robust JSON extraction
            result = extract_json_from_response(response)

            if result is None:
                logger.warning("Failed to parse relationship extraction response")
                return []

            relationships = result.get("relationships", [])
            reasoning = result.get("reasoning", "")

            # Log raw extraction (KG-QW-4: Extraction reasoning logging)
            logger.debug(
                "Raw relationship extraction from LLM",
                extra={
                    "extraction_type": "relationships_raw",
                    "count": len(relationships),
                    "entity_count": len(entity_names),
                    "llm_reasoning": reasoning[:500] if reasoning else None,
                },
            )

            # Validate and filter relationships (KG-P0-3)
            validated_relationships = []
            validation_stats = {"valid": 0, "invalid": 0, "fallback": 0}
            for rel in relationships:
                rel_type = rel.get("type", "RELATED_TO")
                from_name = rel.get("from", "")
                to_name = rel.get("to", "")
                confidence = rel.get("confidence", 0.8)

                # Get entity types for validation
                from_type = entity_types.get(from_name.lower(), "concept")
                to_type = entity_types.get(to_name.lower(), "concept")

                # Validate the relationship (KG-P0-3)
                is_valid, error_msg = validate_entity_relationship(
                    rel_type, from_type, to_type
                )

                if is_valid:
                    validated_relationships.append(rel)
                    validation_stats["valid"] += 1
                else:
                    validation_stats["invalid"] += 1
                    # Log invalid relationship for review
                    logger.debug(
                        "Invalid relationship skipped",
                        extra={
                            "from_entity": from_name,
                            "from_type": from_type,
                            "to_entity": to_name,
                            "to_type": to_type,
                            "relationship_type": rel_type,
                            "error": error_msg,
                        },
                    )
                    # Try to suggest a valid alternative
                    if rel_type in ENTITY_ONLY_RELATIONSHIPS:
                        # Fall back to RELATED_TO if the specific type doesn't work
                        validated_relationships.append(
                            {
                                "from": from_name,
                                "to": to_name,
                                "type": "RELATED_TO",
                                "confidence": confidence
                                * 0.8,  # Lower confidence for fallback
                            }
                        )
                        validation_stats["fallback"] += 1
                        logger.debug(
                            "Relationship type fallback applied",
                            extra={
                                "from_entity": from_name,
                                "to_entity": to_name,
                                "original_type": rel_type,
                                "fallback_type": "RELATED_TO",
                            },
                        )

            # Log relationship extraction summary (KG-QW-4)
            if validated_relationships:
                type_distribution = {}
                for r in validated_relationships:
                    rtype = r.get("type", "RELATED_TO")
                    type_distribution[rtype] = type_distribution.get(rtype, 0) + 1

                logger.info(
                    "Relationship extraction completed",
                    extra={
                        "extraction_type": "relationships",
                        "raw_count": len(relationships),
                        "validated_count": len(validated_relationships),
                        "validation_stats": validation_stats,
                        "type_distribution": type_distribution,
                        "relationships": [
                            {
                                "from": r.get("from"),
                                "to": r.get("to"),
                                "type": r.get("type"),
                                "confidence": r.get("confidence"),
                            }
                            for r in validated_relationships
                        ],
                    },
                )

            # Cache the validated result (KG-P0-2)
            await self.cache.set(cache_text, "relationships", validated_relationships)

            return validated_relationships

        except (TimeoutError, ConnectionError) as e:
            logger.error(f"LLM connection error during relationship extraction: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during relationship extraction: {e}")
            return []

    async def extract_decision_relationship(
        self, decision_a: dict, decision_b: dict
    ) -> Optional[dict]:
        """Analyze two decisions for SUPERSEDES or CONTRADICTS relationship."""
        prompt = DECISION_RELATIONSHIP_PROMPT.format(
            decision_a_date=decision_a.get("created_at", "unknown"),
            decision_a_trigger=decision_a.get("trigger", ""),
            decision_a_text=decision_a.get("decision", ""),
            decision_a_rationale=decision_a.get("rationale", ""),
            decision_b_date=decision_b.get("created_at", "unknown"),
            decision_b_trigger=decision_b.get("trigger", ""),
            decision_b_text=decision_b.get("decision", ""),
            decision_b_rationale=decision_b.get("rationale", ""),
        )

        try:
            response = await self.llm.generate(prompt, temperature=0.3, sanitize_input=False)

            # Use robust JSON extraction
            result = extract_json_from_response(response)

            if result is None:
                logger.warning("Failed to parse decision relationship response")
                return None

            if result.get("relationship") is None:
                return None

            return {
                "type": result.get("relationship"),
                "confidence": result.get("confidence", 0.5),
                "reasoning": result.get("reasoning", ""),
            }

        except (TimeoutError, ConnectionError) as e:
            logger.error(
                f"LLM connection error during decision relationship analysis: {e}"
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error during decision relationship analysis: {e}")
            return None

    async def save_decision(
        self,
        decision: DecisionCreate,
        source: str = "unknown",
        user_id: str = "anonymous",
        provenance: Optional[Provenance] = None,
        source_path: Optional[str] = None,
        message_index: Optional[int] = None,
        project_name: Optional[str] = None,
    ) -> str:
        """Save a decision to Neo4j with embeddings, rich relationships, and provenance (KG-P2-4).

        Uses entity resolution to prevent duplicates and canonicalize names.
        Includes user_id for multi-tenant data isolation.
        Tracks provenance information for data lineage.

        Args:
            decision: The decision to save
            source: Where this decision came from ('claude_logs', 'interview', 'manual')
            user_id: The user ID for multi-tenant isolation (default: "anonymous")
            provenance: Optional provenance information for data lineage (KG-P2-4)
            source_path: Optional path to source file for provenance tracking
            message_index: Optional index of message in conversation
            project_name: Optional project this decision belongs to

        Returns:
            The ID of the created decision
        """
        decision_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        # Use source parameter (decisions from LLM don't include source field)
        decision_source = source
        # Use project_name from decision if provided, otherwise use parameter
        decision_project = getattr(decision, "project_name", None) or project_name
        # Normalize project name to lowercase for consistency
        if decision_project:
            decision_project = decision_project.lower()

        # KG-P2-4: Build provenance if not provided
        if provenance is None:
            source_type_map = {
                "claude_logs": SourceType.CLAUDE_LOG,
                "interview": SourceType.INTERVIEW,
                "manual": SourceType.MANUAL,
                "unknown": SourceType.MANUAL,
            }
            provenance = create_llm_provenance(
                source_type=source_type_map.get(decision_source, SourceType.MANUAL),
                source_path=source_path,
                model_name=self.llm.model if hasattr(self.llm, "model") else None,
                prompt_version=get_settings().llm_extraction_prompt_version,
                confidence=decision.confidence,
                created_by=user_id,
                message_index=message_index,
            )

        # Serialize provenance for storage
        provenance_json = json.dumps(provenance.to_dict()) if provenance else None

        # Generate embedding for the decision
        decision_dict = {
            "trigger": decision.trigger,
            "context": decision.context,
            "options": decision.options,
            "decision": decision.agent_decision,
            "rationale": decision.agent_rationale,
        }

        try:
            embedding = await self.embedding_service.embed_decision(decision_dict)
            logger.debug(f"Generated embedding with {len(embedding)} dimensions")
        except (TimeoutError, ConnectionError) as e:
            logger.warning(f"Embedding service connection failed: {e}")
            embedding = None
        except ValueError as e:
            logger.warning(f"Invalid embedding input: {e}")
            embedding = None

        session = await get_neo4j_session()
        async with session:
            # Extract verbatim fields and turn_index (RQ1.2, RQ1.3: Verbatim grounding & temporal reasoning)
            verbatim_trigger = getattr(decision, "verbatim_trigger", None) or None
            verbatim_decision = getattr(decision, "verbatim_decision", None) or None
            verbatim_rationale = getattr(decision, "verbatim_rationale", None) or None
            turn_index = getattr(decision, "turn_index", None)
            
            # Serialize text spans if available
            trigger_span_json = None
            decision_span_json = None
            rationale_span_json = None
            if hasattr(decision, "trigger_span") and decision.trigger_span:
                trigger_span_json = json.dumps({
                    "text": decision.trigger_span.text,
                    "start_char": decision.trigger_span.start_char,
                    "end_char": decision.trigger_span.end_char,
                    "turn_index": decision.trigger_span.turn_index,
                })
            if hasattr(decision, "decision_span") and decision.decision_span:
                decision_span_json = json.dumps({
                    "text": decision.decision_span.text,
                    "start_char": decision.decision_span.start_char,
                    "end_char": decision.decision_span.end_char,
                    "turn_index": decision.decision_span.turn_index,
                })
            if hasattr(decision, "rationale_span") and decision.rationale_span:
                rationale_span_json = json.dumps({
                    "text": decision.rationale_span.text,
                    "start_char": decision.rationale_span.start_char,
                    "end_char": decision.rationale_span.end_char,
                    "turn_index": decision.rationale_span.turn_index,
                })
            
            # Extract Part 4.7 / 2c / 7 / 11 fields from decision
            decision_scope = getattr(decision, "scope", None)
            decision_scope_val = decision_scope.value if decision_scope else None
            decision_raw_rationale = getattr(decision, "raw_rationale", None) or None
            decision_rationale_author = getattr(decision, "rationale_author", None)
            decision_rationale_author_val = (
                decision_rationale_author.value if decision_rationale_author else None
            )
            decision_assumptions = list(getattr(decision, "assumptions", None) or [])

            # Create decision node with embedding, user_id, provenance, verbatim fields, and turn_index
            if embedding:
                await session.run(
                    """
                    CREATE (d:DecisionTrace {
                        id: $id,
                        trigger: $trigger,
                        context: $context,
                        options: $options,
                        agent_decision: $agent_decision,
                        agent_rationale: $agent_rationale,
                        confidence: $confidence,
                        created_at: $created_at,
                        source: $source,
                        user_id: $user_id,
                        project_name: $project_name,
                        embedding: $embedding,
                        provenance: $provenance,
                        extraction_method: $extraction_method,
                        created_by: $created_by,
                        verbatim_trigger: $verbatim_trigger,
                        verbatim_decision: $verbatim_decision,
                        verbatim_rationale: $verbatim_rationale,
                        turn_index: $turn_index,
                        trigger_span: $trigger_span,
                        decision_span: $decision_span,
                        rationale_span: $rationale_span,
                        scope: $scope,
                        raw_rationale: $raw_rationale,
                        rationale_author: $rationale_author,
                        assumptions: $assumptions
                    })
                    """,
                    id=decision_id,
                    trigger=decision.trigger,
                    context=decision.context,
                    options=decision.options,
                    agent_decision=decision.agent_decision,
                    agent_rationale=decision.agent_rationale,
                    confidence=decision.confidence,
                    created_at=created_at,
                    source=decision_source,
                    user_id=user_id,
                    project_name=decision_project,
                    embedding=embedding,
                    provenance=provenance_json,
                    extraction_method=provenance.extraction.method.value
                    if provenance
                    else "unknown",
                    created_by=provenance.created_by if provenance else user_id,
                    verbatim_trigger=verbatim_trigger,
                    verbatim_decision=verbatim_decision,
                    verbatim_rationale=verbatim_rationale,
                    turn_index=turn_index,
                    trigger_span=trigger_span_json,
                    decision_span=decision_span_json,
                    rationale_span=rationale_span_json,
                    scope=decision_scope_val,
                    raw_rationale=decision_raw_rationale,
                    rationale_author=decision_rationale_author_val,
                    assumptions=decision_assumptions,
                )
            else:
                await session.run(
                    """
                    CREATE (d:DecisionTrace {
                        id: $id,
                        trigger: $trigger,
                        context: $context,
                        options: $options,
                        agent_decision: $agent_decision,
                        agent_rationale: $agent_rationale,
                        confidence: $confidence,
                        created_at: $created_at,
                        source: $source,
                        user_id: $user_id,
                        project_name: $project_name,
                        provenance: $provenance,
                        extraction_method: $extraction_method,
                        created_by: $created_by,
                        verbatim_trigger: $verbatim_trigger,
                        verbatim_decision: $verbatim_decision,
                        verbatim_rationale: $verbatim_rationale,
                        turn_index: $turn_index,
                        trigger_span: $trigger_span,
                        decision_span: $decision_span,
                        rationale_span: $rationale_span,
                        scope: $scope,
                        raw_rationale: $raw_rationale,
                        rationale_author: $rationale_author,
                        assumptions: $assumptions
                    })
                    """,
                    id=decision_id,
                    trigger=decision.trigger,
                    context=decision.context,
                    options=decision.options,
                    agent_decision=decision.agent_decision,
                    agent_rationale=decision.agent_rationale,
                    confidence=decision.confidence,
                    created_at=created_at,
                    source=decision_source,
                    user_id=user_id,
                    project_name=decision_project,
                    provenance=provenance_json,
                    extraction_method=provenance.extraction.method.value
                    if provenance
                    else "unknown",
                    created_by=provenance.created_by if provenance else user_id,
                    verbatim_trigger=verbatim_trigger,
                    verbatim_decision=verbatim_decision,
                    verbatim_rationale=verbatim_rationale,
                    turn_index=turn_index,
                    trigger_span=trigger_span_json,
                    decision_span=decision_span_json,
                    rationale_span=rationale_span_json,
                    scope=decision_scope_val,
                    raw_rationale=decision_raw_rationale,
                    rationale_author=decision_rationale_author_val,
                    assumptions=decision_assumptions,
                )

            logger.info(f"Created decision {decision_id} for user {user_id}")
            
            # RQ1.3: Create temporal relationships if turn_index is available
            if turn_index is not None:
                await self._create_temporal_relationships(
                    session, decision_id, turn_index, user_id, decision_project
                )

            # Extract entities with enhanced prompt
            full_text = f"{decision.trigger} {decision.context} {decision.agent_decision} {decision.agent_rationale}"
            entities_data = await self.extract_entities(full_text)
            logger.debug(
                "Entities data extracted from text",
                extra={
                    "decision_id": decision_id,
                    "entity_count": len(entities_data),
                    "text_length": len(full_text),
                },
            )

            # Create entity resolver for this session
            resolver = EntityResolver(session)

            # Resolve and create/link entities
            resolved_entities = []
            for entity_data in entities_data:
                name = entity_data.get("name", "")
                entity_type = entity_data.get("type", "concept")
                confidence = entity_data.get("confidence", 0.8)

                if not name:
                    continue

                # Resolve entity (finds existing or creates new)
                resolved = await resolver.resolve(name, entity_type)
                resolved_entities.append(resolved)

                # Generate entity embedding for new entities
                entity_embedding = None
                if resolved.is_new:
                    try:
                        entity_embedding = await self.embedding_service.embed_entity(
                            {
                                "name": resolved.name,
                                "type": resolved.type,
                            }
                        )
                    except (TimeoutError, ConnectionError, ValueError):
                        pass

                # Create or update entity node
                # Part 14 (graphiti bi-temporal): INVOLVES edges carry valid_at so
                # that point-in-time queries can reconstruct the graph at any date.
                if resolved.is_new:
                    if entity_embedding:
                        await session.run(
                            """
                            CREATE (e:Entity {
                                id: $id,
                                name: $name,
                                type: $type,
                                aliases: $aliases,
                                embedding: $embedding
                            })
                            WITH e
                            MATCH (d:DecisionTrace {id: $decision_id})
                            CREATE (d)-[:INVOLVES {weight: $confidence, valid_at: $valid_at, invalid_at: null}]->(e)
                            """,
                            id=resolved.id,
                            name=resolved.name,
                            type=resolved.type,
                            aliases=resolved.aliases,
                            embedding=entity_embedding,
                            decision_id=decision_id,
                            confidence=confidence,
                            valid_at=created_at,
                        )
                    else:
                        await session.run(
                            """
                            CREATE (e:Entity {
                                id: $id,
                                name: $name,
                                type: $type,
                                aliases: $aliases
                            })
                            WITH e
                            MATCH (d:DecisionTrace {id: $decision_id})
                            CREATE (d)-[:INVOLVES {weight: $confidence, valid_at: $valid_at, invalid_at: null}]->(e)
                            """,
                            id=resolved.id,
                            name=resolved.name,
                            type=resolved.type,
                            aliases=resolved.aliases,
                            decision_id=decision_id,
                            confidence=confidence,
                            valid_at=created_at,
                        )
                    logger.debug(
                        "Created new entity",
                        extra={
                            "entity_name": resolved.name,
                            "entity_type": resolved.type,
                            "entity_id": resolved.id,
                            "aliases": resolved.aliases,
                        },
                    )
                else:
                    # Link to existing entity
                    await session.run(
                        """
                        MATCH (e:Entity {id: $entity_id})
                        MATCH (d:DecisionTrace {id: $decision_id})
                        MERGE (d)-[r:INVOLVES]->(e)
                        SET r.weight = $confidence,
                            r.valid_at = $valid_at,
                            r.invalid_at = null
                        """,
                        entity_id=resolved.id,
                        decision_id=decision_id,
                        confidence=confidence,
                        valid_at=created_at,
                    )
                    logger.debug(
                        "Linked to existing entity",
                        extra={
                            "entity_name": resolved.name,
                            "entity_type": resolved.type,
                            "match_method": resolved.match_method,
                            "confidence": resolved.confidence,
                            "entity_id": resolved.id,
                        },
                    )

            # Log entity resolution summary (KG-QW-4: Extraction reasoning logging)
            if resolved_entities:
                resolution_summary = {
                    "total_extracted": len(entities_data),
                    "total_resolved": len(resolved_entities),
                    "new_entities": sum(1 for e in resolved_entities if e.is_new),
                    "existing_entities": sum(
                        1 for e in resolved_entities if not e.is_new
                    ),
                    "match_methods": {},
                }
                for e in resolved_entities:
                    method = e.match_method
                    resolution_summary["match_methods"][method] = (
                        resolution_summary["match_methods"].get(method, 0) + 1
                    )

                logger.info(
                    "Entity resolution completed",
                    extra={
                        "decision_id": decision_id,
                        "resolution_summary": resolution_summary,
                        "resolved_entities": [
                            {
                                "name": e.name,
                                "type": e.type,
                                "is_new": e.is_new,
                                "match_method": e.match_method,
                                "confidence": round(e.confidence, 3),
                            }
                            for e in resolved_entities
                        ],
                    },
                )

            # Extract and create entity-to-entity relationships
            if len(resolved_entities) >= 2:
                entity_rels = await self.extract_entity_relationships(
                    [{"name": e.name, "type": e.type} for e in resolved_entities],
                    context=full_text,
                )
                logger.debug(
                    "Entity relationships extracted for decision",
                    extra={
                        "decision_id": decision_id,
                        "relationship_count": len(entity_rels),
                        "entity_count": len(resolved_entities),
                    },
                )

                for rel in entity_rels:
                    rel_type = rel.get("type", "RELATED_TO")
                    confidence = rel.get("confidence", 0.8)
                    from_name = rel.get("from")
                    to_name = rel.get("to")

                    # Validate relationship type (already done in extract_entity_relationships)
                    # KG-P2-1: Include extended relationship types
                    valid_types = [
                        "IS_A",
                        "PART_OF",
                        "RELATED_TO",
                        "DEPENDS_ON",
                        "ALTERNATIVE_TO",
                        "ENABLES",
                        "PREVENTS",
                        "REQUIRES",
                        "REFINES",
                    ]
                    if rel_type not in valid_types:
                        rel_type = "RELATED_TO"

                    # Resolve entity names to canonical forms
                    from_canonical = (
                        get_canonical_name(from_name) if from_name else None
                    )
                    to_canonical = get_canonical_name(to_name) if to_name else None

                    if from_canonical and to_canonical:
                        await session.run(
                            f"""
                            MATCH (e1:Entity)
                            WHERE toLower(e1.name) = toLower($from_name)
                               OR ANY(alias IN COALESCE(e1.aliases, []) WHERE toLower(alias) = toLower($from_name))
                            MATCH (e2:Entity)
                            WHERE toLower(e2.name) = toLower($to_name)
                               OR ANY(alias IN COALESCE(e2.aliases, []) WHERE toLower(alias) = toLower($to_name))
                            WITH e1, e2
                            WHERE e1 <> e2
                            MERGE (e1)-[r:{rel_type}]->(e2)
                            SET r.confidence = $confidence
                            """,
                            from_name=from_name,
                            to_name=to_name,
                            confidence=confidence,
                        )

            # Find and link similar decisions (if embedding exists)
            # Only compare with decisions from the same user for isolation
            if embedding:
                await self._link_similar_decisions(
                    session, decision_id, embedding, user_id
                )

            # Create temporal chains (INFLUENCED_BY)
            # Only within the same user's decisions
            await self._create_temporal_chains(session, decision_id, user_id)
            
            # RQ1.3: Create FOLLOWS/PRECEDES relationships based on turn_index
            if turn_index is not None:
                await self._create_temporal_relationships(
                    session, decision_id, turn_index, user_id, decision_project
                )

            # ---------------------------------------------------------------
            # Part 4.3: Create CandidateDecision nodes for rejected alternatives
            # ---------------------------------------------------------------
            # Any option in decision.options that was NOT chosen becomes a
            # CandidateDecision node linked via REJECTED_BY to this decision.
            # This makes the DormantAlternativeDetector functional end-to-end.
            DormantDetectorCls = _get_dormant_detector_cls()
            if DormantDetectorCls and decision.options and len(decision.options) > 1:
                try:
                    detector = DormantDetectorCls(session, user_id)
                    candidates_created = await detector.create_candidate_decision_nodes(
                        decision_id=decision_id,
                        options=decision.options,
                        chosen_option=decision.agent_decision,
                        created_at=datetime.fromisoformat(created_at),
                    )
                    if candidates_created:
                        logger.debug(
                            f"Created {candidates_created} CandidateDecision nodes "
                            f"for decision {decision_id}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to create CandidateDecision nodes: {e}")

        # ---------------------------------------------------------------
        # Part 4.1: Wire CodeEntity/AFFECTS edges from tool-call file paths
        # ---------------------------------------------------------------
        # If the decision has tool_file_paths (extracted from ToolCall inputs
        # during episode segmentation), create CodeEntity nodes and AFFECTS edges.
        # These have confidence=1.0 (ground-truth from tool calls, not NL matching).
        tool_file_paths = getattr(decision, "_tool_file_paths", None) or []
        if tool_file_paths:
            git_svc_tuple = _get_git_service()
            if git_svc_tuple:
                get_git_svc_fn, create_code_entity_fn, create_affects_fn = git_svc_tuple
                git_svc = get_git_svc_fn()
                if git_svc:
                    affects_session = await get_neo4j_session()
                    async with affects_session:
                        for file_path in tool_file_paths:
                            try:
                                import os
                                if not isinstance(file_path, str) or not file_path.strip():
                                    continue
                                # Infer language from extension
                                ext = os.path.splitext(file_path)[-1].lower()
                                lang_map = {
                                    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
                                    ".js": "javascript", ".jsx": "javascript", ".go": "go",
                                    ".rs": "rust", ".java": "java", ".rb": "ruby",
                                    ".cpp": "cpp", ".c": "c", ".cs": "csharp",
                                }
                                language = lang_map.get(ext, "unknown")
                                await create_code_entity_fn(
                                    affects_session,
                                    file_path=file_path,
                                    language=language,
                                    user_id=user_id,
                                )
                                await create_affects_fn(
                                    affects_session,
                                    decision_id=decision_id,
                                    file_path=file_path,
                                    confidence=1.0,
                                    user_id=user_id,
                                )
                            except Exception as e:
                                logger.debug(f"Failed to create CodeEntity for {file_path}: {e}")

        # ---------------------------------------------------------------
        # Part 8: Fire-and-forget cross-user contradiction scan
        # ---------------------------------------------------------------
        if decision_project and user_id != "anonymous":
            try:
                import asyncio as _asyncio2
                from services.notifications import (
                    CrossUserContradictionScanner,
                    get_notification_service,
                )
                _scan_session = await get_neo4j_session()
                notif_svc = get_notification_service()
                scanner = CrossUserContradictionScanner(_scan_session, notif_svc)
                _asyncio2.ensure_future(
                    scanner.scan_after_save(
                        new_decision_id=decision_id,
                        new_decision={
                            "trigger": decision.trigger,
                            "agent_decision": decision.agent_decision,
                            "agent_rationale": decision.agent_rationale,
                        },
                        user_id=user_id,
                        project_name=decision_project,
                    )
                )
            except Exception as e:
                logger.debug(f"Cross-user contradiction scan setup failed: {e}")

        # ---------------------------------------------------------------
        # Part 12: Fire-and-forget Datadog event for new decision
        # ---------------------------------------------------------------
        dd_fn = _get_datadog_integration()
        if dd_fn:
            try:
                import asyncio
                dd_integration = dd_fn()
                asyncio.ensure_future(
                    dd_integration.post_decision_event(
                        decision_id=decision_id,
                        trigger=decision.trigger,
                        decision_text=decision.agent_decision,
                        project_name=decision_project or "default",
                        scope=decision_scope_val,
                    )
                )
            except Exception:
                pass  # Datadog is always fire-and-forget

        return decision_id

    async def _create_temporal_relationships(
        self,
        session,
        decision_id: str,
        turn_index: int,
        user_id: str,
        project_name: str | None,
    ) -> None:
        """Create temporal relationships (FOLLOWS/PRECEDES) based on turn_index (RQ1.3).
        
        Args:
            session: Neo4j session
            decision_id: ID of the newly created decision
            turn_index: Turn index of this decision
            user_id: User ID for filtering
            project_name: Optional project name for filtering
        """
        from config import get_settings
        
        settings = get_settings()
        if not settings.temporal_reasoning_enabled:
            return
        
        # Find decisions from the same conversation (same project, same user)
        # that happened before (lower turn_index)
        project_filter = "AND d_old.project_name = $project_name" if project_name else ""
        
        # Create PRECEDES relationships: older decisions precede this new decision
        await session.run(
            f"""
            MATCH (d_new:DecisionTrace {{id: $decision_id}})
            MATCH (d_old:DecisionTrace)
            WHERE d_old.user_id = $user_id
              AND d_old.turn_index IS NOT NULL
              AND d_old.turn_index < $turn_index
              {project_filter}
              AND d_old.id <> $decision_id
            MERGE (d_old)-[:PRECEDES]->(d_new)
            """,
            decision_id=decision_id,
            turn_index=turn_index,
            user_id=user_id,
            project_name=project_name,
        )
        
        # Create FOLLOWS relationships: this new decision follows older decisions
        await session.run(
            f"""
            MATCH (d_new:DecisionTrace {{id: $decision_id}})
            MATCH (d_old:DecisionTrace)
            WHERE d_old.user_id = $user_id
              AND d_old.turn_index IS NOT NULL
              AND d_old.turn_index < $turn_index
              {project_filter}
              AND d_old.id <> $decision_id
            MERGE (d_new)-[:FOLLOWS]->(d_old)
            """,
            decision_id=decision_id,
            turn_index=turn_index,
            user_id=user_id,
            project_name=project_name,
        )
        
        logger.debug(
            f"Created temporal relationships for decision {decision_id} at turn {turn_index}"
        )

    async def _link_similar_decisions(
        self,
        session,
        decision_id: str,
        embedding: list[float],
        user_id: str,
    ):
        """Find semantically similar decisions and create SIMILAR_TO edges.

        Only compares within the same user's decisions for multi-tenant isolation.
        Uses configurable similarity threshold from settings.
        """
        try:
            # Use Neo4j vector search to find similar decisions within user scope
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE d.id <> $id AND d.embedding IS NOT NULL
                  AND (d.user_id = $user_id OR d.user_id IS NULL)
                WITH d, gds.similarity.cosine(d.embedding, $embedding) AS similarity
                WHERE similarity > $threshold
                RETURN d.id AS similar_id, similarity
                ORDER BY similarity DESC
                LIMIT 5
                """,
                id=decision_id,
                embedding=embedding,
                threshold=self.similarity_threshold,
                user_id=user_id,
            )

            records = [r async for r in result]

            for record in records:
                similar_id = record["similar_id"]
                similarity = record["similarity"]

                # Determine confidence tier
                confidence_tier = (
                    "high"
                    if similarity >= self.high_confidence_threshold
                    else "moderate"
                )

                await session.run(
                    """
                    MATCH (d1:DecisionTrace {id: $id1})
                    MATCH (d2:DecisionTrace {id: $id2})
                    MERGE (d1)-[r:SIMILAR_TO]->(d2)
                    SET r.score = $score, r.confidence_tier = $tier
                    """,
                    id1=decision_id,
                    id2=similar_id,
                    score=similarity,
                    tier=confidence_tier,
                )
                logger.info(
                    f"Linked similar decision {similar_id} (score: {similarity:.3f}, tier: {confidence_tier})"
                )

        except (ClientError, DatabaseError) as e:
            # GDS library may not be installed, fall back to manual calculation
            logger.debug(f"Vector search failed (GDS may not be installed): {e}")
            await self._link_similar_decisions_manual(
                session, decision_id, embedding, user_id
            )

    async def _link_similar_decisions_manual(
        self,
        session,
        decision_id: str,
        embedding: list[float],
        user_id: str,
    ):
        """Fallback: Calculate similarity manually without GDS.

        Only compares within the same user's decisions.
        """
        try:
            result = await session.run(
                """
                MATCH (d:DecisionTrace)
                WHERE d.id <> $id AND d.embedding IS NOT NULL
                  AND (d.user_id = $user_id OR d.user_id IS NULL)
                RETURN d.id AS other_id, d.embedding AS other_embedding
                """,
                id=decision_id,
                user_id=user_id,
            )

            records = [r async for r in result]

            for record in records:
                other_id = record["other_id"]
                other_embedding = record["other_embedding"]

                # Calculate cosine similarity
                similarity = cosine_similarity(embedding, other_embedding)

                if similarity > self.similarity_threshold:
                    # Determine confidence tier
                    confidence_tier = (
                        "high"
                        if similarity >= self.high_confidence_threshold
                        else "moderate"
                    )

                    await session.run(
                        """
                        MATCH (d1:DecisionTrace {id: $id1})
                        MATCH (d2:DecisionTrace {id: $id2})
                        MERGE (d1)-[r:SIMILAR_TO]->(d2)
                        SET r.score = $score, r.confidence_tier = $tier
                        """,
                        id1=decision_id,
                        id2=other_id,
                        score=similarity,
                        tier=confidence_tier,
                    )
                    logger.info(
                        f"Linked similar decision {other_id} (score: {similarity:.3f}, tier: {confidence_tier})"
                    )

        except (ClientError, DatabaseError) as e:
            logger.error(f"Manual similarity linking failed: {e}")

    async def _create_temporal_chains(self, session, decision_id: str, user_id: str):
        """Create INFLUENCED_BY edges based on shared entities and temporal order.

        Only creates chains within the same user's decisions.
        """
        try:
            # Find older decisions that share entities with this one (within user scope)
            await session.run(
                """
                MATCH (d_new:DecisionTrace {id: $new_id})
                MATCH (d_old:DecisionTrace)-[:INVOLVES]->(e:Entity)<-[:INVOLVES]-(d_new)
                WHERE d_old.id <> d_new.id AND d_old.created_at < d_new.created_at
                  AND (d_old.user_id = $user_id OR d_old.user_id IS NULL)
                WITH d_new, d_old, count(DISTINCT e) AS shared_count
                WHERE shared_count >= 2
                MERGE (d_new)-[r:INFLUENCED_BY]->(d_old)
                SET r.shared_entities = shared_count
                """,
                new_id=decision_id,
                user_id=user_id,
            )
            logger.debug(f"Created temporal chains for decision {decision_id}")
        except (ClientError, DatabaseError) as e:
            logger.error(f"Temporal chain creation failed: {e}")


# Singleton instance
_extractor: Optional[DecisionExtractor] = None


def get_extractor() -> DecisionExtractor:
    """Get the decision extractor singleton."""
    global _extractor
    if _extractor is None:
        _extractor = DecisionExtractor()
    return _extractor
