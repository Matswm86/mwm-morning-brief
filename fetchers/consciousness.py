"""Consciousness & Resonance fetcher — arXiv (q-bio.NC, physics.gen-ph) + r/consciousness + local science synthesis."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from config import SYNTHESIS_DIR
from http_util import get_text

from fetchers.research import _recent_md

log = logging.getLogger("morning-brief.consciousness")


def _arxiv_conscious(cap: int = 4) -> list[dict]:
    text = get_text(
        "http://export.arxiv.org/api/query",
        params={
            "search_query": "cat:q-bio.NC OR cat:physics.gen-ph OR (cat:cs.AI AND abs:consciousness)",
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


def _reddit_consciousness(cap: int = 2) -> list[dict]:
    import requests

    try:
        r = requests.get(
            "https://www.reddit.com/r/consciousness/hot.json",
            headers={"User-Agent": "mwm-morning-brief/0.1 (+https://mwmai.no)"},
            timeout=15,
            params={"limit": cap * 3},
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    out = []
    for c in data.get("data", {}).get("children", [])[: cap * 3]:
        p = c.get("data", {})
        if p.get("stickied"):
            continue
        ups = int(p.get("ups", 0) or 0)
        if ups < 20:
            continue
        out.append(
            {
                "headline": p.get("title", "")[:180],
                "body": f"r/consciousness · {ups} ↑ · {p.get('num_comments', 0)} comments",
                "url": "https://www.reddit.com" + p.get("permalink", ""),
                "source": "reddit:consciousness",
            }
        )
        if len(out) >= cap:
            break
    return out


def fetch() -> dict:
    items: list[dict] = []
    items.extend(_arxiv_conscious(cap=3))
    items.extend(_reddit_consciousness(cap=2))
    items.extend(_recent_md(SYNTHESIS_DIR / "science", cap=2))
    return {
        "items": items,
        "count": len(items),
        "source": "arXiv · r/consciousness · science synthesis",
        "status": "ok" if items else "warn",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
