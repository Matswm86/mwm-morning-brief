"""Research fetcher — recent inbox notes + swarm synthesis + arXiv q-fin."""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import INBOX_DIR, SYNTHESIS_DIR
from http_util import get_text

log = logging.getLogger("morning-brief.research")

LOOKBACK_DAYS = 7


EXCLUDE_PREFIXES = ("daily-diff-review-",)   # system-health artefacts, not research


def _recent_md(dir_path: Path, cap: int = 6) -> list[dict]:
    if not dir_path.exists():
        return []
    cutoff = datetime.now().timestamp() - LOOKBACK_DAYS * 86400
    hits: list[tuple[float, Path]] = []
    for p in dir_path.rglob("*.md"):
        if any(p.name.startswith(pref) for pref in EXCLUDE_PREFIXES):
            continue
        try:
            mtime = p.stat().st_mtime
            if mtime >= cutoff:
                hits.append((mtime, p))
        except OSError:
            continue
    hits.sort(reverse=True)
    out: list[dict] = []
    for _, p in hits[:cap]:
        text = ""
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Skip YAML frontmatter
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end > 0:
                text = text[end + 4 :]
        # First H1 or first non-empty line as headline
        head_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        headline = head_m.group(1).strip() if head_m else p.stem.replace("-", " ").title()
        # First paragraph after heading
        body = ""
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para or para.startswith("#") or para.startswith("---"):
                continue
            body = re.sub(r"\s+", " ", para)[:260]
            break
        out.append({
            "headline": headline[:180],
            "body": body,
            "source": f"inbox:{p.parent.name}",
            "url": "",
        })
    return out


def _arxiv_qfin(cap: int = 3) -> list[dict]:
    text = get_text(
        "http://export.arxiv.org/api/query",
        params={
            "search_query": "cat:q-fin.ST OR cat:q-fin.TR OR cat:q-fin.MF",
            "sortBy": "submittedDate", "sortOrder": "descending",
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
        out.append({
            "headline": t[:180],
            "body": s,
            "url": link_m.group(1).strip(),
            "source": "arxiv:q-fin",
        })
        if len(out) >= cap:
            break
    return out


def fetch() -> dict:
    items: list[dict] = []
    items.extend(_recent_md(INBOX_DIR, cap=4))
    items.extend(_recent_md(SYNTHESIS_DIR / "research", cap=3))
    items.extend(_arxiv_qfin(cap=3))
    return {
        "items": items,
        "count": len(items),
        "source": "inbox · synthesis · arXiv q-fin",
        "status": "ok" if items else "warn",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
