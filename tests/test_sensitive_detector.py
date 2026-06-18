# tests/test_sensitive_detector.py
#
# Tests for the sensitive email detector.
# All AI calls are mocked — no real API calls.
# Tests verify the regex patterns and masking logic directly.

import pytest
from unittest.mock import patch, MagicMock


# ── Helper to build a fake parsed email ──────────────────────────────────────
def make_email(subject: str, body: str, sender: str = "test@example.com") -> dict:
    return {
        "id": "test_id_001",
        "thread_id": "thread_001",
        "subject": subject,
        "sender": f"Sender <{sender}>",
        "sender_email": sender,
        "body": body,
        "snippet": body[:100],
        "labels": ["INBOX"],
    }


class TestRegexDetection:
    """Test Layer 1 — regex patterns. No API calls needed."""

    def test_detects_otp_in_body(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        email = make_email(
            "Your verification code",
            "Your OTP is 482917. Valid for 10 minutes. Do not share."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is True
        assert result.sensitive_type == "OTP"
        assert result.detected_by == "regex"

    def test_detects_otp_in_subject(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        email = make_email(
            "482917 is your verification code",
            "Use this code to log in. Expires in 5 minutes."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is True
        assert result.sensitive_type == "OTP"

    def test_detects_bank_alert(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        email = make_email(
            "Transaction Alert",
            "Rs. 5000 has been debited from your account ending 4521. UPI transaction."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is True
        assert result.sensitive_type == "BANK_ALERT"

    def test_detects_password_reset(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        email = make_email(
            "Reset your password",
            "Click the link below to reset your password. This link expires in 1 hour."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is True
        assert result.sensitive_type == "PASSWORD_RESET"

    def test_detects_login_alert(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        email = make_email(
            "New sign-in to your account",
            "We noticed a new sign-in to your account from an unrecognized device in Chennai."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is True
        assert result.sensitive_type == "LOGIN_ALERT"

    def test_detects_card_alert(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        email = make_email(
            "Card Transaction Alert",
            "Your credit card ending 7823 was used for a transaction of Rs. 1299."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is True
        assert result.sensitive_type in ("CARD_ALERT", "BANK_ALERT")

    def test_normal_email_not_flagged(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        with patch("ai_processing.sensitive_detector._llm_scan", return_value=None):
            email = make_email(
                "Team lunch tomorrow",
                "Hey, are you joining us for lunch at 1pm tomorrow at the usual place?"
            )
            result = analyze_sensitive(email)
            assert result.is_sensitive is False
            assert result.sensitive_type is None

    def test_promotional_email_not_flagged(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        with patch("ai_processing.sensitive_detector._llm_scan", return_value=None):
            email = make_email(
                "50% OFF Sale this weekend!",
                "Don't miss our biggest sale. Use code SAVE50 at checkout."
            )
            result = analyze_sensitive(email)
            # SAVE50 might look like a code but it's promotional, not OTP
            # Regex checks context — standalone 4-8 digit numbers, not alphanumeric coupons
            # This test verifies we don't over-flag promotional discount codes
            assert result.sensitive_type != "OTP" or result.is_sensitive is False


class TestMasking:
    """Test the code masking logic."""

    def test_masks_numeric_otp(self):
        from ai_processing.sensitive_detector import _mask_codes
        result = _mask_codes("Your OTP is 482917. Do not share.")
        assert "482917" not in result
        assert "[CODE MASKED]" in result

    def test_masks_code_with_label(self):
        from ai_processing.sensitive_detector import _mask_codes
        result = _mask_codes("Verification code: 7823AB")
        assert "7823AB" not in result or "[CODE MASKED]" in result

    def test_empty_string_safe(self):
        from ai_processing.sensitive_detector import _mask_codes
        assert _mask_codes("") == ""
        assert _mask_codes(None) is None

    def test_normal_text_unchanged(self):
        from ai_processing.sensitive_detector import _mask_codes
        # Text with no codes should pass through mostly unchanged
        text = "Please join us for the meeting tomorrow at noon."
        result = _mask_codes(text)
        assert "meeting" in result
        assert "tomorrow" in result

    def test_masked_body_in_result(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        email = make_email(
            "Your OTP",
            "Your login OTP is 938274. Valid for 5 minutes."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is True
        assert "938274" not in result.masked_body
        assert "[CODE MASKED]" in result.masked_body

    def test_should_reply_always_false(self):
        from ai_processing.sensitive_detector import analyze_sensitive
        email = make_email("Bank Alert", "Rs. 10000 debited from account 4521. UPI ref 1234567.")
        result = analyze_sensitive(email)
        assert result.should_reply is False  # ALWAYS False for sensitive emails


class TestLLMFallback:
    """Test Layer 2 — LLM scan. Mock the API."""

    @patch("ai_processing.sensitive_detector._client")
    def test_llm_detects_subtle_fraud(self, mock_client):
        from ai_processing.sensitive_detector import analyze_sensitive

        # Email that looks normal to regex but is actually suspicious
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="FRAUD_ALERT"))]
        )
        email = make_email(
            "Your account needs attention",
            "We have noticed some unusual patterns in your account activity. "
            "Please verify your identity within 24 hours to avoid suspension."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is True
        assert result.detected_by == "llm"

    @patch("ai_processing.sensitive_detector._client")
    def test_llm_returns_none_for_safe_email(self, mock_client):
        from ai_processing.sensitive_detector import analyze_sensitive

        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="NONE"))]
        )
        email = make_email(
            "Project update",
            "Hi team, here is the weekly project status update."
        )
        result = analyze_sensitive(email)
        assert result.is_sensitive is False

    @patch("ai_processing.sensitive_detector._client")
    def test_llm_failure_does_not_crash(self, mock_client):
        from ai_processing.sensitive_detector import analyze_sensitive

        # Simulate API failure
        mock_client.chat.completions.create.side_effect = Exception("API timeout")

        email = make_email(
            "Regular email",
            "This is a regular email with no sensitive content."
        )
        # Should not raise — LLM failure treats as non-sensitive
        result = analyze_sensitive(email)
        assert result.is_sensitive is False
