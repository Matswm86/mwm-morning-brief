"""Pre-open expansion / ORB go-no-go object for the brief.

Reads data/cockpit/preopen_expansion.json, written before 08:00 Oslo by
projects/mwm-trading/research/regime-nowcast/preopen_expansion.py, which reads
the range model already shipping on this site (HAR+VOL+EVENT). Nothing new is
fitted; this restates that model's next-session WIDE/NARROW call as an ORB
go/no-go, with its measured hit rate attached.

Every surface must carry: it forecasts RANGE, never ORB P&L, and direction is
not part of it.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("morning-brief.preopen")

SRC = Path.home() / "MWM-AI" / "data" / "cockpit" / "preopen_expansion.json"
STALE_HOURS = 20.0


def fetch() -> dict:
    if not SRC.exists():
        return {"status": "unavailable", "error": f"no artifact at {SRC}"}
    try:
        d = json.loads(SRC.read_text())
    except (OSError, ValueError) as e:
        return {"status": "unavailable", "error": f"{type(e).__name__}: {e}"}

    age_h = None
    try:
        age_h = (datetime.now(UTC) - datetime.fromisoformat(d["generated_at"])).total_seconds() / 3600.0
    except (KeyError, ValueError):
        pass

    insts = {
        code: {
            "status": v.get("status"),
            "session": v.get("session"),
            "call": v.get("call"),
            "orb": v.get("orb"),
            "meaning": v.get("meaning"),
            "expected_range_pts": v.get("expected_range_pts"),
            "median26d_pts": v.get("median26d_pts"),
            "vs_median": v.get("vs_median"),
            "expansion": v.get("expansion"),
            "grade": v.get("grade"),
            "recent_year": v.get("recent_year"),
            "orb_thresholds": v.get("orb_thresholds"),
            "yesterday_pts": v.get("yesterday_pts"),
            "events": v.get("events") or [],
            # Rolling P(wide) that drives the MNQ tight-day call. Public-safe:
            # a probability, a threshold and a measured hit rate, no paths or
            # internal model names.
            "contraction_prob": v.get("contraction_prob"),
            # "accuracy" carries internal validation basis strings; keep it out
            # of the public artifact.

        }
        for code, v in (d.get("instruments") or {}).items()
    }
    out = {
        "status": "ok" if insts else "unavailable",
        "schema": d.get("schema"),
        "generated_at": d.get("generated_at"),
        "decision_time_oslo": d.get("decision_time_oslo", "08:00"),
        "age_hours": round(age_h, 1) if age_h is not None else None,
        "stale": bool(age_h is not None and age_h > STALE_HOURS),
        "instruments": insts,
        "means": d.get("means"),
        "caveat": d.get("caveat"),
    }
    log.info("preopen expansion: %s", {k: v.get("orb") for k, v in insts.items()})
    return out
