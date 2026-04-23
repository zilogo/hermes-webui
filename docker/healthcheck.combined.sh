#!/bin/bash
set -euo pipefail

CONF="/opt/hermes/hermes-webui/docker/supervisord.combined.conf"
PORT="${HERMES_WEBUI_PORT:-8791}"

supervisorctl -c "$CONF" status gateway | grep -q "RUNNING"
supervisorctl -c "$CONF" status webui | grep -q "RUNNING"
curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null
