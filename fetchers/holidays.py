"""US exchange holidays for the front page.

The brief is a morning newspaper. A closed market is the front-page headline,
so this module answers three questions for the builder: is the market closed
today (ET), is it closed tomorrow, and when is the next closure. The dates come
from the CME Group / NYSE holiday calendars for 2026; the per-product halt
times were checked against broker holiday notices on 2026-09-06 (equity index
halt 12:00 CT verified; the metals halt is an early halt in the same hour and
its exact minute is left unverified on purpose). Do not invent minutes.

Display only. Nothing here gates an account or a strategy.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# kind: "closed" = no RTH session at all (NYSE shut; Globex runs overnight and
# halts around midday CT, reopening 17:00 CT for the next trade date).
#        "early" = shortened day session.
HOLIDAYS: list[dict] = [
    {"date": "2026-01-01", "name": "New Year's Day", "kind": "closed"},
    {"date": "2026-01-19", "name": "Martin Luther King Jr. Day", "kind": "closed"},
    {"date": "2026-02-16", "name": "Presidents' Day", "kind": "closed"},
    {"date": "2026-04-03", "name": "Good Friday", "kind": "closed"},
    {"date": "2026-05-25", "name": "Memorial Day", "kind": "closed"},
    {"date": "2026-06-19", "name": "Juneteenth", "kind": "closed"},
    {"date": "2026-07-03", "name": "Independence Day (observed)", "kind": "closed"},
    {
        "date": "2026-09-07",
        "name": "Labor Day",
        "kind": "closed",
        "detail": (
            "US stock exchanges are shut. CME Globex trades the overnight, then "
            "halts: equity index (MNQ) at 13:00 ET / 19:00 Oslo (verified), COMEX "
            "metals (MGC) an early halt in the same hour (exact minute unverified). "
            "Everything reopens 18:00 ET / 00:00 Oslo for the Tuesday trade date."
        ),
        "mnq_halt_et": "13:00",
    },
    {
        "date": "2026-11-26",
        "name": "Thanksgiving",
        "kind": "closed",
        "detail": "US stock exchanges shut; CME Globex day session closed, early halt around midday CT.",
    },
    {
        "date": "2026-11-27",
        "name": "Day after Thanksgiving",
        "kind": "early",
        "detail": "Shortened session: US stocks close 13:00 ET; CME equity index halts early around 12:00-12:15 CT.",
    },
    {
        "date": "2026-12-25",
        "name": "Christmas Day",
        "kind": "closed",
        "detail": "US stock exchanges shut; CME Globex day session closed.",
    },
    {"date": "2027-01-01", "name": "New Year's Day", "kind": "closed"},
]

_BY_DATE = {h["date"]: h for h in HOLIDAYS}


def holiday_on(d: date) -> dict | None:
    return _BY_DATE.get(d.isoformat())


def is_closed(d: date) -> bool:
    """True when there is no regular day session: weekend or a 'closed' holiday."""
    if d.weekday() >= 5:
        return True
    h = holiday_on(d)
    return bool(h and h["kind"] == "closed")


def next_trading_day(d: date) -> date:
    """First date strictly after d with a regular day session."""
    n = d + timedelta(days=1)
    while is_closed(n):
        n += timedelta(days=1)
    return n


def _row(d: date, h: dict | None) -> dict:
    return {
        "date_et": d.isoformat(),
        "weekday": d.strftime("%A"),
        "weekend": d.weekday() >= 5,
        "holiday": h["name"] if h else None,
        "kind": h["kind"] if h else None,
        "detail": h.get("detail") if h else None,
        "closed": is_closed(d),
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
        "next_holiday": {
            "date_et": nxt["date"],
            "name": nxt["name"],
            "kind": nxt["kind"],
            "days_away": (date.fromisoformat(nxt["date"]) - today).days,
        }
        if nxt
        else None,
        "source": "CME Group + NYSE 2026 holiday calendars; halt times checked 2026-09-06",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(fetch(), indent=2))
