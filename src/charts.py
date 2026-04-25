"""
charts.py — Generate PNG charts for the summary coaching card.

Public:
  render_summary_panel    — single PNG combining the two charts below (used on Webex card)
  render_session_trend    — line chart only: speed and evenness across recent sessions
  render_finger_deviation — bar chart only: per-finger timing deviation, color-coded

Webex Messages API allows one file attachment per message, so the combined panel
is what gets posted with summary cards. The individual functions are kept for
testing and one-off use.

Output PNGs go to data/viz/. All functions return a Path or None (when there's
nothing meaningful to draw).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no GUI; runs headless
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


VIZ_DIR = Path("data/viz")
FINGER_NAMES = {1: "Thumb", 2: "Index", 3: "Middle", 4: "Ring", 5: "Pinky"}

# Color thresholds for deviation magnitude (ms)
GREEN_MAX  = 10.0
YELLOW_MAX = 30.0


def _ensure_viz_dir() -> Path:
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    return VIZ_DIR


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _deviation_color(deviation_ms: float) -> str:
    mag = abs(deviation_ms)
    if mag <= GREEN_MAX:
        return "#3aa86b"
    if mag <= YELLOW_MAX:
        return "#e3b341"
    return "#d9534f"


# ── Internal plotters (operate on given axes) ─────────────────────────────────

def _plot_session_trend(ax_bpm, scale: str, history: list[dict], session_id: str | None) -> bool:
    """Plot speed/evenness trend on the given axes. Returns False if nothing drawn."""
    if not history:
        return False

    rows = []
    for r in history:
        t = r.get("time")
        if not t:
            continue
        try:
            ts = datetime.fromisoformat(t.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        rh_bpm = _safe_float(r.get("rh_speed_bpm"))
        lh_bpm = _safe_float(r.get("lh_speed_bpm"))
        rh_cv  = _safe_float(r.get("rh_evenness_cv_pct"))
        lh_cv  = _safe_float(r.get("lh_evenness_cv_pct"))
        avg_bpm = (rh_bpm + lh_bpm) / 2 if (rh_bpm and lh_bpm) else (rh_bpm or lh_bpm)
        avg_cv  = (rh_cv + lh_cv) / 2 if (rh_cv and lh_cv) else (rh_cv or lh_cv)
        rows.append({"time": ts, "session_id": r.get("session_id", ""), "bpm": avg_bpm, "cv": avg_cv})

    if not rows:
        return False

    rows.sort(key=lambda x: x["time"])
    times = [r["time"] for r in rows]
    bpms  = [r["bpm"] for r in rows]
    cvs   = [r["cv"]  for r in rows]

    ax_cv = ax_bpm.twinx()

    ax_bpm.plot(times, bpms, color="#1f77b4", linewidth=2.0, marker="o", markersize=4, label="Speed (BPM)")
    ax_cv.plot(times, cvs,  color="#ff7f0e", linewidth=1.8, linestyle="--", marker="s", markersize=4, label="CV%")

    ax_bpm.set_ylabel("Speed (BPM)", color="#1f77b4", fontsize=9)
    ax_cv.set_ylabel("Evenness CV%", color="#ff7f0e", fontsize=9)
    ax_bpm.tick_params(axis="y", labelcolor="#1f77b4", labelsize=8)
    ax_cv.tick_params(axis="y",  labelcolor="#ff7f0e", labelsize=8)
    ax_bpm.tick_params(axis="x", labelsize=8)

    if session_id:
        for r in rows:
            if r["session_id"] == session_id:
                ax_bpm.plot(r["time"], r["bpm"], marker="o", markersize=10,
                            markerfacecolor="none", markeredgecolor="#1f77b4", markeredgewidth=2)
                ax_bpm.annotate("this session", (r["time"], r["bpm"]),
                                xytext=(8, 8), textcoords="offset points",
                                fontsize=8, color="#444")
                break

    if len(times) > 1:
        span = times[-1] - times[0]
        if span.total_seconds() < 24 * 3600:
            ax_bpm.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        else:
            ax_bpm.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        for label in ax_bpm.get_xticklabels():
            label.set_rotation(20)
            label.set_horizontalalignment("right")

    title = scale.replace("_", " ").title() + " — recent sessions"
    ax_bpm.set_title(title, fontsize=11, fontweight="bold")
    ax_bpm.grid(True, alpha=0.25)
    ax_bpm.spines["top"].set_visible(False)
    ax_cv.spines["top"].set_visible(False)
    return True


def _plot_finger_deviation(ax, scale: str, rh_trends: list[dict], lh_trends: list[dict]) -> bool:
    """Plot per-finger deviation bars on the given axes. Returns False if nothing drawn."""
    rows = []
    for r in sorted(rh_trends or [], key=lambda x: int(x.get("finger", 0))):
        finger = int(r.get("finger", 0))
        rows.append((f"RH {FINGER_NAMES.get(finger, str(finger))}", _safe_float(r.get("avg_deviation_ms"))))
    for r in sorted(lh_trends or [], key=lambda x: int(x.get("finger", 0))):
        finger = int(r.get("finger", 0))
        rows.append((f"LH {FINGER_NAMES.get(finger, str(finger))}", _safe_float(r.get("avg_deviation_ms"))))

    if not rows:
        return False

    labels = [r[0] for r in rows]
    devs   = [r[1] for r in rows]
    colors = [_deviation_color(d) for d in devs]

    y_pos = list(range(len(labels)))
    bars = ax.barh(y_pos, devs, color=colors, edgecolor="#333", linewidth=0.5, height=0.6)

    ax.axvline(0, color="#333", linewidth=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()  # RH on top
    ax.set_xlabel("Avg IOI deviation (ms)  —  rushes ◀ · ▶ lags", fontsize=9)
    ax.tick_params(axis="x", labelsize=8)

    max_abs = max((abs(d) for d in devs), default=10.0)
    pad = max(5.0, max_abs * 0.15)
    ax.set_xlim(-(max_abs + pad), max_abs + pad)

    for bar, dev in zip(bars, devs):
        x = bar.get_width()
        offset = 2 if x >= 0 else -2
        ha = "left" if x >= 0 else "right"
        ax.annotate(f"{dev:+.0f}", (x, bar.get_y() + bar.get_height() / 2),
                    xytext=(offset, 0), textcoords="offset points",
                    va="center", ha=ha, fontsize=8, color="#222")

    title = scale.replace("_", " ").title() + " — finger timing"
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, axis="x", alpha=0.25)
    return True


# ── Public renderers ──────────────────────────────────────────────────────────

def render_session_trend(scale: str, history: list[dict], session_id: str | None = None) -> Path | None:
    fig, ax = plt.subplots(figsize=(6.4, 2.4), dpi=120)
    if not _plot_session_trend(ax, scale, history, session_id):
        plt.close(fig)
        return None
    fig.tight_layout()
    _ensure_viz_dir()
    out = VIZ_DIR / f"{session_id or 'latest'}_{scale}_trend.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out


def render_finger_deviation(scale: str,
                            rh_trends: list[dict],
                            lh_trends: list[dict],
                            session_id: str | None = None) -> Path | None:
    height = max(2.4, 0.35 * len((rh_trends or []) + (lh_trends or [])) + 0.8)
    fig, ax = plt.subplots(figsize=(6.4, height), dpi=120)
    if not _plot_finger_deviation(ax, scale, rh_trends, lh_trends):
        plt.close(fig)
        return None
    fig.tight_layout()
    _ensure_viz_dir()
    out = VIZ_DIR / f"{session_id or 'latest'}_{scale}_fingers.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out


def render_summary_panel(scale: str,
                         history: list[dict],
                         rh_trends: list[dict],
                         lh_trends: list[dict],
                         session_id: str | None = None) -> Path | None:
    """
    Combined PNG: session-trend chart on top, per-finger deviation on bottom.
    This is what gets attached to the Webex summary card.

    Returns None if neither sub-chart has data.
    """
    finger_count = len((rh_trends or []) + (lh_trends or []))
    finger_h = max(2.4, 0.35 * finger_count + 0.8)
    total_h = 2.6 + finger_h

    fig, (ax_trend, ax_finger) = plt.subplots(
        2, 1, figsize=(6.4, total_h), dpi=120,
        gridspec_kw={"height_ratios": [2.6, finger_h]},
    )

    drew_trend  = _plot_session_trend(ax_trend, scale, history, session_id)
    drew_finger = _plot_finger_deviation(ax_finger, scale, rh_trends, lh_trends)

    if not drew_trend:
        ax_trend.set_axis_off()
        ax_trend.text(0.5, 0.5, "no historical data yet — first session for this scale",
                      ha="center", va="center", fontsize=10, color="#666",
                      transform=ax_trend.transAxes)
    if not drew_finger:
        ax_finger.set_axis_off()
        ax_finger.text(0.5, 0.5, "no finger-trend data available",
                       ha="center", va="center", fontsize=10, color="#666",
                       transform=ax_finger.transAxes)

    if not (drew_trend or drew_finger):
        plt.close(fig)
        return None

    fig.tight_layout()
    _ensure_viz_dir()
    out = VIZ_DIR / f"{session_id or 'latest'}_{scale}_summary.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out
