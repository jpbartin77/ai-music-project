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

import glob
import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no GUI; runs headless
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Resolved at import time so glob works regardless of cwd
_SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sessions"

VIZ_DIR = Path(__file__).parent.parent / "data" / "viz"
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

def _plot_scale_runs(ax, scale: str, session_id: str | None) -> bool:
    """
    Plot per-note BPM for each scale run in the current session.

    X-axis: note names in ascending-then-descending order (C4 D4 … C6 … D4 C4).
    Y-axis: BPM at each note transition (60000 / IOI_ms).
    One colored line per segment; averaged across both hands when lengths match.

    Returns False if no segment files are found.
    """
    if not session_id:
        return False

    pattern = str(_SESSIONS_DIR / f"{session_id}_seg*_{scale}.json")
    seg_files = sorted(glob.glob(pattern))
    if not seg_files:
        return False

    PALETTE = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]

    x_labels = None   # note-name labels from the first usable run
    drew_any = False

    for run_idx, seg_file in enumerate(seg_files):
        with open(seg_file) as fh:
            seg = json.load(fh)

        rh = seg.get("notes", {}).get("right", [])
        lh = seg.get("notes", {}).get("left", [])

        # Use both hands if they match length, otherwise the longer one
        if len(rh) == len(lh) and len(rh) >= 4:
            rh_iois = [rh[j]["time_ms"] - rh[j-1]["time_ms"] for j in range(1, len(rh))]
            lh_iois = [lh[j]["time_ms"] - lh[j-1]["time_ms"] for j in range(1, len(lh))]
            iois    = [(a + b) / 2 for a, b in zip(rh_iois, lh_iois)]
            labels  = [rh[j]["name"] for j in range(1, len(rh))]
        else:
            events = rh if len(rh) >= len(lh) else lh
            if len(events) < 4:
                continue
            iois   = [events[j]["time_ms"] - events[j-1]["time_ms"] for j in range(1, len(events))]
            labels = [events[j]["name"] for j in range(1, len(events))]

        bpms = [60000 / ioi for ioi in iois if ioi > 0]
        if not bpms:
            continue

        if x_labels is None:
            x_labels = labels

        xs = list(range(len(bpms)))
        ax.plot(xs, bpms,
                color=PALETTE[run_idx % len(PALETTE)],
                linewidth=1.6, marker="o", markersize=3,
                label=f"Run {run_idx + 1}", alpha=0.88)
        drew_any = True

    if not drew_any or x_labels is None:
        return False

    # X-axis: note names, every other label to avoid crowding
    xs_all = list(range(len(x_labels)))
    ax.set_xticks(xs_all)
    tick_labels = [n if i % 2 == 0 else "" for i, n in enumerate(x_labels)]
    ax.set_xticklabels(tick_labels, fontsize=7, rotation=60, ha="right")

    ax.set_ylabel("Speed (BPM)", fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}"))

    scale_display = scale.replace("_", " ").title()
    ax.set_title(f"{scale_display} — speed per note, this session",
                 fontsize=11, fontweight="bold")
    ncols = min(len(seg_files), 5)
    ax.legend(fontsize=8, loc="upper right", ncol=ncols, framealpha=0.7)
    ax.grid(True, axis="y", alpha=0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
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

def render_session_trend(scale: str, session_id: str | None = None) -> Path | None:
    """Standalone render of the per-note speed chart for a session."""
    fig, ax = plt.subplots(figsize=(6.4, 2.6), dpi=120)
    if not _plot_scale_runs(ax, scale, session_id):
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
    Combined PNG: per-note speed chart on top, per-finger deviation on bottom.
    This is what gets attached to the Webex summary card.

    Returns None if neither sub-chart has data.
    """
    finger_count = len((rh_trends or []) + (lh_trends or []))
    finger_h = max(2.4, 0.35 * finger_count + 0.8)
    trend_h  = 2.6
    total_h  = trend_h + finger_h

    fig, (ax_trend, ax_finger) = plt.subplots(
        2, 1, figsize=(6.4, total_h), dpi=120,
        gridspec_kw={"height_ratios": [trend_h, finger_h]},
    )

    drew_trend  = _plot_scale_runs(ax_trend, scale, session_id)
    drew_finger = _plot_finger_deviation(ax_finger, scale, rh_trends, lh_trends)

    if not drew_trend:
        ax_trend.set_axis_off()
        ax_trend.text(0.5, 0.5, "no session data found",
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
