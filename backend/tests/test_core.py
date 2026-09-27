from app.core.security import reporter_hash, secrets_match
from app.core.text import redact


def test_redaction_removes_phones_emails_and_id_numbers():
    text = "Call me on +91 98450 12345 or mail ravi@example.com, Aadhaar 1234 5678 9012. No water for 3 days."
    out = redact(text)
    assert "98450" not in out and "example.com" not in out and "9012" not in out
    assert "No water for 3 days." in out


def test_reporter_hash_is_stable_and_channel_specific():
    assert reporter_hash("telegram", "42") == reporter_hash("telegram", "42")
    assert reporter_hash("telegram", "42") != reporter_hash("whatsapp", "42")
    assert "42" not in reporter_hash("telegram", "42")


def test_secret_checks_fail_closed():
    assert not secrets_match("anything", "")
    assert not secrets_match(None, "expected")
    assert not secrets_match("wrong", "expected")
    assert secrets_match("expected", "expected")
