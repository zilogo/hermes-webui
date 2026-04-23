import api.profiles as profiles
from api.channels.gateway_view import _parse_pid_file, get_gateway_status


def test_parse_pid_file_accepts_json_dict(tmp_path):
    path = tmp_path / "gateway.pid"
    path.write_text('{"pid": 123}', encoding="utf-8")

    assert _parse_pid_file(path) == 123


def test_parse_pid_file_accepts_json_int(tmp_path):
    path = tmp_path / "gateway.pid"
    path.write_text("123", encoding="utf-8")

    assert _parse_pid_file(path) == 123


def test_parse_pid_file_accepts_bare_int(tmp_path):
    path = tmp_path / "gateway.pid"
    path.write_text("456\n", encoding="utf-8")

    assert _parse_pid_file(path) == 456


def test_parse_pid_file_returns_none_for_invalid_content(tmp_path):
    path = tmp_path / "gateway.pid"
    path.write_text("{bad json", encoding="utf-8")

    assert _parse_pid_file(path) is None


def test_get_gateway_status_is_profile_scoped(monkeypatch, tmp_path):
    base = tmp_path / ".hermes"
    profile_dir = base / "profiles" / "ops"
    profile_dir.mkdir(parents=True)
    monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", base)

    (base / "gateway.pid").write_text("111\n", encoding="utf-8")
    (profile_dir / "gateway.pid").write_text("222\n", encoding="utf-8")

    try:
        profiles.set_request_profile("default")
        default_status = get_gateway_status()
        profiles.set_request_profile("ops")
        ops_status = get_gateway_status()
    finally:
        profiles.clear_request_profile()

    assert default_status["pid"] == 111
    assert default_status["hermes_home"] == str(base)
    assert ops_status["pid"] == 222
    assert ops_status["hermes_home"] == str(profile_dir)
