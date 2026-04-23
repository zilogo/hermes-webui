from __future__ import annotations

from pathlib import Path
from unittest import mock


def test_get_hermes_import_hint_reports_python_mismatch():
    import api.config as config

    expected_python = str(Path("/tmp/hermes-agent/.venv/bin/python").resolve())
    with (
        mock.patch.object(config, "_AGENT_DIR", Path("/tmp/hermes-agent")),
        mock.patch.object(config, "PYTHON_EXE", "/tmp/hermes-agent/.venv/bin/python"),
        mock.patch.object(config.sys, "executable", "/usr/bin/python3"),
        mock.patch.dict(config.os.environ, {"HERMES_WEBUI_PYTHON": "/tmp/hermes-agent/.venv/bin/python"}),
    ):
        hint = config.get_hermes_import_hint()

    assert f"HERMES_WEBUI_PYTHON points to {expected_python}" in hint
    assert "running under /usr/bin/python3" in hint
    assert "./start.sh" in hint


def test_print_startup_config_shows_runtime_and_hint(capsys):
    import api.config as config

    fake_config_path = Path("/tmp/config.yaml")
    expected_python = str(Path("/tmp/hermes-agent/.venv/bin/python").resolve())
    with (
        mock.patch.object(config, "_AGENT_DIR", Path("/tmp/hermes-agent")),
        mock.patch.object(config, "PYTHON_EXE", "/tmp/hermes-agent/.venv/bin/python"),
        mock.patch.object(config.sys, "executable", "/usr/bin/python3"),
        mock.patch.object(config, "_get_config_path", return_value=fake_config_path),
        mock.patch.object(Path, "exists", return_value=False),
    ):
        config.print_startup_config()

    output = capsys.readouterr().out
    assert "python rt   : /usr/bin/python3" in output
    assert f"python hint : {expected_python}" in output


def test_ai_agent_unavailable_message_includes_root_cause_and_hint():
    import api.streaming as streaming

    with (
        mock.patch.object(streaming, "_AI_AGENT_IMPORT_ERROR", ModuleNotFoundError("No module named 'openai'")),
        mock.patch.object(streaming, "get_hermes_import_hint", return_value="Restart with `./start.sh`."),
    ):
        msg = streaming._build_ai_agent_unavailable_message()

    assert "AIAgent import failed: ModuleNotFoundError: No module named 'openai'" in msg
    assert "Restart with `./start.sh`." in msg
    assert "sys.path" not in msg
