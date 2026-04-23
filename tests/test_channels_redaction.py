from api.channels.redaction import MASK, UNCHANGED, merge_form_value, redact_secret


def test_redact_secret_masks_short_values():
    assert redact_secret("secret") == MASK


def test_redact_secret_keeps_edges_for_long_values():
    assert redact_secret("abcdefghijklm") == "abc***jklm"


def test_merge_form_value_keeps_secret_when_empty():
    assert merge_form_value("", "stored-secret", secret=True) is UNCHANGED


def test_merge_form_value_keeps_secret_when_masked():
    assert merge_form_value("abc***1234", "stored-secret", secret=True) is UNCHANGED


def test_merge_form_value_replaces_secret_when_new_value_present():
    assert merge_form_value("new-secret", "stored-secret", secret=True) == "new-secret"


def test_merge_form_value_deletes_non_secret_when_blank():
    assert merge_form_value("", "current", secret=False) is None


def test_merge_form_value_replaces_non_secret_when_new_value_present():
    assert merge_form_value("next", "current", secret=False) == "next"
