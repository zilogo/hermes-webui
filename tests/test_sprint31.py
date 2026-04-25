"""
Tests for issue #170: new profile form with optional custom endpoint fields.

Tests cover:
  1. _write_endpoint_to_config writes base_url into config.yaml
  2. _write_endpoint_to_config writes api_key into config.yaml
  3. _write_endpoint_to_config writes both together
  4. _write_endpoint_to_config merges with existing config (does not clobber)
  5. _write_endpoint_to_config is a no-op when both args are None/empty
  6. API route accepts base_url and api_key in POST body
  7. Profile created via API has base_url in config.yaml
  8. Managed profile writes the KarmaBox managed flag
"""
import json
import pathlib
import shutil
import os
import sys
import types
import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML required for config write tests")


# ── 1-5: _write_endpoint_to_config unit tests ─────────────────────────────────

class TestWriteEndpointToConfig:
    def test_writes_base_url(self, tmp_path):
        from api.profiles import _write_endpoint_to_config
        _write_endpoint_to_config(tmp_path, base_url="http://localhost:11434")
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["model"]["provider"] == "custom"
        assert cfg["model"]["base_url"] == "http://localhost:11434"

    def test_writes_api_key(self, tmp_path):
        from api.profiles import _write_endpoint_to_config
        _write_endpoint_to_config(tmp_path, api_key="sk-local-test")
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["model"]["api_key"] == "sk-local-test"

    def test_writes_both(self, tmp_path):
        from api.profiles import _write_endpoint_to_config
        _write_endpoint_to_config(tmp_path, base_url="http://localhost:8080", api_key="mykey")
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["model"]["provider"] == "custom"
        assert cfg["model"]["base_url"] == "http://localhost:8080"
        assert cfg["model"]["api_key"] == "mykey"

    def test_merges_with_existing_config(self, tmp_path):
        """Does not clobber other top-level config keys."""
        existing = {"model": {"default": "gpt-4o", "provider": "openai"}, "agent": {"max_turns": 90}}
        (tmp_path / "config.yaml").write_text(yaml.dump(existing))
        from api.profiles import _write_endpoint_to_config
        _write_endpoint_to_config(tmp_path, base_url="http://localhost:1234")
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        # Existing keys preserved
        assert cfg["model"]["default"] == "gpt-4o"
        assert cfg["model"]["provider"] == "custom"
        assert cfg["agent"]["max_turns"] == 90
        # New key added
        assert cfg["model"]["base_url"] == "http://localhost:1234"

    def test_noop_when_both_none(self, tmp_path):
        from api.profiles import _write_endpoint_to_config
        _write_endpoint_to_config(tmp_path, base_url=None, api_key=None)
        assert not (tmp_path / "config.yaml").exists()

    def test_noop_when_both_empty_strings(self, tmp_path):
        from api.profiles import _write_endpoint_to_config
        _write_endpoint_to_config(tmp_path, base_url="", api_key="")
        assert not (tmp_path / "config.yaml").exists()

    def test_managed_profile_sets_karmabox_flag(self, tmp_path):
        from api.profiles import _write_endpoint_to_config
        _write_endpoint_to_config(
            tmp_path,
            base_url="https://api.aitokencloud.com",
            api_key="sk-managed",
            managed_profile=True,
        )
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["model"]["provider"] == "custom"
        assert cfg["model"]["base_url"] == "https://api.aitokencloud.com/v1"
        assert cfg["karmabox"]["managed_profile"] is True


class TestCreateProfileModes:
    def test_create_profile_managed_uses_karmabox_base_url(self, tmp_path, monkeypatch):
        import api.profiles as profiles

        created = {}

        def _fake_create_profile(name, clone_from=None, clone_config=False, clone_all=False, no_alias=True):
            profile_dir = tmp_path / "profiles" / name
            profile_dir.mkdir(parents=True, exist_ok=True)
            created["args"] = {
                "clone_from": clone_from,
                "clone_config": clone_config,
                "clone_all": clone_all,
                "no_alias": no_alias,
            }

        monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", tmp_path)
        monkeypatch.setattr(profiles, "list_profiles_api", lambda: [])
        monkeypatch.setitem(sys.modules, "hermes_cli.profiles", types.SimpleNamespace(create_profile=_fake_create_profile))
        monkeypatch.setenv("KARMABOX_MODE", "true")
        monkeypatch.setenv("KARMABOX_MODEL_BASE_URL", "https://managed.example.com/v1/")

        result = profiles.create_profile_api(
            "managed-sprint31",
            create_mode="managed",
            api_key="sk-managed-test",
        )

        cfg = yaml.safe_load((tmp_path / "profiles" / "managed-sprint31" / "config.yaml").read_text())
        assert result["name"] == "managed-sprint31"
        assert created["args"]["clone_from"] is None
        assert created["args"]["clone_config"] is False
        assert cfg["model"]["provider"] == "custom"
        assert cfg["model"]["base_url"] == "https://managed.example.com/v1"
        assert cfg["model"]["api_key"] == "sk-managed-test"
        assert cfg["karmabox"]["managed_profile"] is True

    def test_create_profile_managed_requires_karmabox_mode(self, tmp_path, monkeypatch):
        import api.profiles as profiles

        monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", tmp_path)
        monkeypatch.setattr(profiles, "list_profiles_api", lambda: [])
        monkeypatch.delenv("KARMABOX_MODE", raising=False)

        with pytest.raises(ValueError, match="KARMABOX_MODE=true"):
            profiles.create_profile_api(
                "managed-disabled",
                create_mode="managed",
                api_key="sk-managed-test",
            )

    def test_create_profile_clone_copies_existing_config_without_endpoint_overrides(self, tmp_path, monkeypatch):
        import api.profiles as profiles

        source_dir = tmp_path / "profiles" / "local27b"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_cfg = {
            "model": {
                "provider": "ollama",
                "default": "qwen3-27b",
                "base_url": "http://127.0.0.1:11434",
            },
            "agent": {"max_turns": 42},
        }
        (source_dir / "config.yaml").write_text(yaml.dump(source_cfg), encoding="utf-8")

        def _fake_create_profile(name, clone_from=None, clone_config=False, clone_all=False, no_alias=True):
            profile_dir = tmp_path / "profiles" / name
            profile_dir.mkdir(parents=True, exist_ok=True)
            if clone_config and clone_from:
                shutil.copy2(source_dir / "config.yaml", profile_dir / "config.yaml")

        monkeypatch.setattr(profiles, "_DEFAULT_HERMES_HOME", tmp_path)
        monkeypatch.setattr(profiles, "list_profiles_api", lambda: [])
        monkeypatch.setitem(sys.modules, "hermes_cli.profiles", types.SimpleNamespace(create_profile=_fake_create_profile))

        profiles.create_profile_api(
            "local27b-copy",
            clone_from="local27b",
            create_mode="clone",
            base_url="https://should-not-win.example.com",
            api_key="sk-ignored",
        )

        cfg = yaml.safe_load((tmp_path / "profiles" / "local27b-copy" / "config.yaml").read_text())
        assert cfg["model"]["provider"] == "ollama"
        assert cfg["model"]["default"] == "qwen3-27b"
        assert cfg["model"]["base_url"] == "http://127.0.0.1:11434"
        assert "api_key" not in cfg["model"]
        assert "karmabox" not in cfg


# ── 6-7: API integration tests ────────────────────────────────────────────────

from tests._pytest_port import BASE as _TEST_BASE


def _post(path, body=None):
    import urllib.request
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        _TEST_BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {}, e.code


class TestProfileCreateAPIWithEndpoint:
    _PROFILE_NAME = "test-ep-sprint31"

    def _cleanup(self):
        """Remove the test profile from wherever hermes_cli placed it."""
        home_hermes = pathlib.Path.home() / ".hermes"
        # Walk all profile roots: real ~/.hermes, and any subdirs that might be HERMES_HOME
        roots_to_check = set()
        roots_to_check.add(home_hermes)
        for root, dirs, _ in os.walk(str(home_hermes)):
            if "profiles" in dirs:
                roots_to_check.add(pathlib.Path(root))
            if root.count(os.sep) - str(home_hermes).count(os.sep) > 4:
                break  # don't recurse too deep
        for search_root in roots_to_check:
            candidate = search_root / "profiles" / self._PROFILE_NAME
            if candidate.exists():
                shutil.rmtree(candidate)

    def setup_method(self, _):
        self._cleanup()

    def teardown_method(self, _):
        self._cleanup()

    def test_api_route_accepts_base_url(self, test_server):
        """POST /api/profile/create with base_url returns ok:True."""
        data, err = _post("/api/profile/create", {
            "name": self._PROFILE_NAME,
            "base_url": "http://localhost:11434",
        })
        assert err is None, f"Expected 200, got {err}: {data}"
        assert data.get("ok") is True

    def test_api_route_writes_base_url_to_config(self, test_server):
        """Route accepts base_url and returns profile metadata.

        The actual config.yaml write is covered by the unit tests above.
        """
        data, err = _post("/api/profile/create", {
            "name": self._PROFILE_NAME,
            "base_url": "http://localhost:9999",
        })
        assert err is None, f"Expected 200, got {err}: {data}"
        assert data.get("ok") is True
        assert data.get("profile", {}).get("path"), f"API response missing profile.path: {data}"

    def test_api_route_rejects_invalid_base_url(self, test_server):
        """POST /api/profile/create with a non-http base_url returns 400."""
        data, err = _post("/api/profile/create", {
            "name": self._PROFILE_NAME,
            "base_url": "ftp://localhost:11434",
        })
        assert err == 400, f"Expected 400, got {err}: {data}"


def test_get_settings_exposes_karmabox_flags(monkeypatch):
    import api.config as config
    import api.routes as routes

    captured = {}

    monkeypatch.setattr(routes, "load_settings", lambda: {"bot_name": "KarmaBox", "password_hash": "secret"})
    def _fake_j(handler, data, **kw):
        captured["data"] = data
        return True

    monkeypatch.setattr(routes, "j", _fake_j)
    monkeypatch.setattr(config, "is_karmabox_mode", lambda: True)
    monkeypatch.setattr(config, "get_karmabox_model_base_url", lambda: "https://managed.example.com")

    parsed = types.SimpleNamespace(path="/api/settings")
    assert routes.handle_get(object(), parsed) is True
    assert captured["data"]["bot_name"] == "KarmaBox"
    assert "password_hash" not in captured["data"]
    assert captured["data"]["karmabox_mode"] is True
    assert captured["data"]["karmabox_model_base_url"] == "https://managed.example.com"


def test_get_available_models_marks_managed_profiles(monkeypatch):
    import json as _json
    import api.config as config

    old_cfg = dict(config.cfg)
    old_mtime = config._cfg_mtime
    config.cfg.clear()
    config.cfg.update({
        "model": {
            "provider": "custom",
            "default": "GLM5",
            "base_url": "https://managed.example.com/v1",
            "api_key": "sk-managed",
        },
        "karmabox": {"managed_profile": True},
    })
    try:
        config.invalidate_models_cache()
        try:
            config._cfg_mtime = config.Path(config._get_config_path()).stat().st_mtime
        except Exception:
            config._cfg_mtime = 0.0

        class _Resp:
            def read(self):
                return _json.dumps({"data": [{"id": "GLM5", "name": "GLM5"}]}).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=10: _Resp())
        monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [])

        result = config.get_available_models()
    finally:
        config.cfg.clear()
        config.cfg.update(old_cfg)
        config._cfg_mtime = old_mtime
        config.invalidate_models_cache()

    assert result["managed_profile"] is True
    assert result["allow_custom_model_id"] is False
    assert any(g["provider"] == "AITokenCloud" for g in result["groups"])


def test_managed_profile_allows_karmabox_host_even_if_dns_is_private(monkeypatch):
    import json as _json
    import api.config as config

    old_cfg = dict(config.cfg)
    old_mtime = config._cfg_mtime
    config.cfg.clear()
    config.cfg.update({
        "model": {
            "provider": "custom",
            "base_url": "https://api.aitokencloud.com",
            "api_key": "sk-managed",
        },
        "karmabox": {"managed_profile": True},
    })
    try:
        config.invalidate_models_cache()
        try:
            config._cfg_mtime = config.Path(config._get_config_path()).stat().st_mtime
        except Exception:
            config._cfg_mtime = 0.0

        class _Resp:
            def read(self):
                return _json.dumps({"data": [{"id": "GLM5", "name": "GLM5"}]}).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setenv("KARMABOX_MODE", "true")
        monkeypatch.setenv("KARMABOX_MODEL_BASE_URL", "https://api.aitokencloud.com")
        monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("198.18.142.191", 0))])
        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=10: _Resp())

        result = config.get_available_models()
    finally:
        config.cfg.clear()
        config.cfg.update(old_cfg)
        config._cfg_mtime = old_mtime
        config.invalidate_models_cache()

    model_ids = [m["id"] for g in result["groups"] for m in g.get("models", [])]
    assert "GLM5" in model_ids
    assert any(g["provider"] == "AITokenCloud" for g in result["groups"])
