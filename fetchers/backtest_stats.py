"""backtest_stats — Strategy performance, mirrored from the trading platform.

Sources the exact numbers shown on the trading.mwmai.no strategy site
(`platform/frontend-rr7/app/lib/strategy-showcase.ts`, auto-generated from a
trailing-1-year backtest on the live cells with the canonical platform engine).
Do not hand-edit those numbers here — re-run the platform showcase generator
and this fetcher picks the new values up on the next build.

Surfaces only the strategies running on the 50K Combine account 22484767:
  - Liquidity Sweep  (cell liqsweep_mnq — runs on MNQ 4ct + MGC 4ct)
  - ORB Breakout     (cell orb_breakout_mnq_rth — MNQ 2ct)

The MGC LiqSweep cell runs the same strategy as the MNQ one; the platform
showcases LiqSweep on its MNQ cell, so it appears once here (covering both).
"""
from __future__ import annotations

import json
import logging

from config import MWM_ROOT, SERVICE_ROOT

log = logging.getLogger("morning-brief.backtest_stats")

SHOWCASE_TS = (
    MWM_ROOT
    / "projects/mwm-trading/platform/frontend-rr7/app/lib/strategy-showcase.ts"
)
# MGC LiqSweep is NOT in the platform site's showcase (it only showcases the
# MNQ cell). This file holds the MGC numbers computed via the platform's own
# harness (run_cell / dry_run_backtest) over the identical showcase window
# (2025-05-22..2026-05-22, $50k, gross pnl_usd). Regenerate with the same
# dry_run_backtest call if the MGC cell params change.
MGC_SHOWCASE = SERVICE_ROOT / "data" / "liqsweep_mgc_showcase.json"

REF_CAPITAL = 50_000.0

# showcase key -> brief card slot + display metadata for the platform-site
# strategies. `contracts` = the live cell's native size. The brief slot ids
# come from the card markup: liqsweep (MNQ), orb-br (MGC), orb (ORB Breakout).
_CARDS = {
    "liqsweep": {
        "slot": "liqsweep",
        "label": "LiqSweep MNQ",
        "contracts": 4,
        "source": "MNQ · Globex · 1y · trading.mwmai.no",
    },
    "orb_breakout": {
        "slot": "orb",
        "label": "ORB Breakout",
        "contracts": 2,
        "source": "MNQ · RTH · 1y · trading.mwmai.no",
    },
}

# MGC LiqSweep — own card (slot orb_br), sourced from MGC_SHOWCASE.
_MGC_META = {
    "slot": "orb_br",
    "label": "LiqSweep MGC",
    "contracts": 4,
    "source": "MGC · Globex · 1y · platform engine",
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


def _load_mgc() -> dict | None:
    """Load the harness-computed MGC LiqSweep showcase entry (or None)."""
    try:
        return json.loads(MGC_SHOWCASE.read_text())
    except Exception as exc:
        log.warning("MGC showcase read failed: %s", exc)
        return None


def fetch() -> dict:
    out: dict = {"status": "ok"}

    # MNQ LiqSweep + ORB Breakout — straight from the platform site showcase.
    try:
        sc = _load_showcase()
        for key, meta in _CARDS.items():
            entry = sc.get(key)
            out[meta["slot"]] = _card(entry, meta) if entry else {"status": "error"}
    except Exception as exc:
        log.warning("strategy-showcase parse failed: %s", exc)
        out["liqsweep"] = {"status": "error"}
        out["orb"] = {"status": "error"}
        out["status"] = "error"

    # MGC LiqSweep — own card, platform-engine numbers from MGC_SHOWCASE.
    mgc = _load_mgc()
    out[_MGC_META["slot"]] = _card(mgc, _MGC_META) if mgc else {"status": "error"}

    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch(), indent=2))
