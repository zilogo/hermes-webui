# KarmaBox Pro Deployment Templates

This directory defines a single deployment convention:

- Hermes root directory is `~/.karmabox_pro` on host machines
- container deployments use `/data/.karmabox_pro`
- all entrypoints receive the same 4 environment variables

The goal is to avoid editing upstream default paths in code. Instead, every
launcher injects the same environment explicitly.

## Scope

This convention applies to:

- `hermes-agent`
- `hermes-webui`
- host shells
- `launchd`
- `systemd`
- Docker / Compose deployments

It does **not** rely on changing upstream fallback paths such as `~/.hermes`.
Those defaults remain untouched; this directory standardizes how deployments
override them.

## Canonical Variables

Host machines:

```bash
HERMES_HOME=$HOME/.karmabox_pro
HERMES_BASE_HOME=$HOME/.karmabox_pro
HERMES_CONFIG_PATH=$HOME/.karmabox_pro/config.yaml
HERMES_WEBUI_STATE_DIR=$HOME/.karmabox_pro/webui
```

Containers:

```bash
HERMES_HOME=/data/.karmabox_pro
HERMES_BASE_HOME=/data/.karmabox_pro
HERMES_CONFIG_PATH=/data/.karmabox_pro/config.yaml
HERMES_WEBUI_STATE_DIR=/data/.karmabox_pro/webui
```

## Canonical Directory Layout

Host machines:

```text
~/.karmabox_pro/
  config.yaml
  .env
  SOUL.md
  logs/
  sessions/
  skills/
  plugins/
  profiles/
  webui/
```

Containers:

```text
/data/.karmabox_pro/
  config.yaml
  .env
  SOUL.md
  logs/
  sessions/
  skills/
  plugins/
  profiles/
  webui/
```

The data directory is the persistent root. Runtime processes should treat it as
state, not as an installation target for the core application itself.

## Files

- `env.sh.example`
  Local shell source file. Use this as the single source of truth for local
  interactive shells and wrapper scripts.
- `env.systemd.example`
  Linux `EnvironmentFile=` format.
- `env.docker.example`
  Docker Compose `env_file:` format.
- `launchd/*.example`
  macOS wrapper scripts for `launchd` services. `launchd` does not read shell
  rc files, so these wrappers source `env.sh`.
- `systemd/*.example`
  Linux unit templates that consume `env.systemd`.

## Recommended Host Setup

1. Copy `env.sh.example` to `~/.config/karmabox_pro/env.sh`
2. Adjust absolute repo paths
3. Add this one line to `~/.zshrc`:

```bash
[ -f "$HOME/.config/karmabox_pro/env.sh" ] && source "$HOME/.config/karmabox_pro/env.sh"
```

4. Source the file in any manual shell before running `hermes` or `server.py`

## Recommended Runtime Split

Keep deployment responsibilities separated:

- application code and core Python/Node dependencies
  Managed by the repo checkout or container image
- persistent state and user content
  Managed under `HERMES_HOME`
- service wiring
  Managed by `launchd`, `systemd`, or Docker

This separation matters because skills, plugins, and base runtime libraries do
not update through the same mechanism.

## Recommended Service Pattern

- `launchd`: run a wrapper script that sources `env.sh`, then `exec`s the real
  command
- `systemd`: use `EnvironmentFile=%h/.config/karmabox_pro/env.systemd`
- `docker compose`: mount the data directory and pass `env.docker`

## Update Policy

Treat updates as four separate layers:

1. Agent / WebUI code and bundled runtime dependencies
   Update through a repo refresh or a rebuilt container image. This includes
   Python packages, Node packages, and bundled skills that ship with the code.
2. Bundled skills
   Update together with the application version. Do not patch them in place as
   if they were an independent package feed.
3. Hub-installed or local skills in `$HERMES_HOME/skills/`
   Update separately from the application runtime.
4. Plugins in `$HERMES_HOME/plugins/`
   Update separately from both the application and Skills Hub content.

### Agent / WebUI Runtime

For source deployments, the canonical update entrypoint is:

```bash
hermes update
```

That path is preferred over a manual `git pull` because it also refreshes:

- Python dependencies
- Node dependencies
- bundled skills sync
- Web UI build artifacts

For container deployments, the canonical update entrypoint is a new image
build. Do not rely on in-place `pip install` inside a running production
container to upgrade the base runtime.

### Skills

Hub-installed skills are independent content under `$HERMES_HOME/skills/`.
Recommended operations:

```bash
hermes skills check
hermes skills update
hermes skills audit
```

Use these for hub content. Do not use them as a replacement for upgrading the
base agent runtime.

### Plugins

Plugins are a separate layer under `$HERMES_HOME/plugins/`. They may need:

- a plugin source update
- extra Python dependencies
- extra external tools

Do not assume `hermes update` upgrades plugin repositories or their custom
dependencies. Each plugin should carry its own install or upgrade instructions.

## Operational Rules

- Do not treat `~/.zshrc` as the system of record. It is only one consumer of
  the shared environment file.
- Do not write application code into `HERMES_HOME`.
- Do not make `HERMES_HOME` serve as a mutable substitute for a proper image or
  virtualenv update process.
- Prefer rebuilding an image over mutating production Python environments
  interactively.

## Docker Guidance

The recommended combined-container target is documented in:

- [`combined-docker-spec.md`](./combined-docker-spec.md)

That document defines the single-image / single-container `KarmaBox Pro`
deployment shape and the update boundary between image contents and persistent
state.

## Important Constraint

Do not rely on `~/.zshrc` as the only configuration source. It only affects
interactive shells. Service managers and containers need explicit environment
injection.
