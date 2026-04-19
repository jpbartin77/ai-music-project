# 1Password Secrets Management (April 18, 2026)

## Summary

All API keys are stored in 1Password and injected at runtime via the `op` CLI.
Nothing sensitive is ever written to disk or committed to git.

---

## How it works

`.env.tpl` contains 1Password secret references, not real values:

```
ANTHROPIC_API_KEY=op://Private/claude_api_key_vscode/credential
SPLUNK_TOKEN=op://Private/dcloud splunk api token/credential
WEBEX_BOT_TOKEN=op://Private/43s5ntukc25q7zonpo4wvtjnh4/credential
```

At runtime, `op run` resolves each reference to the real secret and injects it as an
environment variable into the child process:

```bash
op run --env-file=.env.tpl -- python src/coach_agent.py
```

The child process sees `ANTHROPIC_API_KEY`, `SPLUNK_TOKEN`, etc. as normal env vars.
No temp files are written. The `.env.tpl` file itself contains no secrets and is safe
to commit to git.

---

## Secret item reference format

```
op://<vault>/<item-name-or-uuid>/<field>
```

- **Vault:** `Private` (all secrets in the user's personal vault)
- **Item name:** Use the exact item name in 1Password, or the item UUID
- **Field:** Almost always `credential` for API tokens

### Gotcha: special characters in item names

Item names with parentheses, slashes, or spaces that can't be percent-encoded will be
rejected by `op run`. If you get an error like "invalid character '('" in the reference:

Use the item's UUID instead of its name:
```bash
op item get "ai-music-coach-bot-token (webex)" --fields id
# returns: 43s5ntukc25q7zonpo4wvtjnh4
```

Then reference it as:
```
WEBEX_BOT_TOKEN=op://Private/43s5ntukc25q7zonpo4wvtjnh4/credential
```

---

## Items in 1Password (Private vault)

| Item name | Reference used in .env.tpl | Used by |
|-----------|---------------------------|---------|
| `claude_api_key_vscode` | `op://Private/claude_api_key_vscode/credential` | `coach_agent.py` → Anthropic API |
| `dcloud splunk api token` | `op://Private/dcloud splunk api token/credential` | `mcp_server.py` → Splunk REST |
| `ai-music-coach-bot-token (webex)` | `op://Private/43s5ntukc25q7zonpo4wvtjnh4/credential` | `webex_delivery.py` → Webex API |

---

## Non-secret config (hardcoded in .env.tpl)

```
WEBEX_ROOM_ID=Y2lzY29zcGFyazovL3VzL1JPT00vODFhZjMzZDAtM2I4OC0xMWYxLWI0M2MtM2YzODEyYjMyMTcz
SPLUNK_URL=https://198.18.135.50:8089
SPLUNK_INDEX=edge_hub_mqtt
MQTT_HOST=198.18.133.101
MQTT_PORT=1883
```

These are configuration values (not credentials) and are safe in the template file.

---

## Prerequisites

- `op` CLI installed: [1password.com/downloads/command-line](https://1password.com/downloads/command-line/)
- Signed in: `op signin` (uses system keychain, persists across sessions)
- Items added to the Private vault via 1Password desktop app

---

## Future: Cloud Run

For Cloud Run, the `op` CLI approach won't work directly (no interactive sign-in in a
container). Two options:

1. **Google Secret Manager** — native GCP integration. Store secrets there and reference
   them in the Cloud Run service definition. No 1Password dependency in production.
2. **1Password Service Account** — non-interactive `op` auth for CI/CD. More complex.

Recommended: Google Secret Manager for Cloud Run, 1Password for local dev.
