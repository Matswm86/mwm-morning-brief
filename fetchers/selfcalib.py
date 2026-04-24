"""selfcalib — enrich the self-calibration progress bar state.

Reads the authoritative hand-tuned rubric from selfcalib_state.json, enriches it
with freshness signals (as_of, last_shipped per dimension, auto-flipped
status_badge), and returns the dict that the builder atomically writes to
web/selfcalib.json.

Percentages are NOT auto-computed. They are human-set, revised during CIP
weekly review. The bar was designed to replace vibes with defensible
readouts — auto-bumping pcts without a formal signals-to-pct rubric would
regress that. See handoff-brief-selfcalib-progress-graph-2026-04-24.md.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from config import MWM_ROOT, SERVICE_ROOT

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
    }
