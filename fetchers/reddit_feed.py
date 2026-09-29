"""Reddit posts for the brief via the shared paced client in ~/MWM/core/lib/reddit_rss.py.

This IP gets one Reddit RSS request per minute, shared with the research swarm
and the scouts. The brief spends two: one "hot" feed for the large AI subs and
one for the small subs. tech_ai and consciousness ask for the same small-sub
feed URL, so the second caller reads it from the client's 15-minute cache.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import UTC, datetime, timedelta

log = logging.getLogger("morning-brief.reddit")

_CORE = os.path.expanduser("~/MWM/core")
if os.path.isdir(_CORE) and _CORE not in sys.path:
    sys.path.insert(0, _CORE)

LARGE_SUBS = ("ClaudeAI", "LocalLLaMA", "singularity")
SMALL_SUBS = ("MachineLearning", "consciousness")

# Drop anything older than this so pinned megathreads can't make a section
# look stale (the "40-day post" bug, 2026-06-04).
MAX_AGE_DAYS = 14
_SKIP_TITLE = re.compile(
    r"megathread|ongoing|read before posting|rules|weekly|monthly|discord"
    r"|self.?promotion|sticky|pinned",
    re.IGNORECASE,
)


def _group_for(sub: str) -> tuple[str, ...]:
    return LARGE_SUBS if sub in LARGE_SUBS else SMALL_SUBS


def posts(sub: str, cap: int, caller: str) -> list[dict]:
    """Up to ``cap`` recent hot posts from ``sub`` as brief items."""
    try:
        from lib.reddit_rss import fetch_feed
    except ImportError as e:
        log.warning("reddit client unavailable: %s", e)
        return []
    group = _group_for(sub)
    if sub not in group:
        log.warning("r/%s is not in a brief reddit group; add it to reddit_feed.py", sub)
        return []
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=MAX_AGE_DAYS)
    out: list[dict] = []
    for p in fetch_feed(list(group), sort="hot", limit=100, caller=f"brief:{caller}"):
        if p.subreddit.lower() != sub.lower() or _SKIP_TITLE.search(p.title):
            continue
        if p.published is not None and p.published < cutoff:
            continue
        age = f"{(now - p.published).days}d ago" if p.published else "recent"
        out.append(
            {
                "headline": p.title[:180],
                "body": f"r/{sub} · {age}",
                "url": p.url,
                "source": f"reddit:{sub}",
            }
        )
        if len(out) >= cap:
            break
    return out
