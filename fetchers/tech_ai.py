"""Tech + AI + Claude + LLM fetcher — HN Algolia + Reddit + arXiv."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from http_util import get_json

log = logging.getLogger("morning-brief.tech_ai")

# Reddit recency cutoff — drop anything older than this so evergreen
# megathreads / pinned posts can't make the section look stale (the "40-day
# post" bug, 2026-06-04). The .rss "hot" feed surfaces sticky/old items first.
REDDIT_MAX_AGE_DAYS = 14
_REDDIT_SKIP_TITLE = re.compile(
    r"megathread|ongoing|read before posting|rules|weekly|monthly|discord"
    r"|self.?promotion|sticky|pinned",
    re.IGNORECASE,
)

HN_URL = "https://hn.algolia.com/api/v1/search_by_date"
HN_QUERIES = [
    ("claude OR anthropic", 4),
    ('LLM OR "large language model" OR "open weights"', 3),
    ('"MCP" OR "Model Context Protocol"', 2),
]

REDDIT_SUBS = [
    ("ClaudeAI", 3),
    ("LocalLLaMA", 3),
    ("singularity", 2),
    ("MachineLearning", 2),
]

REDDIT_UA = "mwm-morning-brief/0.1 (+https://mwmai.no)"


def _hn(query: str, cap: int) -> list[dict]:
    data = get_json(
        HN_URL,
        params={
            "query": query,
            "tags": "story",
            "hitsPerPage": cap * 3,
            "numericFilters": "points>40",
        },
    )
    try:
        hits = data.get("hits", [])
    except Exception:
        return []
    out = []
    for h in hits[: cap * 3]:
        title = h.get("title")
        if not title:
            continue
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        out.append(
            {
                "headline": title[:180],
                "body": f"{h.get('points', 0)} pts · {h.get('num_comments', 0)} comments",
                "url": url,
                "source": "hn",
            }
        )
        if len(out) >= cap:
            break
    return out


def _reddit(sub: str, cap: int) -> list[dict]:
    # Reddit blocks /hot.json (403). The .rss "hot" feed works with the
    # mwm-trading UA — see feedback_reddit_fetch_via_curl_json. RSS carries no
    # ups/comments, so we filter by recency + skip pinned/evergreen titles
    # instead, and label with the post age.
    import requests

    url = f"https://www.reddit.com/r/{sub}/hot/.rss"
    try:
        r = requests.get(url, headers={"User-Agent": REDDIT_UA}, timeout=15)
        r.raise_for_status()
        text = r.text
    except Exception as e:
        log.warning("reddit %s fail: %s", sub, e)
        return []
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=REDDIT_MAX_AGE_DAYS)
    out = []
    for entry in re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL):
        title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        link_m = re.search(r'<link[^>]*href="([^"]+)"', entry)
        date_m = re.search(r"<(?:updated|published)>(.*?)</(?:updated|published)>", entry)
        if not (title_m and link_m):
            continue
        title = re.sub(r"\s+", " ", title_m.group(1)).strip()[:180]
        if not title or _REDDIT_SKIP_TITLE.search(title):
            continue
        posted = None
        if date_m:
            try:
                posted = datetime.fromisoformat(date_m.group(1).strip())
                if posted.tzinfo is None:
                    posted = posted.replace(tzinfo=UTC)
            except ValueError:
                posted = None
        if posted is not None and posted < cutoff:
            continue  # evergreen / stale — the 40-day-post guard
        age = f"{(now - posted).days}d ago" if posted else "recent"
        out.append(
            {
                "headline": title,
                "body": f"r/{sub} · {age}",
                "url": link_m.group(1).strip(),
                "source": f"reddit:{sub}",
            }
        )
        if len(out) >= cap:
            break
    return out


def _arxiv_ai(cap: int = 3) -> list[dict]:
    """arXiv cs.AI + cs.CL new submissions (pseudo-Atom -> plain text)."""
    import re

    from http_util import get_text

    text = get_text(
        "http://export.arxiv.org/api/query",
        params={
            "search_query": "cat:cs.AI OR cat:cs.CL",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(cap * 2),
        },
        timeout=30,
    )
    if not text:
        return []
    entries = re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL)
    out = []
    for e in entries[: cap * 2]:
        title_m = re.search(r"<title>(.*?)</title>", e, re.DOTALL)
        summary_m = re.search(r"<summary>(.*?)</summary>", e, re.DOTALL)
        link_m = re.search(r"<id>(.*?)</id>", e, re.DOTALL)
        if not (title_m and link_m):
            continue
        t = re.sub(r"\s+", " ", title_m.group(1)).strip()
        s = re.sub(r"\s+", " ", (summary_m.group(1) if summary_m else ""))[:240].strip()
        out.append(
            {
                "headline": t[:180],
                "body": s,
                "url": link_m.group(1).strip(),
                "source": "arxiv",
            }
        )
        if len(out) >= cap:
            break
    return out


def fetch() -> dict:
    items: list[dict] = []
    for q, cap in HN_QUERIES:
        items.extend(_hn(q, cap))
    for sub, cap in REDDIT_SUBS:
        items.extend(_reddit(sub, cap))
    items.extend(_arxiv_ai(cap=3))
    return {
        "items": items,
        "count": len(items),
        "source": "HN · Reddit · arXiv",
        "status": "ok" if items else "warn",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
