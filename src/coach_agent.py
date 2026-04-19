"""
coach_agent.py — Agentic Claude session that analyzes a practice session
and returns structured coaching feedback.

Claude is given MCP tools to query Splunk directly. It autonomously decides
what to look up before generating its coaching report.

Usage (standalone):
    $env:ANTHROPIC_API_KEY = "..."
    $env:SPLUNK_TOKEN       = "..."
    $env:SPLUNK_URL         = "https://198.18.135.50:8089"
    python src/coach_agent.py [session_id]

    If session_id is omitted, uses the most recent session in Splunk.
"""

import asyncio
import json
import os
import sys
import pathlib

import anthropic

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mcp_server import _dispatch
from webex_delivery import post_card

MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = """You are an expert piano practice coach analyzing a student's scale practice data.

You have access to tools that query the student's full practice history in Splunk.
When given a new session, autonomously investigate the data to build context before writing feedback:
- Use get_recent_sessions to understand the broader trend across the last several sessions
- Use compare_hands on the current session to identify any left/right imbalance
- Use get_scale_history for the scale just practiced to see if speed and evenness are trending
- Use get_finger_trends if you want to identify which fingers are consistently late or early

The most important thing to communicate is progress over time — not just how today went,
but whether the student is measurably improving. Concrete comparisons ("your evenness improved
18% over the last 5 sessions") are far more valuable than generic encouragement.

Key metrics to reason about:
- speed_bpm: higher is faster. Typical beginner range 120-200 BPM, advancing 200-300+
- evenness_cv_pct: coefficient of variation — LOWER is better (more even timing)
- evenness_std_ms: standard deviation of inter-note intervals in ms — LOWER is better
- segment_index: segments within one session — later segments often show fatigue or warmup effects

After gathering enough context (3-5 tool calls is usually sufficient), write your coaching report.

Return ONLY a valid JSON object with exactly these fields — no markdown, no explanation outside the JSON:
{
  "summary": "2-3 sentence overall assessment including trend context",
  "strengths": ["specific strength with data reference", "..."],
  "focus_areas": ["specific area with finger numbers or hand if relevant", "..."],
  "suggested_next_session": "one concrete, actionable practice instruction",
  "trend": "improving | stable | needs_attention",
  "trend_detail": "1-2 sentences on the specific metric driving the trend assessment",
  "milestone": "call out a personal best if one was set this session, otherwise empty string"
}"""


def build_tools() -> list[dict]:
    """Return Claude tool definitions matching the MCP server tools."""
    return [
        {
            "name": "get_recent_sessions",
            "description": "Get the last N practice session summaries including speed and evenness scores for both hands.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of sessions to return (default 10)"}
                },
            },
        },
        {
            "name": "get_session_detail",
            "description": "Get full note-level data for a specific session.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"}
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "get_finger_trends",
            "description": "Get per-finger average timing deviation across recent sessions for a given scale and hand.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "scale":         {"type": "string", "description": "Scale name e.g. c_major"},
                    "hand":          {"type": "string", "description": "left or right"},
                    "sessions_back": {"type": "integer", "description": "How many recent sessions to include"},
                },
                "required": ["scale", "hand"],
            },
        },
        {
            "name": "compare_hands",
            "description": "Compare left hand vs right hand speed and evenness for a specific session.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"}
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "get_scale_history",
            "description": "Get speed and evenness trend over all recorded sessions for a specific scale.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "scale": {"type": "string", "description": "Scale name e.g. c_major"}
                },
                "required": ["scale"],
            },
        },
    ]


def run_tool(name: str, arguments: dict) -> str:
    try:
        result = _dispatch(name, arguments)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_latest_session_id() -> str | None:
    results = _dispatch("get_recent_sessions", {"count": 1})
    if results and isinstance(results, list):
        sid = results[0].get("session_id")
        if sid and not sid.startswith("TEST_"):
            return sid
    return None


def run_coach(session_id: str | None = None) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

    if not session_id:
        print("No session_id provided — fetching most recent session...")
        session_id = get_latest_session_id()
        if not session_id:
            raise RuntimeError("No real sessions found in Splunk (only TEST_ sessions)")

    print(f"Coaching session: {session_id}")

    client = anthropic.Anthropic(api_key=api_key)
    messages = [
        {
            "role": "user",
            "content": f"Please analyze practice session {session_id} and provide coaching feedback."
        }
    ]

    tools = build_tools()
    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"  [agent] iteration {iteration}...")

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # Add assistant response to message history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Collect all text blocks into one string
            text = " ".join(
                block.text for block in response.content if hasattr(block, "text")
            ).strip()

            if not text:
                raise RuntimeError("Claude returned an empty final response")

            # Strip markdown code fences if present
            if "```" in text:
                parts = text.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        text = part
                        break

            # Find the outermost JSON object in case of surrounding text
            start = text.find("{")
            end   = text.rfind("}") + 1
            if start == -1 or end == 0:
                print(f"\n[debug] Raw Claude response:\n{text}")
                raise RuntimeError("No JSON object found in Claude response")

            return json.loads(text[start:end])

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool] {block.name}({json.dumps(block.input)})")
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(f"Agent did not complete within {max_iterations} iterations")


if __name__ == "__main__":
    session_id = sys.argv[1] if len(sys.argv) > 1 else None

    print("Starting piano coach agent...")
    try:
        report = run_coach(session_id)
        print("\n" + "="*60)
        print("  COACHING REPORT")
        print("="*60)
        print(json.dumps(report, indent=2))

        if os.environ.get("WEBEX_ROOM_ID"):
            print("\nPosting to Webex...")
            post_card(report)
        else:
            print("\n[webex] WEBEX_ROOM_ID not set — skipping card delivery.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
