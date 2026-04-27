"""selfcalib — enrich the self-calibration progress bar state.

Reads the authoritative hand-tuned rubric from selfcalib_state.json, enriches it
with freshness signals (as_of, last_shipped per dimension, auto-flipped
status_badge), and returns the dict that the builder atomically writes to
web/selfcalib.json.

Percentages are NOT auto-computed. They are human-set, revised during CIP
weekly review. The bar was designed to replace vibes with defensible
readouts — auto-bumping pcts without a formal signals-to-pct rubric would
regress that. See handoff-brief-selfcalib-progress-graph-2026-04-24.md.

Also emits a `judge_score_ci` block — F4.5 conformal-wrapped rolling-mean
judge confidence. Dark behind SCCS_CONFORMAL_ENABLED (default false): when
disabled, returns method='disabled' with bare value and the brief-side
template should fall back to the point. Below MIN_N_CAL=30 returns
method='point'. See handoff-sccs-audit-fields-shipped-2026-04-27.md Block 1.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

from config import MWM_ROOT, SERVICE_ROOT

_MWM_CORE = str(MWM_ROOT / "core")
if Path(_MWM_CORE).is_dir() and _MWM_CORE not in sys.path:
    sys.path.insert(0, _MWM_CORE)
try:
    from sccs import (  # type: ignore
        MIN_N_CAL,
        read_recent_predictions,
        read_recent_residuals,
        wrap_metric,
    )
    _SCCS_AVAILABLE = True
except Exception as _e:  # pragma: no cover
    MIN_N_CAL = 30  # type: ignore[assignment]
    read_recent_predictions = None  # type: ignore[assignment]
    read_recent_residuals = None  # type: ignore[assignment]
    wrap_metric = None  # type: ignore[assignment]
    _SCCS_AVAILABLE = False
    logging.getLogger("morning-brief.selfcalib").warning(
        "sccs unavailable, judge_score_ci will report sccs_unavailable: %s", _e,
    )

log = logging.getLogger("morning-brief.selfcalib")

STATE_FILE = SERVICE_ROOT / "selfcalib_state.json"

HANDOFF_DIRS = [
    Path.home() / ".claude" / "projects" / "-home-mats-MWM-AI" / "memory",
    MWM_ROOT / "memory",
    MWM_ROOT / "notes" / "handoffs",
]

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _badge_from_pct(pct: int) -> str:
    if pct >= 80: return "live"
    if pct >= 50: return "partial"
    if pct >= 30: return "shadow"
    if pct >= 10: return "thin"
    return "manual"


def _collect_handoffs() -> list[tuple[str, str]]:
    """Return [(filename_slug_lower, date_yyyy_mm_dd), ...] across all dirs."""
    out: list[tuple[str, str]] = []
    for d in HANDOFF_DIRS:
        if not d.exists():
            continue
        for p in d.glob("handoff-*.md"):
            name = p.stem.lower()
            m = DATE_RE.search(name)
            if not m:
                continue
            out.append((name, m.group(1)))
    return out


def _last_shipped_for(keywords: list[str], handoffs: list[tuple[str, str]]) -> str | None:
    best: str | None = None
    for name, d in handoffs:
        if any(k in name for k in keywords):
            if best is None or d > best:
                best = d
    return best


def _aggregate(dims: list[dict]) -> float:
    total_w = sum(d.get("weight", 0) for d in dims) or 1
    sum_wp = sum(d.get("weight", 0) * d.get("pct", 0) for d in dims)
    return round(sum_wp / total_w, 2)


def _is_truthy(val: str) -> bool:
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _judge_score_ci(rubric: str = "scientific_method", window_days: int = 30) -> dict:
    """F4.5 conformal-wrapped rolling-mean judge confidence (dark by default).

    Behaviour matrix:
      - sccs unavailable          → status='sccs_unavailable', method='disabled'
      - SCCS_CONFORMAL_ENABLED=0  → method='disabled', point only (no wrap)
      - n_cal < MIN_N_CAL         → method='point' (wrap_metric self-handles)
      - n_cal ≥ MIN_N_CAL         → method='aci' with [lower, upper]

    The point estimate is the rolling mean of `predicted_normalized` over
    the same window. Empty window → status='no_recent_predictions'. The
    miscoverage history is left empty on first call (ACI degrades to
    split-conformal); a future iteration can reconstruct it from prior
    half-widths once those are persisted.
    """
    enabled = _is_truthy(os.environ.get("SCCS_CONFORMAL_ENABLED", "false"))

    if not _SCCS_AVAILABLE:
        return {
            "status": "sccs_unavailable",
            "method": "disabled",
            "rubric": rubric,
            "window_days": window_days,
            "n_cal": 0,
        }

    try:
        residuals = read_recent_residuals(window_days=window_days, rubric=rubric)  # type: ignore[misc]
        predictions = read_recent_predictions(window_days=window_days, rubric=rubric)  # type: ignore[misc]
    except Exception as e:  # pragma: no cover
        log.warning("judge_score_ci read failed: %s", e)
        return {
            "status": f"read_err:{type(e).__name__}",
            "method": "disabled",
            "rubric": rubric,
            "window_days": window_days,
            "n_cal": 0,
        }

    n_cal = len(residuals)
    if not predictions:
        return {
            "status": "no_recent_predictions",
            "method": "disabled",
            "rubric": rubric,
            "window_days": window_days,
            "n_cal": n_cal,
        }

    point = sum(predictions) / len(predictions)

    if not enabled:
        return {
            "status": "dark",
            "value": round(point, 4),
            "lower": round(point, 4),
            "upper": round(point, 4),
            "method": "disabled",
            "rubric": rubric,
            "window_days": window_days,
            "n_cal": n_cal,
            "min_n_cal": int(MIN_N_CAL),
            "n_predictions": len(predictions),
        }

    out = wrap_metric(  # type: ignore[misc]
        point=point,
        cal_residuals=residuals,
        method="aci",
        miscoverage_history=[],
        alpha=0.10,
        gamma=0.05,
        clip_to=(0.0, 1.0),
    )
    out["rubric"] = rubric
    out["window_days"] = window_days
    out["min_n_cal"] = int(MIN_N_CAL)
    out["n_predictions"] = len(predictions)
    out["status"] = "live"
    for k in ("value", "lower", "upper"):
        if isinstance(out.get(k), (int, float)):
            out[k] = round(float(out[k]), 4)
    return out


def fetch() -> dict:
    if not STATE_FILE.exists():
        log.warning("selfcalib_state.json missing at %s", STATE_FILE)
        return {"status": "missing_state", "dimensions": []}

    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception as e:
        log.exception("selfcalib state parse failed")
        return {"status": f"parse_err:{e.__class__.__name__}", "dimensions": []}

    handoffs = _collect_handoffs()
    log.info("selfcalib: %d dated handoffs scanned", len(handoffs))

    enriched_dims: list[dict] = []
    for dim in state.get("dimensions", []):
        keywords = [k.lower() for k in dim.get("keywords", [])]
        last = _last_shipped_for(keywords, handoffs) if keywords else None
        out = {
            "id": dim["id"],
            "label": dim["label"],
            "weight": dim["weight"],
            "pct": dim["pct"],
            "status_badge": _badge_from_pct(int(dim["pct"])),
            "done": list(dim.get("done", [])),
            "next": list(dim.get("next", [])),
            "last_shipped": last,
        }
        enriched_dims.append(out)

    return {
        "as_of": date.today().isoformat(),
        "target_state": state.get("target_state", ""),
        "target_state_no": state.get("target_state_no", ""),
        "subtitle": state.get("subtitle", ""),
        "dimensions": enriched_dims,
        "aggregate_pct": _aggregate(enriched_dims),
        "judge_score_ci": _judge_score_ci(),
    }
