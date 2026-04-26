"""
demo_emitter.py — Fire-and-forget HTTP event emitter for the demo dashboard.

Reads DEMO_SERVER_URL from the environment (e.g. http://localhost:5000/event).
If the env var is unset or the server is unreachable, emits are silently skipped
so practice_session.py works normally without the demo UI running.
"""

import json
import os
import threading
import urllib.request
import urllib.error

_URL = os.environ.get("DEMO_SERVER_URL", "").rstrip("/") + "/event"
_ENABLED = bool(os.environ.get("DEMO_SERVER_URL", ""))


def emit(event: str, **data) -> None:
    """Post an event to the demo server without blocking the caller."""
    if not _ENABLED:
        return
    payload = json.dumps({"event": event, **data}).encode()
    threading.Thread(target=_post, args=(payload,), daemon=True).start()


def _post(payload: bytes) -> None:
    req = urllib.request.Request(
        _URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=1):
            pass
    except Exception:
        pass  # demo server not running — silently skip
