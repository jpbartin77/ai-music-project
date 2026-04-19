# Webex Card Delivery (April 18, 2026)

## Summary

`src/webex_delivery.py` formats a coaching report as a Webex Adaptive Card and posts it
to a Webex space via the Webex REST API. The card renders beautifully in the Webex desktop
and mobile clients with color-coded trend indicators, bullet lists, and a milestone callout.

---

## Setup

### 1. Create a Webex bot

1. Go to [developer.webex.com](https://developer.webex.com) → My Webex Apps → Create a New App → Bot
2. Give the bot a name and icon (bot icon saved at `plan/ai-music-coach_webex-bot_icon.png`)
3. Copy the bot token — save it to 1Password immediately (see `2026-04-18_1password.md`)

### 2. Add the bot to a Webex space

Add the bot as a participant in the target Webex space. The bot can only post to spaces
it has been explicitly added to.

### 3. Find the room ID

```bash
op run --env-file=.env.tpl -- python src/webex_delivery.py --list-rooms
```

This calls `GET /v1/rooms` with the bot token and prints all spaces the bot is in.
Copy the room ID and add it to `.env.tpl` as `WEBEX_ROOM_ID`.

---

## Architecture

```
coach_agent.py → post_card(report)
  → build_card(report) → Adaptive Card JSON
  → POST https://webexapis.com/v1/messages
      Authorization: Bearer <WEBEX_BOT_TOKEN>
      body: { roomId, markdown, attachments: [{ adaptive card }] }
```

The `markdown` field is included as a fallback for clients that don't render Adaptive Cards.
It contains the summary text prefixed with `🎹 **Piano Practice Report**`.

---

## Card layout

The Adaptive Card body (version 1.2) is structured as:

| Section | Content |
|---------|---------|
| Header | "🎹 Piano Practice — Coaching Report" (large, accent color) |
| Summary | 2-3 sentence assessment from Claude |
| Trend | Color-coded badge: 📈 Improving (green) / ➡️ Stable (yellow) / ⚠️ Needs Attention (red) |
| Trend detail | Subtle 1-2 sentences on the driving metric |
| Strengths | Bulleted list (`• item`) |
| Focus areas | Bulleted list (`• item`) |
| Next session | Actionable instruction in accent color |
| Milestone | Gold bold callout — only shown if `milestone` field is non-empty |

Trend color mapping:
```python
{"improving": "Good", "stable": "Warning", "needs_attention": "Attention"}
```
These are Adaptive Card color names (not hex) — they adapt to the client's theme.

---

## Standalone test

```bash
op run --env-file=.env.tpl -- python src/webex_delivery.py
```

Posts a dummy report card to the configured room. Use this to verify bot token and room ID
are correct before running the full coaching pipeline.

---

## Environment variables

| Variable | Source | Description |
|----------|--------|-------------|
| `WEBEX_BOT_TOKEN` | 1Password (op://) | Bot token from developer.webex.com |
| `WEBEX_ROOM_ID` | `.env.tpl` (plaintext) | Space ID — not a secret, hardcoded is fine |

---

## Confirmed working

End-to-end test on April 18, 2026:
- Full coaching report rendered as Adaptive Card in Webex
- Trend badge showed "📈 Improving" in green
- Strengths and focus areas rendered as bullet lists
- Gold "🏆" milestone callout appeared for 286 BPM personal best
- Fallback markdown also visible for non-card clients
