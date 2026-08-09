"""Strategy picker.

Two generations live here:

pick_play() — CURRENT (2026-08-09). "Today's Play" for the QuantCrawler pair
(QCS-Preset / QC Trend Strat), gated by the scheduled-macro calendar the brief
already fetches. The rule and every number come from the 1-year TradingView
List-of-Trades exports measured 2026-08-09 (handoff-strategy-selector-not-
regime-label-2026-08-08, Phase B): the preset shows NO news penalty (87% win on
event days vs 80% off them) so it always runs; QC Trend Strat earns 4% of its
net from 20% of its trades on tier-1 release days, so it sits out those days.
Gate set = the families the study measured (CPI, NFP, PCE, PPI, GDP, retail
sales at 08:30 ET, plus FOMC decisions). Claims / ISM / Fed speakers are shown
but NOT gated — unmeasured. Display only: verdicts are something Mats reads;
nothing here touches QuantCrawler, a runner, or an account.

pick() — LEGACY (Market Detector v3 → ORB/PDHR). The detector's alert path was
decommissioned; kept only because the SCCS policy-state log still records its
output shape.

Legacy strategy_code map (v3, 2026-04-20): 0 FLAT · 1 ORB_full · 2 ORB_half ·
3 PDHR (replaced retired LiqSweep) · 4 SKIP.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Families whose event-day cost to QC Trend Strat was MEASURED (tier>=1 in the
# 2026-08-09 study). Anything outside this set does not gate — unmeasured.
GATE_FAMILIES = {
    "CPI · inflation",
    "Nonfarm payrolls",
    "PCE prices",
    "PPI",
    "GDP",
    "Retail sales",
}
FOMC_DECISION = "FOMC rate decision"

EVIDENCE = (
    "Basis: 1-yr TV exports measured 2026-08-09 — preset event days win 87% "
    "(carry 36% of net, never gate it); QC event days = 20% of trades but 4% "
    "of net, post-release entries 29% win; skipping them keeps $21.1k of "
    "$23.4k and cuts maxDD 23%. Descriptive study, not pre-registered. "
    "Gate set = CPI/NFP/PCE/PPI/GDP/retail + FOMC; claims/ISM/speakers shown "
    "but unmeasured. Display only — you flip the QuantCrawler switch, not this page."
)


def pick_play(event_section: dict, now: datetime | None = None) -> dict:
    """Today's Play from the already-fetched event_calendar section."""
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    today = now_et.strftime("%Y-%m-%d")
    weekend = now_et.weekday() >= 5

    items = event_section.get("items") or []
    calendar_ok = event_section.get("status") == "ok" and not event_section.get("error")
    todays = [it for it in items if it.get("date_et") == today]
    gate_hits = [it for it in todays if it.get("family") in GATE_FAMILIES]
    fomc_today = any(it.get("family") == FOMC_DECISION for it in todays)
    other = [it for it in todays if it not in gate_hits]

    def _evt(it: dict) -> dict:
        return {
            "family": it.get("family"),
            "detail": it.get("detail"),
            "time_et": it.get("time_et"),
            "time_oslo": it.get("time_oslo"),
            "impact": it.get("impact"),
        }

    preset = {
        "strategy": "QCS-Preset",
        "size": "4ct MNQ",
        "verdict": "RUN",
        "why": "Event-immune: wins 87% on release days vs 80% off them. Always on.",
    }
    qc = {"strategy": "QC Trend Strat", "size": "2ct MNQ"}

    if weekend:
        preset = {**preset, "verdict": "CLOSED", "why": "Markets closed (weekend)."}
        qc.update(verdict="CLOSED", why="Markets closed (weekend).")
    elif not calendar_ok:
        qc.update(
            verdict="UNKNOWN",
            why=(
                "Calendar fetch FAILED — cannot confirm a no-event day. "
                "Treat as an event day (sit out) until the schedule is back."
            ),
        )
    elif fomc_today:
        qc.update(
            verdict="SKIP",
            why=(
                "FOMC decision 14:00 ET today. QC on FOMC days: 36 trades, "
                "33% win, net -$194 over the year."
            ),
        )
        preset["why"] += " FOMC 14:00 ET today: held-through-print evidence is n=2 (both won, triple MAE)."
    elif gate_hits:
        names = ", ".join(
            f"{g['family']} {g['time_et']} ET" for g in map(_evt, gate_hits)
        )
        qc.update(
            verdict="SKIP",
            why=(
                f"Tier-1 release today: {names}. QC event days carry 20% of "
                "its trades but 4% of its net; sitting out keeps 90% of the "
                "year's profit at 23% less drawdown."
            ),
        )
    else:
        qc.update(
            verdict="RUN",
            why=(
                "No tier-1 release scheduled. No-event days carry 96% of QC's "
                "annual net."
                + (
                    " (Unmeasured events today: "
                    + ", ".join(f"{o.get('family')} {o.get('time_et')} ET" for o in other)
                    + " — not gated.)"
                    if other
                    else ""
                )
            ),
        )

    return {
        "date_et": today,
        "weekend": weekend,
        "calendar_ok": calendar_ok,
        "fomc_today": fomc_today,
        "gate_events": [_evt(g) for g in gate_hits],
        "other_events": [_evt(o) for o in other],
        "rows": [preset, qc],
        "evidence": EVIDENCE,
    }

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
