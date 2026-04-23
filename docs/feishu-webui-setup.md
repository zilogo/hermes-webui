# Feishu / Lark Setup In Hermes WebUI

This guide is the WebUI-oriented version of Feishu / Lark setup. It focuses on:

- what to configure in the Feishu developer console
- what to fill in inside Hermes WebUI
- which settings still live in `~/.hermes/.env`
- how to start or restart the gateway
- the failure modes we actually hit while wiring this up

This document focuses on the WebUI workflow rather than the full adapter
reference.

## How The Pieces Fit Together

Hermes WebUI does not talk to Feishu directly.

The flow is:

1. You configure Feishu credentials in the WebUI Channels panel.
2. The WebUI writes profile-scoped values into that profile's `.env`.
3. Hermes gateway, running inside `hermes-agent`, connects to Feishu/Lark.
4. Inbound Feishu messages are processed by the gateway and routed into Hermes.
5. Hermes sends the reply back through the same gateway.

This means a successful "Test credentials" result in the WebUI only proves that
the App ID and App Secret are valid. It does not prove that:

- the app has the right bot permissions
- the app was published after permission changes
- the gateway was restarted and reloaded the new `.env`
- Feishu is allowed to deliver or send the message you expect

## Recommended Mode

Use `WebSocket` unless you have a strong reason to expose a public callback URL.

`WebSocket`:

- recommended for laptops, workstations, private servers, and Tailscale setups
- does not require public inbound HTTP
- only needs the gateway to establish an outbound connection

`Webhook`:

- useful if you already expose Hermes behind a reachable HTTPS endpoint
- requires webhook host/port/path plus Feishu event callback configuration
- usually requires `FEISHU_ENCRYPT_KEY` and `FEISHU_VERIFICATION_TOKEN`

For most Hermes WebUI installs, `WebSocket` is the simplest and least fragile
choice.

## Prerequisites

Before you start:

- Hermes WebUI must already be running.
- Hermes gateway must be available from the same `hermes-agent` checkout the
  WebUI uses.
- You need a Feishu or Lark custom app with Bot capability enabled.
- You need to know which Hermes profile you are editing.

If you use the WebUI gateway Start / Restart buttons, there is one extra
requirement:

- the gateway service must have been installed once with Hermes CLI

Example:

```bash
export HERMES_HOME=~/.hermes
hermes gateway install
```

On non-default profiles:

```bash
export HERMES_HOME=~/.hermes/profiles/<profile>
hermes gateway install
```

After that one-time install, the WebUI can control the current profile gateway
directly on macOS `launchd` and Linux `systemd` hosts.

## Step 1: Create The Feishu / Lark App

In the Feishu or Lark developer console:

1. Create a new custom app.
2. Enable the Bot capability.
3. Copy the `App ID`.
4. Copy the `App Secret`.
5. Decide whether the app should use:
   - `feishu` domain for Feishu China
   - `lark` domain for Lark international

If you plan to use `Webhook` mode, also note:

- verification token
- encrypt key

## Step 2: Configure Required Events And Permissions

This is the part that most often breaks the integration.

### Minimum Checklist For Plain Text Chat

For a normal "message the bot and get a reply" setup, make sure the app has:

- Bot capability enabled
- event subscription for `im.message.receive_v1`
- at least one outbound send permission:
  - `im:message:send_as_bot`
  - or `im:message`
  - or `im:message:send`

If outbound send permission is missing, Hermes will receive the message, think,
and then fail to reply with an access-denied error.

### Strongly Recommended Permissions

Add one of these so Hermes can resolve bot identity more accurately in group
mentions:

- `application:application:self_manage`
- `admin:app.info:readonly`

Without one of those, direct messages still work, but group `@bot` detection can
be less precise and the gateway may log a warning at startup.

### Optional Media Permissions

If you want Hermes to send images or files back into Feishu, also grant:

- `im:resource`
- or `im:resource:upload`

Without those, plain text can work while file or image sending fails later.

### Webhook-Only Requirements

If you choose `Webhook` mode instead of `WebSocket`, also configure:

- callback URL
- verification token
- encrypt key

And make sure the callback target matches the Hermes gateway webhook endpoint.

Typical webhook-related variables:

```bash
FEISHU_CONNECTION_MODE=webhook
FEISHU_WEBHOOK_HOST=127.0.0.1
FEISHU_WEBHOOK_PORT=8765
FEISHU_WEBHOOK_PATH=/feishu/webhook
FEISHU_ENCRYPT_KEY=your-encrypt-key
FEISHU_VERIFICATION_TOKEN=your-verification-token
```

## Step 3: Publish The App Version

After changing bot capability, events, or permissions, publish the app version.

Do not skip this.

A very common failure mode is:

- credentials test passes
- inbound event is partially working or looks correct in the console
- real chat still fails because the new permission scope was never published

If your org requires admin approval, finish that approval step too.

## Step 4: Fill In Hermes WebUI

Open the WebUI and go to the Channels panel.

Fill in the Feishu / Lark card with:

- `App ID`
- `App secret`
- `Domain`
- `Connection mode`
- optional `Home channel`

Current field mapping:

| WebUI field | Environment variable |
|---|---|
| App ID | `FEISHU_APP_ID` |
| App secret | `FEISHU_APP_SECRET` |
| Domain | `FEISHU_DOMAIN` |
| Connection mode | `FEISHU_CONNECTION_MODE` |
| Home channel | `FEISHU_HOME_CHANNEL` |

Use the `Test` button first. If it passes, save the channel config.

## Step 5: Add The Runtime Policy Settings

The WebUI currently stores the main Feishu credentials, but some runtime policy
switches are still easiest to manage in the profile `.env`.

For an open internal rollout, these settings are useful:

```bash
FEISHU_ALLOW_ALL_USERS=true
FEISHU_GROUP_POLICY=open
```

What they do:

- `FEISHU_ALLOW_ALL_USERS=true`
  allows direct-message usage without maintaining a Feishu user allowlist
- `FEISHU_GROUP_POLICY=open`
  allows group messages from any sender to pass the group policy gate

Important:

- group replies still require an explicit `@bot` mention
- `FEISHU_GROUP_POLICY=open` does not turn group chats into ambient listening

If you prefer a stricter setup, use:

```bash
FEISHU_ALLOWED_USERS=ou_xxx,ou_yyy
FEISHU_GROUP_POLICY=allowlist
```

## Step 6: Start Or Restart The Gateway

The gateway must reload after `.env` changes.

### Option A: Use The WebUI Buttons

If the current host supports WebUI gateway control, use the Feishu / gateway
card's `Start` or `Restart` button.

Current support:

- macOS user-level `launchd`
- Linux `systemd`

If the WebUI says the service is not installed yet, install it once from CLI:

```bash
export HERMES_HOME=~/.hermes
hermes gateway install
```

Then come back to the WebUI and use Start / Restart normally.

### Option B: CLI Fallback

Default profile:

```bash
export HERMES_HOME=~/.hermes
hermes gateway restart
hermes gateway status
```

Non-default profile:

```bash
export HERMES_HOME=~/.hermes/profiles/<profile>
hermes gateway restart
hermes gateway status
```

## Step 7: Verify End-To-End

Use this test order:

1. Send the bot a direct message.
2. Confirm the gateway receives it.
3. Confirm Hermes generates a reply.
4. Confirm Feishu accepts the outbound reply.
5. Then test a group message with an explicit `@bot`.

Useful log files:

- `~/.hermes/logs/agent.log`
- `~/.hermes/logs/errors.log`
- `~/.hermes/logs/gateway.log`
- `~/.hermes/logs/gateway.error.log`

Good signs:

- WebSocket connected successfully
- inbound Feishu message logged
- response generated
- outbound send succeeds

Example success path:

```text
[Feishu] Inbound dm message received ...
gateway.run: inbound message: platform=feishu ...
gateway.run: response ready: platform=feishu ...
[Feishu] Sending response ...
```

## Common Pitfalls We Hit

These are the issues that actually came up while bringing Feishu online through
the WebUI.

### 1. Inbound Works, Outbound Reply Fails

Symptom:

- you send the bot a DM
- Hermes clearly receives it
- no reply appears in Feishu

Typical log:

```text
Access denied. One of the following scopes is required:
[im:message:send, im:message, im:message:send_as_bot]
```

Meaning:

- the app can receive events
- the app cannot send messages back yet

Fix:

- add one of the outbound send permissions
- publish the app version
- restart the gateway

### 2. `im.message.receive_v1` Alone Is Not Enough

This is easy to miss.

`im.message.receive_v1` only covers inbound event delivery. It does not grant
the app permission to send a reply.

If chat feels "silent", always check whether Hermes is failing on the send step
rather than the receive step.

### 3. WebSocket Mode Broke Behind A System SOCKS Proxy

Symptom:

```text
connect failed, err: connecting through a SOCKS proxy requires python-socks
```

Meaning:

- the Feishu SDK is trying to use a SOCKS proxy
- the Hermes Python environment does not have `python-socks`

This can happen even when your shell does not export `HTTP_PROXY`, because on
macOS the runtime may still pick up the system proxy configuration.

Fix:

```bash
/path/to/hermes-agent/.venv/bin/python -m pip install python-socks
```

Then restart the gateway.

### 4. Credentials Test Passed, But Real Chat Still Failed

Meaning:

- App ID and App Secret are valid
- runtime permissions, event config, publish status, or gateway restart are not
  valid yet

The WebUI test checks auth, not the full chat path.

### 5. Group Messages Still Did Not Trigger The Bot

Check all of these:

- the bot is actually in the group
- the message explicitly `@` mentions the bot
- `FEISHU_GROUP_POLICY` is not `disabled`
- if you use `allowlist`, the sender is in `FEISHU_ALLOWED_USERS`
- the app version containing the latest bot permissions was published

### 6. Bot Name / Mention Detection Warning At Startup

Typical warning:

```text
Unable to hydrate bot name from application info.
Grant admin:app.info:readonly or application:application:self_manage ...
```

Fix:

- grant one of those permissions
- publish the app version
- restart the gateway

Direct messages can still work without this, but group mention handling is
better with it.

### 7. Gateway Was Restarted, But Old Errors Were Still In The Log

`gateway.error.log` and `errors.log` are append-only. Old startup failures stay
there after later successful runs.

Do not diagnose Feishu by reading the first matching error in the file. Always
check the newest timestamps.

## Recommended Baseline Configuration

For a simple internal Feishu setup, this is a good starting point:

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=secret_xxx
FEISHU_DOMAIN=feishu
FEISHU_CONNECTION_MODE=websocket
FEISHU_ALLOW_ALL_USERS=true
FEISHU_GROUP_POLICY=open
```

And in the Feishu developer console:

- Bot capability enabled
- `im.message.receive_v1` subscribed
- `im:message:send_as_bot` granted
- `application:application:self_manage` granted
- app version published

## When To Use Webhook Instead

Use `Webhook` mode only if you specifically need Feishu to push events into a
public Hermes endpoint.

That usually means:

- reverse proxy
- public DNS
- HTTPS
- callback URL registration
- `FEISHU_ENCRYPT_KEY`
- `FEISHU_VERIFICATION_TOKEN`

If you do not need those things, `WebSocket` is simpler and usually more robust.

## Related Files And Commands

Useful files:

- `~/.hermes/.env`
- `~/.hermes/config.yaml`
- `~/.hermes/logs/agent.log`
- `~/.hermes/logs/errors.log`
- `~/.hermes/logs/gateway.log`
- `~/.hermes/logs/gateway.error.log`

Useful commands:

```bash
hermes gateway status
hermes gateway start
hermes gateway restart
hermes gateway install
hermes gateway setup
```
