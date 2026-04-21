"""backtest_stats — Strategy performance from actual backtest JSON files.

Both strategies normalized to a $50k TopstepX account / 2ct MNQ for
apples-to-apples comparison. ORB backtest was run at 5ct/$1M, so P&L
and risk figures are scaled down by factor 0.4 (2/5).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from config import MWM_ROOT

log = logging.getLogger("morning-brief.backtest_stats")

LIQSWEEP_FILE = (
    MWM_ROOT / "data/backtest/results/liqsweep_v10/v10_arm12_confirm_summary.json"
)
ORB_FILE = (
    MWM_ROOT
    / "data/backtest/results/orb_layered/layer3_bucket945_orb110_tueoff_summary.json"
)

REF_CAPITAL = 50_000.0
REF_CONTRACTS = 2
POINT_VALUE = 2.0


def _months_between(start: str, end: str) -> float:
    try:
        d1 = datetime.fromisoformat(start[:10])
        d2 = datetime.fromisoformat(end[:10])
        return (d2.year - d1.year) * 12 + (d2.month - d1.month) + (d2.day - d1.day) / 30
    except Exception:
        return 12.0


def _liqsweep() -> dict:
    try:
        raw = json.loads(LIQSWEEP_FILE.read_text())
    except Exception as exc:
        log.warning("LiqSweep file missing: %s", exc)
        return {"status": "error"}

    p = raw["params"]
    s = raw["summary"]
    start, end = p["start_date"], p.get("end_date", "2026-02-13")
    months = _months_between(start, end)
    years = months / 12

    # Backtest is already 2ct/$50k — no scaling
    total_pnl = s["total_pnl"]
    avg_loss = abs(s["avg_loss"])
    max_dd = s["max_drawdown"]
    initial = p["initial_capital"]
    trades = s["total_positions"]

    monthly_usd = total_pnl / months
    yearly_usd = total_pnl / years

    return {
        "status": "ok",
        "label": "iFVG LiqSweep",
        "period": f"{start[:4]}–{end[:4]} ({round(years)}y)",
        "total_trades": trades,
        "win_rate_pct": round(s["win_rate"], 1),
        "profit_factor": round(s["profit_factor"], 2),
        "max_dd_pct": round(max_dd / initial * 100, 1),
        "risk_per_trade_usd": round(avg_loss),
        "risk_per_trade_pct": round(avg_loss / REF_CAPITAL * 100, 2),
        "monthly_avg_usd": round(monthly_usd),
        "monthly_avg_pct": round(monthly_usd / REF_CAPITAL * 100, 1),
        "monthly_avg_trades": round(trades / months, 1),
        "yearly_avg_usd": round(yearly_usd),
        "yearly_avg_pct": round(yearly_usd / REF_CAPITAL * 100, 1),
        "yearly_avg_trades": round(trades / years),
        "ref_capital": int(REF_CAPITAL),
        "ref_contracts": REF_CONTRACTS,
        "source": f"NQ 1m · {round(years)}y OOS · ${int(REF_CAPITAL/1000)}k ref",
    }


def _orb() -> dict:
    try:
        raw = json.loads(ORB_FILE.read_text())
    except Exception as exc:
        log.warning("ORB file missing: %s", exc)
        return {"status": "error"}

    bt_contracts = raw.get("contracts", 5)
    bt_capital = raw.get("initial_capital", 1_000_000.0)
    start = raw.get("period_start", "2025-02-01")
    end = raw.get("period_end", "2026-02-01")
    months = _months_between(start, end)

    # Normalize 5ct/$1M → 2ct/$50k
    scale = REF_CONTRACTS / bt_contracts
    total_pnl = raw["total_pnl_usd"] * scale
    avg_loss = abs(raw["avg_loss_usd"]) * scale
    max_dd = raw["max_drawdown_usd"] * scale
    trades = raw["trades"]

    monthly_usd = total_pnl / months
    yearly_usd = total_pnl  # 1-year backtest

    return {
        "status": "ok",
        "label": "ORB",
        "period": f"{start[:4]}–{end[:4]} (1y)",
        "total_trades": trades,
        "win_rate_pct": round(raw["win_rate_pct"], 1),
        "profit_factor": round(raw["profit_factor"], 2),
        "max_dd_pct": round(max_dd / REF_CAPITAL * 100, 1),
        "risk_per_trade_usd": round(avg_loss),
        "risk_per_trade_pct": round(avg_loss / REF_CAPITAL * 100, 2),
        "monthly_avg_usd": round(monthly_usd),
        "monthly_avg_pct": round(monthly_usd / REF_CAPITAL * 100, 2),
        "monthly_avg_trades": round(trades / months, 1),
        "yearly_avg_usd": round(yearly_usd),
        "yearly_avg_pct": round(yearly_usd / REF_CAPITAL * 100, 1),
        "yearly_avg_trades": trades,
        "ref_capital": int(REF_CAPITAL),
        "ref_contracts": REF_CONTRACTS,
        "source": f"NQ 1m · 1y regime-filtered · ${int(REF_CAPITAL/1000)}k ref",
    }


def fetch() -> dict:
    return {
        "liqsweep": _liqsweep(),
        "orb": _orb(),
        "status": "ok",
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch(), indent=2))
