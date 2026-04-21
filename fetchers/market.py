"""Market fetcher — Yahoo futures quotes + Finnhub / Google News headlines."""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from config import FINNHUB_API_KEY
from http_util import get_json, get_text

log = logging.getLogger("morning-brief.market")

YAHOO_SYMBOLS = [
    ("NQ=F",  "Nasdaq futures"),
    ("ES=F",  "S&P futures"),
    ("GC=F",  "Gold futures"),
    ("^VIX",  "VIX"),
    ("^TNX",  "10Y yield"),
    ("DX-Y.NYB", "Dollar index"),
]


def _yahoo_quote(symbol: str) -> dict | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    data = get_json(url, params={"interval": "5m", "range": "1d"})
    try:
        r = data["chart"]["result"][0]
        meta = r.get("meta", {})
        last = float(meta.get("regularMarketPrice"))
        prev = float(meta.get("chartPreviousClose") or meta.get("previousClose") or last)
        chg = last - prev
        chg_pct = (chg / prev) * 100.0 if prev else 0.0
        return {
            "symbol": symbol,
            "last": last,
            "change": chg,
            "change_pct": chg_pct,
            "session_high": meta.get("regularMarketDayHigh"),
            "session_low": meta.get("regularMarketDayLow"),
        }
    except Exception:
        return None


def _finnhub_news() -> list[dict]:
    if not FINNHUB_API_KEY:
        return []
    data = get_json(
        "https://finnhub.io/api/v1/news",
        params={"category": "general", "token": FINNHUB_API_KEY},
    )
    if not isinstance(data, list):
        return []
    out = []
    for it in data[:30]:
        out.append({
            "headline": it.get("headline", "")[:180],
            "body": it.get("summary", "")[:400],
            "url": it.get("url", ""),
            "source": f"finnhub:{it.get('source', '')}",
        })
    return out


def _quotes_as_items(quotes: list[dict]) -> list[dict]:
    items = []
    for q in quotes:
        sym = q["symbol"]
        label = dict(YAHOO_SYMBOLS).get(sym, sym)
        pct = q["change_pct"]
        sign = "+" if pct >= 0 else ""
        items.append({
            "headline": f"{label} {sign}{pct:.2f}% vs prev close",
            "body": f"last {q['last']:.2f} · session range {q['session_low']:.2f}–{q['session_high']:.2f}",
            "source": "yahoo",
        })
    return items


def fetch() -> dict:
    quotes = [q for q in (_yahoo_quote(s) for s, _ in YAHOO_SYMBOLS) if q]
    news = _finnhub_news()
    items = _quotes_as_items(quotes) + news
    return {
        "items": items,
        "count": len(items),
        "source": "Yahoo · Finnhub",
        "status": "ok" if items else "warn",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": quotes,  # raw for possible future use
    }
