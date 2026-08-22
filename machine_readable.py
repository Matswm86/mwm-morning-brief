"""Machine-readable surface for brief.mwmai.no: llms.txt, robots.txt, <noscript>.

Every panel on the page is injected by JS from brief.json, so a fetcher without a
JS engine (LLM browsing tools, curl, text crawlers) previously saw 1,273
characters of "loading..." placeholders and nothing else.

Nothing here changes what a human sees. The <noscript> block is invisible in
every browser that runs JS, which is every real visitor on desktop, iPhone,
Android and tablet. llms.txt and robots.txt are separate files.

Called from builder.py after brief.json is written, before the rsync.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("morning-brief.machine")

START = "<!-- NOSCRIPT:START (generated, do not hand-edit) -->"
END = "<!-- NOSCRIPT:END -->"


def _pts(x) -> str:
    return "n/a" if x is None else f"{round(float(x)):,}".replace(",", " ") + " pts"


def _lines(brief: dict) -> list[str]:
    """Plain-text summary of the numbers the page renders."""
    out: list[str] = []
    gen = brief.get("generated_at") or "unknown"
    out.append(f"The Morning Brief. Generated {gen}.")

    pre = brief.get("preopen") or {}
    for code, v in (pre.get("instruments") or {}).items():
        if v.get("status") != "ok":
            continue
        rng = v.get("expected_range_pts") or {}
        bits = [f"{code}: expected range {_pts(rng.get('p50'))}"]
        if rng.get("p80"):
            bits.append(f"8 days in 10 land under {_pts(rng.get('p80'))}")
        if v.get("median26d_pts"):
            bits.append(f"recent norm {_pts(v.get('median26d_pts'))}")
        if v.get("call"):
            bits.append(f"call {v['call']}")
        out.append("; ".join(bits) + ".")
    if pre.get("caveat"):
        out.append(pre["caveat"])

    lens = brief.get("lens") or {}
    if lens.get("status") == "ok":
        when = lens.get("decision_time_oslo", "15:25")
        out.append(f"Pre-open read for {lens.get('session', 'today')}, taken {when} Oslo.")
        v = lens.get("vol_regime") or {}
        if v.get("status") == "ok":
            tr = v.get("track_record") or {}
            s = f"Range: {v.get('call')}. {v.get('meaning', '')}"
            if tr.get("hit_rate"):
                s += f" Right {round(tr['hit_rate'] * 100)}% of the time over {tr.get('years')} years."
            out.append(s.strip())
        g = lens.get("dol_draw") or {}
        if g.get("status") == "ok":
            if g.get("callable"):
                out.append(
                    f"Which level first: {g.get('call')}. {g.get('meaning', '')} "
                    f"Yesterday's high {g.get('pdh')}, low {g.get('pdl')}. {g.get('basis', '')}".strip()
                )
            else:
                out.append(f"Which level first: no call today. {g.get('no_call_reason', '')}".strip())
        if lens.get("caveat"):
            out.append(lens["caveat"])
    return [ln for ln in out if ln]


def noscript_block(brief: dict) -> str:
    body = "\n".join(f"    <p>{html.escape(ln)}</p>" for ln in _lines(brief))
    return (
        f"{START}\n"
        f'<noscript>\n  <section id="noscript-summary">\n'
        f"{body}\n"
        f'    <p>Full structured data: <a href="brief.json">brief.json</a></p>\n'
        f"  </section>\n</noscript>\n{END}"
    )


def inject_noscript(index_html: Path, brief: dict) -> bool:
    """Replace the generated block in index.html. Idempotent."""
    if not index_html.exists():
        return False
    s = index_html.read_text()
    block = noscript_block(brief)
    if START in s and END in s:
        s = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, s, flags=re.S)
    else:
        anchor = "</header>"
        if anchor not in s:
            log.warning("no </header> anchor in index.html; noscript not injected")
            return False
        s = s.replace(anchor, anchor + "\n\n" + block + "\n", 1)
    index_html.write_text(s)
    return True


def write_llms_txt(web_dir: Path, brief: dict) -> None:
    lines = _lines(brief)
    txt = (
        "# The Morning Brief\n\n"
        "> Daily pre-open market brief for Nasdaq (MNQ) and gold (MGC) futures: "
        "expected session size, which prior-day level is reached first, macro "
        "calendar and news. Forecasts day character, never direction and never "
        "profit.\n\n"
        "The page renders client-side from JSON. For machine reading, fetch the "
        "structured data directly rather than scraping the HTML.\n\n"
        "## Data\n\n"
        "- [brief.json](https://brief.mwmai.no/brief.json): the complete brief as "
        "structured JSON, rebuilt several times a day. Keys of interest: `preopen` "
        "(expected session range), `lens` (pre-open read), `nq` (week-ahead board), "
        "`regime`, `play`.\n"
        "- [selfcalib.json](https://brief.mwmai.no/selfcalib.json): self-assessment "
        "scores for the site's own forecasts.\n\n"
        "## Today\n\n" + "\n".join(f"- {ln}" for ln in lines) + "\n\n"
        "## Notes\n\n"
        "- Hit rates quoted on the page are measured out of sample on historical "
        "sessions. They describe past accuracy, not a guarantee.\n"
        "- Nothing here is financial advice or a trade recommendation.\n\n"
        f"Last generated: {datetime.now(UTC).isoformat(timespec='seconds')}\n"
    )
    (web_dir / "llms.txt").write_text(txt)


def write_robots_txt(web_dir: Path) -> None:
    (web_dir / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n\n"
        "# Structured data, preferred over scraping the client-rendered HTML\n"
        "# https://brief.mwmai.no/brief.json\n"
        "# https://brief.mwmai.no/llms.txt\n\n"
        "Sitemap: https://brief.mwmai.no/sitemap.xml\n"
    )


def write_sitemap(web_dir: Path) -> None:
    today = datetime.now(UTC).date().isoformat()
    urls = ["https://brief.mwmai.no/", "https://brief.mwmai.no/nq/weekahead-latest.html"]
    body = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls
    )
    (web_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n"
    )


def emit_all(web_dir: Path, brief: dict) -> None:
    try:
        write_llms_txt(web_dir, brief)
        write_robots_txt(web_dir)
        write_sitemap(web_dir)
        ok = inject_noscript(web_dir / "index.html", brief)
        log.info("machine-readable: llms.txt + robots.txt + sitemap.xml, noscript=%s", ok)
    except OSError:
        log.exception("machine-readable emit failed")
