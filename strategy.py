"""Strategy picker.

Two generations live here:

pick_play() — CURRENT (2026-09-06). "Today's Play" for the live pair (Drift
VWAP Pullback on MNQ, Tokyo Drift on MGC, one contract each). Holiday/weekend
aware via fetchers/holidays.py; calendar rows are shown, not gated (unmeasured
for these two). The 2026-08-09 QuantCrawler-pair text below is history: The rule and every number come from the 1-year TradingView
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

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Tier-1 US releases the desk watches. For the current live pair (Drift VWAP,
# Tokyo Drift) the event-day effect is UNMEASURED, so these rows are shown on the
# card as information and never flip a verdict. FOMC decision days are the one
# exception: the desk sits both out by house rule, not by measurement.
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
    "Live book since 2026-09-06: Drift VWAP Pullback v3.4.1 on MNQ and Tokyo "
    "Drift v1.5.1 on MGC, one contract each, one 50K account. Calendar effect "
    "on either strategy is unmeasured, so tier-1 releases are listed, not "
    "gated; FOMC decision days are a house-rule SKIP. Backtest numbers live on "
    "the Strategy Desk page. Display only: you flip the switch, not this page."
)

LIVE_ROWS = [
    {
        "strategy": "Drift VWAP Pullback",
        "instrument": "MNQ",
        "size": "1ct MNQ",
        "session": "US session, VWAP pullback with a fixed 85-point stop",
    },
    {
        "strategy": "Tokyo Drift",
        "instrument": "MGC",
        "size": "1ct MGC",
        "session": "Asia session drift on Micro Gold, flat by session end",
    },
]


def _evt(it: dict) -> dict:
    return {
        "family": it.get("family"),
        "detail": it.get("detail"),
        "time_et": it.get("time_et"),
        "time_oslo": it.get("time_oslo"),
        "impact": it.get("impact"),
    }


def pick_play(
    event_section: dict,
    now: datetime | None = None,
    edge_payload: dict | None = None,
    holidays: dict | None = None,
) -> dict:
    """Today's Play for the live pair.

    Weekend or holiday: the card says CLOSED for that date and previews the
    next real session underneath. The edge watchdog is NOT consulted: it
    tracks the retired strategies on an account that no longer trades, so its
    GREEN/YELLOW would be a fake signal on these rows.
    """
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    today_d = now_et.date()
    hol = holidays or {}
    h_today = hol.get("today") or {}
    closed_today = bool(h_today.get("closed")) if h_today else now_et.weekday() >= 5
    holiday_name = h_today.get("holiday")

    if closed_today:
        target = hol.get("next_trading_day")
        if not target:
            t = today_d + timedelta(days=7 - now_et.weekday() if now_et.weekday() >= 5 else 1)
            target = t.isoformat()
    else:
        target = today_d.isoformat()

    items = event_section.get("items") or []
    calendar_ok = event_section.get("status") == "ok" and not event_section.get("error")
    todays = [it for it in items if it.get("date_et") == target]
    gate_hits = [it for it in todays if it.get("family") in GATE_FAMILIES]
    fomc_today = any(it.get("family") == FOMC_DECISION for it in todays)
    other = [it for it in todays if it not in gate_hits and it.get("family") != FOMC_DECISION]

    rows = []
    for base in LIVE_ROWS:
        row = dict(base)
        row["edge"] = None
        if not calendar_ok:
            row["verdict"] = "UNKNOWN"
            row["why"] = (
                "Calendar fetch FAILED, so the desk cannot see what is scheduled. "
                "Check the release schedule yourself before arming."
            )
        elif fomc_today:
            row["verdict"] = "SKIP"
            row["why"] = "FOMC decision 14:00 ET. House rule: the live book sits out decision days."
        else:
            row["verdict"] = "RUN"
            why = f"{row['session']}. "
            if gate_hits:
                names = ", ".join(f"{g['family']} {g.get('time_et')} ET" for g in gate_hits)
                why += (
                    f"Tier-1 release on the slate: {names}. Effect on this strategy is "
                    "unmeasured, so it is listed, not gated."
                )
            else:
                why += "No tier-1 US release scheduled."
            if other:
                why += " Also scheduled: " + ", ".join(
                    f"{o.get('family')} {o.get('time_et')} ET" for o in other
                ) + "."
            row["why"] = why
        rows.append(row)

    closed_row = None
    if closed_today:
        h_tom = hol.get("tomorrow") or {}
        label = holiday_name or "Weekend"
        detail = h_today.get("detail")
        if not holiday_name and h_tom.get("holiday"):
            label = f"Weekend, then {h_tom['holiday']} on {h_tom.get('weekday')}"
            detail = h_tom.get("detail")
        closed_row = {
            "date_et": today_d.isoformat(),
            "label": label,
            "detail": detail,
        }

    return {
        "date_et": target,
        "preview": closed_today,
        "weekend": now_et.weekday() >= 5,
        "closed_today": closed_row,
        "calendar_ok": calendar_ok,
        "fomc_today": fomc_today,
        "edge_ok": False,
        "gate_events": [_evt(g) for g in gate_hits],
        "other_events": [_evt(o) for o in other],
        "rows": rows,
        "hidden_rows": [],
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
