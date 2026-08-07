"""Gold & Metals fetcher — Yahoo metals quotes + Finnhub headlines filtered to gold.

Feeds the `gold` section of brief.json (Gold & Metals card) so the public
brief covers MGC/Gold alongside MNQ. Same shape as fetchers/market.py.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from config import FINNHUB_API_KEY
from http_util import get_json

log = logging.getLogger("morning-brief.gold")

YAHOO_SYMBOLS = [
    ("GC=F", "Gold futures"),
    ("SI=F", "Silver futures"),
    ("DX-Y.NYB", "Dollar index"),
    ("^TNX", "10Y yield"),
]

# A headline must contain one of these (case-insensitive) to make the card.
KEYWORDS = (
    "gold", "bullion", "precious metal", "silver", "xau",
    "comex", "central bank buying", "safe haven", "safe-haven",
)


def _yahoo_quote(symbol: str) -> dict | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    data = get_json(url, params={"interval": "5m", "range": "1d"})
    try:
        r = data["chart"]["result"][0]
        meta = r.get("meta", {})
        last = float(meta.get("regularMarketPrice"))
        prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or last)
        chg = last - prev
        return {
            "symbol": symbol,
            "last": last,
            "change_pct": (chg / prev) * 100.0 if prev else 0.0,
            "session_low": float(meta.get("regularMarketDayLow") or last),
            "session_high": float(meta.get("regularMarketDayHigh") or last),
        }
    except (KeyError, IndexError, TypeError, ValueError) as e:
        log.warning("yahoo quote %s failed: %s", symbol, e)
        return None


def _quotes_as_items(quotes: list[dict]) -> list[dict]:
    items = []
    for q in quotes:
        label = dict(YAHOO_SYMBOLS).get(q["symbol"], q["symbol"])
        pct = q["change_pct"]
        sign = "+" if pct >= 0 else ""
        items.append({
            "headline": f"{label} {sign}{pct:.2f}% vs prev close",
            "body": f"last {q['last']:.2f} · session range {q['session_low']:.2f}–{q['session_high']:.2f}",
            "source": "yahoo",
        })
    return items


def _finnhub_gold_news() -> list[dict]:
    if not FINNHUB_API_KEY:
        return []
    data = get_json(
        "https://finnhub.io/api/v1/news",
        params={"category": "general", "token": FINNHUB_API_KEY},
    )
    if not isinstance(data, list):
        return []
    out = []
    for it in data:
        text = f"{it.get('headline', '')} {it.get('summary', '')}".lower()
        if not any(k in text for k in KEYWORDS):
            continue
        out.append({
            "headline": it.get("headline", "")[:180],
            "body": it.get("summary", "")[:400],
            "url": it.get("url", ""),
            "source": f"finnhub:{it.get('source', '')}",
        })
        if len(out) >= 10:
            break
    return out


def fetch() -> dict:
    quotes = [q for q in (_yahoo_quote(s) for s, _ in YAHOO_SYMBOLS) if q]
    items = _quotes_as_items(quotes) + _finnhub_gold_news()
    return {
        "items": items,
        "count": len(items),
        "source": "Yahoo · Finnhub (gold filter)",
        "status": "ok" if items else "warn",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": quotes,
    }
