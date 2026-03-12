"""Tests for error message redaction utilities."""

from __future__ import annotations

from app.common.redaction_utils import redact_error_message


class TestRedactErrorMessage:
    """redact_error_message should strip quoted content, PII, and truncate."""

    def test_none_passthrough(self):
        assert redact_error_message(None) is None

    def test_empty_string(self):
        assert redact_error_message("") == ""

    def test_normal_error_unchanged(self):
        msg = "Connection refused: could not connect to host"
        assert redact_error_message(msg) == msg

    def test_double_quoted_content_removed(self):
        msg = 'Error processing chunk "The defendant met with counsel on March 5"'
        result = redact_error_message(msg)
        assert "defendant" not in result
        assert "[REDACTED]" in result

    def test_single_quoted_content_removed(self):
        msg = "Error processing chunk 'Privileged communication between attorney and client'"
        result = redact_error_message(msg)
        assert "Privileged" not in result
        assert "[REDACTED]" in result

    def test_ssn_redacted(self):
        msg = "Validation failed for SSN 123-45-6789 in document"
        result = redact_error_message(msg)
        assert "123-45-6789" not in result
        assert "[SSN]" in result

    def test_phone_redacted(self):
        msg = "Invalid phone field: 555-123-4567 found in record"
        result = redact_error_message(msg)
        assert "555-123-4567" not in result
        assert "[PHONE]" in result

    def test_phone_with_parens_redacted(self):
        msg = "Phone: (555) 123-4567 was found"
        result = redact_error_message(msg)
        assert "(555) 123-4567" not in result
        assert "[PHONE]" in result

    def test_email_redacted(self):
        msg = "Failed to send to john.doe@example.com during processing"
        result = redact_error_message(msg)
        assert "john.doe@example.com" not in result
        assert "[EMAIL]" in result

    def test_truncation_at_500_chars(self):
        msg = "A" * 600
        result = redact_error_message(msg)
        assert len(result) == 500
        assert result.endswith("...")

    def test_exactly_500_chars_no_truncation(self):
        msg = "B" * 500
        result = redact_error_message(msg)
        assert result == msg
        assert len(result) == 500

    def test_combined_pii_types(self):
        msg = 'Error: user john@acme.com SSN 111-22-3333 phone 555-867-5309 said "this is privileged"'
        result = redact_error_message(msg)
        assert "john@acme.com" not in result
        assert "111-22-3333" not in result
        assert "555-867-5309" not in result
        assert "privileged" not in result
        assert "[EMAIL]" in result
        assert "[SSN]" in result
        assert "[PHONE]" in result
        assert "[REDACTED]" in result

    def test_nested_quotes(self):
        msg = """Error: "He said 'hello' to them" was invalid"""
        result = redact_error_message(msg)
        # The double-quoted content should be replaced first
        assert "hello" not in result

    def test_document_text_fragment_in_error(self):
        msg = (
            'LLM parse error on chunk: "CONFIDENTIAL - Attorney Work Product. '
            'This memorandum summarizes the key findings of the internal investigation."'
        )
        result = redact_error_message(msg)
        assert "CONFIDENTIAL" not in result
        assert "Attorney Work Product" not in result
        assert "memorandum" not in result

    def test_all_pii_string(self):
        msg = "123-45-6789 john@test.com 555-000-1234"
        result = redact_error_message(msg)
        assert "123-45-6789" not in result
        assert "john@test.com" not in result
        assert "555-000-1234" not in result

    def test_error_with_traceback_style(self):
        msg = "KeyError: 'document_text' in /app/common/llm.py line 42"
        result = redact_error_message(msg)
        # Single-quoted key name gets redacted but the rest stays
        assert "[REDACTED]" in result
        assert "KeyError:" in result
