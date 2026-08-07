"""Trading news (24h) — headlines that plausibly move MNQ or MGC.

Feeds the `trading_news` section, rendered FIRST on brief.mwmai.no. Scope is
deliberately narrow: only the last 24 hours, only stories whose subject is a
known driver of Nasdaq-100 futures (MNQ) or gold futures (MGC). Everything
else the brief already covers in Market / Gold / Geopolitics / Tech.

Each item is tagged MNQ, MGC, or BOTH by which driver family it matched, and
carries a `driver` label so the card can say WHY it is here rather than making
the reader infer it. No price prediction is made or implied.

Sources (free): Finnhub general + Google News RSS per driver query.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone

from config import FINNHUB_API_KEY
from http_util import get_json, get_text

log = logging.getLogger("morning-brief.trading_news")

GNEWS_RSS = "https://news.google.com/rss/search"
WINDOW_HOURS = 24
MAX_ITEMS = 12

# (driver label, instrument tag, keywords), matched case-insensitively against
# headline + summary. ORDER MATTERS: first match wins, so instrument-specific
# families are listed BEFORE the broad macro ones. Otherwise an Nvidia-earnings
# story matches "Fed / rates" on a passing mention and lands in BOTH, which
# tells the reader nothing.
DRIVERS: list[tuple[str, str, tuple[str, ...]]] = [
    ("Megacap / AI earnings", "MNQ",
     ("nvidia", "apple", "microsoft", "alphabet", "amazon", "meta platforms", "tesla",
      "broadcom", "earnings beat", "earnings miss", "guidance cut", "chip demand",
      "ai capex", "semiconductor")),
    ("Gold demand / safe haven", "MGC",
     ("gold", "bullion", "xau", "central bank buying", "safe haven", "safe-haven",
      "comex", "silver")),
    ("Nasdaq / risk tone", "MNQ",
     ("nasdaq", "tech stocks", "tech futures", "nasdaq 100", "qqq",
      "risk-off", "risk off", "vix", "equity futures")),
    ("Fed / rates", "BOTH",
     ("federal reserve", "fomc", "powell", "rate cut", "rate hike", "interest rate",
      "dot plot", "fed official", "hawkish", "dovish")),
    ("Inflation data", "BOTH",
     ("cpi", "inflation", "ppi", "pce", "core prices")),
    ("Jobs data", "BOTH",
     ("nonfarm", "payrolls", "jobless claims", "unemployment rate", "jobs report")),
    ("Dollar / yields", "BOTH",
     ("dollar index", "treasury yield", "10-year yield", "bond selloff", "dxy")),
    ("Geopolitical risk", "BOTH",
     ("tariff", "sanction", "military strike", "war", "opec", "oil output",
      "trade deal", "export ban")),
]

# Queries sent to Google News; kept tight so the 24h window stays signal-dense.
QUERIES = [
    "Nasdaq futures", "Federal Reserve interest rates", "gold price forecast",
    "US inflation data", "treasury yields dollar",
]


def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)


def _classify(text: str) -> tuple[str, str] | None:
    """-> (driver label, instrument tag) for the first matching family."""
    low = text.lower()
    for label, tag, keys in DRIVERS:
        if any(k in low for k in keys):
            return label, tag
    return None


def _finnhub_items() -> list[dict]:
    if not FINNHUB_API_KEY:
        return []
    data = get_json(
        "https://finnhub.io/api/v1/news",
        params={"category": "general", "token": FINNHUB_API_KEY},
    )
    if not isinstance(data, list):
        return []
    cut = _cutoff()
    out = []
    for it in data:
        ts = it.get("datetime")
        if not ts:
            continue
        when = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        if when < cut:
            continue
        headline = html.unescape((it.get("headline") or "")).strip()
        hit = _classify(f"{headline} {it.get('summary', '')}")
        if not hit or not headline:
            continue
        driver, tag = hit
        out.append({
            "headline": headline[:180],
            "body": (it.get("summary") or "")[:320],
            "url": it.get("url", ""),
            "source": f"finnhub:{(it.get('source') or '')[:24]}",
            "driver": driver,
            "instrument": tag,
            "published": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return out


def _parse_pubdate(raw: str) -> datetime | None:
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            d = datetime.strptime(raw.strip(), fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _gnews_items(query: str, cap: int = 6) -> list[dict]:
    text = get_text(
        GNEWS_RSS, params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    if not text:
        return []
    cut = _cutoff()
    out = []
    for m in re.finditer(
        r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?"
        r"<pubDate>(.*?)</pubDate>.*?<source[^>]*>(.*?)</source>.*?</item>",
        text,
        re.DOTALL,
    ):
        title, link, pub, src = m.groups()
        title = html.unescape(re.sub(r"<.*?>", "", title)).strip()
        when = _parse_pubdate(pub)
        if when is None or when < cut:
            continue
        hit = _classify(title)
        if not hit:
            continue
        driver, tag = hit
        out.append({
            "headline": title[:180],
            "body": f"via {src.strip()[:40]}",
            "url": link.strip(),
            "source": src.strip()[:40],
            "driver": driver,
            "instrument": tag,
            "published": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        if len(out) >= cap:
            break
    return out


def _dedupe(items: list[dict]) -> list[dict]:
    """Drop near-duplicate headlines (same story, different outlet)."""
    seen: set[str] = set()
    out = []
    for it in items:
        key = re.sub(r"[^a-z0-9 ]", "", it["headline"].lower())
        key = " ".join(sorted(key.split()[:8]))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def fetch() -> dict:
    items: list[dict] = list(_finnhub_items())
    for q in QUERIES:
        try:
            items.extend(_gnews_items(q))
        except Exception as e:  # noqa: BLE001 — one dead query must not kill the card
            log.warning("gnews query %r failed: %s", q, e)

    items = _dedupe(items)
    items.sort(key=lambda it: it.get("published", ""), reverse=True)
    items = items[:MAX_ITEMS]

    counts = {"MNQ": 0, "MGC": 0, "BOTH": 0}
    for it in items:
        counts[it["instrument"]] = counts.get(it["instrument"], 0) + 1

    return {
        "items": items,
        "count": len(items),
        "source": "Finnhub · Google News (24h, MNQ/MGC drivers)",
        "status": "ok" if items else "warn",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_hours": WINDOW_HOURS,
        "instrument_counts": counts,
    }
