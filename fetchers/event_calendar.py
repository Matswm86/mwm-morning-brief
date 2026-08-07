"""US macro event calendar — today + 7 days, for the Regime block.

A regime read that ignores an 08:30 ET CPI print is misleading, so the schedule
sits inside the Regime block as its own tier between Structural and Intraday:
backdrop -> what is scheduled -> what the session is doing.

Scope: US only, HIGH-impact plus the named releases Mats watches (CPI/Core CPI,
PPI, PCE, NFP, unemployment, jobless claims, GDP, retail sales, ISM) plus every
FOMC decision/minutes and Fed speaker appearance regardless of the scraper's
own impact tier. Each row carries ET and Oslo times, the impact tier, and which
instrument it bears on, tagged with the SAME driver vocabulary as
`trading_news.DRIVERS` rather than a second one.

Sources:
  - TradingEconomics /calendar — the same page and the same row/CSS parsing the
    market-news MCP `get_economic_calendar()` uses; only the today-filter is
    widened to a 7-day horizon. Times on that page are UTC (verified
    2026-08-07: NFP and CPI both render as 12:30 = 08:30 ET).
  - federalreserve.gov FOMC calendar for meeting dates. Scraped live, NOT
    copied from market-news `get_fed_calendar()`, whose hardcoded "2026 FOMC
    schedule" is in fact the 2025 schedule (every date off by roughly a week;
    verified against the Fed's own page 2026-08-07). FOMC_2026_FALLBACK below
    holds the Fed-verified dates for when the scrape fails.

Display only. Nothing here gates a cell, runner, or account.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from fetchers.trading_news import DRIVERS
from http_util import get_text

log = logging.getLogger("morning-brief.event_calendar")

TE_CALENDAR = "https://tradingeconomics.com/calendar"
FED_CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ET = ZoneInfo("America/New_York")
OSLO = ZoneInfo("Europe/Oslo")
HORIZON_DAYS = 7
MAX_ITEMS = 16

# Verified against federalreserve.gov/monetarypolicy/fomccalendars.htm on
# 2026-08-07. Used only when the live scrape fails; a stale list is worse than
# no list, so `fomc.source` always says which one is in play.
FOMC_2026_FALLBACK = [
    ("2026-01-27", "2026-01-28"),
    ("2026-03-17", "2026-03-18"),
    ("2026-04-28", "2026-04-29"),
    ("2026-06-16", "2026-06-17"),
    ("2026-07-28", "2026-07-29"),
    ("2026-09-15", "2026-09-16"),
    ("2026-10-27", "2026-10-28"),
    ("2026-12-08", "2026-12-09"),
]

MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "January February March April May June July August September "
            "October November December"
        ).split(),
        start=1,
    )
}

# (display family, regex). First match wins, so the specific families precede
# the generic ones. Rows in the same family at the same timestamp collapse to
# one line — TradingEconomics lists CPI as six separate rows at 12:30.
FAMILIES: list[tuple[str, re.Pattern]] = [
    ("FOMC rate decision", re.compile(r"fed interest rate decision|fomc statement", re.I)),
    ("FOMC minutes", re.compile(r"fomc minutes", re.I)),
    ("Fed speaker", re.compile(r"\bfed\b.*(speech|testimony)|powell", re.I)),
    ("CPI · inflation", re.compile(r"inflation rate|^cpi\b|core cpi", re.I)),
    ("PCE prices", re.compile(r"\bpce\b", re.I)),
    ("PPI", re.compile(r"\bppi\b", re.I)),
    ("Nonfarm payrolls", re.compile(r"non ?farm payrolls|unemployment rate|participation rate|average hourly earnings", re.I)),
    ("Jobless claims", re.compile(r"jobless claims", re.I)),
    ("GDP", re.compile(r"\bgdp\b", re.I)),
    ("Retail sales", re.compile(r"retail sales", re.I)),
    ("ISM", re.compile(r"\bism\b", re.I)),
]
# Families that qualify even when TradingEconomics tiers them MEDIUM/LOW.
ALWAYS_KEEP = {
    "FOMC rate decision", "FOMC minutes", "Fed speaker", "CPI · inflation",
    "PCE prices", "PPI", "Nonfarm payrolls", "Jobless claims", "GDP",
    "Retail sales", "ISM",
}
IMPACT_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _family(name: str) -> str | None:
    for label, rx in FAMILIES:
        if rx.search(name):
            return label
    return None


def _driver(name: str) -> tuple[str, str]:
    """Reuse the trading_news driver vocabulary; macro default is BOTH."""
    low = name.lower()
    for label, tag, keys in DRIVERS:
        if any(k in low for k in keys):
            return label, tag
    return "US macro release", "BOTH"


def _parse_te_rows(html: str, now_utc: datetime) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="calendar")
    if not table:
        raise RuntimeError("TradingEconomics: no #calendar table")
    horizon = now_utc + timedelta(days=HORIZON_DAYS)
    out: list[dict] = []
    for row in table.find_all("tr", attrs={"data-url": True}):
        cells = row.find_all("td")
        if len(cells) < 8 or cells[3].get_text(strip=True) != "US":
            continue
        dates = [c for c in cells[0].get("class", []) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c)]
        if not dates:
            continue
        raw_time = cells[0].get_text(strip=True)
        try:  # page renders UTC as e.g. "12:30 PM"; all-day rows have no time
            when = datetime.strptime(
                f"{dates[0]} {raw_time}", "%Y-%m-%d %I:%M %p"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not (now_utc <= when <= horizon):
            continue

        span = cells[0].find("span")
        cls = " ".join(span.get("class", [])) if span else ""
        impact = (
            "HIGH" if "calendar-date-3" in cls
            else "MEDIUM" if "calendar-date-2" in cls
            else "LOW"
        )
        link = cells[4].find("a", class_="calendar-event")
        name = (link or cells[4]).get_text(strip=True)
        ref = cells[4].find("span", class_="calendar-reference")
        period = ref.get_text(strip=True) if ref else ""
        if period and name.endswith(period):
            name = name[: -len(period)].strip()
        if not name:
            continue

        fam = _family(name)
        if impact != "HIGH" and fam not in ALWAYS_KEEP:
            continue
        # Speaker/meeting rows carry no keyword the DRIVERS table matches
        # ("Fed Bowman Speech"), so name the family they obviously belong to.
        if fam in {"FOMC rate decision", "FOMC minutes", "Fed speaker"}:
            driver, instrument = "Fed / rates", "BOTH"
        else:
            driver, instrument = _driver(name)
        out.append({
            "when_utc": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "_when": when,
            "family": fam or name,
            "detail": name,
            "period": period,
            "impact": impact,
            "driver": driver,
            "instrument": instrument,
            "forecast": cells[7].get_text(strip=True) if len(cells) > 7 else "",
            "previous": cells[6].get_text(strip=True) if len(cells) > 6 else "",
        })
    return out


def _collapse(rows: list[dict]) -> list[dict]:
    """One line per (timestamp, family) — TE lists CPI as six rows at 12:30."""
    best: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["when_utc"], r["family"])
        cur = best.get(key)
        if cur is None or IMPACT_RANK[r["impact"]] > IMPACT_RANK[cur["impact"]]:
            best[key] = r
    items = sorted(best.values(), key=lambda r: r["_when"])
    out = []
    for r in items[:MAX_ITEMS]:
        when = r.pop("_when")
        et, oslo = when.astimezone(ET), when.astimezone(OSLO)
        out.append({
            **r,
            "date_et": et.strftime("%Y-%m-%d"),
            "day_et": et.strftime("%a %d %b"),
            "time_et": et.strftime("%H:%M"),
            "time_oslo": oslo.strftime("%H:%M"),
        })
    return out


def _fomc(now_utc: datetime) -> dict:
    """Meeting dates from the Fed's own page; fall back to the verified list."""
    meetings: list[tuple[str, str]] = []
    source = "federalreserve.gov (live)"
    text = get_text(FED_CALENDAR, timeout=25)
    if text:
        flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
        start = flat.find("2026 FOMC Meetings")
        end = flat.find("2025 FOMC Meetings", start + 1)
        if start >= 0 and end > start:
            for mon, d1, d2 in re.findall(
                r"(January|February|March|April|May|June|July|August|September|"
                r"October|November|December)\s+(\d{1,2})-(\d{1,2})",
                flat[start:end],
            ):
                m = MONTHS[mon]
                meetings.append((f"2026-{m:02d}-{int(d1):02d}", f"2026-{m:02d}-{int(d2):02d}"))
    if len(meetings) != 8:  # partial parse is untrustworthy — use the verified list
        if meetings:
            log.warning("FOMC scrape parsed %d meetings, expected 8", len(meetings))
        meetings = list(FOMC_2026_FALLBACK)
        source = "federalreserve.gov (verified 2026-08-07, cached)"
    today = now_utc.date().isoformat()
    upcoming = [m for m in meetings if m[1] >= today]
    return {
        "meetings_2026": [{"start": a, "end": b} for a, b in meetings],
        "next": {"start": upcoming[0][0], "end": upcoming[0][1]} if upcoming else None,
        "source": source,
    }


def fetch() -> dict:
    now = datetime.now(timezone.utc)
    generated = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    fomc = _fomc(now)

    html = get_text(TE_CALENDAR, timeout=25)
    if not html:
        # An empty timeline reads as "nothing scheduled", which is the one
        # failure mode that is actively dangerous here. Say it is broken.
        return {
            "items": [], "count": 0, "fomc": fomc,
            "source": "TradingEconomics (unreachable)",
            "status": "err",
            "error": "calendar fetch failed — schedule unknown, not empty",
            "generated_at": generated, "horizon_days": HORIZON_DAYS,
        }
    try:
        items = _collapse(_parse_te_rows(html, now))
    except Exception as e:  # noqa: BLE001 — layout drift must not blank the block
        log.warning("TradingEconomics parse failed: %s", e)
        return {
            "items": [], "count": 0, "fomc": fomc,
            "source": "TradingEconomics (parse failed)",
            "status": "err",
            "error": f"calendar parse failed ({type(e).__name__}) — schedule unknown",
            "generated_at": generated, "horizon_days": HORIZON_DAYS,
        }

    return {
        "items": items,
        "count": len(items),
        "fomc": fomc,
        "source": f"TradingEconomics · US, next {HORIZON_DAYS}d · Fed: {fomc['source']}",
        "status": "ok" if items else "warn",
        "generated_at": generated,
        "horizon_days": HORIZON_DAYS,
    }
