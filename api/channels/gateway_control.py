"""Gateway control helpers that proxy fixed Hermes CLI actions."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from api.channels.gateway_view import get_gateway_runtime_status
from api.config import PYTHON_EXE, _AGENT_DIR
from api.helpers import _redact_text
from api.profiles import get_active_hermes_home, get_active_profile_name

_COMMAND_TIMEOUTS = {
    "start": 90,
    "restart": 180,
    "status": 30,
}

_MAX_OUTPUT_CHARS = 8000


class GatewayControlUnavailable(RuntimeError):
    """Raised when the current WebUI runtime cannot invoke Hermes CLI."""


class GatewayControlFailed(RuntimeError):
    """Raised when a gateway control command exits unsuccessfully."""


def _service_name(profile_name: str) -> str:
    profile = (profile_name or "default").strip()
    return "hermes-gateway" if profile == "default" else f"hermes-gateway-{profile}"


def _launchd_plist_path(profile_name: str) -> Path:
    suffix = "" if (profile_name or "default") == "default" else f"-{profile_name}"
    return Path.home() / "Library" / "LaunchAgents" / f"ai.hermes.gateway{suffix}.plist"


def _python_available(python_exe: str) -> bool:
    if not python_exe:
        return False
    candidate = Path(python_exe)
    if candidate.exists():
        return True
    return shutil.which(python_exe) is not None


def _result_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _clip_output(text: str) -> str:
    rendered = _redact_text(str(text or "")).strip()
    if len(rendered) <= _MAX_OUTPUT_CHARS:
        return rendered
    return rendered[:_MAX_OUTPUT_CHARS].rstrip() + "\n...[truncated]"


def _reason_payload(
    *,
    available: bool,
    reason_key: str = "",
    reason: str = "",
    manager: str | None = None,
    scope: str | None = None,
    service_name: str = "",
    service_path: Path | None = None,
    service_installed: bool | None = None,
) -> dict[str, Any]:
    profile_name = get_active_profile_name()
    hermes_home = get_active_hermes_home()
    agent_dir = Path(_AGENT_DIR).resolve() if _AGENT_DIR else None
    python_exe = str(PYTHON_EXE or "").strip()
    return {
        "available": available,
        "reason_key": reason_key,
        "reason": reason,
        "manager": manager,
        "scope": scope,
        "profile": profile_name,
        "hermes_home": str(hermes_home),
        "service_name": service_name,
        "service_path": str(service_path) if service_path else None,
        "service_installed": service_installed,
        "agent_dir": str(agent_dir) if agent_dir else None,
        "python": python_exe or None,
    }


def get_gateway_control_capability() -> dict[str, Any]:
    profile_name = get_active_profile_name()
    service_name = _service_name(profile_name)
    agent_dir = Path(_AGENT_DIR).resolve() if _AGENT_DIR else None
    python_exe = str(PYTHON_EXE or "").strip()

    if agent_dir is None or not (agent_dir / "run_agent.py").exists():
        return _reason_payload(
            available=False,
            reason_key="channels_gateway_control_missing_agent",
            reason="This WebUI instance cannot find a usable hermes-agent checkout.",
            service_name=service_name,
        )

    if not _python_available(python_exe):
        return _reason_payload(
            available=False,
            reason_key="channels_gateway_control_missing_python",
            reason="This WebUI instance cannot find the configured Hermes Python runtime.",
            service_name=service_name,
        )

    if sys.platform == "darwin":
        plist_path = _launchd_plist_path(profile_name)
        return _reason_payload(
            available=True,
            manager="launchd",
            scope="user",
            service_name=service_name,
            service_path=plist_path,
            service_installed=plist_path.exists(),
        )

    if sys.platform.startswith("linux"):
        user_unit = Path.home() / ".config" / "systemd" / "user" / f"{service_name}.service"
        system_unit = Path("/etc/systemd/system") / f"{service_name}.service"
        if user_unit.exists() or system_unit.exists():
            scope = "system" if system_unit.exists() and not user_unit.exists() else "user"
            service_path = system_unit if scope == "system" else user_unit
            return _reason_payload(
                available=True,
                manager="systemd",
                scope=scope,
                service_name=service_name,
                service_path=service_path,
                service_installed=True,
            )
        return _reason_payload(
            available=True,
            manager="systemd" if shutil.which("systemctl") else None,
            scope="user" if shutil.which("systemctl") else None,
            service_name=service_name,
            service_path=user_unit,
            service_installed=False,
        )

    return _reason_payload(
        available=True,
        service_name=service_name,
    )


def _wait_for_gateway_running(home: Path, timeout: float) -> dict[str, Any]:
    snapshot = get_gateway_runtime_status(home)
    if snapshot.get("running"):
        return snapshot

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        snapshot = get_gateway_runtime_status(home)
        if snapshot.get("running"):
            return snapshot
    return snapshot


def _command_summary(action: str, stdout: str, stderr: str) -> str:
    detail = _result_line(stdout) or _result_line(stderr)
    if detail:
        return detail
    return f"Gateway {action} completed."


def _command_failure(action: str, stdout: str, stderr: str, returncode: int) -> str:
    detail = _result_line(stderr) or _result_line(stdout)
    if detail:
        return detail
    return f"Gateway {action} failed with exit code {returncode}."


def run_gateway_action(action: str) -> dict[str, Any]:
    action_name = (action or "").strip().lower()
    if action_name not in _COMMAND_TIMEOUTS:
        raise ValueError(f"Unsupported gateway action: {action}")

    capability = get_gateway_control_capability()
    if not capability.get("available"):
        raise GatewayControlUnavailable(
            capability.get("reason")
            or "Gateway control is not available from this WebUI runtime."
        )

    home = get_active_hermes_home()
    python_exe = str(capability.get("python") or PYTHON_EXE or "").strip()
    agent_dir = capability.get("agent_dir") or str(_AGENT_DIR or "")

    env = os.environ.copy()
    env["HERMES_HOME"] = str(home)

    try:
        result = subprocess.run(
            [python_exe, "-m", "hermes_cli.main", "gateway", action_name],
            cwd=agent_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUTS[action_name],
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GatewayControlFailed(
            f"Gateway {action_name} timed out after {_COMMAND_TIMEOUTS[action_name]} seconds."
        ) from exc
    except OSError as exc:
        raise GatewayControlFailed(f"Gateway {action_name} failed to start: {exc}") from exc

    stdout = _clip_output(result.stdout)
    stderr = _clip_output(result.stderr)
    if result.returncode != 0:
        raise GatewayControlFailed(
            _command_failure(action_name, stdout, stderr, result.returncode)
        )

    gateway = (
        _wait_for_gateway_running(home, timeout=15.0)
        if action_name in {"start", "restart"}
        else get_gateway_runtime_status(home)
    )
    if action_name in {"start", "restart"} and not gateway.get("running"):
        raise GatewayControlFailed(
            f"Gateway {action_name} finished, but the gateway is still not running."
        )

    return {
        "ok": True,
        "action": action_name,
        "summary": _command_summary(action_name, stdout, stderr),
        "stdout": stdout,
        "stderr": stderr,
        "gateway": {
            **gateway,
            "control": get_gateway_control_capability(),
        },
    }
