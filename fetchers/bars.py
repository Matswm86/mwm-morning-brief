"""MNQ candlestick bars for the chart widget.

Pulls Yahoo NQ=F bars and writes them in TradingView lightweight-charts
format. Separate from the main `build_brief()` flow so it can refresh
every 5 minutes during market hours without rebuilding the whole brief.

Usage (from the morning-brief dir):
  python3 -m fetchers.bars                     # 1d of 5m bars
  python3 -m fetchers.bars --interval 1m --range 1d
  python3 -m fetchers.bars --write web/bars_mnq.json
"""
from __future__ import annotations
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("morning-brief.bars")

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
UA = {"User-Agent": "Mozilla/5.0 mwm-morning-brief/1.0"}
DEFAULT_SYMBOL = "NQ=F"


def _fetch_yahoo(symbol: str, interval: str, range_: str) -> Optional[dict]:
    try:
        resp = requests.get(
            YAHOO_CHART_URL.format(sym=symbol),
            params={"interval": interval, "range": range_,
                    "includePrePost": "true"},
            headers=UA, timeout=12,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("yahoo %s %s/%s failed: %s", symbol, interval, range_, e)
        return None


def _to_lightweight_charts(data: dict) -> list[dict]:
    """Convert Yahoo chart payload → list[{time, open, high, low, close, volume}]."""
    try:
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        q = result["indicators"]["quote"][0]
        o = q.get("open") or []
        h = q.get("high") or []
        l = q.get("low") or []
        c = q.get("close") or []
        v = q.get("volume") or []
        out = []
        for i, t in enumerate(ts):
            if i >= len(c) or c[i] is None:
                continue
            out.append({
                "time": int(t),
                "open": round(float(o[i]), 2) if o[i] is not None else None,
                "high": round(float(h[i]), 2) if h[i] is not None else None,
                "low": round(float(l[i]), 2) if l[i] is not None else None,
                "close": round(float(c[i]), 2),
                "volume": int(v[i]) if v[i] is not None else 0,
            })
        return out
    except (KeyError, IndexError, TypeError) as e:
        log.warning("parse failed: %s", e)
        return []


def fetch(symbol: str = DEFAULT_SYMBOL, interval: str = "5m",
          range_: str = "1d") -> dict:
    data = _fetch_yahoo(symbol, interval, range_)
    bars = _to_lightweight_charts(data) if data else []
    # Also include previous day close for % change
    prev_close = None
    if data:
        try:
            prev_close = float(data["chart"]["result"][0]["meta"].get("chartPreviousClose"))
        except (KeyError, TypeError, ValueError):
            prev_close = None
    return {
        "symbol": symbol,
        "interval": interval,
        "range": range_,
        "bars": bars,
        "prev_close": prev_close,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(bars),
    }


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=DEFAULT_SYMBOL)
    ap.add_argument("--interval", default="5m",
                    help="1m | 5m | 15m | 60m | 1d (yahoo intervals)")
    ap.add_argument("--range", dest="range_", default="1d",
                    help="1d | 5d | 1mo (yahoo ranges)")
    ap.add_argument("--write", type=Path,
                    default=Path(__file__).resolve().parents[1] / "web" / "bars_mnq.json")
    ap.add_argument("--stdout", action="store_true",
                    help="print payload to stdout instead of writing")
    args = ap.parse_args()

    payload = fetch(args.symbol, args.interval, args.range_)
    if args.stdout:
        print(json.dumps(payload, indent=2))
    else:
        write(args.write, payload)
        log.info("wrote %d bars → %s  (last=%.2f)",
                 payload["count"], args.write,
                 payload["bars"][-1]["close"] if payload["bars"] else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
