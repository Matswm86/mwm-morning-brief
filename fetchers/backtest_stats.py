"""backtest_stats — Strategy performance, mirrored from the trading platform.

Sources the exact numbers shown on the trading.mwmai.no strategy site
(`platform/frontend-rr7/app/lib/strategy-showcase.ts`, auto-generated from a
trailing-1-year backtest on the live cells with the canonical platform engine).
Do not hand-edit those numbers here — re-run the platform showcase generator
and this fetcher picks the new values up on the next build.

Two showcase cards:
  - PDHR MNQ  (the funded PDHR cell — MNQ 5ct)
  - ORB c5    (cell orbaron-orbc5-practice — MNQ 2ct, RTH; LOCKED Ironclad)

LiqSweep was RETIRED fleet-wide 2026-06-22 (an overnight loss blew the funded account)
and PARKED for a future save-attempt; the funded fleet now runs PDHR
(Prior-Day H/L break-and-retest, RTH-only) on all three funded accounts. The
second card (orb_br slot) shows ORB c5 — the best-performing locked ORB
(PF 4.3, the opening-range break + stop-to-breakeven), a validated backtest
showcase rather than a second funded strategy.
"""

from __future__ import annotations

import json
import logging

from config import MWM_ROOT

log = logging.getLogger("morning-brief.backtest_stats")

SHOWCASE_TS = MWM_ROOT / "projects/mwm-trading/platform/frontend-rr7/app/lib/strategy-showcase.ts"

REF_CAPITAL = 50_000.0

# showcase key -> brief card slot + display metadata.
# `contracts` = each cell's native size. The primary card slot id is `liqsweep`
# (legacy markup id, now the PDHR funded cell); the second slot (orb_br) carries
# ORB c5, the best locked ORB showcase.
_CARDS = {
    "pdhr": {
        "slot": "liqsweep",
        "label": "PDHR MNQ",
        "contracts": 5,
        "source": "MNQ · RTH · 1y · trading.mwmai.no",
    },
    "orb_c5": {
        "slot": "orb_br",
        "label": "ORB c5",
        "contracts": 2,
        "source": "MNQ · RTH · 1y · trading.mwmai.no",
    },
}


def _load_showcase() -> dict[str, dict]:
    """Parse the STRATEGIES array out of the showcase TS into {key: entry}."""
    text = SHOWCASE_TS.read_text()
    i = text.index("export const STRATEGIES")
    # anchor on "= [" — the type annotation StratShowcase[] also contains "[".
    start = text.index("= [", i) + 2
    end = text.index("];", start)
    arr = json.loads(text[start : end + 1])
    return {e["key"]: e for e in arr}


def _card(entry: dict, meta: dict) -> dict:
    m = entry["metrics"]
    total = float(m["totalPnl"])
    ret = float(m["returnPct"])
    trades = int(m["trades"])
    avg_loss = abs(float(m.get("avgLoss") or 0.0))
    pf = m.get("profitFactor")
    return {
        "status": "ok",
        "label": meta["label"],
        "period": "1 year backtest",
        "total_trades": trades,
        "win_rate_pct": round(float(m["winRate"]), 1),
        "profit_factor": round(float(pf), 2) if pf else None,
        "max_dd_pct": round(float(m["maxDdPct"]), 1),
        "risk_per_trade_usd": round(avg_loss),
        "risk_per_trade_pct": round(avg_loss / REF_CAPITAL * 100, 2),
        "monthly_avg_usd": round(total / 12),
        "monthly_avg_pct": round(ret / 12, 1),
        "monthly_avg_trades": round(trades / 12, 1),
        "yearly_avg_usd": round(total),
        "yearly_avg_pct": round(ret, 1),
        "yearly_avg_trades": trades,
        "ref_capital": int(REF_CAPITAL),
        "ref_contracts": meta["contracts"],
        "source": meta["source"],
    }


def fetch() -> dict:
    # Both cards (PDHR MNQ + ORB c5) straight from the platform showcase.
    # The loop populates each slot; orb_br falls back to None (card hidden)
    # only if the showcase has no orb_c5 entry.
    out: dict = {"status": "ok", "orb_br": None}

    try:
        sc = _load_showcase()
        for key, meta in _CARDS.items():
            entry = sc.get(key)
            out[meta["slot"]] = _card(entry, meta) if entry else {"status": "error"}
    except Exception as exc:
        log.warning("strategy-showcase parse failed: %s", exc)
        out["liqsweep"] = {"status": "error"}
        out["status"] = "error"

    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch(), indent=2))
