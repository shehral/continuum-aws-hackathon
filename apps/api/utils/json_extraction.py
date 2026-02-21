"""Robust JSON extraction from LLM responses.

Handles various LLM output formats including:
- Pure JSON
- Markdown code blocks (```json...``` or ```...```)
- JSON embedded in text
- Dict-to-list conversion for single decision objects
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)

# Directory for logging raw LLM responses
# Use absolute path from the API directory
import os
_api_dir = Path(__file__).parent.parent
LLM_RESPONSE_LOG_DIR = _api_dir / "logs" / "llm_responses"
LLM_RESPONSE_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _log_raw_response(response: str, context: str = "extraction") -> None:
    """Log raw LLM response to a file for debugging.
    
    Args:
        response: The raw LLM response text
        context: Context identifier (e.g., "decision_extraction", "type_detection")
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{context}_{timestamp}.txt"
        filepath = LLM_RESPONSE_LOG_DIR / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Context: {context}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Response Length: {len(response)} chars\n")
            f.write("=" * 80 + "\n")
            f.write(response)
            f.write("\n" + "=" * 80 + "\n")
        
        logger.debug(f"Logged raw LLM response to {filepath}")
    except Exception as e:
        logger.warning(f"Failed to log raw LLM response: {e}")


def extract_json_from_response(response: str, context: str = "extraction", expect_list: bool = False) -> Any | None:
    """Extract JSON from an LLM response using multiple strategies.

    Tries the following strategies in order:
    1. Parse as pure JSON
    2. Extract from ```json code blocks
    3. Extract from ``` code blocks (untyped)
    4. Regex fallback for embedded JSON objects/arrays
    5. Dict-to-list conversion if expect_list=True and result is a dict

    Args:
        response: The raw LLM response text
        context: Context identifier for logging (e.g., "decision_extraction")
        expect_list: If True, convert single dict to list [dict]

    Returns:
        Parsed JSON data (dict or list), or None if parsing fails
    """
    if not response:
        return None

    # Log raw response before processing
    _log_raw_response(response, context)

    text = response.strip()

    result = None

    # Strategy 1: Try pure JSON first
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from ```json code blocks
    if result is None:
        json_block_match = re.search(
            r"```json\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE
        )
        if json_block_match:
            try:
                result = json.loads(json_block_match.group(1).strip())
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse ```json block: {e}")

    # Strategy 3: Extract from untyped ``` code blocks
    if result is None:
        generic_block_match = re.search(r"```\s*\n?(.*?)\n?```", text, re.DOTALL)
        if generic_block_match:
            try:
                result = json.loads(generic_block_match.group(1).strip())
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse ``` block: {e}")

    # Strategy 4: Regex fallback - find JSON object or array in text
    if result is None:
        # Look for JSON arrays first (more specific)
        json_array_match = re.search(r"\[[^\]]*(?:\{[^\}]*\}[^\]]*)*\]", text, re.DOTALL)
        if json_array_match:
            try:
                result = json.loads(json_array_match.group(0))
            except json.JSONDecodeError:
                pass

    # Strategy 5: Look for JSON objects (less specific, try after arrays)
    if result is None:
        # Improved regex for nested objects
        json_object_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if json_object_match:
            try:
                result = json.loads(json_object_match.group(0))
            except json.JSONDecodeError:
                pass

    # Strategy 6: Dict-to-list conversion if expect_list=True
    if result is not None and expect_list and isinstance(result, dict):
        logger.info(f"Converting single dict to list for context: {context}")
        result = [result]
    elif result is not None and expect_list and not isinstance(result, list):
        # Log unexpected type when expect_list=True
        logger.warning(
            f"Expected list for context {context}, but got {type(result)}: {result}"
        )

    # All strategies failed
    if result is None:
        logger.warning(
            f"Failed to extract JSON from response. "
            f"Response length: {len(text)}, "
            f"First 200 chars: {text[:200]!r}"
        )
        return None

    # Debug logging for the return value
    if expect_list:
        logger.debug(
            f"extract_json_from_response returning {type(result)} for context {context}, "
            f"expect_list={expect_list}"
        )

    return result


def extract_json_or_default(response: str, default: Any) -> Any:
    """Extract JSON from response, returning default on failure.

    Args:
        response: The raw LLM response text
        default: Value to return if extraction fails

    Returns:
        Parsed JSON data or the default value
    """
    result = extract_json_from_response(response)
    if result is None:
        return default
    return result
