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
import json
import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
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
        return {
            "word": "NO LOSSES",
            "basis": basis,
            "line": f"{n} trades, not one loser. Too few trades to believe.",
        }
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
        comeback = "Eligible for a return on these numbers; the desk's condition is one contract on a practice account first."
    elif word == "BELOW THE BAR":
        comeback = "Not eligible on these numbers. The win rate is the problem, and a filter that raises it would have to be measured on a window this export has not seen."
    else:
        comeback = "Not eligible. The export loses money before slippage."
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


PROSE_CACHE = EXPORT_DIR.parent / "book_prose_cache.json"

PROSE_SYSTEM = """You are the strategy correspondent of a small daily trading newspaper set like a 1920s broadsheet. You write about one trading strategy at a time, from its backtest figures, for a reader who runs Micro Nasdaq and Micro Gold futures on a 50,000-dollar prop-firm account with a 1,000-dollar daily loss limit.

Binding rules:
- Use ONLY the figures and notes in the user message. Never invent a cause, a market event, a fill, or a number. If something cannot be judged from the figures, say so in one clause.
- Voice: a seasoned wire-desk journalist. Short declarative sentences, concrete nouns, active voice. No hedging filler, no cliches ("at the end of the day", "the numbers speak for themselves", "only time will tell", "navigate", "landscape", "delve", "robust", "game-changer"), no rhetorical questions, no exclamation marks, no bullet points, no headings, no emoji, no second person.
- Dry wit is allowed once, at the expense of the strategy or the desk, never a person.
- The house bar for a sub-year backtest is win rate 62% AND profit factor 1.4 together. Use the verdict given; do not overrule it.
- All figures are TradingView strategy-tester fills at the export's contract size, not broker fills. Say this once, plainly, where it matters.
- Length: three paragraphs, 170-240 words total. Paragraph one: what the last 90 days show, led by the fact that matters most (worst day against the daily loss limit, or the win rate, or the drawdown). Paragraph two: the full export against the 90 days, and what changed or did not. Paragraph three: for a LIVE strategy, what the reader should watch for as evidence it has stopped working; for a BENCH or RETIRED strategy, whether it can come back and the one condition that would have to be met, stated as a fact about the figures.
- Call the strategy by the exact name given and nothing else; invent no nicknames or version labels.
- Typography: no em dashes or en dashes anywhere; use commas, colons or full stops. Never write "essentially", "basically", "robust", "comprehensive", "seems to".
- Output the three paragraphs separated by blank lines and nothing else."""


def _clean(text: str) -> str:
    """House typography: no dashes as punctuation, no doubled spaces."""
    text = re.sub(r"\s*[\u2014\u2013]\s*", ", ", text)
    text = re.sub(r"(\w)\s*--\s*(\w)", r"\1, \2", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _prose_facts(e: dict) -> str:
    s, f, v = e["last_90d"], e["full"], e["verdict"]

    def block(name: str, x: dict) -> str:
        return (
            f"{name}: {x['from']} to {x['to']}, {x['trades']} trades over {x['trading_days']} trading days, "
            f"win rate {x['win_rate_pct']}%, profit factor {x['profit_factor']}, net ${x['net_usd']:,}, "
            f"${x['per_day_usd']:,} per trading day, {x['trades_per_day']} trades per day, "
            f"average win ${x['avg_win_usd']:,} / average loss ${x['avg_loss_usd']:,}, expectancy ${x['expectancy_usd']} per trade, "
            f"max drawdown ${x['max_dd_usd']:,} (closed-trade equity), worst trade ${x['biggest_loss_usd']:,}, "
            f"best trade ${x['biggest_win_usd']:,}, worst day ${x['worst_day']['usd']:,} on {x['worst_day']['date']}, "
            f"best day ${x['best_day']['usd']:,} on {x['best_day']['date']}."
        )

    return "\n".join(
        [
            f"STRATEGY: {e['name']} {e['version']} on {e['instrument']}. ROLE: {e['role'].upper()}."
            + (f" Traded live at {e['live_size']}." if e.get("live_size") else ""),
            f"EXPORT: TradingView List of Trades dated {e.get('export_date')}, {e.get('export_size_contracts')} contract(s) per trade in the log.",
            f"DESK NOTE (human-written context, may be quoted): {e['note']}",
            block("LAST 90 DAYS", s),
            block("FULL EXPORT", f),
            f"VERDICT: {v['word']} ({v['basis']}). {v['line']}"
            + (f" {v['comeback']}" if v.get("comeback") else ""),
            "ACCOUNT CONTEXT: 50K prop-firm account, $1,000 daily loss limit, $2,000 maximum drawdown from the starting balance.",
        ]
    )


def _load_prose_cache() -> dict:
    try:
        return json.loads(PROSE_CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _fallback_prose(e: dict) -> list[str]:
    s, f, v = e["last_90d"], e["full"], e["verdict"]
    p1 = (
        f"Over the last {s['trading_days']} trading days the export closed {s['trades']} trades for ${s['net_usd']:,} net, "
        f"a win rate of {s['win_rate_pct']}% and a profit factor of {s['profit_factor']}. The worst day cost ${abs(s['worst_day']['usd']):,} "
        f"on {s['worst_day']['date']}, the deepest closed-trade drawdown ${s['max_dd_usd']:,}."
    )
    p2 = (
        f"The full export runs {f['from']} to {f['to']}: {f['trades']} trades, profit factor {f['profit_factor']}, ${f['net_usd']:,} net. "
        f"Figures are TradingView strategy-tester fills at {e.get('export_size_contracts')} contract(s)."
    )
    p3 = v["line"] + (" " + v["comeback"] if v.get("comeback") else "")
    return [p1, p2, p3]


def _write_prose(entries: list[dict]) -> None:
    """Attach `prose` (list of paragraphs) to each ok entry; Sonnet via claude -p, cached by export identity."""
    cache = _load_prose_cache()
    changed = False
    call = None
    try:
        import os
        import sys

        core = os.path.expanduser("~/MWM/core")
        if core not in sys.path:
            sys.path.insert(0, core)
        from anthropic_via_claude_cli import call_claude_cli as call  # type: ignore
    except Exception:
        log.warning("claude cli unavailable; book prose falls back to tables")
    for e in entries:
        if e.get("status") != "ok":
            continue
        path = _newest(REGISTRY[[m["key"] for m in REGISTRY].index(e["key"])]["file"])
        ident = f"{e['key']}|{path.name if path else ''}|{int(path.stat().st_mtime) if path else 0}|{e['verdict']['word']}|v3"
        hit = cache.get(e["key"])
        if hit and hit.get("ident") == ident and hit.get("paragraphs"):
            e["prose"], e["prose_by"] = hit["paragraphs"], hit.get("by", "the strategy desk")
            continue
        paras: list[str] | None = None
        if call:
            text = call(
                model="sonnet", system_prompt=PROSE_SYSTEM, user_prompt=_prose_facts(e), timeout=180
            )
            if text:
                paras = [_clean(p) for p in text.strip().split("\n\n") if p.strip()]
                if not (2 <= len(paras) <= 4) or sum(len(p) for p in paras) < 400:
                    log.warning("book prose rejected for %s: %r", e["key"], text[:100])
                    paras = None
        if paras:
            e["prose"], e["prose_by"] = paras, "the strategy desk"
            cache[e["key"]] = {
                "ident": ident,
                "paragraphs": paras,
                "by": "the strategy desk",
                "written": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            changed = True
        else:
            e["prose"], e["prose_by"] = (
                _fallback_prose(e),
                "the tables (correspondent unavailable this edition)",
            )
    if changed:
        try:
            PROSE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
        except OSError:
            log.warning("book prose cache not written")


def fetch() -> dict:
    entries = [_entry(m) for m in REGISTRY]
    _write_prose(entries)
    ok = [e for e in entries if e.get("status") == "ok"]
    return {
        "status": "ok" if ok else "error",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
            print(
                f"{grp:8} {e['name']:24} {e['instrument']} n={s.get('trades')} WR={s.get('win_rate_pct')} PF={s.get('profit_factor')} net={s.get('net_usd')} dd={s.get('max_dd_usd')} -> {e.get('verdict', {}).get('word')}"
            )
    print(
        json.dumps({k: v for k, v in d.items() if k not in ("live", "bench", "retired")}, indent=1)
    )
