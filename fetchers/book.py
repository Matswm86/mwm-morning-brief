"""The Strategy Desk — backtest book for the live pair and the bench.

Reads TradingView "List of Trades" exports (one Entry row + one Exit row per
trade) from data/tv_exports/ and computes, per strategy, the trailing-90-day
window and the full export window: trades, win rate, profit factor, net,
average win / loss, max drawdown (closed-trade equity), biggest loss, best and
worst day, and a downsampled equity curve for a sparkline.

Numbers are TradingView backtest fills at the export's own contract size, not
broker fills. That caveat ships on every card. The house bar for a sub-year
backtest is WR >= 62% and PF >= 1.4 together (reporting rule 2026-08-29): a
strategy either clears it or reads "below the bar"; nothing here hides a
number.

Public-site rule: strategy names only. No account ids, no usernames, no paths.
"""
from __future__ import annotations

import csv
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("morning-brief.book")

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "tv_exports"
BAR_WR = 62.0
BAR_PF = 1.4
WINDOW_DAYS = 90

# The book. `role` = live | bench | retired. `file` is a glob prefix inside
# EXPORT_DIR; the newest matching file wins. `note` is the desk's one-line
# context, written by a human, not inferred from the numbers.
REGISTRY: list[dict] = [
    {
        "key": "drift_vwap",
        "name": "Drift VWAP Pullback",
        "version": "v3.4.1",
        "instrument": "MNQ",
        "role": "live",
        "file": "Drift_VWAP_Pullback_Strategy_v3.4.1_",
        "live_size": "1 contract",
        "note": "Live since 2026-09-06 with one contract. Take-profit limits traded through on 87-92% of exits when checked against real MNQ one-minute data, so the export's fills are close to honest.",
    },
    {
        "key": "tokyo_drift",
        "name": "Tokyo Drift",
        "version": "v1.5.1",
        "instrument": "MGC",
        "role": "live",
        "file": "Tokyo_Drift_v1.5.1_",
        "live_size": "1 contract",
        "note": "Live since 2026-09-06 with one contract on Micro Gold. Asia-session drift model; fills confirmed against real orders, so the export's numbers are not a spot-gold proxy.",
    },
    {
        "key": "crt_sniper",
        "name": "CRT Sniper",
        "version": "v3.2.8 single-leg",
        "instrument": "MNQ",
        "role": "bench",
        "file": "CRT_SNIPER_v3.2.8_CME_MINI_MNQ1!_2026-09-06_49c58",
        "note": "Candle-range-theory sweep model. Not deployed: its worst loss is a range-sized stop (203 points on 2026-07-30), which is the size of stop a 50K account cannot wear twice in a day.",
    },
    {
        "key": "magic_hour",
        "name": "Magic Hour Blueprint",
        "version": "v1.9.1 prop-friendly",
        "instrument": "MNQ",
        "role": "bench",
        "file": "Magic_Hour_Blueprint_v1.9.1_",
        "note": "Added to the bench 2026-09-06. Session-window breakout with a hard flatten; take-profits traded through 95% of the time in the fill check. Not deployed.",
    },
    {
        "key": "qcs_preset",
        "name": "QCS-Preset",
        "version": "1-year export",
        "instrument": "MNQ",
        "role": "retired",
        "file": "QCS-Preset_",
        "note": "The former main strategy, four contracts. Its edge watchdog went YELLOW in early September (rolling win rate 70%, three straight losses) and the desk moved on. Numbers here are per the export's four-contract size.",
    },
    {
        "key": "qc_trend_mgc",
        "name": "QC Trend",
        "version": "MGC export 2026-09-04",
        "instrument": "MGC",
        "role": "retired",
        "file": "QC_Trend_Strat_COMEX_MINI_MGC1!",
        "note": "The gold trend follower that ran beside QCS-Preset. Replaced on the gold slot by Tokyo Drift. Short export: three months only.",
    },
    {
        "key": "liqsweep_ifvg",
        "name": "LiqSweep + iFVG",
        "version": "S3",
        "instrument": "MNQ",
        "role": "retired",
        "file": "LiqSweep+iFVG_S3_",
        "note": "Liquidity-sweep into inverted fair-value-gap model, two contracts in the export. The research arc closed NULL on 2026-09-03: every variant landed below the bar.",
    },
]


def _newest(prefix: str) -> Path | None:
    hits = sorted(EXPORT_DIR.glob(prefix + "*.csv"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_trades(path: Path) -> list[dict]:
    """One dict per closed trade: exit time, pnl, qty, signal."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if not str(r.get("Type", "")).startswith("Exit"):
            continue
        ts = str(r.get("Date and time", "")).strip()
        pnl = _f(r.get("Net PnL USD"))
        if pnl is None:
            continue
        try:
            t = datetime.strptime(ts, "%Y-%m-%d %H:%M")
        except ValueError:
            continue  # "Open" rows (trade still running) carry no exit time
        out.append(
            {
                "t": t,
                "pnl": pnl,
                "qty": int(_f(r.get("Size (qty)")) or 1),
                "signal": str(r.get("Signal", "")).strip(),
                "mae": _f(r.get("Adverse excursion USD")),
            }
        )
    out.sort(key=lambda x: x["t"])
    return out


def _stats(trades: list[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gw, gl = sum(wins), -sum(losses)
    eq = peak = dd = 0.0
    curve = []
    for t in trades:
        eq += t["pnl"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        curve.append(round(eq))
    by_day: dict[str, float] = defaultdict(float)
    for t in trades:
        by_day[t["t"].strftime("%Y-%m-%d")] += t["pnl"]
    days = sorted(by_day.items())
    best = max(days, key=lambda kv: kv[1])
    worst = min(days, key=lambda kv: kv[1])
    wr = 100.0 * len(wins) / n
    pf = (gw / gl) if gl > 0 else None
    step = max(1, n // 60)
    spark = curve[::step]
    if spark[-1] != curve[-1]:
        spark.append(curve[-1])
    return {
        "trades": n,
        "from": trades[0]["t"].strftime("%Y-%m-%d"),
        "to": trades[-1]["t"].strftime("%Y-%m-%d"),
        "calendar_days": (trades[-1]["t"] - trades[0]["t"]).days + 1,
        "trading_days": len(days),
        "net_usd": round(sum(pnls)),
        "win_rate_pct": round(wr, 1),
        "profit_factor": round(pf, 2) if pf is not None else None,
        "avg_win_usd": round(gw / len(wins)) if wins else 0,
        "avg_loss_usd": round(-gl / len(losses)) if losses else 0,
        "expectancy_usd": round(sum(pnls) / n, 1),
        "max_dd_usd": round(dd),
        "biggest_loss_usd": round(min(pnls)),
        "biggest_win_usd": round(max(pnls)),
        "best_day": {"date": best[0], "usd": round(best[1])},
        "worst_day": {"date": worst[0], "usd": round(worst[1])},
        "per_day_usd": round(sum(pnls) / len(days)),
        "trades_per_day": round(n / len(days), 2),
        "clears_bar": bool(wr >= BAR_WR and pf is not None and pf >= BAR_PF),
        "spark": spark,
    }


def _verdict(s90: dict, sfull: dict, role: str) -> dict:
    """Desk verdict: a word + one honest sentence, from the numbers only."""
    s = s90 if s90.get("trades", 0) >= 20 else sfull
    basis = "90d" if s is s90 else "full export"
    pf, wr, n = s.get("profit_factor"), s.get("win_rate_pct"), s.get("trades", 0)
    if n == 0:
        return {"word": "NO DATA", "basis": basis, "line": "No closed trades in the export."}
    if pf is None:
        return {"word": "NO LOSSES", "basis": basis, "line": f"{n} trades, not one loser. Too few trades to believe."}
    if pf < 1.0:
        word = "LOSING"
        line = f"Lost money in its own backtest ({basis}): PF {pf}, win rate {wr}% over {n} trades."
    elif s.get("clears_bar"):
        word = "CLEARS THE BAR"
        line = f"Win rate {wr}% and PF {pf} over {n} trades ({basis}) clear the house bar of 62% and 1.4 together."
    else:
        word = "BELOW THE BAR"
        line = f"PF {pf} with win rate {wr}% over {n} trades ({basis}). Profitable on paper, below the house bar of 62% / 1.4."
    if role == "live":
        comeback = None
    elif word == "CLEARS THE BAR":
        comeback = "Comeback? The numbers say yes; the desk says one contract on a practice account first."
    elif word == "BELOW THE BAR":
        comeback = "Comeback? Not on these numbers. It needs a stop it can afford or a filter that lifts the win rate."
    else:
        comeback = "Comeback? No. A model that loses in its own backtest is not resting, it is retired."
    return {"word": word, "basis": basis, "line": line, "comeback": comeback}


def _entry(meta: dict) -> dict:
    path = _newest(meta["file"])
    base = {k: meta[k] for k in ("key", "name", "version", "instrument", "role", "note")}
    base["live_size"] = meta.get("live_size")
    if path is None:
        base.update(status="missing", error="no export on file")
        return base
    trades = _load_trades(path)
    if not trades:
        base.update(status="empty", error="export has no closed trades")
        return base
    cutoff = trades[-1]["t"] - timedelta(days=WINDOW_DAYS)
    t90 = [t for t in trades if t["t"] >= cutoff]
    qty = sorted({t["qty"] for t in trades})
    base.update(
        status="ok",
        export_date=path.name.split("_")[-2] if "_" in path.name else None,
        export_size_contracts=qty[0] if len(qty) == 1 else qty,
        last_90d=_stats(t90),
        full=_stats(trades),
        verdict=_verdict(_stats(t90), _stats(trades), meta["role"]),
    )
    return base


def fetch() -> dict:
    entries = [_entry(m) for m in REGISTRY]
    ok = [e for e in entries if e.get("status") == "ok"]
    return {
        "status": "ok" if ok else "error",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": WINDOW_DAYS,
        "bar": {"win_rate_pct": BAR_WR, "profit_factor": BAR_PF},
        "fill_basis": "TradingView List-of-Trades exports, strategy-tester fills, export's own contract size",
        "live": [e for e in entries if e["role"] == "live"],
        "bench": [e for e in entries if e["role"] == "bench"],
        "retired": [e for e in entries if e["role"] == "retired"],
    }


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO)
    d = fetch()
    for grp in ("live", "bench", "retired"):
        for e in d[grp]:
            s = e.get("last_90d") or {}
            print(f"{grp:8} {e['name']:24} {e['instrument']} n={s.get('trades')} WR={s.get('win_rate_pct')} PF={s.get('profit_factor')} net={s.get('net_usd')} dd={s.get('max_dd_usd')} -> {e.get('verdict',{}).get('word')}")
    print(json.dumps({k: v for k, v in d.items() if k not in ('live','bench','retired')}, indent=1))
