"""Telegram channel provider."""

from __future__ import annotations

from urllib.parse import quote

from api.channels.base import ChannelField, ChannelProvider, json_request


class TelegramProvider(ChannelProvider):
    key = "telegram"
    title = "Telegram"
    description = "Connect a BotFather bot token for inbound chat and cron delivery."
    supports_test = True
    fields = (
        ChannelField(
            name="bot_token",
            env="TELEGRAM_BOT_TOKEN",
            label="Bot token",
            label_key="channels_field_bot_token",
            type="password",
            placeholder="123456789:ABC...",
            placeholder_key="channels_placeholder_bot_token",
            required=True,
            secret=True,
        ),
        ChannelField(
            name="home_channel",
            env="TELEGRAM_HOME_CHANNEL",
            label="Home channel",
            label_key="channels_field_home_channel",
            placeholder="Optional chat ID",
            placeholder_key="channels_placeholder_home_channel",
        ),
    )

    def test(self, payload):
        values = self.merge_payload(payload)
        token = values.get("bot_token", "").strip()
        if not token:
            raise ValueError("Telegram bot token is required.")
        response = json_request(
            f"https://api.telegram.org/bot{quote(token, safe=':')}/getMe",
            timeout=15.0,
        )
        if not isinstance(response, dict) or not response.get("ok"):
            detail = ""
            if isinstance(response, dict):
                detail = str(response.get("description") or "")
            raise RuntimeError(detail or "Telegram rejected the bot token.")
        bot = response.get("result") or {}
        username = str(bot.get("username") or "").strip()
        bot_id = bot.get("id")
        return {
            "ok": True,
            "message": f"Telegram bot verified: @{username}" if username else "Telegram bot verified.",
            "detail": {
                "username": username,
                "id": bot_id,
            },
        }


TELEGRAM_PROVIDER = TelegramProvider()
