"""MNQ candlestick bars via project-x-py (TopstepX / ProjectX gateway).

Replaces fetchers/bars.py Yahoo path (15-min delayed) with CME real-time
bars pulled through the ProjectX REST History endpoint. Same output JSON
shape so web/assets/chart.js needs no change.

Runs under the mwm-trading venv (py3.12, project-x-py 3.5.9):
  /home/mats/MWM-AI/projects/mwm-trading/.venv/bin/python \
      -m fetchers.bars_pxpy --write web/bars_mnq.json

Required env (loaded from ~/MWM-AI/projects/mwm-trading/.env):
  PROJECT_X_API_KEY
  PROJECT_X_USERNAME

Exit codes:
  0 success (file written)
  2 auth or fetch failure — caller should fall back
"""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("morning-brief.bars_pxpy")

DEFAULT_SYMBOL = "MNQ"
DEFAULT_INTERVAL_MIN = 5
DEFAULT_DAYS = 1
PXPY_ENV_FILE = Path.home() / "MWM-AI" / "projects" / "mwm-trading" / ".env"


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


async def _fetch_bars(symbol: str, days: int, interval_min: int) -> dict:
    from project_x_py import ProjectX  # type: ignore

    async with ProjectX.from_env() as client:
        await client.authenticate()
        df = await client.get_bars(symbol, days=days, interval=interval_min, unit=2)

    if df is None or df.is_empty():
        raise RuntimeError(f"empty bars for {symbol}")

    import polars as pl  # type: ignore

    df = df.with_columns(
        pl.col("timestamp").dt.epoch("s").alias("time_epoch")
    ).sort("time_epoch")

    bars: list[dict] = []
    for row in df.iter_rows(named=True):
        bars.append({
            "time": int(row["time_epoch"]),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"] or 0),
        })

    prev_close = _compute_prev_close(bars)

    return {
        "symbol": symbol,
        "interval": f"{interval_min}m",
        "range": f"{days}d",
        "bars": bars,
        "prev_close": prev_close,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "project-x-py",
        "count": len(bars),
    }


def _compute_prev_close(bars: list[dict]) -> float | None:
    """Previous RTH session close = last bar close before today's NY 09:30 ET.

    Good-enough approximation: take the close 17h before the last bar,
    which lands in the prior CME Globex session while skipping Sun
    maintenance. Returns None if unavailable.
    """
    if len(bars) < 2:
        return None
    last_t = bars[-1]["time"]
    cutoff = last_t - 17 * 3600
    anchor = None
    for b in bars:
        if b["time"] <= cutoff:
            anchor = b
        else:
            break
    if anchor is None:
        return bars[0]["close"]
    return anchor["close"]


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=DEFAULT_SYMBOL)
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MIN,
                    help="bar interval in minutes (default 5)")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--write", type=Path,
                    default=Path(__file__).resolve().parents[1] / "web" / "bars_mnq.json")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    _load_env(PXPY_ENV_FILE)
    if not os.environ.get("PROJECT_X_API_KEY") or not os.environ.get("PROJECT_X_USERNAME"):
        log.error("PROJECT_X_API_KEY / PROJECT_X_USERNAME missing (checked %s)", PXPY_ENV_FILE)
        return 2

    try:
        payload = asyncio.run(_fetch_bars(args.symbol, args.days, args.interval))
    except Exception as e:
        log.error("project-x-py bar fetch failed: %s: %s", type(e).__name__, e)
        return 2

    if args.stdout:
        print(json.dumps(payload, indent=2))
        return 0

    _write(args.write, payload)
    last = payload["bars"][-1] if payload["bars"] else None
    log.info("wrote %d bars → %s  (last=%s @ %s)",
             payload["count"], args.write,
             f"{last['close']:.2f}" if last else "n/a",
             datetime.fromtimestamp(last["time"], tz=timezone.utc).isoformat() if last else "n/a")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
