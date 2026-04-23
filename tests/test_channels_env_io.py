import stat
import threading

import pytest

import api.channels.env_io as env_io


def test_safe_write_env_creates_private_file(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(env_io, "get_env_path", lambda: env_path)

    env_io.safe_write_env({"TELEGRAM_BOT_TOKEN": "secret"})

    assert env_path.read_text(encoding="utf-8") == "TELEGRAM_BOT_TOKEN=secret\n"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_safe_write_env_rejects_newlines(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(env_io, "get_env_path", lambda: env_path)

    with pytest.raises(ValueError, match="newline forbidden"):
        env_io.safe_write_env({"BAD_VALUE": "line1\nline2"})


def test_safe_write_env_serializes_concurrent_writes(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(env_io, "get_env_path", lambda: env_path)

    errors = []

    def writer(index):
        try:
            env_io.safe_write_env({f"KEY_{index}": f"value-{index}"})
        except Exception as exc:  # pragma: no cover - debugging aid
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not errors
    values = env_io.load_env_file(env_path)
    for index in range(8):
        assert values[f"KEY_{index}"] == f"value-{index}"
    assert all(line.count("=") == 1 for line in env_path.read_text(encoding="utf-8").splitlines() if line)
