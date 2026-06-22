"""Strategy picker — maps Market Detector v3 payload to today's recommended strategy.

v3 (2026-04-20): ORB + sweep-code. LiqSweep was RETIRED fleet-wide 2026-06-22
(blew XFA 24154823 on an overnight loss); the funded fleet now runs PDHR
(Prior-Day H/L break-and-retest, MNQ @5ct, RTH-only). The detector still emits
the legacy sweep-affinity code 3, so it now surfaces PDHR as the live funded
strategy rather than the dead LiqSweep.
  0 = FLAT (regime below WARM or event guard active)
  1 = ORB_full       (HOT regime + ORB affinity)
  2 = ORB_half       (WARM regime + ORB affinity)
  3 = PDHR           (funded fleet — prior-day H/L retest, not regime-gated)
  4 = SKIP           (no clear edge)
"""
from __future__ import annotations
from typing import Any

NAME_BY_CODE = {
    0: "Stand down",
    1: "ORB · full",
    2: "ORB · reduced",
    3: "PDHR MNQ",
    4: "No trade",
}

SUBTITLE_BY_CODE = {
    0: "flat · no edge",
    1: "trend continuation",
    2: "trend continuation (reduced)",
    3: "prior-day H/L break-and-retest",
    4: "conditions off-system",
}


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def pick(regime: dict) -> dict:
    """Return {name, subtitle, why, contracts, symbol} for the hero card."""
    sc = _safe_int(regime.get("strategy_code"), -1)
    contracts = _safe_int(regime.get("contracts"), 0)
    regime_label = (regime.get("regime") or "").upper() or None
    score = regime.get("score")
    age_h = regime.get("age_hours")
    hurst = regime.get("raw", {}).get("hurst") if isinstance(regime.get("raw"), dict) else None

    # Stale regime → recommend stand-down regardless
    if age_h is not None and age_h > 26:
        return {
            "name": "Stand down",
            "subtitle": "stale regime",
            "why": f"Last ORB lock is {age_h:.1f}h old (>26h). Wait for a fresh 08:00 ET lock before sizing in.",
            "contracts": 0,
            "symbol": "MNQ",
        }

    # No lock at all
    if sc < 0 or regime_label is None:
        return {
            "name": "Awaiting open",
            "subtitle": "no ORB lock",
            "why": "No ORB regime received yet for today. Dashboard refreshes as soon as the webhook fires at 08:00 ET.",
            "contracts": 0,
            "symbol": "MNQ",
        }

    name = NAME_BY_CODE.get(sc, f"strategy_code {sc}")
    subtitle = SUBTITLE_BY_CODE.get(sc, "—")
    # PDHR runs a fixed funded size (5 MNQ @5ct), not the detector's regime-scaled count.
    if sc == 3:
        contracts = 5
    why = _justify(sc, regime_label, score, contracts, hurst)

    return {
        "name": name,
        "subtitle": subtitle,
        "why": why,
        "contracts": contracts,
        "symbol": "MNQ",
    }


def _justify(sc: int, regime_label: str, score: Any, contracts: int, hurst: Any) -> str:
    try:
        s = float(score)
        score_part = f" at {s:.0f}%"
    except Exception:
        score_part = ""
    try:
        h = float(hurst)
        hurst_part = f", Hurst {h:.2f}"
    except Exception:
        hurst_part = ""

    if sc == 0:
        return f"Regime {regime_label}{score_part}{hurst_part} — no edge registered. Stand down."
    if sc == 1:
        return (
            f"HOT regime{score_part}{hurst_part}. ORB v4 baseline handled this tier cleanly "
            f"(12/16 ironclad gates). Both sides armed, {contracts} MNQ."
        )
    if sc == 2:
        return (
            f"WARM regime{score_part}{hurst_part}. ORB reduced — tighter stops, "
            f"{contracts} MNQ. Funded fleet runs PDHR alongside (prior-day H/L retest)."
        )
    if sc == 3:
        return (
            f"Funded fleet runs PDHR — Prior-Day H/L break-and-retest, RTH-only, "
            f"{contracts} MNQ @5ct on all three funded accounts. Not regime-gated; "
            f"PDHR replaced LiqSweep (parked 2026-06-22) on the funded fleet."
        )
    if sc == 4:
        return (
            f"Regime {regime_label}{score_part}{hurst_part} — outside the system's "
            f"tested envelope. Skip the session."
        )
    return f"Regime {regime_label}{score_part}{hurst_part}."
