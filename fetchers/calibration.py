"""Calibration fetcher — reads latest market_detector accuracy stats.

Source: ~/MWM-AI/projects/mwm-trading/data/market_detector_predictions/
        calibration_*.json (written by `python -m market_detector.replay`)

Returns the shape the dashboard hero strip expects: direction/strategy
accuracy + CI + lift-vs-baseline + simulated PnL.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("morning-brief.calibration")

_ROOT = Path(os.environ.get("MWM_AI_ROOT", Path.home() / "MWM"))  # ~/MWM-AI is gone on this box
CAL_DIR = _ROOT / "projects" / "mwm-trading" / "data" / "market_detector_predictions"


def _latest_file() -> Optional[Path]:
    if not CAL_DIR.exists():
        return None
    files = sorted(CAL_DIR.glob("calibration_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _live() -> Optional[dict]:
    """Direction accuracy of the live locks, from score_live.py's nightly file."""
    path = CAL_DIR / "live_scored.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        log.warning("live calibration load failed: %s", e)
        return None
    o = data.get("overall") or {}
    return {
        "n": o.get("n"),
        "accuracy": o.get("accuracy"),
        "baseline": o.get("baseline_majority"),
        "lift": o.get("lift_vs_baseline"),
        "ci_90": o.get("ci90"),
        "first": o.get("first"),
        "last": o.get("last"),
        "generated_at": data.get("generated_at"),
        "by_session": {
            k: {x: v.get(x) for x in ("n", "accuracy", "baseline_majority", "lift_vs_baseline")}
            for k, v in (data.get("by_session") or {}).items()
        },
    }


def fetch() -> dict:
    path = _latest_file()
    if not path:
        return {"status": "missing", "n": 0}
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        log.warning("calibration load failed: %s", e)
        return {"status": "error", "n": 0, "error": str(e)}

    d = data.get("direction", {})
    s = data.get("strategy", {})
    sim = data.get("simulation", {})

    def _caption(sub: dict) -> str:
        if sub.get("accuracy") is None:
            return "—"
        acc = sub["accuracy"] * 100
        base = sub.get("baseline_majority", 0) * 100
        lift = sub.get("lift_vs_baseline", 0) * 100
        badge = "↑" if lift > 2 else "→" if abs(lift) <= 2 else "↓"
        return f"{acc:.0f}% {badge} baseline {base:.0f}% (lift {lift:+.0f}pp)"

    usable_direction = d.get("lift_vs_baseline", 0) > 0.02
    usable_strategy = s.get("lift_vs_baseline", 0) > 0.02

    return {
        "status": "ok",
        "n": data.get("n", 0),
        "source_file": path.name,
        # The numbers below this block come from replay.py, which refits on data
        # the live lock never had. "live" is the scored record of the calls as
        # they were actually locked (score_live.py), and is the one to quote.
        "basis": "replay",
        "live": _live(),
        "direction": {
            "accuracy": d.get("accuracy"),
            "baseline": d.get("baseline_majority"),
            "lift": d.get("lift_vs_baseline"),
            "ci_90": d.get("ci_90"),
            "caption": _caption(d),
            "usable": usable_direction,
        },
        "strategy": {
            "accuracy": s.get("accuracy"),
            "baseline": s.get("baseline_majority"),
            "lift": s.get("lift_vs_baseline"),
            "ci_90": s.get("ci_90"),
            "caption": _caption(s),
            "usable": usable_strategy,
        },
        "simulation": {
            "avg_r": sim.get("avg_r_per_trade"),
            "n_trades": sim.get("n_trades"),
            "total_r": sim.get("total_r"),
        },
        "per_regime": data.get("per_regime", {}),
        "per_strategy": data.get("per_strategy", {}),
    }
