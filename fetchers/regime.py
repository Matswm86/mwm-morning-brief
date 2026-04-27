"""Regime fetcher — reads Market Detector v3 state from local files.

v3 (2026-04-20): Reads ~/MWM-AI/projects/mwm-trading/data/market_regime/
  latest_ldn.json + latest_ny.json (written by mwm-market-detector-{ldn,ny}
  systemd timers).

2026-04-27: Legacy ORB v2.5 webhook fallback removed. TradingView is
decommissioned and the VPS receiver no longer fed. Local v3 files are
the sole source.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from http_util import get_json  # kept import for forward compat (unused since v2.5 removal)

log = logging.getLogger("morning-brief.regime")

# v3 local state paths (same host as this builder)
_V3_DIR = Path.home() / "MWM-AI" / "projects" / "mwm-trading" / "data" / "market_regime"
V3_PATHS = {
    "ldn": _V3_DIR / "latest_ldn.json",
    "ny": _V3_DIR / "latest_ny.json",
    "latest": _V3_DIR / "latest.json",
}

# v3 strategy labels (ORB + LiqSweep only per 2026-04-20 user lock)
STRATEGY_LABELS = {
    0: "FLAT / stand down",
    1: "ORB both sides, full size",
    2: "ORB both sides, reduced",
    3: "LiqSweep iFVG",
    4: "SKIP",
}
STRATEGY_DESC = {
    0: "No edge — sit out.",
    1: "Full ORB breakout playbook with both-sides armed.",
    2: "ORB with reduced confidence — tighter stops, fewer contracts.",
    3: "Liquidity sweep + iFVG entries on DOL levels.",
    4: "Conditions outside system — do not trade.",
}

REGIME_TO_TIER = {"HOT": "A", "WARM": "B", "MILD": "B", "COLD": "C", "FROZEN": "C"}


def _age_hours(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0
    except Exception:
        return None


def _load_local(session: str) -> Optional[dict]:
    path = V3_PATHS.get(session)
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:
        log.warning("v3 load failed %s: %s", path, e)
        return None


def _shape_v3(data: dict) -> dict:
    """Transform market_regime.v3 payload into dashboard dict."""
    regime = str(data.get("regime") or "").upper() or None
    score = data.get("score")          # 0..1
    score_pct = float(score) * 100 if score is not None else None
    sc = data.get("strategy_code")
    contracts = data.get("contracts_reco") or data.get("contracts") or 0
    ts = data.get("ts")
    age_h = _age_hours(ts)

    tier = REGIME_TO_TIER.get(regime or "", None)
    strategy_label = STRATEGY_LABELS.get(int(sc), "—") if isinstance(sc, int) else "—"

    direction_raw = str(data.get("direction") or "").upper() or None
    direction_score = data.get("direction_score")
    direction_conf = data.get("direction_confidence")

    tier_a = data.get("tier_a_score")
    tier_b = data.get("tier_b_score")
    tier_c = data.get("tier_c_score")

    tier_c_dict = data.get("tier_c") or {}
    hurst = tier_c_dict.get("hurst")
    adx = tier_c_dict.get("adx")

    session = (data.get("session") or "").upper() or "?"
    session_label = f"Market Detector · {session}"
    if age_h is not None and age_h > 26:
        session_label += " · STALE"

    vol = _volatility_label(adx)
    direction = _direction_caption(direction_raw, direction_score, direction_conf)

    return {
        "tier": tier,
        "tier_caption": _tier_caption_v3(regime, score_pct, age_h),
        "session_label": session_label,
        "session": session,
        "strategy_code": sc if isinstance(sc, int) else None,
        "strategy_label": strategy_label,
        "strategy_confidence": data.get("strategy_confidence"),
        "strategy_rationale": data.get("strategy_rationale", ""),
        "orb_affinity": data.get("orb_affinity"),
        "liqsweep_affinity": data.get("liqsweep_affinity"),
        "volatility": vol,
        "direction": direction,
        "direction_raw": direction_raw,
        "direction_score": direction_score,
        "direction_confidence": direction_conf,
        "regime": regime,
        "score": score_pct,
        "contracts": contracts,
        "tier_a_score": tier_a,
        "tier_b_score": tier_b,
        "tier_c_score": tier_c,
        "age_hours": round(age_h, 2) if age_h is not None else None,
        "generated_at": ts or "",
        "raw": data,
    }


def fetch() -> dict:
    """Return v3 regime dict with both session tiles when available.

    Output shape keeps keys used by builder.py and strategy_picker.py but
    adds a `sessions` sub-dict with LDN + NY shaped dicts so the template
    can render both tiles.
    """
    ldn = _load_local("ldn")
    ny = _load_local("ny")
    latest = _load_local("latest")

    sessions: dict[str, dict] = {}
    if ldn:
        sessions["LDN"] = _shape_v3(ldn)
    if ny:
        sessions["NY"] = _shape_v3(ny)

    # Pick the most recent as primary
    if latest:
        primary = _shape_v3(latest)
        primary["sessions"] = sessions
        return primary

    # v3 local files missing — TradingView v2.5 fallback removed 2026-04-27.
    return _empty("no local v3 state (Market Detector v3 has not run yet today)")


def _empty(reason: str) -> dict:
    return {
        "tier": None,
        "tier_caption": f"no lock ({reason})",
        "session_label": "Market Detector",
        "session": "—",
        "strategy_code": None,
        "strategy_label": "—",
        "strategy_confidence": None,
        "strategy_rationale": "",
        "orb_affinity": None,
        "liqsweep_affinity": None,
        "volatility": "—",
        "direction": "—",
        "direction_raw": None,
        "direction_score": None,
        "direction_confidence": None,
        "regime": None,
        "score": None,
        "contracts": 0,
        "tier_a_score": None,
        "tier_b_score": None,
        "tier_c_score": None,
        "age_hours": None,
        "generated_at": "",
        "sessions": {},
        "raw": {},
    }


def _volatility_label(adx: Any) -> str:
    try:
        v = float(adx)
    except Exception:
        return "—"
    if v < 15: return "low"
    if v < 25: return "medium"
    if v < 40: return "elevated"
    return "high"


def _direction_caption(raw: str | None, score: Any, conf: Any) -> str:
    if not raw or raw == "—":
        return "—"
    try:
        c = float(conf) if conf is not None else 0.0
    except Exception:
        c = 0.0
    qual = "high" if c >= 0.5 else "medium" if c >= 0.25 else "low"
    return f"{raw.lower()} ({qual})"


def _tier_caption_v3(regime: str | None, score_pct: float | None,
                     age_h: float | None) -> str:
    if not regime:
        return "awaiting lock"
    s_part = f" {score_pct:.0f}%" if score_pct is not None else ""
    caption = f"{regime.lower()}{s_part}"
    if age_h is not None and age_h > 26:
        caption += " · stale"
    return caption
