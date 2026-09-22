"""Yesterday and the week, reviewed — did the news move anything?

Two inputs, one column.

1. A story ledger. Every build appends the trading wire's items to
   data/news_ledger.jsonl (deduplicated by URL, first-seen date kept). The
   ledger is the paper's own morgue: without it there is no "yesterday".
   On first run it is seeded from Google News with a 7-day window so the
   column has a week to look back on from day one.

2. Daily bars for MNQ and MGC (Yahoo, NQ=F / MGC=F, one month). For every
   session the desk records close-to-close move in percent, the day's range in
   points, and the range against the trailing-20-session median. A session
   "mattered" when its range ran at or above 1.25x that median or the move
   was at or above 1%; anything smaller is filed as noise.

The narration is written by the paper's analyst model from those facts only
(claude -p, Sonnet; the call carries the story list and the session table and
nothing else). It is cached per session date so the 07:00 Oslo edition writes
the column once and every later build that day reuses it. If the model is
unavailable the column falls back to plain sentences built from the same
facts, and says so in its byline.

Public-site rule: no names, no accounts, no internal system names.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fetchers import bars as f_bars

log = logging.getLogger("morning-brief.review")

ET = ZoneInfo("America/New_York")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LEDGER = DATA_DIR / "news_ledger.jsonl"
CACHE = DATA_DIR / "review_cache.json"
MOVE_PCT = 1.0
RANGE_X = 1.25
SEED_DAYS = 7

SYSTEM_PROMPT = """You write the "Yesterday, reviewed" column for a small daily trading newspaper set like a 1920s broadsheet. The reader trades Micro Nasdaq (MNQ) and Micro Gold (MGC) futures and wants to know, in plain newspaper English, whether the stories the wire ran actually moved the tape.

Rules, all binding:
- Use ONLY the facts in the user message: the listed headlines and the session table. Never add a number, a cause, a company, or an event that is not there. If the facts do not support a link between a story and a move, say the link is unproven.
- A session "mattered" when the table marks it so. Do not overrule the table.
- Voice: a seasoned wire-desk journalist. Short declarative sentences. Concrete nouns. No hedging filler, no "it remains to be seen", no "in a world where", no "navigating", no "landscape", no "delve", no rhetorical questions, no exclamation marks, no bullet points, no headings, no emoji.
- Dry wit is allowed, one line at most, and only at the expense of the news cycle or the desk itself, never a person.
- Write two parts separated by a line containing only "---":
  Part 1, headed by nothing, 90-140 words: yesterday's session and the stories that ran that day.
  Part 2, 120-180 words: the week. Which days mattered, which stories were loud and changed nothing, one sentence on what that says about the week's tape.
- Percentages and points appear exactly as given. Dates as weekday names.
- Typography: no em dashes or en dashes anywhere; use commas, colons or full stops. Never write "essentially", "basically", "robust", "seems to".
- Output the two parts and nothing else."""


def _clean(text: str) -> str:
    text = re.sub(r"\s*[\u2014\u2013]\s*", ", ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _append_ledger(items: list[dict], seen_date: str) -> int:
    """Append unseen URLs. Returns number of rows written."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    known = {r.get("url") for r in _read_ledger()}
    n = 0
    with LEDGER.open("a") as fh:
        for it in items:
            u = it.get("url")
            if not u or u in known:
                continue
            known.add(u)
            pub = (it.get("published") or "")[:10]
            row = {
                "url": u,
                "headline": it.get("headline"),
                "source": it.get("source"),
                "driver": it.get("driver"),
                "instrument": it.get("instrument") or "BOTH",
                "published": it.get("published"),
                "date_et": _et_date(it.get("published")) or pub or seen_date,
                "seen": seen_date,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def _et_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return (
            datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=UTC)
            .astimezone(ET)
            .date()
            .isoformat()
        )
    except ValueError:
        return None


def _seed_if_empty() -> None:
    """First run: pull a 7-day window so the column has a week behind it."""
    if LEDGER.exists() and LEDGER.stat().st_size > 0:
        return
    try:
        from fetchers import trading_news as tn

        cut = datetime.now(UTC) - timedelta(days=SEED_DAYS)
        orig = tn._cutoff
        tn._cutoff = lambda: cut  # type: ignore[assignment]
        items: list[dict] = []
        try:
            for q in tn.QUERIES:
                try:
                    items.extend(tn._gnews_items(q, cap=40))
                except Exception as e:  # noqa: BLE001
                    log.warning("seed query %r failed: %s", q, e)
        finally:
            tn._cutoff = orig  # type: ignore[assignment]
        items = tn._dedupe(items)
        n = _append_ledger(items, date.today().isoformat())
        log.info("news ledger seeded with %d rows over %d days", n, SEED_DAYS)
    except Exception:
        log.exception("ledger seed failed")


def _sessions(symbol: str, median_pts: float | None = None) -> list[dict]:
    """Daily sessions from Yahoo. The range median comes from the paper's own
    26-day range model when available (preopen.median26d_pts); Yahoo's MGC=F
    daily bars carry broken ranges on thin days (a 2.8-point gold day on
    2026-08-26), so the feed's own medians are not trusted for that."""
    d = f_bars.fetch(symbol, "1d", "1mo")
    rows = d.get("bars") or []
    out = []
    ranges: list[float] = []
    prev_close = None
    for b in rows:
        try:
            day = datetime.fromtimestamp(int(b["time"]), tz=UTC).date()
            h, lo, c = float(b["high"]), float(b["low"]), float(b["close"])
        except (KeyError, TypeError, ValueError):
            continue
        rng = h - lo
        med = median_pts or (statistics.median(ranges[-20:]) if len(ranges) >= 5 else None)
        move = (c / prev_close - 1.0) * 100.0 if prev_close else None
        if med and rng < 0.15 * med:
            # a bar that thin is a feed artefact, not a session; keep the close, drop the range
            rng = None
        out.append(
            {
                "date": day.isoformat(),
                "weekday": day.strftime("%A"),
                "close": round(c, 2),
                "move_pct": round(move, 2) if move is not None else None,
                "range_pts": round(rng, 1) if rng is not None else None,
                "range_x_median": round(rng / med, 2) if (med and rng is not None) else None,
                "mattered": bool(
                    (med and rng is not None and rng / med >= RANGE_X)
                    or (move is not None and abs(move) >= MOVE_PCT)
                ),
            }
        )
        if rng is not None:
            ranges.append(rng)
        prev_close = c
    return out


def _last_completed(sessions: list[dict], today: date) -> list[dict]:
    """Drop a partial 'today' bar: only sessions strictly before today count."""
    return [s for s in sessions if s["date"] < today.isoformat()]


def _stories_for(ledger: list[dict], day: str) -> list[dict]:
    rows = [r for r in ledger if r.get("date_et") == day]
    rows.sort(key=lambda r: r.get("published") or "")
    return rows[:8]


def _facts(ledger: list[dict], mnq: list[dict], mgc: list[dict], today: date) -> dict:
    mnq = _last_completed(mnq, today)
    mgc = _last_completed(mgc, today)
    if not mnq:
        return {"status": "error", "error": "no completed MNQ sessions"}
    y = mnq[-1]["date"]
    week_days = [s["date"] for s in mnq[-5:]]
    by_day = []
    for d in week_days:
        m = next((s for s in mnq if s["date"] == d), None)
        g = next((s for s in mgc if s["date"] == d), None)
        by_day.append(
            {
                "date": d,
                "weekday": m["weekday"] if m else d,
                "mnq": m,
                "mgc": g,
                "mattered": bool((m and m["mattered"]) or (g and g["mattered"])),
                "stories": [
                    {
                        "headline": r["headline"],
                        "driver": r.get("driver"),
                        "instrument": r.get("instrument"),
                        "source": r.get("source"),
                    }
                    for r in _stories_for(ledger, d)
                ],
            }
        )
    return {
        "status": "ok",
        "yesterday": by_day[-1] if by_day else None,
        "week": by_day,
        "thresholds": {"move_pct": MOVE_PCT, "range_x_median": RANGE_X},
        "yesterday_date": y,
    }


def _facts_text(f: dict) -> str:
    lines = [
        "SESSION TABLE (close-to-close move %, day range in points, range vs trailing-20-session median, mattered = range >= 1.25x median or |move| >= 1.0%)"
    ]
    for d in f["week"]:
        m, g = d.get("mnq") or {}, d.get("mgc") or {}
        lines.append(
            f"- {d['weekday']} {d['date']}: MNQ move {m.get('move_pct')}% range {m.get('range_pts')} pts ({m.get('range_x_median')}x median); "
            f"MGC move {g.get('move_pct')}% range {g.get('range_pts')} pts ({g.get('range_x_median')}x median); MATTERED={'YES' if d['mattered'] else 'NO'}"
        )
    lines.append("")
    lines.append(
        "STORIES THE WIRE RAN, BY DAY (headline · driver family · instrument tag · outlet)"
    )
    for d in f["week"]:
        lines.append(f"{d['weekday']} {d['date']}:")
        if not d["stories"]:
            lines.append("  (no stories on file for this day)")
        for s in d["stories"]:
            lines.append(
                f"  - {s['headline']} · {s.get('driver')} · {s.get('instrument')} · {s.get('source')}"
            )
    lines.append("")
    lines.append(f"YESTERDAY = {f['yesterday']['weekday']} {f['yesterday']['date']}.")
    return "\n".join(lines)


def _fallback_prose(f: dict) -> tuple[str, str]:
    y = f["yesterday"]
    m, g = y.get("mnq") or {}, y.get("mgc") or {}
    p1 = (
        f"{y['weekday']}: MNQ moved {m.get('move_pct')}% on a {m.get('range_pts')}-point range, "
        f"{m.get('range_x_median')} times its recent median; MGC moved {g.get('move_pct')}% on {g.get('range_pts')} points. "
        + (
            "The session mattered by the desk's rule. "
            if y["mattered"]
            else "By the desk's rule the session was noise. "
        )
        + (
            f"The wire ran {len(y['stories'])} stories that day, led by: {y['stories'][0]['headline']}."
            if y["stories"]
            else "The wire has no stories on file for that day."
        )
    )
    loud = [d for d in f["week"] if d["stories"] and not d["mattered"]]
    moved = [d for d in f["week"] if d["mattered"]]
    p2 = (
        f"The week: {len(moved)} of {len(f['week'])} sessions mattered ({', '.join(d['weekday'] for d in moved) or 'none'}). "
        + (
            f"Stories ran on {', '.join(d['weekday'] for d in loud)} without moving the tape past the bar. "
            if loud
            else ""
        )
        + "Ranges and moves are read from daily bars; no story is credited with a move the table does not show."
    )
    return p1, p2


def _narrate(f: dict) -> tuple[str, str, str]:
    """Returns (part1, part2, byline)."""
    try:
        import os
        import sys

        core = os.path.expanduser("~/MWM/core")
        if core not in sys.path:
            sys.path.insert(0, core)
        from anthropic_via_claude_cli import call_claude_cli  # type: ignore

        text = call_claude_cli(
            model="sonnet", system_prompt=SYSTEM_PROMPT, user_prompt=_facts_text(f), timeout=180
        )
        if text and "---" in text:
            a, b = text.split("---", 1)
            a, b = _clean(a), _clean(b)
            if len(a) > 80 and len(b) > 80:
                return a, b, "By the analyst desk"
        log.warning("review narration rejected: %r", (text or "")[:120])
    except Exception:
        log.exception("review narration failed")
    a, b = _fallback_prose(f)
    return a, b, "By the desk, from the tables (analyst unavailable this edition)"


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def fetch(
    trading_news: dict | None = None, now: datetime | None = None, preopen: dict | None = None
) -> dict:
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    today = now_et.date()
    _seed_if_empty()
    items = (trading_news or {}).get("items") or []
    if items:
        n = _append_ledger(items, today.isoformat())
        if n:
            log.info("news ledger +%d rows", n)
    ledger = _read_ledger()
    insts = (preopen or {}).get("instruments") or {}
    med_m = (insts.get("MNQ") or {}).get("median26d_pts")
    med_g = (insts.get("MGC") or {}).get("median26d_pts")
    try:
        mnq = _sessions("NQ=F", med_m)
        mgc = _sessions("MGC=F", med_g)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": f"bars: {type(e).__name__}: {e}"}
    f = _facts(ledger, mnq, mgc, today)
    if f.get("status") != "ok":
        return f
    key = f["yesterday_date"]
    cache = _load_cache()
    hit = cache.get(key)
    if hit and hit.get("part1") and hit.get("part2"):
        p1, p2, by = hit["part1"], hit["part2"], hit.get("byline", "By the analyst desk")
    else:
        p1, p2, by = _narrate(f)
        if "unavailable" not in by:
            cache = {key: {"part1": p1, "part2": p2, "byline": by, "written": now_et.isoformat()}}
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
            except OSError:
                log.warning("review cache not written")
    return {
        "status": "ok",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "yesterday_date": key,
        "byline": by,
        "yesterday_text": p1,
        "week_text": p2,
        "yesterday": f["yesterday"],
        "week": f["week"],
        "thresholds": f["thresholds"],
        "ledger_rows": len(ledger),
        "medians": {"MNQ": med_m, "MGC": med_g},
        "basis": "Daily bars from Yahoo (NQ=F, MGC=F) against the paper's own 26-day range medians; stories from the paper's wire ledger. A session mattered when its range reached 1.25x the median or the close moved 1% or more.",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = fetch()
    print(
        json.dumps(
            {k: v for k, v in r.items() if k not in ("week",)}, indent=1, ensure_ascii=False
        )[:4000]
    )
