"""
mcp_server.py — Exposes Splunk practice data as MCP tools for Claude.

Tools:
  get_recent_sessions    — last N session summaries
  get_session_detail     — full note-level data for one session
  get_finger_trends      — per-finger timing history across sessions
  compare_hands          — LH vs RH speed/evenness delta for a session
  get_scale_history      — speed and evenness trend for a specific scale

Configuration via environment variables:
  SPLUNK_URL    — e.g. https://198.18.135.50:8089
  SPLUNK_TOKEN  — Splunk API token (not HEC token)
  SPLUNK_INDEX  — default: edge_hub_mqtt

Run:
  python src/mcp_server.py
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import ssl

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

SPLUNK_URL   = os.environ.get("SPLUNK_URL",   "https://198.18.135.50:8089")
SPLUNK_TOKEN = os.environ.get("SPLUNK_TOKEN",  "")
SPLUNK_INDEX = os.environ.get("SPLUNK_INDEX",  "edge_hub_mqtt")

# Accept self-signed cert in the lab environment
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def splunk_search(spl: str, max_results: int = 100) -> list[dict]:
    """Run a blocking SPL search and return results as a list of dicts."""
    if not SPLUNK_TOKEN:
        raise RuntimeError("SPLUNK_TOKEN environment variable is not set")

    headers = {
        "Authorization": f"Splunk {SPLUNK_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # Create search job
    body = urllib.parse.urlencode({
        "search": f"search {spl}",
        "output_mode": "json",
        "exec_mode": "blocking",
        "count": str(max_results),
    }).encode()

    req = urllib.request.Request(
        f"{SPLUNK_URL}/services/search/jobs",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, context=SSL_CTX) as resp:
        job = json.loads(resp.read())
    sid = job["sid"]

    # Fetch results
    results_req = urllib.request.Request(
        f"{SPLUNK_URL}/services/search/jobs/{sid}/results?output_mode=json&count={max_results}",
        headers=headers,
    )
    with urllib.request.urlopen(results_req, context=SSL_CTX) as resp:
        data = json.loads(resp.read())

    return data.get("results", [])


def extract_session_fields(row: dict) -> dict:
    """Flatten spath-extracted fields from a session result row."""
    return {
        "time":               row.get("_time", ""),
        "session_id":         row.get("session_id", ""),
        "scale":              row.get("scale", ""),
        "scale_display":      row.get("scale_display", ""),
        "segment_index":      row.get("segment_index", ""),
        "rh_speed_bpm":       row.get("metrics.right.speed_bpm", ""),
        "rh_evenness_cv_pct": row.get("metrics.right.evenness_cv_pct", ""),
        "rh_evenness_std_ms": row.get("metrics.right.evenness_stddev_ms", ""),
        "lh_speed_bpm":       row.get("metrics.left.speed_bpm", ""),
        "lh_evenness_cv_pct": row.get("metrics.left.evenness_cv_pct", ""),
        "lh_evenness_std_ms": row.get("metrics.left.evenness_stddev_ms", ""),
    }


server = Server("piano-coach")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_recent_sessions",
            description="Get the last N practice session summaries including speed and evenness scores for both hands.",
            inputSchema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of sessions to return (default 10)", "default": 10}
                },
            },
        ),
        types.Tool(
            name="get_session_detail",
            description="Get full note-level data for a specific session including per-note finger, timing, and velocity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "The session_id to retrieve"}
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="get_finger_trends",
            description="Get per-finger average timing deviation across recent sessions for a given scale and hand. Lower deviation = more even.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scale":         {"type": "string", "description": "Scale name e.g. c_major"},
                    "hand":          {"type": "string", "description": "left or right"},
                    "sessions_back": {"type": "integer", "description": "How many recent sessions to include (default 10)", "default": 10},
                },
                "required": ["scale", "hand"],
            },
        ),
        types.Tool(
            name="compare_hands",
            description="Compare left hand vs right hand speed and evenness for a specific session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "The session_id to compare"}
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="get_scale_history",
            description="Get speed and evenness trend over all recorded sessions for a specific scale.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scale": {"type": "string", "description": "Scale name e.g. c_major"}
                },
                "required": ["scale"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = _dispatch(name, arguments)
    except Exception as e:
        result = {"error": str(e)}
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _dispatch(name: str, args: dict) -> dict | list:
    if name == "get_recent_sessions":
        count = args.get("count", 10)
        rows = splunk_search(
            f'index={SPLUNK_INDEX} source="piano/sessions" '
            f'| spath input=event '
            f'| table _time session_id scale scale_display segment_index '
            f'  "metrics.right.speed_bpm" "metrics.right.evenness_cv_pct" "metrics.right.evenness_stddev_ms" '
            f'  "metrics.left.speed_bpm" "metrics.left.evenness_cv_pct" "metrics.left.evenness_stddev_ms" '
            f'| sort -_time | head {count}',
            max_results=count,
        )
        return [extract_session_fields(r) for r in rows]

    elif name == "get_session_detail":
        sid = args["session_id"]
        rows = splunk_search(
            f'index={SPLUNK_INDEX} source="piano/notes" session_id="{sid}" '
            f'| spath input=event '
            f'| table _time hand name midi finger velocity time_ms '
            f'| sort _time',
            max_results=500,
        )
        return rows

    elif name == "get_finger_trends":
        scale = args["scale"]
        hand  = args["hand"]
        n     = args.get("sessions_back", 10)
        rows = splunk_search(
            f'index={SPLUNK_INDEX} source="piano/notes" '
            f'| spath input=event '
            f'| search scale="{scale}" hand="{hand}" finger!=null finger!="null" '
            f'| eventstats avg(time_ms) as session_mean_ms by session_id '
            f'| eval deviation_ms=time_ms-session_mean_ms '
            f'| stats avg(deviation_ms) as avg_deviation_ms, '
            f'        count as note_count by finger '
            f'| eval avg_deviation_ms=round(avg_deviation_ms,2) '
            f'| sort finger',
            max_results=20,
        )
        return rows

    elif name == "compare_hands":
        sid = args["session_id"]
        rows = splunk_search(
            f'index={SPLUNK_INDEX} source="piano/sessions" session_id="{sid}" '
            f'| spath input=event '
            f'| table _time session_id scale scale_display segment_index '
            f'  "metrics.right.speed_bpm" "metrics.right.evenness_cv_pct" "metrics.right.evenness_stddev_ms" '
            f'  "metrics.left.speed_bpm" "metrics.left.evenness_cv_pct" "metrics.left.evenness_stddev_ms" '
            f'| sort -_time',
            max_results=20,
        )
        return [extract_session_fields(r) for r in rows]

    elif name == "get_scale_history":
        scale = args["scale"]
        rows = splunk_search(
            f'index={SPLUNK_INDEX} source="piano/sessions" '
            f'| spath input=event '
            f'| search scale="{scale}" '
            f'| table _time session_id scale scale_display segment_index '
            f'  "metrics.right.speed_bpm" "metrics.right.evenness_cv_pct" "metrics.right.evenness_stddev_ms" '
            f'  "metrics.left.speed_bpm" "metrics.left.evenness_cv_pct" "metrics.left.evenness_stddev_ms" '
            f'| sort _time',
            max_results=100,
        )
        return [extract_session_fields(r) for r in rows]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
