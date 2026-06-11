"""backtest_stats — Strategy performance, mirrored from the trading platform.

Sources the exact numbers shown on the trading.mwmai.no strategy site
(`platform/frontend-rr7/app/lib/strategy-showcase.ts`, auto-generated from a
trailing-1-year backtest on the live cells with the canonical platform engine).
Do not hand-edit those numbers here — re-run the platform showcase generator
and this fetcher picks the new values up on the next build.

Surfaces only the strategies running on the XFA Funded account 24154823 (ex-Combine 22484767, passed 2026-06-11):
  - LiqSweep MNQ  (cell liqsweep-v10-mnq-combine — MNQ 4ct)
  - LiqSweep MGC  (cell liqsweep-v10-mgc-combine — MGC 2ct)

Both are the same iFVG-reversion engine on different contracts. The ORB-Breakout
cell was pulled off Combine onto PRAC 2026-06-02, so it is no longer surfaced
here (this panel mirrors the real-money XFA fleet only).
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

# showcase key -> brief card slot + display metadata for the two live-XFA
# LiqSweep cells. `contracts` = the live cell's native size. The brief slot ids
# come from the card markup: liqsweep (MNQ), orb-br (MGC). Both cards now pull
# straight from the platform showcase (which carries a dedicated MGC entry).
_CARDS = {
    "liqsweep": {
        "slot": "liqsweep",
        "label": "LiqSweep MNQ",
        "contracts": 4,
        "source": "MNQ · Globex · 1y · trading.mwmai.no",
    },
    "liqsweep_mgc": {
        "slot": "orb_br",
        "label": "LiqSweep MGC",
        "contracts": 2,
        "source": "MGC · Globex · 1y · trading.mwmai.no",
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
    out: dict = {"status": "ok"}

    # Both LiqSweep XFA cells (MNQ + MGC) straight from the platform showcase.
    try:
        sc = _load_showcase()
        for key, meta in _CARDS.items():
            entry = sc.get(key)
            out[meta["slot"]] = _card(entry, meta) if entry else {"status": "error"}
    except Exception as exc:
        log.warning("strategy-showcase parse failed: %s", exc)
        out["liqsweep"] = {"status": "error"}
        out["orb_br"] = {"status": "error"}
        out["status"] = "error"

    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch(), indent=2))
