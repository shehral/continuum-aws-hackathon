"""Log sanitization utilities for sensitive data protection (SEC-015).

This module provides functions to sanitize PII and sensitive data before logging.
"""

import hashlib
import re
from typing import Any

# Patterns for sensitive data detection
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*\b")
API_KEY_PATTERN = re.compile(
    r'\b(?:api[_-]?key|apikey|bearer|token|secret|password|credential)[\s:=]+[\'"]?([^\s\'"]+)',
    re.IGNORECASE,
)
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
)

# Fields that should always be masked when found in dicts
SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "api-key",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "auth",
        "credential",
        "credentials",
        "private_key",
        "secret_key",
        "client_secret",
        "api_secret",
        "bearer",
    }
)


def hash_identifier(value: str, length: int = 8) -> str:
    """Create a short hash of a value for correlation without exposing PII.

    Args:
        value: The value to hash
        length: Number of characters in the hash (default 8)

    Returns:
        Short hash string prefixed with 'h:'
    """
    if not value:
        return "h:empty"
    hashed = hashlib.sha256(value.encode()).hexdigest()[:length]
    return f"h:{hashed}"


def mask_email(email: str) -> str:
    """Mask an email address while preserving domain for debugging.

    Example: user@example.com -> u***@example.com
    """
    if "@" not in email:
        return "***@***"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "***"
    return f"{masked_local}@{domain}"


def mask_ip(ip: str) -> str:
    """Mask an IP address, preserving first octet for network debugging.

    Example: 192.168.1.100 -> 192.***.***.**
    """
    parts = ip.split(".")
    if len(parts) != 4:
        return "***.***.***.***"
    return f"{parts[0]}.***.***.**"


def mask_token(token: str) -> str:
    """Mask a token, showing only first and last 4 characters.

    Example: eyJhbGciOiJIUzI1... -> eyJh...last4
    """
    if len(token) <= 10:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def sanitize_string(text: str) -> str:
    """Sanitize a string by replacing detected sensitive patterns.

    Args:
        text: The text to sanitize

    Returns:
        Sanitized text with sensitive data masked
    """
    if not isinstance(text, str):
        return str(text)

    result = text

    # Mask JWTs
    result = JWT_PATTERN.sub("[MASKED_JWT]", result)

    # Mask emails
    for match in EMAIL_PATTERN.finditer(result):
        email = match.group()
        result = result.replace(email, mask_email(email))

    # Mask IPs (be careful not to mask version numbers like 1.2.3)
    for match in IP_PATTERN.finditer(result):
        ip = match.group()
        # Only mask if all octets are valid IP ranges
        parts = ip.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            result = result.replace(ip, mask_ip(ip))

    # Mask API keys and tokens in common formats
    def mask_api_key(m):
        prefix = m.group(0).split(m.group(1))[0]
        return prefix + "[MASKED]"

    result = API_KEY_PATTERN.sub(mask_api_key, result)

    return result


def sanitize_dict(
    data: dict[str, Any], depth: int = 0, max_depth: int = 10
) -> dict[str, Any]:
    """Recursively sanitize a dictionary, masking sensitive fields.

    Args:
        data: The dictionary to sanitize
        depth: Current recursion depth
        max_depth: Maximum recursion depth to prevent infinite loops

    Returns:
        Sanitized dictionary
    """
    if depth > max_depth:
        return {"_truncated": "max depth exceeded"}

    result = {}
    for key, value in data.items():
        key_lower = key.lower()

        # Mask sensitive fields entirely
        if key_lower in SENSITIVE_FIELDS:
            result[key] = "[MASKED]"
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value, depth + 1, max_depth)
        elif isinstance(value, list):
            result[key] = sanitize_list(value, depth + 1, max_depth)
        elif isinstance(value, str):
            result[key] = sanitize_string(value)
        else:
            result[key] = value

    return result


def sanitize_list(data: list, depth: int = 0, max_depth: int = 10) -> list:
    """Recursively sanitize a list.

    Args:
        data: The list to sanitize
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        Sanitized list
    """
    if depth > max_depth:
        return ["_truncated: max depth exceeded"]

    result = []
    for item in data:
        if isinstance(item, dict):
            result.append(sanitize_dict(item, depth + 1, max_depth))
        elif isinstance(item, list):
            result.append(sanitize_list(item, depth + 1, max_depth))
        elif isinstance(item, str):
            result.append(sanitize_string(item))
        else:
            result.append(item)

    return result


def sanitize_user_id(user_id: str) -> str:
    """Sanitize a user ID for logging.

    Returns a hashed version that can be used for correlation
    without exposing the actual user ID.

    Args:
        user_id: The user ID to sanitize

    Returns:
        Hashed user ID for logging
    """
    if not user_id or user_id == "anonymous":
        return "anonymous"
    return hash_identifier(user_id)


def sanitize_for_logging(data: Any) -> Any:
    """Main entry point for sanitizing any data before logging.

    Args:
        data: Any data to sanitize (str, dict, list, or other)

    Returns:
        Sanitized data safe for logging
    """
    if isinstance(data, dict):
        return sanitize_dict(data)
    elif isinstance(data, list):
        return sanitize_list(data)
    elif isinstance(data, str):
        return sanitize_string(data)
    else:
        return data
