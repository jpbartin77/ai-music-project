"""
cloud_run_app.py — Flask endpoint for Cloud Run.

Accepts POST /coach with an optional session_id and runs the coaching agent.
Also handles Splunk alert webhook payloads (result.session_id).

Secrets (ANTHROPIC_API_KEY, SPLUNK_TOKEN, WEBEX_BOT_TOKEN) are injected by
Cloud Run from Google Secret Manager — no op run needed in this environment.

Usage (local test):
    ANTHROPIC_API_KEY=... SPLUNK_TOKEN=... python src/cloud_run_app.py

Cloud Run trigger (Splunk alert webhook or manual):
    POST /coach
    Content-Type: application/json
    {"session_id": "abc123"}          # manual
    {"result": {"session_id": "abc123"}, ...}  # Splunk alert format
"""

import os
import sys
import pathlib

from flask import Flask, request, jsonify

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from coach_agent import run_coach

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/coach", methods=["POST"])
def coach():
    data = request.get_json(silent=True) or {}

    # Support both manual {"session_id": "..."} and Splunk alert webhook format
    # {"result": {"session_id": "..."}, "sid": "...", ...}
    session_id = data.get("session_id") or data.get("result", {}).get("session_id")

    print(f"[cloud_run] /coach triggered — session_id={session_id or 'latest'}")

    try:
        report = run_coach(session_id)
        return jsonify(report)
    except Exception as e:
        print(f"[cloud_run] error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
