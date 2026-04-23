"""Feishu / Lark channel provider."""

from __future__ import annotations

from api.channels.base import ChannelField, ChannelProvider, json_request


_DOMAIN_OPTIONS = (
    {"value": "feishu", "label": "Feishu"},
    {"value": "lark", "label": "Lark"},
)

_MODE_OPTIONS = (
    {"value": "websocket", "label": "WebSocket"},
    {"value": "webhook", "label": "Webhook"},
)


class FeishuProvider(ChannelProvider):
    key = "feishu"
    title = "Feishu / Lark"
    description = "Save an App ID / App Secret pair and optional delivery defaults."
    supports_test = True
    fields = (
        ChannelField(
            name="app_id",
            env="FEISHU_APP_ID",
            label="App ID",
            label_key="channels_field_app_id",
            placeholder="cli_xxx",
            placeholder_key="channels_placeholder_app_id",
            required=True,
        ),
        ChannelField(
            name="app_secret",
            env="FEISHU_APP_SECRET",
            label="App secret",
            label_key="channels_field_app_secret",
            type="password",
            placeholder="secret_xxx",
            placeholder_key="channels_placeholder_app_secret",
            required=True,
            secret=True,
        ),
        ChannelField(
            name="domain",
            env="FEISHU_DOMAIN",
            label="Domain",
            label_key="channels_field_domain",
            type="select",
            default="feishu",
            options=_DOMAIN_OPTIONS,
        ),
        ChannelField(
            name="connection_mode",
            env="FEISHU_CONNECTION_MODE",
            label="Connection mode",
            label_key="channels_field_connection_mode",
            type="select",
            default="websocket",
            options=_MODE_OPTIONS,
        ),
        ChannelField(
            name="home_channel",
            env="FEISHU_HOME_CHANNEL",
            label="Home channel",
            label_key="channels_field_home_channel",
            placeholder="Optional chat ID",
            placeholder_key="channels_placeholder_home_channel",
        ),
    )

    def test(self, payload):
        values = self.merge_payload(payload)
        app_id = values.get("app_id", "").strip()
        app_secret = values.get("app_secret", "").strip()
        domain = values.get("domain", "feishu").strip().lower() or "feishu"
        if not app_id or not app_secret:
            raise ValueError("Feishu App ID and App Secret are required.")
        host = "open.larksuite.com" if domain == "lark" else "open.feishu.cn"
        response = json_request(
            f"https://{host}/open-apis/auth/v3/tenant_access_token/internal",
            method="POST",
            payload={"app_id": app_id, "app_secret": app_secret},
            timeout=15.0,
        )
        if not isinstance(response, dict):
            raise RuntimeError("Feishu returned an invalid response.")
        code = response.get("code")
        if code not in (0, "0", None):
            message = str(response.get("msg") or response.get("message") or "").strip()
            raise RuntimeError(message or "Feishu rejected the credentials.")
        return {
            "ok": True,
            "message": "Feishu credentials verified.",
            "detail": {
                "domain": domain,
            },
        }


FEISHU_PROVIDER = FeishuProvider()
