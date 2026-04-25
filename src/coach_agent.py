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
- get_finger_trends returns avg_deviation_ms per finger: POSITIVE = finger consistently lags,
  NEGATIVE = finger consistently rushes. stdev_deviation_ms shows how consistent the timing is.

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


SUMMARY_SYSTEM_PROMPT = """You are an expert piano practice coach analyzing MULTIPLE REPETITIONS of one scale within a single practice session.

The student played the same scale several times in this session. Your job is to coach across all the reps together, not just one.

You have access to tools that query the student's full practice history in Splunk:
- compare_hands(session_id) returns ALL segments of this session — filter the results to just the scale you're coaching on
- get_scale_history(scale) gives the cross-session arc for the scale — useful for placing today in context
- get_session_detail(session_id) returns per-note timing — useful for spotting which rep was the best
- get_finger_trends(scale, hand) shows which fingers consistently lag or rush across history

For summary coaching, communicate:
- The BEST rep of the session (call out segment_index, BPM, evenness)
- TYPICAL performance — what the student delivered most reps (speak in averages)
- TREND WITHIN this session — did the player get faster/slower or more/less even across repetitions?
  This is the fatigue-vs-warmup question. Compare first rep to last rep.
- HISTORICAL trend — how today fits in the larger arc (improving, stable, needs attention)

Reference specific reps when useful: "your 3rd rep set a session-best 286 BPM, but evenness slipped on rep 5".

Key metrics to reason about:
- speed_bpm: higher is faster. Typical beginner 120-200, advancing 200-300+
- evenness_cv_pct: LOWER is better
- get_finger_trends avg_deviation_ms: POSITIVE = lags, NEGATIVE = rushes; stdev shows consistency

Return ONLY a valid JSON object with exactly these fields — no markdown, no explanation outside the JSON:
{
  "summary": "2-3 sentence assessment integrating best, typical, and trend",
  "strengths": ["specific strength with rep reference if applicable", "..."],
  "focus_areas": ["specific area, with finger numbers or hand if relevant", "..."],
  "suggested_next_session": "one concrete, actionable practice instruction",
  "trend": "improving | stable | needs_attention",
  "trend_detail": "1-2 sentences covering both within-session trend and historical trend",
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


def _run_agent_loop(system_prompt: str, user_message: str, max_iterations: int = 10) -> dict:
    """Shared agent loop. Sends the prompt, executes tool calls, returns parsed JSON report."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": user_message}]
    tools = build_tools()
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"  [agent] iteration {iteration}...")

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = " ".join(
                block.text for block in response.content if hasattr(block, "text")
            ).strip()
            if not text:
                raise RuntimeError("Claude returned an empty final response")

            if "```" in text:
                parts = text.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        text = part
                        break

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


def run_coach(session_id: str | None = None) -> dict:
    """Per-segment coaching — analyzes one session's most recent segment."""
    if not session_id:
        print("No session_id provided -- fetching most recent session...")
        session_id = get_latest_session_id()
        if not session_id:
            raise RuntimeError("No real sessions found in Splunk (only TEST_ sessions)")

    print(f"Coaching session: {session_id}")
    return _run_agent_loop(
        SYSTEM_PROMPT,
        f"Please analyze practice session {session_id} and provide coaching feedback.",
    )


def run_coach_summary(session_id: str, scale: str) -> dict:
    """Summary coaching — analyzes multiple reps of one scale within a session."""
    print(f"Coaching summary: session {session_id}, scale {scale}")
    return _run_agent_loop(
        SUMMARY_SYSTEM_PROMPT,
        f"In session {session_id}, the student played multiple repetitions of {scale}. "
        f"Provide a summary coaching report covering the best rep, typical performance, "
        f"the trend within the session, and how today fits in the historical arc.",
    )


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
