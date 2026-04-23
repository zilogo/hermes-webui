#!/bin/bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/data/.karmabox_pro}"
HERMES_WEBUI_STATE_DIR="${HERMES_WEBUI_STATE_DIR:-$HERMES_HOME/webui}"
HERMES_WEBUI_DEFAULT_WORKSPACE="${HERMES_WEBUI_DEFAULT_WORKSPACE:-/workspace}"
INSTALL_ROOT="/opt/hermes"
AGENT_DIR="$INSTALL_ROOT/hermes-agent"
WEBUI_DIR="$INSTALL_ROOT/hermes-webui"
SUPERVISOR_CONF="$WEBUI_DIR/docker/supervisord.combined.conf"

if [ "$(id -u)" = "0" ]; then
    if [ -n "${HERMES_UID:-}" ] && [ "$HERMES_UID" != "$(id -u hermes)" ]; then
        usermod -u "$HERMES_UID" hermes
    fi

    if [ -n "${HERMES_GID:-}" ] && [ "$HERMES_GID" != "$(id -g hermes)" ]; then
        groupmod -o -g "$HERMES_GID" hermes 2>/dev/null || true
    fi

    mkdir -p "$HERMES_HOME" "$HERMES_WEBUI_STATE_DIR" "$HERMES_WEBUI_DEFAULT_WORKSPACE"
    chown -R hermes:hermes "$HERMES_HOME" "$HERMES_WEBUI_STATE_DIR" 2>/dev/null || true
    chown -R hermes:hermes "$HERMES_WEBUI_DEFAULT_WORKSPACE" 2>/dev/null || true

    exec gosu hermes "$0" "$@"
fi

mkdir -p \
    "$HERMES_HOME/cron" \
    "$HERMES_HOME/home" \
    "$HERMES_HOME/hooks" \
    "$HERMES_HOME/logs" \
    "$HERMES_HOME/memories" \
    "$HERMES_HOME/plans" \
    "$HERMES_HOME/plugins" \
    "$HERMES_HOME/profiles" \
    "$HERMES_HOME/sessions" \
    "$HERMES_HOME/skills" \
    "$HERMES_HOME/skins" \
    "$HERMES_HOME/workspace" \
    "$HERMES_WEBUI_STATE_DIR" \
    "$HERMES_WEBUI_DEFAULT_WORKSPACE"

if [ ! -f "$HERMES_HOME/.env" ]; then
    cp "$AGENT_DIR/.env.example" "$HERMES_HOME/.env"
fi

if [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cp "$AGENT_DIR/cli-config.yaml.example" "$HERMES_HOME/config.yaml"
fi

if [ ! -f "$HERMES_HOME/SOUL.md" ]; then
    cp "$AGENT_DIR/docker/SOUL.md" "$HERMES_HOME/SOUL.md"
fi

if [ -d "$AGENT_DIR/skills" ]; then
    /opt/venv/bin/python "$AGENT_DIR/tools/skills_sync.py"
fi

exec /usr/bin/supervisord -c "$SUPERVISOR_CONF"
