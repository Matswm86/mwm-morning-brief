"""Research fetcher — pipeline-only sources.

Sources (in order of precedence):
  1. research-swarm DB (core/research-swarm/db/swarm.db, status='ingested')
     — papers/news that passed the audit + LLM review gate
  2. synthesis/research/ weekly reports (swarm syntheses)
  3. arXiv q-fin latest (direct API)

The Obsidian inbox (`notes/inbox/`) is **intentionally NOT read** here —
that is the user's personal/private writing surface and must never be
published to brief.mwmai.no.
"""
from __future__ import annotations
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import MWM_ROOT, SYNTHESIS_DIR
from http_util import get_text

log = logging.getLogger("morning-brief.research")

LOOKBACK_DAYS = 14
SWARM_DB = MWM_ROOT / "core" / "research-swarm" / "db" / "swarm.db"

# Domains we publish publicly. Drop `saas` / internal domains.
PUBLIC_DOMAINS = {"trading", "science", "research", "finance", None}


def _swarm_candidates(cap: int = 6) -> list[dict]:
    if not SWARM_DB.exists():
        log.warning("swarm DB missing at %s", SWARM_DB)
        return []
    try:
        conn = sqlite3.connect(f"file:{SWARM_DB}?mode=ro", uri=True, timeout=3.0)
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT title, url, source_type, target_domain, abstract, inserted_at
            FROM candidates
            WHERE status = 'ingested'
              AND inserted_at > datetime('now', ?)
              AND title IS NOT NULL AND title != ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (f"-{LOOKBACK_DAYS} days", cap * 3),
        ).fetchall()
        conn.close()
    except Exception as e:
        log.warning("swarm DB read failed: %s", e)
        return []

    out: list[dict] = []
    for title, url, src, domain, abstract, inserted in rows:
        if domain not in PUBLIC_DOMAINS:
            continue
        body = (abstract or "").strip()
        body = re.sub(r"\s+", " ", body)[:260]
        tag = domain or src
        out.append({
            "headline": (title or "").strip()[:180],
            "body": body,
            "url": (url or "").strip(),
            "source": f"swarm:{tag}",
        })
        if len(out) >= cap:
            break
    return out


def _recent_md(dir_path: Path, cap: int = 3) -> list[dict]:
    if not dir_path.exists():
        return []
    cutoff = datetime.now().timestamp() - LOOKBACK_DAYS * 86400
    hits: list[tuple[float, Path]] = []
    for p in dir_path.rglob("*.md"):
        try:
            mtime = p.stat().st_mtime
            if mtime >= cutoff:
                hits.append((mtime, p))
        except OSError:
            continue
    hits.sort(reverse=True)
    out: list[dict] = []
    for _, p in hits[:cap]:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end > 0:
                text = text[end + 4:]
        head_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        headline = head_m.group(1).strip() if head_m else p.stem.replace("-", " ").title()
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
            "source": f"synthesis:{p.parent.name}",
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
    items.extend(_swarm_candidates(cap=5))
    items.extend(_recent_md(SYNTHESIS_DIR / "research", cap=2))
    items.extend(_arxiv_qfin(cap=3))

    # Deduplicate by url/headline
    seen = set()
    unique: list[dict] = []
    for it in items:
        key = (it.get("url") or "", it.get("headline") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    return {
        "items": unique,
        "count": len(unique),
        "source": "swarm · synthesis · arXiv q-fin",
        "status": "ok" if unique else "warn",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
