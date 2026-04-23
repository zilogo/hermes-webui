"""Profile-scoped .env IO for Channels."""

from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path
from typing import Mapping

from api.profiles import get_active_hermes_home


def get_env_path() -> Path:
    return get_active_hermes_home() / ".env"


def load_env_file(env_path: Path | None = None) -> dict[str, str]:
    env_path = env_path or get_env_path()
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return values


def safe_write_env(updates: Mapping[str, str | None]) -> Path:
    """POSIX-only atomic .env update with an external lock file."""

    env_path = get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = env_path.parent / ".env.lock"
    with open(lock_path, "a+", encoding="utf-8") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            current = load_env_file(env_path)
            for key, value in updates.items():
                if value is None:
                    current.pop(key, None)
                    continue
                clean = str(value).strip()
                if "\n" in clean or "\r" in clean:
                    raise ValueError(f"newline forbidden: {key}")
                current[key] = clean

            fd, tmp_path = tempfile.mkstemp(
                dir=str(env_path.parent),
                prefix=".env.tmp.",
                text=True,
            )
            tmp = Path(tmp_path)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    for key in sorted(current):
                        handle.write(f"{key}={current[key]}\n")
                os.chmod(tmp, 0o600)
                os.replace(tmp, env_path)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)

    if env_path.exists():
        try:
            env_path.chmod(0o600)
        except OSError:
            pass
    return env_path
