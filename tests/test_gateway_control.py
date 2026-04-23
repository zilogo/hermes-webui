from types import SimpleNamespace

import pytest

import api.channels.gateway_control as gateway_control
import api.profiles as profiles


def _patch_control_runtime(monkeypatch, tmp_path):
    agent_dir = tmp_path / "hermes-agent"
    agent_dir.mkdir()
    (agent_dir / "run_agent.py").write_text("# test\n", encoding="utf-8")

    python_exe = tmp_path / "python"
    python_exe.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    monkeypatch.setattr(gateway_control, "_AGENT_DIR", agent_dir)
    monkeypatch.setattr(gateway_control, "PYTHON_EXE", str(python_exe))
    return agent_dir, python_exe


def test_gateway_control_capability_is_profile_scoped_for_systemd(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    profile_dir = base / "profiles" / "ops"
    profile_dir.mkdir(parents=True)
    home_dir = tmp_path / "home"
    service_dir = home_dir / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True)
    service_path = service_dir / "hermes-gateway-ops.service"
    service_path.write_text("[Unit]\nDescription=test\n", encoding="utf-8")

    _patch_control_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", base)
    monkeypatch.setattr(gateway_control.sys, "platform", "linux")
    monkeypatch.setattr(
        gateway_control.shutil,
        "which",
        lambda name: "/bin/systemctl" if name == "systemctl" else None,
    )
    monkeypatch.setattr(gateway_control.Path, "home", staticmethod(lambda: home_dir))

    try:
        profiles.set_request_profile("ops")
        capability = gateway_control.get_gateway_control_capability()
    finally:
        profiles.clear_request_profile()

    assert capability["available"] is True
    assert capability["manager"] == "systemd"
    assert capability["scope"] == "user"
    assert capability["service_name"] == "hermes-gateway-ops"
    assert capability["service_path"] == str(service_path)
    assert capability["service_installed"] is True
    assert capability["hermes_home"] == str(profile_dir)


def test_gateway_control_capability_still_available_without_systemd_unit(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    base.mkdir(parents=True)
    home_dir = tmp_path / "home"
    (home_dir / ".config" / "systemd" / "user").mkdir(parents=True)

    _patch_control_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", base)
    monkeypatch.setattr(gateway_control.sys, "platform", "linux")
    monkeypatch.setattr(
        gateway_control.shutil,
        "which",
        lambda name: "/bin/systemctl" if name == "systemctl" else None,
    )
    monkeypatch.setattr(gateway_control.Path, "home", staticmethod(lambda: home_dir))

    capability = gateway_control.get_gateway_control_capability()

    assert capability["available"] is True
    assert capability["service_name"] == "hermes-gateway"
    assert capability["service_installed"] is False
    assert capability["service_path"].endswith("/.config/systemd/user/hermes-gateway.service")
    assert capability["hermes_home"] == str(base)


def test_gateway_control_capability_is_available_without_launchd_plist(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    base.mkdir(parents=True)
    home_dir = tmp_path / "home"
    (home_dir / "Library" / "LaunchAgents").mkdir(parents=True)

    _patch_control_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", base)
    monkeypatch.setattr(gateway_control.sys, "platform", "darwin")
    monkeypatch.setattr(gateway_control.Path, "home", staticmethod(lambda: home_dir))

    capability = gateway_control.get_gateway_control_capability()

    assert capability["available"] is True
    assert capability["manager"] == "launchd"
    assert capability["service_installed"] is False
    assert capability["service_path"].endswith("/Library/LaunchAgents/ai.hermes.gateway.plist")


def test_run_gateway_action_uses_active_profile_home(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    profile_dir = base / "profiles" / "ops"
    profile_dir.mkdir(parents=True)
    agent_dir, python_exe = _patch_control_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", base)

    capability = {
        "available": True,
        "manager": "systemd",
        "scope": "user",
        "service_name": "hermes-gateway-ops",
        "service_path": str(tmp_path / "service.service"),
        "agent_dir": str(agent_dir),
        "python": str(python_exe),
        "hermes_home": str(profile_dir),
    }
    monkeypatch.setattr(gateway_control, "get_gateway_control_capability", lambda: capability)

    captured = {}

    def fake_run(args, cwd, env, stdin, capture_output, text, timeout, check):
        captured["args"] = args
        captured["cwd"] = cwd
        captured["env_home"] = env.get("HERMES_HOME")
        captured["timeout"] = timeout
        return SimpleNamespace(
            returncode=0,
            stdout="✓ User service started\n",
            stderr="",
        )

    monkeypatch.setattr(gateway_control.subprocess, "run", fake_run)
    monkeypatch.setattr(
        gateway_control,
        "_wait_for_gateway_running",
        lambda home, timeout: {
            "running": True,
            "pid": 222,
            "gateway_state": None,
            "platforms": ["feishu"],
            "active_agents": 1,
            "updated_at": None,
            "state_mtime": None,
            "hermes_home": str(home),
        },
    )

    try:
        profiles.set_request_profile("ops")
        result = gateway_control.run_gateway_action("start")
    finally:
        profiles.clear_request_profile()

    assert captured["args"] == [
        str(python_exe),
        "-m",
        "hermes_cli.main",
        "gateway",
        "start",
    ]
    assert captured["cwd"] == str(agent_dir)
    assert captured["env_home"] == str(profile_dir)
    assert captured["timeout"] == 90
    assert result["summary"] == "✓ User service started"
    assert result["gateway"]["running"] is True
    assert result["gateway"]["hermes_home"] == str(profile_dir)


def test_run_gateway_action_rejects_unavailable_control(monkeypatch):
    monkeypatch.setattr(
        gateway_control,
        "get_gateway_control_capability",
        lambda: {
            "available": False,
            "reason": "unavailable",
        },
    )

    with pytest.raises(gateway_control.GatewayControlUnavailable, match="unavailable"):
        gateway_control.run_gateway_action("restart")
