"""Tests for log sanitization utility (SEC-015)."""

from utils.sanitize import (
    hash_identifier,
    mask_email,
    mask_ip,
    mask_token,
    sanitize_dict,
    sanitize_for_logging,
    sanitize_list,
    sanitize_string,
    sanitize_user_id,
)


class TestHashIdentifier:
    """Test identifier hashing."""

    def test_hash_empty_string(self):
        """Empty string should return special marker."""
        assert hash_identifier("") == "h:empty"

    def test_hash_produces_consistent_output(self):
        """Same input should produce same output."""
        result1 = hash_identifier("test@example.com")
        result2 = hash_identifier("test@example.com")
        assert result1 == result2

    def test_hash_different_inputs(self):
        """Different inputs should produce different hashes."""
        result1 = hash_identifier("user1@example.com")
        result2 = hash_identifier("user2@example.com")
        assert result1 != result2

    def test_hash_has_prefix(self):
        """Hash should be prefixed with 'h:'."""
        result = hash_identifier("test")
        assert result.startswith("h:")


class TestMaskEmail:
    """Test email masking."""

    def test_mask_normal_email(self):
        """Should mask local part, preserve domain."""
        result = mask_email("user@example.com")
        assert result == "u***@example.com"

    def test_mask_single_char_local(self):
        """Single char local should mask to *."""
        result = mask_email("a@example.com")
        assert result == "*@example.com"

    def test_mask_invalid_email(self):
        """Invalid email should return masked placeholder."""
        result = mask_email("notanemail")
        assert result == "***@***"


class TestMaskIp:
    """Test IP address masking."""

    def test_mask_valid_ip(self):
        """Should preserve first octet, mask rest."""
        result = mask_ip("192.168.1.100")
        assert result == "192.***.***.**"

    def test_mask_invalid_ip(self):
        """Invalid IP should return masked placeholder."""
        result = mask_ip("invalid")
        assert result == "***.***.***.***"


class TestMaskToken:
    """Test token masking."""

    def test_mask_long_token(self):
        """Long token should show first and last 4 chars."""
        result = mask_token("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
        # First 4: "eyJh", Last 4: "VCJ9"
        assert result.startswith("eyJh")
        assert result.endswith("VCJ9")
        assert "..." in result

    def test_mask_short_token(self):
        """Short token should be completely masked."""
        result = mask_token("short")
        assert result == "***"


class TestSanitizeString:
    """Test string sanitization."""

    def test_sanitize_jwt_token(self):
        """JWTs should be replaced with marker."""
        text = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c in header"
        result = sanitize_string(text)
        # Should be sanitized (either MASKED_JWT or MASKED)
        assert "eyJhbGci" not in result
        assert "MASKED" in result

    def test_sanitize_email(self):
        """Emails should be masked."""
        text = "User email is user@example.com"
        result = sanitize_string(text)
        assert "u***@example.com" in result
        assert "user@example.com" not in result

    def test_sanitize_ip(self):
        """IP addresses should be masked."""
        text = "Client IP: 192.168.1.100"
        result = sanitize_string(text)
        assert "192.***.***.**" in result
        assert "192.168.1.100" not in result


class TestSanitizeDict:
    """Test dictionary sanitization."""

    def test_mask_password_field(self):
        """Password fields should be masked."""
        data = {"username": "admin", "password": "secret123"}
        result = sanitize_dict(data)
        assert result["username"] == "admin"
        assert result["password"] == "[MASKED]"

    def test_mask_token_field(self):
        """Token fields should be masked."""
        data = {"access_token": "abc123", "data": "visible"}
        result = sanitize_dict(data)
        assert result["access_token"] == "[MASKED]"
        assert result["data"] == "visible"

    def test_nested_sanitization(self):
        """Should sanitize nested dictionaries."""
        data = {"user": {"email": "test@example.com", "password": "secret"}}
        result = sanitize_dict(data)
        assert result["user"]["password"] == "[MASKED]"
        assert "t***@example.com" in result["user"]["email"]

    def test_max_depth(self):
        """Should truncate at max depth."""
        deep = {"a": {"b": {"c": {"d": {"e": "value"}}}}}
        result = sanitize_dict(deep, max_depth=2)
        assert "_truncated" in str(result)


class TestSanitizeList:
    """Test list sanitization."""

    def test_sanitize_list_of_strings(self):
        """Should sanitize strings in list."""
        data = ["user@example.com", "normal"]
        result = sanitize_list(data)
        assert "u***@example.com" in result[0]
        assert result[1] == "normal"

    def test_sanitize_list_of_dicts(self):
        """Should sanitize dicts in list."""
        data = [{"password": "secret"}, {"data": "visible"}]
        result = sanitize_list(data)
        assert result[0]["password"] == "[MASKED]"
        assert result[1]["data"] == "visible"


class TestSanitizeUserId:
    """Test user ID sanitization."""

    def test_anonymous_unchanged(self):
        """Anonymous should stay anonymous."""
        result = sanitize_user_id("anonymous")
        assert result == "anonymous"

    def test_empty_unchanged(self):
        """Empty should return anonymous."""
        result = sanitize_user_id("")
        assert result == "anonymous"

    def test_user_id_hashed(self):
        """Real user IDs should be hashed."""
        result = sanitize_user_id("user-12345-abcde")
        assert result.startswith("h:")
        assert "user-12345" not in result


class TestSanitizeForLogging:
    """Test main sanitization entry point."""

    def test_sanitize_dict(self):
        """Should handle dicts."""
        data = {"password": "secret"}
        result = sanitize_for_logging(data)
        assert result["password"] == "[MASKED]"

    def test_sanitize_list(self):
        """Should handle lists."""
        data = ["user@example.com"]
        result = sanitize_for_logging(data)
        assert "u***@example.com" in result[0]

    def test_sanitize_string(self):
        """Should handle strings."""
        data = "user@example.com"
        result = sanitize_for_logging(data)
        assert "u***@example.com" in result

    def test_passthrough_other_types(self):
        """Should pass through other types unchanged."""
        assert sanitize_for_logging(123) == 123
        assert sanitize_for_logging(True) is True
        assert sanitize_for_logging(None) is None
