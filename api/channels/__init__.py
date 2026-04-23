"""Route helpers for the Channels panel."""

from __future__ import annotations

from urllib.parse import parse_qs

from api.channels.base import ensure_channels_allowed, provider_payload
from api.channels.feishu import FEISHU_PROVIDER
from api.channels.gateway_control import (
    GatewayControlFailed,
    GatewayControlUnavailable,
    run_gateway_action,
)
from api.channels.gateway_view import get_gateway_status
from api.channels.telegram import TELEGRAM_PROVIDER
from api.channels.weixin import WEIXIN_PROVIDER
from api.helpers import bad, j
from api.profiles import get_active_hermes_home, get_active_profile_name

PROVIDERS = {
    provider.key: provider
    for provider in (TELEGRAM_PROVIDER, FEISHU_PROVIDER, WEIXIN_PROVIDER)
}


def _provider_for(key: str):
    provider = PROVIDERS.get((key or "").strip().lower())
    if provider is None:
        raise KeyError(key)
    return provider


def _channels_payload() -> dict:
    payload = provider_payload(
        get_active_profile_name(),
        str(get_active_hermes_home()),
        PROVIDERS.values(),
    )
    payload["gateway"] = get_gateway_status()
    return payload


def handle_get(handler, parsed) -> bool:
    if parsed.path == "/api/gateway/status":
        if not ensure_channels_allowed(handler):
            return True
        return j(handler, get_gateway_status())

    if parsed.path == "/api/channels":
        if not ensure_channels_allowed(handler):
            return True
        return j(handler, _channels_payload())

    if parsed.path == "/api/channels/weixin/qr/stream":
        if not ensure_channels_allowed(handler):
            return True
        poll_token = parse_qs(parsed.query).get("poll_token", [""])[0]
        if not poll_token:
            return bad(handler, "poll_token is required")
        return WEIXIN_PROVIDER.handle_qr_stream(handler, poll_token)

    parts = [part for part in parsed.path.split("/") if part]
    if parts[:2] != ["api", "channels"] or len(parts) != 3:
        return False

    if not ensure_channels_allowed(handler):
        return True

    try:
        provider = _provider_for(parts[2])
    except KeyError:
        return bad(handler, "Unknown channel.", 404)
    return j(handler, provider.summary())


def handle_post(handler, parsed, body: dict) -> bool:
    if parsed.path == "/api/gateway/start":
        if not ensure_channels_allowed(handler):
            return True
        try:
            return j(handler, run_gateway_action("start"))
        except GatewayControlUnavailable as exc:
            return bad(handler, str(exc), 409)
        except GatewayControlFailed as exc:
            return bad(handler, str(exc), 500)

    if parsed.path == "/api/gateway/restart":
        if not ensure_channels_allowed(handler):
            return True
        try:
            return j(handler, run_gateway_action("restart"))
        except GatewayControlUnavailable as exc:
            return bad(handler, str(exc), 409)
        except GatewayControlFailed as exc:
            return bad(handler, str(exc), 500)

    if parsed.path == "/api/channels/weixin/qr/start":
        if not ensure_channels_allowed(handler):
            return True
        try:
            return j(handler, WEIXIN_PROVIDER.start_qr())
        except (ValueError, RuntimeError) as exc:
            return bad(handler, str(exc))

    parts = [part for part in parsed.path.split("/") if part]
    if parts[:2] != ["api", "channels"] or len(parts) != 4:
        return False

    if not ensure_channels_allowed(handler):
        return True

    try:
        provider = _provider_for(parts[2])
    except KeyError:
        return bad(handler, "Unknown channel.", 404)

    action = parts[3]
    try:
        if action == "save":
            return j(handler, provider.save(body))
        if action == "test":
            return j(handler, provider.test(body))
    except (ValueError, RuntimeError) as exc:
        return bad(handler, str(exc))
    return False


def handle_delete(handler, parsed) -> bool:
    parts = [part for part in parsed.path.split("/") if part]
    if parts[:2] != ["api", "channels"] or len(parts) != 3:
        return False

    if not ensure_channels_allowed(handler):
        return True

    try:
        provider = _provider_for(parts[2])
    except KeyError:
        return bad(handler, "Unknown channel.", 404)
    return j(handler, {"ok": True, "channel": provider.delete()})
