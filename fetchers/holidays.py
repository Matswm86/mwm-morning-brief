"""US exchange holidays for the front page.

The brief is a morning newspaper. A closed market is the front-page headline,
so this module answers three questions for the builder: is the market closed
today (ET), is it closed tomorrow, and when is the next closure. The dates come
from the CME Group / NYSE holiday calendars for 2026; the per-product halt
times were checked against broker holiday notices on 2026-09-06 (equity index
halt 12:00 CT verified; the metals halt is an early halt in the same hour and
its exact minute is left unverified on purpose). Do not invent minutes.

An early halt is not a closed market. Mats reads a 13:00 ET halt as a
shortened day, so the headline says CLOSING EARLY and the live book still runs.

Display only. Nothing here gates an account or a strategy.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# globex: "early_halt" = US stocks shut, CME Globex trades the overnight and
#         halts around midday CT (the Monday-holiday pattern, and Thanksgiving);
#         "closed" = no Globex session at all for the day (Good Friday, Christmas,
#         New Year's). mnq_halt_et is the verified equity-index halt; the COMEX
#         metals minute is not printed because it was not verified.
HOLIDAYS: list[dict] = [
    {"date": "2026-01-01", "name": "New Year's Day", "globex": "closed"},
    {"date": "2026-01-19", "name": "Martin Luther King Jr. Day", "globex": "early_halt", "mnq_halt_et": "13:00"},
    {"date": "2026-02-16", "name": "Presidents' Day", "globex": "early_halt", "mnq_halt_et": "13:00"},
    {"date": "2026-04-03", "name": "Good Friday", "globex": "closed"},
    {"date": "2026-05-25", "name": "Memorial Day", "globex": "early_halt", "mnq_halt_et": "13:00"},
    {"date": "2026-06-19", "name": "Juneteenth", "globex": "early_halt", "mnq_halt_et": "13:00"},
    {"date": "2026-07-03", "name": "Independence Day (observed)", "globex": "early_halt", "mnq_halt_et": "13:00"},
    {"date": "2026-09-07", "name": "Labor Day", "globex": "early_halt", "mnq_halt_et": "13:00"},
    {"date": "2026-11-26", "name": "Thanksgiving", "globex": "early_halt", "mnq_halt_et": "13:00"},
    {"date": "2026-11-27", "name": "Day after Thanksgiving", "globex": "early_halt", "mnq_halt_et": "13:15", "stocks": "13:00 ET close"},
    {"date": "2026-12-25", "name": "Christmas Day", "globex": "closed"},
    {"date": "2027-01-01", "name": "New Year's Day", "globex": "closed"},
]


def _oslo(hhmm_et: str) -> str:
    h, m = hhmm_et.split(":")
    return f"{(int(h) + 6) % 24:02d}:{m}"  # ET -> Oslo is +6 h on every 2026 holiday date above


def describe(h: dict) -> str:
    """One deck sentence for the front page, from the row only."""
    if h["globex"] == "closed":
        return f"{h['name']}. US stock exchanges shut and CME Globex has no session; nothing prints until the next trade date opens at 18:00 ET / 00:00 Oslo."
    halt = h.get("mnq_halt_et", "13:00")
    stocks = h.get("stocks") or "US stock exchanges shut"
    return (
        f"{h['name']}. {stocks}. CME Globex trades the overnight and the morning, "
        f"then MNQ halts at {halt} ET / {_oslo(halt)} Oslo (verified); COMEX metals halt "
        f"early in the same hour (minute unverified). Everything reopens 18:00 ET / "
        f"00:00 Oslo for the next trade date."
    )


_BY_DATE = {h["date"]: h for h in HOLIDAYS}


def holiday_on(d: date) -> dict | None:
    return _BY_DATE.get(d.isoformat())


def is_closed(d: date) -> bool:
    """True when Globex has no session at all: weekend or a 'closed' holiday.

    Early-halt holidays are NOT closed: the live book trades the morning and
    the halt is a note on the card, not a stand-down.
    """
    if d.weekday() >= 5:
        return True
    h = holiday_on(d)
    return bool(h and h["globex"] == "closed")


def next_trading_day(d: date) -> date:
    """First date strictly after d with a regular day session."""
    n = d + timedelta(days=1)
    while is_closed(n):
        n += timedelta(days=1)
    return n


def next_full_session(d: date) -> date:
    """First date strictly after d that is neither closed nor an early halt."""
    n = d + timedelta(days=1)
    while is_closed(n) or (holiday_on(n) or {}).get("globex") == "early_halt":
        n += timedelta(days=1)
    return n


def _row(d: date, h: dict | None) -> dict:
    return {
        "date_et": d.isoformat(),
        "weekday": d.strftime("%A"),
        "weekend": d.weekday() >= 5,
        "holiday": h["name"] if h else None,
        "globex": h["globex"] if h else None,
        "mnq_halt_et": h.get("mnq_halt_et") if h else None,
        "mnq_halt_oslo": _oslo(h["mnq_halt_et"]) if h and h.get("mnq_halt_et") else None,
        "detail": describe(h) if h else None,
        "closed": is_closed(d),
        "early_halt": bool(h and h["globex"] == "early_halt"),
    }


def fetch(now: datetime | None = None) -> dict:
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    today = now_et.date()
    tomorrow = today + timedelta(days=1)
    upcoming = [
        h for h in HOLIDAYS if date.fromisoformat(h["date"]) > today
    ]
    nxt = upcoming[0] if upcoming else None
    return {
        "status": "ok",
        "asof_et": now_et.strftime("%Y-%m-%d %H:%M ET"),
        "today": _row(today, holiday_on(today)),
        "tomorrow": _row(tomorrow, holiday_on(tomorrow)),
        "next_trading_day": next_trading_day(today).isoformat(),
        "next_full_session": next_full_session(today).isoformat(),
        "next_holiday": {
            "date_et": nxt["date"],
            "name": nxt["name"],
            "globex": nxt["globex"],
            "days_away": (date.fromisoformat(nxt["date"]) - today).days,
        }
        if nxt
        else None,
        "source": "CME Group + NYSE 2026 holiday calendars; halt times checked 2026-09-06",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(fetch(), indent=2))
