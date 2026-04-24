"""backtest_stats — Strategy performance from actual backtest JSON files.

Both strategies normalised to a $50k TopstepX account / 2ct MNQ reference.
LiqSweep v10 was run directly at 2ct/$50k — no scaling.
ORBaron locked config was run at 2ct/$1M — dollar amounts are identical since
contract count is the same; only initial_capital differs (irrelevant for P&L/DD).
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
# ORBaron RTH 1m — locked config (Mon+Tue OFF, bk_dist=1.0, tp=3.0)
ORB_CONFIG_FILE = (
    MWM_ROOT / "data/backtest/results/orbaron/locked/config_locked.json"
)
ORB_PARITY_FILE = (
    MWM_ROOT / "data/backtest/results/orbaron/parity_report.json"
)
ORB_DETAIL_FILE = (
    MWM_ROOT / "data/backtest/results/orbaron/locked/summary_1y.json"
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
        cfg = json.loads(ORB_CONFIG_FILE.read_text())
        parity = json.loads(ORB_PARITY_FILE.read_text())
        detail = json.loads(ORB_DETAIL_FILE.read_text())
    except Exception as exc:
        log.warning("ORBaron locked files missing: %s", exc)
        return {"status": "error"}

    # _summary_1y_2ct is the canonical locked-config result (106 trades, Mon+Tue OFF)
    s = cfg["_summary_1y_2ct"]
    start, end = parity["period"]
    months = _months_between(start, end)

    total_pnl = s["total_pnl_usd"]
    max_dd = s["max_drawdown_usd"]
    trades = s["trades"]
    # avg_loss from the 1y detail run (same 2ct setup, negligible config drift)
    avg_loss = abs(detail.get("avg_loss_usd", -201.0))

    monthly_usd = total_pnl / months

    return {
        "status": "ok",
        "label": "ORB RT",
        "period": f"{start[:4]}–{end[:4]} (1y)",
        "total_trades": trades,
        "win_rate_pct": round(s["win_rate_pct"], 1),
        "profit_factor": round(s["profit_factor"], 2),
        "max_dd_pct": round(max_dd / REF_CAPITAL * 100, 1),
        "risk_per_trade_usd": round(avg_loss),
        "risk_per_trade_pct": round(avg_loss / REF_CAPITAL * 100, 2),
        "monthly_avg_usd": round(monthly_usd),
        "monthly_avg_pct": round(monthly_usd / REF_CAPITAL * 100, 1),
        "monthly_avg_trades": round(trades / months, 1),
        "yearly_avg_usd": round(total_pnl),
        "yearly_avg_pct": round(total_pnl / REF_CAPITAL * 100, 1),
        "yearly_avg_trades": trades,
        "ref_capital": int(REF_CAPITAL),
        "ref_contracts": REF_CONTRACTS,
        "source": f"NQ 1m · 1y locked · ${int(REF_CAPITAL/1000)}k ref · Mon+Tue OFF",
    }


# ORB BR (simple-breakout) — MGC Asia 02:00 Oslo, 5m, best cell from the family
ORB_BR_CONFIG_FILE = (
    MWM_ROOT / "projects/mwm-trading/deploy/configs/orbaron-mgc-asia-practice.json"
)


def _orb_br() -> dict:
    try:
        cfg = json.loads(ORB_BR_CONFIG_FILE.read_text())
    except Exception as exc:
        log.warning("ORB BR config missing: %s", exc)
        return {"status": "error"}

    s = cfg["_summary_1y_2ct"]
    start, end = "2025-02-17", "2026-02-17"
    months = _months_between(start, end)

    total_pnl = s["total_pnl_usd"]
    max_dd = s["max_drawdown_usd"]
    trades = s["trades"]

    # Derive avg_loss from PF + trade counts (no per-trade file in deploy config)
    wins = round(trades * s["win_rate_pct"] / 100)
    losses = trades - wins
    if losses > 0:
        # total_loss = total_pnl / (PF - 1) × (1/PF) … simpler: solve PF equation
        total_loss = total_pnl / (s["profit_factor"] - 1)
        avg_loss = total_loss / losses
    else:
        avg_loss = 0.0

    monthly_usd = total_pnl / months

    return {
        "status": "ok",
        "label": "ORB BR",
        "period": f"{start[:4]}–{end[:4]} (1y)",
        "total_trades": trades,
        "win_rate_pct": round(s["win_rate_pct"], 1),
        "profit_factor": round(s["profit_factor"], 2),
        "max_dd_pct": round(max_dd / REF_CAPITAL * 100, 1),
        "risk_per_trade_usd": round(avg_loss),
        "risk_per_trade_pct": round(avg_loss / REF_CAPITAL * 100, 2),
        "monthly_avg_usd": round(monthly_usd),
        "monthly_avg_pct": round(monthly_usd / REF_CAPITAL * 100, 1),
        "monthly_avg_trades": round(trades / months, 1),
        "yearly_avg_usd": round(total_pnl),
        "yearly_avg_pct": round(total_pnl / REF_CAPITAL * 100, 1),
        "yearly_avg_trades": trades,
        "ref_capital": int(REF_CAPITAL),
        "ref_contracts": REF_CONTRACTS,
        "source": f"MGC 5m · 1y locked · ${int(REF_CAPITAL/1000)}k ref · Asia OR Oslo 02:00",
    }


def fetch() -> dict:
    return {
        "liqsweep": _liqsweep(),
        "orb": _orb(),
        "orb_br": _orb_br(),
        "status": "ok",
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch(), indent=2))
