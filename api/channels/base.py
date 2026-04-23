"""Shared provider definitions and HTTP helpers for Channels."""

from __future__ import annotations

import json
import re
import ssl
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from api.channels.env_io import load_env_file, safe_write_env
from api.channels.redaction import UNCHANGED, merge_form_value, redact_secret
from api.auth import is_auth_enabled
from api.helpers import j

_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class ChannelField:
    name: str
    env: str
    label: str
    label_key: str
    type: str = "text"
    placeholder: str = ""
    placeholder_key: str = ""
    required: bool = False
    secret: bool = False
    default: str = ""
    options: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "secret": self.secret,
            "label": self.label,
            "label_key": self.label_key,
        }
        if self.placeholder or self.placeholder_key:
            data["placeholder"] = self.placeholder
            data["placeholder_key"] = self.placeholder_key
        if self.default:
            data["default"] = self.default
        if self.options:
            data["options"] = list(self.options)
        return data


def ensure_channels_allowed(handler) -> bool:
    """Backstop auth-disabled mode for the Channels surface.

    ``server.py`` still calls ``check_auth()`` at every request entry, and that is the
    real session/cookie enforcement path when password auth is enabled.

    The gap this helper closes is the auth-disabled case: ``check_auth()`` returns
    ``True`` when auth is off, but the Channels panel should remain unavailable unless
    password auth is explicitly enabled. Do not treat this helper as a full replacement
    for the server entry auth checks.
    """

    if is_auth_enabled():
        return True
    j(handler, {"error": "channels_require_auth_enabled"}, status=403)
    return False


def _validate_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are allowed.")
    if not parsed.netloc:
        raise ValueError("URL must include a hostname.")
    return url.rstrip("/")


def json_request(
    url: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 15.0,
) -> Any:
    """Fetch JSON from a validated HTTP(S) endpoint."""

    validated_url = _validate_http_url(url)
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = Request(validated_url, data=body, headers=req_headers, method=method)
    try:
        with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as response:  # nosec B310
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(_format_remote_error(exc.code, raw)) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", None) or str(exc)
        raise RuntimeError(f"Network error: {reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Remote service returned invalid JSON.") from exc


def _format_remote_error(status: int, raw: str) -> str:
    detail = raw.strip()
    try:
        payload = json.loads(detail) if detail else {}
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        detail = str(
            payload.get("description")
            or payload.get("msg")
            or payload.get("message")
            or payload.get("error")
            or detail
        ).strip()
    return f"{status} {detail or 'Remote request failed.'}"


class ChannelProvider:
    key = ""
    title = ""
    description = ""
    warning = ""
    warning_key = ""
    fields: Sequence[ChannelField] = ()
    supports_test = False
    supports_qr = False

    def schema(self) -> list[dict[str, Any]]:
        return [field.to_dict() for field in self.fields]

    def load_env(self) -> dict[str, str]:
        return load_env_file()

    def _field_value(self, field: ChannelField, env_values: Mapping[str, str]) -> str:
        raw = str(env_values.get(field.env, "") or "").strip()
        if field.secret:
            return redact_secret(raw)
        if raw:
            return raw
        return field.default

    def _raw_field_value(self, field: ChannelField, env_values: Mapping[str, str]) -> str:
        raw = str(env_values.get(field.env, "") or "").strip()
        if raw:
            return raw
        return field.default

    def configured(self, env_values: Mapping[str, str]) -> bool:
        for field in self.fields:
            if field.required and not str(env_values.get(field.env, "") or "").strip():
                return False
        return True

    def summary(self, env_values: Mapping[str, str] | None = None) -> dict[str, Any]:
        env_values = env_values or self.load_env()
        configured = self.configured(env_values)
        payload = {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "warning": self.warning,
            "warning_key": self.warning_key,
            "configured": configured,
            "schema": self.schema(),
            "values": {
                field.name: self._field_value(field, env_values)
                for field in self.fields
            },
            "supports_test": self.supports_test,
            "supports_qr": self.supports_qr,
            "status": {
                "level": "ok" if configured else "idle",
                "key": "channels_status_configured" if configured else "channels_status_not_configured",
                "text": "Configured" if configured else "Not configured",
            },
        }
        return self.augment_summary(payload, env_values)

    def augment_summary(
        self,
        payload: dict[str, Any],
        env_values: Mapping[str, str],
    ) -> dict[str, Any]:
        return payload

    def merge_payload(self, payload: Mapping[str, Any]) -> dict[str, str]:
        env_values = self.load_env()
        merged: dict[str, str] = {}
        for field in self.fields:
            current = str(env_values.get(field.env, "") or "").strip()
            value = merge_form_value(payload.get(field.name), current, secret=field.secret)
            if value is UNCHANGED:
                merged[field.name] = current or field.default
            elif value is None:
                merged[field.name] = ""
            else:
                merged[field.name] = str(value)
        return merged

    def save(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        env_values = self.load_env()
        updates: dict[str, str | None] = {}
        for field in self.fields:
            current = str(env_values.get(field.env, "") or "").strip()
            merged = merge_form_value(payload.get(field.name), current, secret=field.secret)
            if merged is UNCHANGED:
                continue
            updates[field.env] = merged
        if updates:
            safe_write_env(updates)
        latest = self.load_env()
        self.after_save(latest)
        return self.summary(latest)

    def after_save(self, env_values: Mapping[str, str]) -> None:
        return None

    def delete(self) -> dict[str, Any]:
        before = self.load_env()
        safe_write_env({field.env: None for field in self.fields})
        self.after_delete(before)
        return self.summary(self.load_env())

    def after_delete(self, env_values: Mapping[str, str]) -> None:
        return None

    def test(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Channel test is not supported.")


def provider_payload(
    profile_name: str,
    hermes_home: str,
    providers: Iterable[ChannelProvider],
) -> dict[str, Any]:
    return {
        "profile": {
            "name": profile_name,
            "hermes_home": hermes_home,
        },
        "channels": [provider.summary() for provider in providers],
    }
