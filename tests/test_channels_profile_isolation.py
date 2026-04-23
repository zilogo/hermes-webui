from pathlib import Path

import api.profiles as profiles
from api.channels.telegram import TELEGRAM_PROVIDER


def test_channels_env_writes_follow_request_profile(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    (base / "profiles" / "ops").mkdir(parents=True)
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", base)

    try:
        profiles.set_request_profile("default")
        TELEGRAM_PROVIDER.save({"bot_token": "default-token", "home_channel": "general"})

        profiles.set_request_profile("ops")
        TELEGRAM_PROVIDER.save({"bot_token": "ops-token", "home_channel": "alerts"})

        default_summary = None
        ops_summary = TELEGRAM_PROVIDER.summary()

        profiles.set_request_profile("default")
        default_summary = TELEGRAM_PROVIDER.summary()
    finally:
        profiles.clear_request_profile()

    default_env = (base / ".env").read_text(encoding="utf-8")
    ops_env = (base / "profiles" / "ops" / ".env").read_text(encoding="utf-8")

    assert "default-token" in default_env
    assert "ops-token" not in default_env
    assert "ops-token" in ops_env
    assert "default-token" not in ops_env
    assert default_summary["values"]["home_channel"] == "general"
    assert ops_summary["values"]["home_channel"] == "alerts"
    assert default_summary["values"]["bot_token"] != ops_summary["values"]["bot_token"]
