"""
Quick smoke test for MCP server tools — calls each tool directly without
starting the MCP server. Run this to verify Splunk connectivity and field paths.

Usage:
    $env:SPLUNK_TOKEN = "your-token-here"
    python tools/test_mcp_tools.py
"""

import sys, os, json
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent / 'src'))
from mcp_server import _dispatch, SPLUNK_URL, SPLUNK_TOKEN

def show(label, result):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)
    print(json.dumps(result, indent=2)[:2000])

if not SPLUNK_TOKEN:
    print("ERROR: SPLUNK_TOKEN not set. Run: $env:SPLUNK_TOKEN = 'your-token'")
    sys.exit(1)

print(f"Connecting to {SPLUNK_URL} ...")

sessions = _dispatch("get_recent_sessions", {"count": 5})
show("get_recent_sessions (last 5)", sessions)

if sessions and sessions[0].get("session_id"):
    sid = sessions[0]["session_id"]
    scale = sessions[0].get("scale", "c_major")

    show("compare_hands", _dispatch("compare_hands", {"session_id": sid}))
    show("get_session_detail (first 5 notes)", _dispatch("get_session_detail", {"session_id": sid})[:5])
    show("get_scale_history", _dispatch("get_scale_history", {"scale": scale}))
    show("get_finger_trends (right hand)", _dispatch("get_finger_trends", {"scale": scale, "hand": "right"}))
else:
    print("\nNo sessions found — check SPLUNK_INDEX or run practice_session.py first.")
