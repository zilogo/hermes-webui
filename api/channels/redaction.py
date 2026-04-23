"""Helpers for masking and merging channel credentials."""

from __future__ import annotations

MASK = "***"
UNCHANGED = object()


def redact_secret(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 7:
        return MASK
    return f"{raw[:3]}{MASK}{raw[-4:]}"


def looks_masked(value: str | None) -> bool:
    return MASK in str(value or "")


def merge_form_value(
    submitted: object,
    current: str | None,
    *,
    secret: bool = False,
):
    """Merge a browser-submitted value with the stored env value.

    Rules:
    - ``None`` means the field was omitted entirely -> keep current value.
    - Secret fields:
      - empty string keeps the current stored secret
      - masked placeholder input keeps the current stored secret
      - any non-empty unmasked value replaces the secret
    - Non-secret fields:
      - empty string removes the env key
      - non-empty string replaces the env key
    """

    if submitted is None:
        return UNCHANGED

    clean = str(submitted).strip()
    if secret:
        if not clean or looks_masked(clean):
            return UNCHANGED
        return clean

    if not clean:
        return None
    return clean
