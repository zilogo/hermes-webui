from pathlib import Path


def test_channels_assets_are_wired_into_index():
    html = Path("static/index.html").read_text(encoding="utf-8")

    assert 'data-panel="channels"' in html
    assert 'id="panelChannels"' in html
    assert 'src="static/channels.js"' in html
    assert 'src="static/vendor/qrcode.min.js"' in html


def test_channels_panel_logic_is_hooked_into_sidebar_switching():
    panels = Path("static/panels.js").read_text(encoding="utf-8")
    channels = Path("static/channels.js").read_text(encoding="utf-8")
    i18n = Path("static/i18n.js").read_text(encoding="utf-8")
    routes = Path("api/channels/__init__.py").read_text(encoding="utf-8")
    top_routes = Path("api/routes.py").read_text(encoding="utf-8")

    assert "name === 'channels'" in panels
    assert "loadChannelsPanel" in panels
    assert "setChannelsAvailability" in panels
    assert "hermes.weixin.ilink_risk_acknowledged:" in channels
    assert "startGateway" in channels
    assert "restartGateway" in channels
    assert "/api/gateway/start" in routes
    assert "/api/gateway/restart" in routes
    assert '"/api/gateway/start"' in top_routes
    assert '"/api/gateway/restart"' in top_routes
    assert "weixin_ilink_warning_title" in i18n
    assert "weixin_ilink_warning_acknowledge" in i18n
    assert "channels_gateway_start" in i18n
    assert "channels_gateway_restart_confirm_title" in i18n
    assert "channels_gateway_service_status" in i18n
    assert "channels_gateway_service_expected_path" in i18n


def test_boot_fetches_auth_status_for_channels_gate():
    boot = Path("static/boot.js").read_text(encoding="utf-8")

    assert "/api/auth/status" in boot
    assert "refreshChannelsAvailability" in boot
