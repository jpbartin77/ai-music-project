"""
webex_delivery.py — Posts a coaching report as a Webex Adaptive Card.

Configuration via environment variables (all injected via op run):
  WEBEX_BOT_TOKEN  — bot token from developer.webex.com
  WEBEX_ROOM_ID    — ID of the space the bot has been added to

Usage:
  # List rooms the bot is in (to find WEBEX_ROOM_ID):
  op run --env-file=.env.tpl -- python src/webex_delivery.py --list-rooms

  # Post a card (called automatically from coach_agent.py):
  op run --env-file=.env.tpl -- python src/webex_delivery.py
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

import requests


WEBEX_API = "https://webexapis.com/v1"


def _headers() -> dict:
    token = os.environ.get("WEBEX_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("WEBEX_BOT_TOKEN environment variable is not set")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def list_rooms() -> None:
    """Print all rooms the bot is a member of."""
    req = urllib.request.Request(f"{WEBEX_API}/rooms", headers=_headers())
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    rooms = data.get("items", [])
    if not rooms:
        print("Bot is not in any rooms. Add it to a Webex space first.")
        return
    print(f"\n{'='*60}")
    print(f"  Rooms the bot belongs to ({len(rooms)} found)")
    print(f"{'='*60}")
    for r in rooms:
        print(f"  Name : {r.get('title', '(no title)')}")
        print(f"  ID   : {r['id']}")
        print()
    print("Set WEBEX_ROOM_ID in .env.tpl to the ID above.")


def _trend_color(trend: str) -> str:
    return {"improving": "Good", "stable": "Warning", "needs_attention": "Attention"}.get(trend, "Default")


def _bullets(items: list[str]) -> str:
    return "\n".join(f"• {item}" for item in items) if items else "—"


def build_card(report: dict) -> dict:
    trend        = report.get("trend", "stable")
    trend_color  = _trend_color(trend)
    trend_emoji  = {"improving": "📈", "stable": "➡️", "needs_attention": "⚠️"}.get(trend, "")
    milestone    = report.get("milestone", "")

    body = [
        {
            "type": "TextBlock",
            "text": "🎹 Piano Practice — Coaching Report",
            "size": "Large",
            "weight": "Bolder",
            "color": "Accent",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": report.get("summary", ""),
            "wrap": True,
            "spacing": "Medium",
        },
        {
            "type": "ColumnSet",
            "spacing": "Medium",
            "columns": [
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [{
                        "type": "TextBlock",
                        "text": f"{trend_emoji} Trend: **{trend.replace('_', ' ').title()}**",
                        "color": trend_color,
                        "wrap": True,
                    }],
                }
            ],
        },
        {
            "type": "TextBlock",
            "text": report.get("trend_detail", ""),
            "wrap": True,
            "isSubtle": True,
            "size": "Small",
        },
        {
            "type": "TextBlock",
            "text": "✅ Strengths",
            "weight": "Bolder",
            "spacing": "Medium",
        },
        {
            "type": "TextBlock",
            "text": _bullets(report.get("strengths", [])),
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "🎯 Focus Areas",
            "weight": "Bolder",
            "spacing": "Medium",
        },
        {
            "type": "TextBlock",
            "text": _bullets(report.get("focus_areas", [])),
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "Next session:",
            "weight": "Bolder",
            "spacing": "Medium",
        },
        {
            "type": "TextBlock",
            "text": report.get("suggested_next_session", ""),
            "wrap": True,
            "color": "Accent",
        },
    ]

    if milestone:
        body.append({
            "type": "TextBlock",
            "text": f"🏆 {milestone}",
            "wrap": True,
            "weight": "Bolder",
            "color": "Good",
            "spacing": "Medium",
        })

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.2",
        "body": body,
    }


def _post_adaptive_card(room_id: str, card: dict, markdown: str) -> dict:
    """Post the Adaptive Card via JSON. Returns the parsed Webex response."""
    payload = json.dumps({
        "roomId": room_id,
        "markdown": markdown,
        "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
    }).encode()
    req = urllib.request.Request(
        f"{WEBEX_API}/messages",
        data=payload,
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _post_file(room_id: str, file_path: Path, markdown: str) -> dict:
    """Post a file attachment via multipart. Returns the parsed Webex response."""
    token = os.environ.get("WEBEX_BOT_TOKEN", "")
    with open(file_path, "rb") as fh:
        resp = requests.post(
            f"{WEBEX_API}/messages",
            headers={"Authorization": f"Bearer {token}"},
            data={"roomId": room_id, "markdown": markdown},
            files={"files": (file_path.name, fh, "image/png")},
            timeout=30,
        )
    if not resp.ok:
        print(f"  [webex] File post failed: {resp.status_code} — {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()


def post_card(report: dict, attachment: Path | str | None = None) -> None:
    """
    Post the coaching Adaptive Card to Webex.

    Webex's API doesn't accept Adaptive Card attachments and file uploads in the
    same multipart request, so when `attachment` is provided we send two messages
    in sequence: the card first (headline), then the chart (supporting visual).
    """
    room_id = os.environ.get("WEBEX_ROOM_ID", "")
    if not room_id:
        raise RuntimeError("WEBEX_ROOM_ID environment variable is not set — run with --list-rooms to find it")

    card     = build_card(report)
    markdown = f"🎹 **Piano Practice Report** — {report.get('summary', '')}"

    card_result = _post_adaptive_card(room_id, card, markdown)
    print(f"  [webex] Card posted -- message id: {card_result.get('id', '?')}")

    if attachment:
        attachment = Path(attachment)
        if not attachment.exists():
            print(f"  [webex] Attachment {attachment} missing — skipping chart post.")
            return
        chart_result = _post_file(room_id, attachment, "📊 Practice charts")
        print(f"  [webex] Chart posted -- message id: {chart_result.get('id', '?')}")


if __name__ == "__main__":
    if "--list-rooms" in sys.argv:
        list_rooms()
    else:
        # Quick test with a dummy report
        dummy = {
            "summary": "Test card — if you see this in Webex the delivery pipeline is working.",
            "strengths": ["Delivery pipeline connected", "Adaptive Card rendering correctly"],
            "focus_areas": ["This is a test — run coach_agent.py for real feedback"],
            "suggested_next_session": "Run: op run --env-file=.env.tpl -- python src/coach_agent.py",
            "trend": "improving",
            "trend_detail": "Test message only — no real session data.",
            "milestone": "",
        }
        post_card(dummy)
