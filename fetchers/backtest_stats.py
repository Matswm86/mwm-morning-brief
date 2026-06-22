"""backtest_stats — Strategy performance, mirrored from the trading platform.

Sources the exact numbers shown on the trading.mwmai.no strategy site
(`platform/frontend-rr7/app/lib/strategy-showcase.ts`, auto-generated from a
trailing-1-year backtest on the live cells with the canonical platform engine).
Do not hand-edit those numbers here — re-run the platform showcase generator
and this fetcher picks the new values up on the next build.

Surfaces only the strategy running on the XFA Funded account 24154823 (the
priority funded; ex-Combine 22484767, passed 2026-06-11):
  - PDHR MNQ  (cell pdhr-mnq-funded-24154823 — MNQ 5ct)

LiqSweep was RETIRED fleet-wide 2026-06-22 (overnight loss blew XFA 24154823)
and PARKED for a future save-attempt; the funded fleet now runs PDHR
(Prior-Day H/L break-and-retest, RTH-only) on all three funded accounts, so
this panel mirrors that single real-money strategy. The MGC card slot (orb_br)
is dropped — there is no second funded strategy.
"""

from __future__ import annotations

import json
import logging

from config import MWM_ROOT

log = logging.getLogger("morning-brief.backtest_stats")

SHOWCASE_TS = (
    MWM_ROOT / "projects/mwm-trading/platform/frontend-rr7/app/lib/strategy-showcase.ts"
)

REF_CAPITAL = 50_000.0

# showcase key -> brief card slot + display metadata for the live-XFA PDHR cell.
# `contracts` = the live funded cell's native size (5ct). The surviving brief
# slot id is `liqsweep` (the primary perf card in the markup); the second slot
# (orb_br) is no longer populated now that the funded fleet runs one strategy.
_CARDS = {
    "pdhr": {
        "slot": "liqsweep",
        "label": "PDHR MNQ",
        "contracts": 5,
        "source": "MNQ · Globex · 1y · trading.mwmai.no",
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
    # The single funded strategy (PDHR MNQ) straight from the platform showcase.
    # orb_br stays absent — the frontend hides the second card when it is unset.
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
