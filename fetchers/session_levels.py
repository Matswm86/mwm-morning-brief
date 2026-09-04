"""Prior-session highs and lows for the MNQ chart — the liquidity pools.

Mats trades three sessions, defined in his own local wall-clock (Europe/Oslo):

    Asia    02:00 - 07:00
    London  09:00 - 15:30
    New York 15:30 - 22:00

Each completed block leaves a high and a low. Those two prices are where
resting stops sit, so they are the levels price tends to reach for. This
module buckets ~16 days of 5-minute bars into those blocks, takes the
extremes of each, and marks whether later price action has already traded
back to them (a taken pool is no longer a target).

Output feeds web/assets/session_levels.js, which draws them as horizontal
price lines on the live MNQ chart.

Two fetch paths, matching bar_refresh.sh:
  --source pxpy   project-x-py / TopstepX real-time MNQ  (run under the
                  mwm-trading venv, py3.12)
  --source yahoo  Yahoo NQ=F, 15-min delayed, front-month NQ not MNQ
                  (run under python3.11) — fallback only

Usage:
  /home/mats/MWM-AI/projects/mwm-trading/.venv/bin/python \
      -m fetchers.session_levels --source pxpy --write web/session_levels_mnq.json
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("morning-brief.session_levels")

OSLO = ZoneInfo("Europe/Oslo")

# Mats's session blocks, half-open [start, end) in Oslo wall-clock. London and
# New York touch at 15:30; the half-open interval puts the 15:30 bar in NY.
SESSIONS: list[tuple[str, str, time, time]] = [
    ("asia", "Asia", time(2, 0), time(7, 0)),
    ("london", "London", time(9, 0), time(15, 30)),
    ("ny", "New York", time(15, 30), time(22, 0)),
]

DEFAULT_DAYS = 16  # ~11 trading days, enough for 30 session blocks
DEFAULT_KEEP = 30  # blocks written to JSON; the page shows the last 10
DEFAULT_SYMBOL = "MNQ"
YAHOO_SYMBOL = "NQ=F"


# --------------------------------------------------------------------------
# bar sources
# --------------------------------------------------------------------------


def _bars_pxpy(symbol: str, days: int) -> tuple[list[dict], str]:
    from fetchers import bars_pxpy as f_px

    f_px._load_env(f_px.PXPY_ENV_FILE)
    import asyncio

    payload = asyncio.run(f_px._fetch_bars(symbol, days, 5))
    return payload["bars"], "project-x-py"


def _bars_yahoo(days: int) -> tuple[list[dict], str]:
    from fetchers import bars as f_bars

    range_ = "1mo" if days > 5 else f"{days}d"
    payload = f_bars.fetch(YAHOO_SYMBOL, "5m", range_)
    return payload["bars"], f"yahoo {YAHOO_SYMBOL} (delayed, NQ not MNQ)"


# --------------------------------------------------------------------------
# session bucketing
# --------------------------------------------------------------------------


def _block_of(dt: datetime) -> tuple[str, date] | None:
    """Which session block an Oslo-local timestamp falls in, or None for the
    dead zones (07:00-09:00 and 22:00-02:00)."""
    t = dt.time()
    for key, _label, start, end in SESSIONS:
        if start <= t < end:
            return key, dt.date()
    return None


def _bounds(day: date, key: str) -> tuple[datetime, datetime]:
    start, end = next((s, e) for k, _lbl, s, e in SESSIONS if k == key)
    return (
        datetime.combine(day, start, tzinfo=OSLO),
        datetime.combine(day, end, tzinfo=OSLO),
    )


def build(bars: list[dict], keep: int = DEFAULT_KEEP) -> list[dict]:
    """Bucket bars into session blocks, newest first, with sweep flags.

    A level counts as swept when any bar AFTER the block closed traded back to
    it — `high` needs a later bar whose high reached it, `low` a later bar
    whose low reached it. Touching the exact price counts: that is where the
    resting orders are.
    """
    buckets: dict[tuple[date, str], dict] = {}
    for b in bars:
        if b.get("high") is None or b.get("low") is None:
            continue
        dt = datetime.fromtimestamp(b["time"], tz=OSLO)
        hit = _block_of(dt)
        if hit is None:
            continue
        key, day = hit
        cur = buckets.get((day, key))
        if cur is None:
            buckets[(day, key)] = {
                "high": b["high"],
                "low": b["low"],
                "bars": 1,
                "last_time": b["time"],
            }
        else:
            cur["high"] = max(cur["high"], b["high"])
            cur["low"] = min(cur["low"], b["low"])
            cur["bars"] += 1
            cur["last_time"] = b["time"]

    now = datetime.now(OSLO)
    labels = {k: lbl for k, lbl, _s, _e in SESSIONS}
    order = {k: i for i, (k, _lbl, _s, _e) in enumerate(SESSIONS)}

    out: list[dict] = []
    for (day, key), agg in sorted(
        buckets.items(), key=lambda kv: (kv[0][0], order[kv[0][1]])
    ):
        start_dt, end_dt = _bounds(day, key)
        complete = now >= end_dt
        end_epoch = int(end_dt.timestamp())
        later = [b for b in bars if b["time"] >= end_epoch]
        high_swept = any(b["high"] >= agg["high"] for b in later)
        low_swept = any(b["low"] <= agg["low"] for b in later)
        out.append(
            {
                "id": f"{day.isoformat()}-{key}",
                "session": key,
                "label": labels[key],
                "date": day.isoformat(),
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "high": round(agg["high"], 2),
                "low": round(agg["low"], 2),
                "high_swept": high_swept,
                "low_swept": low_swept,
                "complete": complete,
                "bars": agg["bars"],
            }
        )

    out.reverse()  # newest first
    return out[:keep]


def fetch(
    source: str,
    symbol: str = DEFAULT_SYMBOL,
    days: int = DEFAULT_DAYS,
    keep: int = DEFAULT_KEEP,
) -> dict:
    if source == "pxpy":
        bars, src = _bars_pxpy(symbol, days)
    elif source == "yahoo":
        bars, src = _bars_yahoo(days)
    else:
        raise ValueError(f"unknown source {source!r}")

    sessions = build(bars, keep=keep)
    if not sessions:
        raise RuntimeError(f"no session blocks from {len(bars)} bars")

    return {
        "symbol": symbol,
        "timezone": "Europe/Oslo",
        "interval": "5m",
        "source": src,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_defs": {
            k: [s.strftime("%H:%M"), e.strftime("%H:%M")] for k, _lbl, s, e in SESSIONS
        },
        "count": len(sessions),
        "sessions": sessions,
    }


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=("pxpy", "yahoo"), default="pxpy")
    ap.add_argument("--symbol", default=DEFAULT_SYMBOL)
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    ap.add_argument(
        "--write",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "web" / "session_levels_mnq.json",
    )
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    try:
        payload = fetch(args.source, args.symbol, args.days, args.keep)
    except Exception as e:
        log.error(
            "session levels (%s) failed: %s: %s", args.source, type(e).__name__, e
        )
        return 2

    if args.stdout:
        print(json.dumps(payload, indent=2))
        return 0

    _write(args.write, payload)
    newest = payload["sessions"][0]
    log.info(
        "wrote %d session blocks → %s  (newest %s %s  H %.2f / L %.2f)",
        payload["count"],
        args.write,
        newest["date"],
        newest["label"],
        newest["high"],
        newest["low"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
