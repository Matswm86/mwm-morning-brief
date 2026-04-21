"""Geopolitics fetcher — GDELT tone + Google News RSS + GSCPI readback."""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone

from http_util import get_json, get_text

log = logging.getLogger("morning-brief.geopolitics")

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GNEWS_RSS = "https://news.google.com/rss/search"

QUERIES = [
    ("Russia OR Ukraine OR Israel OR China OR Taiwan", "global conflict"),
    ("OPEC OR \"oil production\" OR \"energy sanctions\"", "energy"),
    ("\"supply chain\" OR \"Red Sea\" OR Suez", "supply chain"),
    ("\"central bank\" OR ECB OR PBOC OR BoE", "central banks"),
]


def _gdelt_tone(query: str) -> dict | None:
    data = get_json(GDELT_URL, params={
        "query": query, "mode": "tonechart", "format": "json", "timespan": "24h",
    })
    try:
        bins = data.get("tonechart", [])
        if not bins:
            return None
        total = sum(b.get("count", 0) for b in bins)
        if total == 0:
            return None
        weighted = sum(b.get("bin", 0) * b.get("count", 0) for b in bins) / total
        return {"query": query, "tone": weighted, "articles": total}
    except Exception:
        return None


def _gnews_items(query: str, cap: int = 4) -> list[dict]:
    text = get_text(GNEWS_RSS, params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    if not text:
        return []
    # Minimal RSS parse without bs4: titles + links
    items = []
    for m in re.finditer(
        r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<pubDate>(.*?)</pubDate>.*?<source[^>]*>(.*?)</source>.*?</item>",
        text, re.DOTALL,
    ):
        title, link, pub, src = m.groups()
        title = re.sub(r"<.*?>", "", title).strip()
        # Google News wraps titles like "Headline - Source"
        if " - " in title and not src:
            title, _, _ = title.rpartition(" - ")
        items.append({
            "headline": title[:180],
            "body": f"via {src}",
            "url": link.strip(),
            "source": src.strip()[:40],
        })
        if len(items) >= cap:
            break
    return items


def fetch() -> dict:
    items: list[dict] = []
    tone_summary = []
    for q, label in QUERIES:
        t = _gdelt_tone(q)
        if t:
            tone_summary.append((label, t["tone"], t["articles"]))
        items.extend(_gnews_items(q, cap=3))

    # Merge GDELT tone headline-style lines
    tone_items: list[dict] = []
    for label, tone, n in tone_summary:
        sign = "+" if tone >= 0 else ""
        tone_items.append({
            "headline": f"{label} tone {sign}{tone:.1f}",
            "body": f"GDELT 24h, {n} articles",
            "source": "gdelt",
        })

    merged = tone_items + items
    return {
        "items": merged,
        "count": len(merged),
        "source": "GDELT · Google News",
        "status": "ok" if merged else "warn",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
