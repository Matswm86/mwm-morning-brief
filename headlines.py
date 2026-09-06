"""Front page headlines — the newspaper's top of page one.

Composes, from sections the builder already fetched, a lead headline with a
deck, three sub-headlines from the trading wire, and the small satirical
furniture an old broadsheet carried (the ear, the weather, the corrections
box). Priority for the lead:

  1. market closed today (holiday or weekend)  -> MARKETS CLOSED
  2. market closed tomorrow                     -> MARKETS CLOSED TOMORROW
  3. a tier-1 US release today                  -> the release, its time
  4. the pre-open range call                    -> expected size of the day

Every figure in a headline is read from the feed. The jokes are written here
by hand; they name no person, no account, no internal system. Display only.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

TIER1 = {
    "CPI · inflation": "CPI",
    "Nonfarm payrolls": "PAYROLLS",
    "PCE prices": "PCE",
    "PPI": "PPI",
    "GDP": "GDP",
    "Retail sales": "RETAIL SALES",
    "FOMC rate decision": "THE FED DECIDES",
}

# Rotated by day of year so the page changes daily without a model in the loop.
EARS = [
    "All the signal that's fit to print.",
    "Est. 2026. Never once early.",
    "Published daily, read by one, ignored by the market.",
    "Now with 30% fewer opinions about direction.",
    "The only paper whose weather report is a volatility forecast.",
    "Printed on recycled drawdowns.",
    "We do not predict direction. We have tried. It did not go well.",
    "Yesterday's news, today, in a serif.",
    "Independent since the last time we were wrong.",
    "A newspaper for a reader who flips the switch himself.",
    "Size of the day, not the side of the day.",
    "Correct 65% of the time, humble 100% of the time.",
]

CORRECTIONS = [
    "An earlier edition described the market as 'obviously' about to do something. It did the other thing. We regret the adverb.",
    "The desk wishes to clarify that a 'narrow' day is not a promise, merely a well-documented lean.",
    "In a previous issue the weather column forecast 'chop'. It chopped. No correction required; we simply wanted that on the record.",
    "A reader writes to ask whether the paper has ever been early. The paper has not. The reader's letter arrived late.",
    "Our gold correspondent reports that gold 'went up because of reasons'. The reasons have been referred to the research desk.",
    "The phrase 'this time is different' has been removed from the style guide following an internal review.",
    "An ORB verdict published on a Saturday referred to a session that did not exist. The verdict stands; the session has been reprimanded.",
]

WEATHER = {
    "NARROW": "Tight and drizzly. Range contracting; bring a small stop and low expectations.",
    "CONTRACTION": "Tight and drizzly. Range contracting; bring a small stop and low expectations.",
    "WIDE": "Gusty with a chance of expansion. Ranges above the recent norm; hold on to your hat and your stop.",
    "EXPANSION": "Gusty with a chance of expansion. Ranges above the recent norm; hold on to your hat and your stop.",
    "NO CALL": "Overcast. The range model declines to commit, which is the most honest forecast in the paper.",
}


def _pick(pool: list[str], d: date) -> str:
    return pool[d.timetuple().tm_yday % len(pool)]


def _fmt_date(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%A %d %B")
    except ValueError:
        return iso


def _closed_lead(row: dict, when: str) -> dict:
    name = row.get("holiday")
    day = _fmt_date(row["date_et"])
    if name:
        head = "MARKETS CLOSED" if when == "today" else "MARKETS CLOSED TOMORROW"
        kicker = f"{name} · {day}"
        deck = row.get("detail") or f"{name}. No regular session on {day}."
    else:
        head = "MARKETS CLOSED"
        kicker = f"Weekend · {day}"
        deck = "No session. Globex reopens Sunday 18:00 ET / 00:00 Oslo."
    return {"kicker": kicker, "headline": head, "deck": deck, "tone": "closed"}


def _event_lead(events: list[dict], today: str) -> dict | None:
    todays = [e for e in events if e.get("date_et") == today and e.get("family") in TIER1]
    if not todays:
        return None
    todays.sort(key=lambda e: e.get("time_et") or "")
    e = todays[0]
    word = TIER1[e["family"]]
    t = f"{e.get('time_et')} ET / {e.get('time_oslo')} Oslo" if e.get("time_et") else "today"
    more = ", ".join(TIER1[x["family"]] for x in todays[1:])
    deck = f"{e['family']} lands at {t}."
    if more:
        deck += f" Also on the slate: {more}."
    deck += " Tier-1 prints move the tape faster than a stop can; the calendar block below carries every row."
    return {"kicker": f"Scheduled · {_fmt_date(today)}", "headline": f"{word} AT {e.get('time_et', '—')} ET", "deck": deck, "tone": "event"}


def _range_lead(preopen: dict, today: str) -> dict:
    insts = (preopen or {}).get("instruments") or {}
    mnq, mgc = insts.get("MNQ") or {}, insts.get("MGC") or {}
    call_m = (mnq.get("expansion") or mnq.get("call") or "NO CALL").upper()
    call_g = (mgc.get("expansion") or mgc.get("call") or "NO CALL").upper()
    word = {"EXPANSION": "WIDE", "CONTRACTION": "NARROW"}.get(call_m, call_m)
    gold = {"EXPANSION": "WIDE", "CONTRACTION": "NARROW"}.get(call_g, call_g)
    head = f"NASDAQ: {word} DAY EXPECTED" if word != "NO CALL" else "NASDAQ: RANGE MODEL DECLINES TO CALL"
    rng = (mnq.get("expected_range_pts") or {}).get("p50")
    rng_g = (mgc.get("expected_range_pts") or {}).get("p50")
    deck = ""
    if rng:
        deck += f"Median forecast {round(rng)} points on MNQ against a 26-day median of {round(mnq.get('median26d_pts') or 0)}. "
    if gold != "NO CALL" and rng_g:
        deck += f"Gold reads {gold.lower()}, {round(rng_g)} points expected. "
    deck += "Size of the day, not a direction call and not a profit claim."
    if preopen and preopen.get("stale"):
        deck += f" (Read is {preopen.get('age_hours')} h old.)"
    return {"kicker": f"Pre-open · {_fmt_date(today)}", "headline": head, "deck": deck.strip(), "tone": "range"}


def compose(
    holidays: dict,
    event_section: dict,
    preopen: dict,
    trading_news: dict,
    play: dict,
    now: datetime | None = None,
) -> dict:
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    d = now_et.date()
    today = d.isoformat()
    h_today = (holidays or {}).get("today") or {}
    h_tom = (holidays or {}).get("tomorrow") or {}

    if h_today.get("closed") and (h_today.get("holiday") or h_tom.get("holiday")):
        # Weekend before a Monday holiday: the holiday IS the news.
        lead = _closed_lead(h_tom if (not h_today.get("holiday") and h_tom.get("holiday")) else h_today,
                            "today" if h_today.get("holiday") else "tomorrow")
    elif h_today.get("closed"):
        lead = _closed_lead(h_today, "today")
    elif h_tom.get("closed") and h_tom.get("holiday"):
        lead = _closed_lead(h_tom, "tomorrow")
    else:
        lead = _event_lead((event_section or {}).get("items") or [], today) or _range_lead(preopen, today)

    subs = []
    for it in ((trading_news or {}).get("items") or [])[:3]:
        subs.append({
            "headline": it.get("headline"),
            "url": it.get("url"),
            "tag": it.get("instrument") or "BOTH",
            "driver": it.get("driver"),
            "source": it.get("source"),
        })

    # Weather = the range call, read as a forecast. Closed days get a calm front.
    insts = (preopen or {}).get("instruments") or {}
    call = ((insts.get("MNQ") or {}).get("expansion") or (insts.get("MNQ") or {}).get("call") or "NO CALL").upper()
    weather = (
        "Calm. Nothing is open, so nothing can chop you. Enjoy it."
        if lead["tone"] == "closed"
        else WEATHER.get(call, WEATHER["NO CALL"])
    )

    nxt = (holidays or {}).get("next_holiday") or {}
    notice = None
    if nxt and lead["tone"] != "closed":
        notice = f"Next closure: {nxt.get('name')}, {_fmt_date(nxt.get('date_et'))} ({nxt.get('days_away')} days)."
    elif h_today.get("closed"):
        notice = f"Next session: {_fmt_date((holidays or {}).get('next_trading_day') or '')}."

    live = [r.get("strategy") for r in (play or {}).get("rows") or []]
    return {
        "status": "ok",
        "date_et": today,
        "lead": lead,
        "subheads": subs,
        "ear": _pick(EARS, d),
        "weather": weather,
        "correction": _pick(CORRECTIONS, d),
        "notice": notice,
        "desk_line": ("Live book: " + " · ".join(live) + " · one contract each.") if live else None,
    }
