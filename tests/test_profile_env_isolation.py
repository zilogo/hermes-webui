import importlib
import json
import os
import sys
from pathlib import Path


def test_profile_switch_clears_previous_profile_env_vars(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    (base / "profiles" / "p1").mkdir(parents=True)
    (base / "profiles" / "p2").mkdir(parents=True)
    (base / "profiles" / "p1" / ".env").write_text(
        "OPENAI_API_KEY=secret-from-p1\nCUSTOM_TOKEN=token-from-p1\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_TOKEN", raising=False)

    sys.modules.pop("api.profiles", None)
    profiles = importlib.import_module("api.profiles")
    profiles = importlib.reload(profiles)

    profiles.init_profile_state()
    profiles.switch_profile("p1")
    assert os.environ.get("OPENAI_API_KEY") == "secret-from-p1"
    assert os.environ.get("CUSTOM_TOKEN") == "token-from-p1"

    profiles.switch_profile("p2")
    assert os.environ.get("OPENAI_API_KEY") is None
    assert os.environ.get("CUSTOM_TOKEN") is None
    assert profiles.get_active_profile_name() == "p2"


def test_profile_switch_replaces_overlapping_keys(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    (base / "profiles" / "p1").mkdir(parents=True)
    (base / "profiles" / "p2").mkdir(parents=True)
    (base / "profiles" / "p1" / ".env").write_text(
        "OPENAI_API_KEY=secret-from-p1\nONLY_P1=one\n",
        encoding="utf-8",
    )
    (base / "profiles" / "p2" / ".env").write_text(
        "OPENAI_API_KEY=secret-from-p2\nONLY_P2=two\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ONLY_P1", raising=False)
    monkeypatch.delenv("ONLY_P2", raising=False)

    sys.modules.pop("api.profiles", None)
    profiles = importlib.import_module("api.profiles")
    profiles = importlib.reload(profiles)

    profiles.init_profile_state()
    profiles.switch_profile("p1")
    assert os.environ.get("OPENAI_API_KEY") == "secret-from-p1"
    assert os.environ.get("ONLY_P1") == "one"

    profiles.switch_profile("p2")
    assert os.environ.get("OPENAI_API_KEY") == "secret-from-p2"
    assert os.environ.get("ONLY_P1") is None
    assert os.environ.get("ONLY_P2") == "two"


def test_profile_config_path_ignores_root_override_for_non_default_profile(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    (base / "profiles" / "cloud-1").mkdir(parents=True)
    (base / "config.yaml").write_text("model:\n  default: root-model\n", encoding="utf-8")
    (base / "profiles" / "cloud-1" / "config.yaml").write_text(
        "model:\n  default: cloud-model\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(base / "config.yaml"))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    sys.modules.pop("api.profiles", None)
    sys.modules.pop("api.config", None)
    profiles = importlib.import_module("api.profiles")
    profiles = importlib.reload(profiles)
    config = importlib.import_module("api.config")
    config = importlib.reload(config)

    assert config._get_config_path() == base / "config.yaml"

    profiles.set_request_profile("cloud-1")
    try:
        assert config._get_config_path() == base / "profiles" / "cloud-1" / "config.yaml"
    finally:
        profiles.clear_request_profile()


def test_get_config_switches_to_request_profile_without_process_wide_reload(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    (base / "profiles" / "cloud-1").mkdir(parents=True)
    (base / "config.yaml").write_text(
        "model:\n  default: root-model\n",
        encoding="utf-8",
    )
    (base / "profiles" / "cloud-1" / "config.yaml").write_text(
        "model:\n  default: cloud-model\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(base / "config.yaml"))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    sys.modules.pop("api.profiles", None)
    sys.modules.pop("api.config", None)
    profiles = importlib.import_module("api.profiles")
    profiles = importlib.reload(profiles)
    config = importlib.import_module("api.config")
    config = importlib.reload(config)

    assert config.get_config().get("model", {}).get("default") == "root-model"
    assert config.cfg.get("model", {}).get("default") == "root-model"

    profiles.set_request_profile("cloud-1")
    try:
        assert config.get_config().get("model", {}).get("default") == "cloud-model"
        assert config.cfg.get("model", {}).get("default") == "cloud-model"
    finally:
        profiles.clear_request_profile()

    assert config.get_config().get("model", {}).get("default") == "root-model"
    assert config.cfg.get("model", {}).get("default") == "root-model"


def test_onboarding_status_uses_request_profile_config(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    (base / "profiles" / "cloud-1" / "webui_state").mkdir(parents=True)
    (base / "webui").mkdir(parents=True)
    (base / "config.yaml").write_text(
        "model:\n  default: root-model\n",
        encoding="utf-8",
    )
    (base / "profiles" / "cloud-1" / "config.yaml").write_text(
        "model:\n"
        "  provider: custom\n"
        "  default: cloud-model\n"
        "  base_url: https://example.test/v1\n"
        "  api_key: cloud-key\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(base / "config.yaml"))
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(base / "webui"))
    monkeypatch.delenv("HERMES_HOME", raising=False)

    sys.modules.pop("api.profiles", None)
    sys.modules.pop("api.config", None)
    sys.modules.pop("api.onboarding", None)
    profiles = importlib.import_module("api.profiles")
    profiles = importlib.reload(profiles)
    importlib.reload(importlib.import_module("api.config"))
    onboarding = importlib.import_module("api.onboarding")
    onboarding = importlib.reload(onboarding)

    monkeypatch.setattr(onboarding, "_HERMES_FOUND", True)
    monkeypatch.setattr(onboarding, "verify_hermes_imports", lambda: (True, [], {}))
    monkeypatch.setattr(onboarding, "load_settings", lambda: {"onboarding_completed": False})
    monkeypatch.setattr(onboarding, "load_workspaces", lambda: [])
    monkeypatch.setattr(onboarding, "get_last_workspace", lambda: "")
    monkeypatch.setattr(onboarding, "get_available_models", lambda: {})

    profiles.set_request_profile("cloud-1")
    try:
        status = onboarding.get_onboarding_status()
    finally:
        profiles.clear_request_profile()

    assert status["completed"] is True
    assert status["system"]["config_exists"] is True
    assert status["system"]["current_provider"] == "custom"
    assert status["system"]["current_model"] == "cloud-model"
    assert status["system"]["chat_ready"] is True


def test_named_profile_last_workspace_ignores_global_fallback(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    profile_dir = base / "profiles" / "demo"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "workspace").mkdir(parents=True, exist_ok=True)
    (profile_dir / "webui_state").mkdir(parents=True, exist_ok=True)
    (base / "webui").mkdir(parents=True, exist_ok=True)

    global_workspace = tmp_path / "global-workspace"
    global_workspace.mkdir(parents=True, exist_ok=True)

    (profile_dir / "webui_state" / "last_workspace.txt").write_text(
        str(global_workspace),
        encoding="utf-8",
    )
    (profile_dir / "webui_state" / "workspaces.json").write_text(
        json.dumps([{"path": str((profile_dir / "workspace").resolve()), "name": "Home"}]),
        encoding="utf-8",
    )
    (base / "webui" / "last_workspace.txt").write_text(
        str(global_workspace),
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.setenv("HERMES_HOME", str(base))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(base / "config.yaml"))
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(base / "webui"))

    sys.modules.pop("api.profiles", None)
    sys.modules.pop("api.workspace", None)
    profiles = importlib.import_module("api.profiles")
    profiles = importlib.reload(profiles)
    workspace = importlib.import_module("api.workspace")
    workspace = importlib.reload(workspace)

    profiles.set_request_profile("demo")
    try:
        expected = str((profile_dir / "workspace").resolve())
        assert workspace.get_last_workspace() == expected
        assert (profile_dir / "webui_state" / "last_workspace.txt").read_text(encoding="utf-8").strip() == expected
    finally:
        profiles.clear_request_profile()


def test_named_profile_without_workspace_state_defaults_to_own_workspace(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    profile_dir = base / "profiles" / "cloud-1"
    (profile_dir / "workspace").mkdir(parents=True, exist_ok=True)
    (base / "webui").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.setenv("HERMES_HOME", str(base))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(base / "config.yaml"))
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(base / "webui"))

    sys.modules.pop("api.profiles", None)
    sys.modules.pop("api.workspace", None)
    profiles = importlib.import_module("api.profiles")
    profiles = importlib.reload(profiles)
    workspace = importlib.import_module("api.workspace")
    workspace = importlib.reload(workspace)

    profiles.set_request_profile("cloud-1")
    try:
        expected = str((profile_dir / "workspace").resolve())
        assert workspace.load_workspaces() == [{"path": expected, "name": "Home"}]
        assert workspace.get_last_workspace() == expected
    finally:
        profiles.clear_request_profile()


def test_switch_profile_returns_target_profile_workspace_for_per_client_switch(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    first_profile = base / "profiles" / "cloud-1"
    second_profile = base / "profiles" / "test1"
    for profile_dir in (first_profile, second_profile):
        (profile_dir / "workspace").mkdir(parents=True, exist_ok=True)
        (profile_dir / "webui_state").mkdir(parents=True, exist_ok=True)
        (profile_dir / "webui_state" / "workspaces.json").write_text(
            json.dumps([{"path": str((profile_dir / "workspace").resolve()), "name": "Home"}]),
            encoding="utf-8",
        )
        (profile_dir / "webui_state" / "last_workspace.txt").write_text(
            str((profile_dir / "workspace").resolve()),
            encoding="utf-8",
        )

    monkeypatch.setenv("HERMES_BASE_HOME", str(base))
    monkeypatch.setenv("HERMES_HOME", str(base))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(base / "config.yaml"))
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(base / "webui"))

    sys.modules.pop("api.config", None)
    sys.modules.pop("api.profiles", None)
    sys.modules.pop("api.workspace", None)
    config = importlib.import_module("api.config")
    config = importlib.reload(config)
    profiles = importlib.import_module("api.profiles")
    profiles = importlib.reload(profiles)
    workspace = importlib.import_module("api.workspace")
    workspace = importlib.reload(workspace)

    profiles.set_request_profile("cloud-1")
    try:
        result = profiles.switch_profile("test1", process_wide=False)
        expected = str((second_profile / "workspace").resolve())
        assert result["default_workspace"] == expected
        assert workspace.get_last_workspace() == str((first_profile / "workspace").resolve())
    finally:
        profiles.clear_request_profile()
