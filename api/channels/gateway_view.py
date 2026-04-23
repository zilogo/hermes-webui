"""Gateway runtime view helpers for the active profile."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from api.profiles import get_active_hermes_home


def _parse_pid_file(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            pid = payload.get("pid")
            return int(pid) if isinstance(pid, int) else None
        if isinstance(payload, int):
            return payload
    except json.JSONDecodeError:
        pass
    try:
        return int(raw)
    except ValueError:
        return None


def _is_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _platform_names(payload: dict[str, Any]) -> list[str]:
    platforms = payload.get("platforms")
    if isinstance(platforms, dict):
        return sorted(str(key) for key in platforms.keys())
    if isinstance(platforms, list):
        return sorted(str(key) for key in platforms if key)
    return []


def get_gateway_runtime_status(home: Path | None = None) -> dict[str, Any]:
    home = home or get_active_hermes_home()
    pid_path = home / "gateway.pid"
    state_path = home / "gateway_state.json"

    pid = _parse_pid_file(pid_path)
    state = _read_state(state_path)
    running = _is_alive(pid)

    return {
        "running": running,
        "pid": pid,
        "gateway_state": state.get("gateway_state"),
        "platforms": _platform_names(state),
        "active_agents": state.get("active_agents"),
        "updated_at": state.get("updated_at"),
        "state_mtime": state_path.stat().st_mtime if state_path.exists() else None,
        "hermes_home": str(home),
    }


def get_gateway_status() -> dict[str, Any]:
    payload = get_gateway_runtime_status()
    from api.channels.gateway_control import get_gateway_control_capability

    payload["control"] = get_gateway_control_capability()
    return payload
