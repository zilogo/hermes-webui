"""Weixin channel provider and QR-login flow."""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from api.channels.base import ChannelField, ChannelProvider, json_request
from api.channels.env_io import safe_write_env
from api.helpers import bad
from api.profiles import get_active_hermes_home

try:
    from gateway.platforms.weixin import (
        EP_GET_BOT_QR,
        EP_GET_QR_STATUS,
        ILINK_BASE_URL,
        check_weixin_requirements,
        save_weixin_account,
    )
except Exception:  # pragma: no cover - depends on local hermes-agent install
    EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
    EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"
    ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"

    def check_weixin_requirements() -> bool:  # type: ignore[redefining]
        return False

    def save_weixin_account(*args, **kwargs) -> None:  # type: ignore[redefining]
        return None


_DM_OPTIONS = (
    {"value": "pairing", "label": "Pairing"},
    {"value": "open", "label": "Open"},
    {"value": "allowlist", "label": "Allowlist"},
    {"value": "disabled", "label": "Disabled"},
)

_GROUP_OPTIONS = (
    {"value": "disabled", "label": "Disabled"},
    {"value": "open", "label": "Open"},
    {"value": "allowlist", "label": "Allowlist"},
)

_QR_LOCK = threading.Lock()
_QR_SESSIONS: dict[str, dict[str, Any]] = {}
_QR_MAX_REFRESHES = 3
_QR_SESSION_TTL_SECONDS = 10 * 60


def _account_dir() -> Path:
    return get_active_hermes_home() / "weixin" / "accounts"


def _account_file(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.json"


def _context_file(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.context-tokens.json"


def _load_account(account_id: str) -> dict[str, Any]:
    if not account_id:
        return {}
    path = _account_file(account_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _cleanup_qr_sessions() -> None:
    now = time.time()
    stale = [
        token
        for token, payload in _QR_SESSIONS.items()
        if now - float(payload.get("updated_at") or 0.0) > _QR_SESSION_TTL_SECONDS
    ]
    for token in stale:
        _QR_SESSIONS.pop(token, None)


def _ilink_get(base_url: str, endpoint: str) -> dict[str, Any]:
    response = json_request(
        f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}",
        timeout=35.0,
        headers={
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": str((2 << 16) | (2 << 8) | 0),
        },
    )
    if not isinstance(response, dict):
        raise RuntimeError("Weixin iLink returned an invalid response.")
    return response


class WeixinProvider(ChannelProvider):
    key = "weixin"
    title = "Weixin"
    description = "QR-connect a personal WeChat account via Tencent iLink, then tune DM/group policies."
    warning = "The iLink Weixin adapter is community-supported and may trigger WeChat risk controls."
    warning_key = "channels_weixin_warning"
    supports_qr = True
    fields = (
        ChannelField(
            name="account_id",
            env="WEIXIN_ACCOUNT_ID",
            label="Account ID",
            label_key="channels_field_account_id",
            placeholder="bot-account",
            placeholder_key="channels_placeholder_account_id",
            required=True,
        ),
        ChannelField(
            name="token",
            env="WEIXIN_TOKEN",
            label="Bot token",
            label_key="channels_field_bot_token",
            type="password",
            placeholder="bot-token",
            placeholder_key="channels_placeholder_bot_token",
            required=True,
            secret=True,
        ),
        ChannelField(
            name="base_url",
            env="WEIXIN_BASE_URL",
            label="Base URL",
            label_key="channels_field_base_url",
            type="url",
            default=ILINK_BASE_URL,
        ),
        ChannelField(
            name="dm_policy",
            env="WEIXIN_DM_POLICY",
            label="DM policy",
            label_key="channels_field_dm_policy",
            type="select",
            default="pairing",
            options=_DM_OPTIONS,
        ),
        ChannelField(
            name="allowed_users",
            env="WEIXIN_ALLOWED_USERS",
            label="Allowed users",
            label_key="channels_field_allowed_users",
            placeholder="Comma-separated user IDs",
            placeholder_key="channels_placeholder_allowed_users",
        ),
        ChannelField(
            name="group_policy",
            env="WEIXIN_GROUP_POLICY",
            label="Group policy",
            label_key="channels_field_group_policy",
            type="select",
            default="disabled",
            options=_GROUP_OPTIONS,
        ),
        ChannelField(
            name="group_allowed_users",
            env="WEIXIN_GROUP_ALLOWED_USERS",
            label="Allowed groups",
            label_key="channels_field_group_allowed_users",
            placeholder="Comma-separated group IDs",
            placeholder_key="channels_placeholder_group_allowed_users",
        ),
        ChannelField(
            name="home_channel",
            env="WEIXIN_HOME_CHANNEL",
            label="Home channel",
            label_key="channels_field_home_channel",
            placeholder="Optional user or group ID",
            placeholder_key="channels_placeholder_home_channel",
        ),
    )

    def augment_summary(self, payload: dict[str, Any], env_values: Mapping[str, str]) -> dict[str, Any]:
        runtime_ready = bool(check_weixin_requirements())
        account_id = str(env_values.get("WEIXIN_ACCOUNT_ID", "") or "").strip()
        account = _load_account(account_id)
        payload["runtime_ready"] = runtime_ready
        payload["meta"] = {
            "user_id": str(account.get("user_id") or "").strip(),
            "saved_at": str(account.get("saved_at") or "").strip(),
        }
        if not runtime_ready:
            payload["status"] = {
                "level": "warn",
                "key": "channels_status_missing_runtime",
                "text": "Gateway runtime dependencies are missing.",
            }
        return payload

    def after_save(self, env_values: Mapping[str, str]) -> None:
        account_id = str(env_values.get("WEIXIN_ACCOUNT_ID", "") or "").strip()
        token = str(env_values.get("WEIXIN_TOKEN", "") or "").strip()
        if not account_id or not token:
            return
        base_url = str(env_values.get("WEIXIN_BASE_URL", "") or ILINK_BASE_URL).strip()
        account = _load_account(account_id)
        save_weixin_account(
            str(get_active_hermes_home()),
            account_id=account_id,
            token=token,
            base_url=base_url,
            user_id=str(account.get("user_id") or "").strip(),
        )

    def after_delete(self, env_values: Mapping[str, str]) -> None:
        account_id = str(env_values.get("WEIXIN_ACCOUNT_ID", "") or "").strip()
        if not account_id:
            return
        _account_file(account_id).unlink(missing_ok=True)
        _context_file(account_id).unlink(missing_ok=True)

    def test(self, payload):  # pragma: no cover - UI does not expose this button for Weixin
        values = self.merge_payload(payload)
        if not values.get("account_id") or not values.get("token"):
            raise ValueError("Weixin account ID and token are required.")
        return {
            "ok": True,
            "message": "Weixin credentials look complete. Use QR reconnect if they need rotation.",
        }

    def start_qr(self) -> dict[str, Any]:
        if not check_weixin_requirements():
            raise RuntimeError("Weixin runtime dependencies are missing. Install hermes-agent gateway deps first.")

        response = _ilink_get(ILINK_BASE_URL, f"{EP_GET_BOT_QR}?bot_type=3")
        qrcode_value = str(response.get("qrcode") or "").strip()
        qrcode_url = str(response.get("qrcode_img_content") or "").strip()
        if not qrcode_value:
            raise RuntimeError("Weixin QR response did not include a qrcode token.")

        poll_token = secrets.token_urlsafe(24)
        with _QR_LOCK:
            _cleanup_qr_sessions()
            _QR_SESSIONS[poll_token] = {
                "qrcode_value": qrcode_value,
                "qrcode_url": qrcode_url or qrcode_value,
                "base_url": ILINK_BASE_URL,
                "refreshes": 0,
                "status": "wait",
                "updated_at": time.time(),
                "confirmed": None,
            }
        return {
            "poll_token": poll_token,
            "qrcode_url": qrcode_url or qrcode_value,
        }

    def handle_qr_stream(self, handler, poll_token: str):
        with _QR_LOCK:
            _cleanup_qr_sessions()
            session = _QR_SESSIONS.get(poll_token)
        if not session:
            return bad(handler, "Unknown Weixin poll token.", 404)

        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("X-Accel-Buffering", "no")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()

        def emit(event: str, payload: Mapping[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False)
            handler.wfile.write(f"event: {event}\n".encode("utf-8"))
            handler.wfile.write(f"data: {body}\n\n".encode("utf-8"))
            handler.wfile.flush()

        try:
            emit(
                "wait",
                {
                    "qrcode_url": str(session.get("qrcode_url") or ""),
                    "status": str(session.get("status") or "wait"),
                },
            )
            last_event = str(session.get("status") or "wait")
            last_heartbeat = time.time()
            while True:
                with _QR_LOCK:
                    session = _QR_SESSIONS.get(poll_token)
                if not session:
                    emit("failed", {"message": "Weixin QR session is no longer available."})
                    break

                confirmed = session.get("confirmed")
                if isinstance(confirmed, dict):
                    emit("confirmed", confirmed)
                    break

                try:
                    response = _ilink_get(
                        str(session.get("base_url") or ILINK_BASE_URL),
                        f"{EP_GET_QR_STATUS}?qrcode={session['qrcode_value']}",
                    )
                except Exception as exc:
                    emit("failed", {"message": str(exc)})
                    break

                status = str(response.get("status") or "wait").strip().lower()
                if status == "scaned_but_redirect":
                    redirect_host = str(response.get("redirect_host") or "").strip()
                    if redirect_host:
                        with _QR_LOCK:
                            current = _QR_SESSIONS.get(poll_token)
                            if current:
                                current["base_url"] = f"https://{redirect_host}"
                                current["updated_at"] = time.time()
                    status = "scaned"

                if status == "expired":
                    refreshed = self._refresh_qr_session(poll_token)
                    emit(
                        "expired",
                        {
                            "status": "expired",
                            "qrcode_url": refreshed["qrcode_url"],
                            "refreshes": refreshed["refreshes"],
                        },
                    )
                    last_event = "expired"
                    time.sleep(1)
                    continue

                if status == "confirmed":
                    payload = self._complete_qr_session(response)
                    with _QR_LOCK:
                        current = _QR_SESSIONS.get(poll_token)
                        if current:
                            current["confirmed"] = payload
                            current["updated_at"] = time.time()
                    emit("confirmed", payload)
                    break

                if status == "scaned" and last_event != "scaned":
                    emit("scanned", {"status": "scaned"})
                    last_event = "scaned"
                elif status == "wait" and last_event != "wait":
                    emit("wait", {"status": "wait"})
                    last_event = "wait"

                if time.time() - last_heartbeat >= 20:
                    handler.wfile.write(b": keepalive\n\n")
                    handler.wfile.flush()
                    last_heartbeat = time.time()
                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            with _QR_LOCK:
                session = _QR_SESSIONS.get(poll_token)
                if session and session.get("confirmed"):
                    _QR_SESSIONS.pop(poll_token, None)
        return True

    def _refresh_qr_session(self, poll_token: str) -> dict[str, Any]:
        response = _ilink_get(ILINK_BASE_URL, f"{EP_GET_BOT_QR}?bot_type=3")
        qrcode_value = str(response.get("qrcode") or "").strip()
        qrcode_url = str(response.get("qrcode_img_content") or "").strip() or qrcode_value
        if not qrcode_value:
            raise RuntimeError("Weixin QR refresh failed to return a qrcode token.")
        with _QR_LOCK:
            current = _QR_SESSIONS.get(poll_token)
            if current is None:
                raise RuntimeError("Weixin QR session expired.")
            current["refreshes"] = int(current.get("refreshes") or 0) + 1
            if current["refreshes"] > _QR_MAX_REFRESHES:
                _QR_SESSIONS.pop(poll_token, None)
                raise RuntimeError("Weixin QR code expired too many times. Start again.")
            current["qrcode_value"] = qrcode_value
            current["qrcode_url"] = qrcode_url
            current["base_url"] = ILINK_BASE_URL
            current["status"] = "wait"
            current["updated_at"] = time.time()
            return {
                "qrcode_url": qrcode_url,
                "refreshes": current["refreshes"],
            }

    def _complete_qr_session(self, response: Mapping[str, Any]) -> dict[str, Any]:
        account_id = str(response.get("ilink_bot_id") or "").strip()
        token = str(response.get("bot_token") or "").strip()
        base_url = str(response.get("baseurl") or ILINK_BASE_URL).strip().rstrip("/")
        user_id = str(response.get("ilink_user_id") or "").strip()
        if not account_id or not token:
            raise RuntimeError("Weixin confirmed the QR login but did not return credentials.")

        save_weixin_account(
            str(get_active_hermes_home()),
            account_id=account_id,
            token=token,
            base_url=base_url,
            user_id=user_id,
        )
        safe_write_env(
            {
                "WEIXIN_ACCOUNT_ID": account_id,
                "WEIXIN_TOKEN": token,
                "WEIXIN_BASE_URL": base_url,
            }
        )
        return {
            "account_id": account_id,
            "base_url": base_url,
            "user_id": user_id,
        }


WEIXIN_PROVIDER = WeixinProvider()
