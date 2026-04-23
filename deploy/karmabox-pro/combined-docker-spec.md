# KarmaBox Pro Combined Docker Spec

This document defines the recommended "B plan" deployment target:

- one image
- one container
- both `hermes-agent` and `hermes-webui` inside
- one persistent state root at `/data/.karmabox_pro`

The purpose is to simplify deployment while keeping a clear boundary between:

- immutable application/runtime layers
- mutable user state

## Non-Goals

This spec does not try to:

- make upstream code defaults equal `.karmabox_pro`
- preserve host-service semantics inside the container
- support ad-hoc runtime package installation as the primary update path

## Canonical Runtime Variables

```bash
HERMES_HOME=/data/.karmabox_pro
HERMES_BASE_HOME=/data/.karmabox_pro
HERMES_CONFIG_PATH=/data/.karmabox_pro/config.yaml
HERMES_WEBUI_STATE_DIR=/data/.karmabox_pro/webui
```

Optional runtime variables:

```bash
HERMES_WEBUI_HOST=0.0.0.0
HERMES_WEBUI_PORT=8791
```

## Filesystem Model

Container image contents:

```text
/app/hermes-agent
/app/hermes-webui
/opt/venv
```

Persistent mounts:

```text
/data/.karmabox_pro
/workspace
```

Rules:

- `/data/.karmabox_pro` stores profiles, `.env`, `config.yaml`, skills,
  plugins, logs, and WebUI state
- `/workspace` stores user working files
- application source and Python packages live in the image, not in
  `HERMES_HOME`

## Process Model

Use a real supervisor inside the container.

Recommended first implementation:

- `supervisord`

Managed processes:

1. Hermes gateway
2. Hermes WebUI server

Do not use:

- `tmux`
- background shell hacks
- `systemd` or `launchd` inside the container

## Network Model

Default exposed port:

- `8791` for WebUI

Gateway platform traffic should normally be outbound-only from the container.
If a platform later requires inbound callbacks, expose that separately and
document it explicitly.

## Update Boundary

There are two update classes.

### 1. Image Upgrades

Rebuild the image when changing:

- `hermes-agent` version
- `hermes-webui` version
- Python dependencies
- Node dependencies
- bundled skills that ship with the repos
- system packages required by the runtime

This is the canonical path for upgrading the core application stack.

### 2. Persistent Content Updates

Update in the mounted data volume when changing:

- `.env`
- `config.yaml`
- profile data
- hub-installed skills in `/data/.karmabox_pro/skills/`
- plugins in `/data/.karmabox_pro/plugins/`

This content survives container replacement.

## Skills And Plugin Policy

Bundled skills:

- shipped by the image
- updated with the image

Hub-installed skills:

- live in `HERMES_HOME`
- may be updated in place with:

```bash
hermes skills check
hermes skills update
hermes skills audit
```

Plugins:

- live in `HERMES_HOME/plugins`
- are not assumed to be upgraded by `hermes update`
- may require plugin-specific dependency installation

Operational rule:

- do not use in-container ad-hoc `pip install` as the default maintenance path
  for production

If a plugin introduces heavy or broadly shared dependencies, fold them into the
next image build instead.

## WebUI Gateway Controls In Container Mode

Current WebUI gateway controls were designed around host service managers such
as `launchd` and `systemd`.

That does not map directly to the combined container model.

Recommended rollout:

### Phase 1

- supervisor auto-starts gateway and WebUI
- container mode exposes gateway status as read-only
- host-service specific `start/restart` controls are hidden or disabled

### Phase 2

- add container-mode control endpoints
- map WebUI actions to `supervisorctl start|restart|status`

## Health Checks

A healthy container should satisfy both:

1. WebUI HTTP endpoint responds
2. gateway process is supervisor-managed and running

Typical health check behavior:

- HTTP probe to `http://127.0.0.1:8791/`
- supervisor status probe for `gateway`

## Build Strategy

The combined image should:

1. copy both repositories into the build context
2. create one Python environment
3. install `hermes-agent`
4. install `hermes-webui`
5. install required Node dependencies or prebuilt UI assets
6. set the canonical container environment defaults

Avoid runtime installation from a mounted source tree such as:

```text
/home/.../.hermes/hermes-agent
```

The image should be self-contained.

## Recommended Next Artifacts

Implementation should add:

- `Dockerfile.combined`
- `docker/entrypoint.combined.sh`
- `docker/supervisord.combined.conf`
- `docker-compose.combined.yml`

The first implementation goal is stability, not maximum flexibility.
