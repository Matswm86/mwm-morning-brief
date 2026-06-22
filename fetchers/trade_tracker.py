"""trade_tracker — Live trade count, sourced from engine event logs.

Counts ONLY the PDHR cell on the XFA Funded account 24154823 (see
COMBINE_SERVICES below) — the practice (19907662) cells are excluded so the
Live Trades panel reflects real-money activity only. LiqSweep was retired
fleet-wide 2026-06-22 and replaced by PDHR MNQ @5ct on the funded fleet.

Aligns with cell_activity by counting the SAME events per_cell_tracker
counts: entry_market_placed + entry_limit_placed emitted by the live
XFA runners, mirrored to ~/MWM-AI/data/vps_logs/<svc>/ via the
mwm-brief-vps-logs-sync.timer (5 min cadence).

Previously this hit TopstepX /api/Trade/search for *closed* trades,
which caused misalignment: cell_activity would show '2 entries today'
while Live Trades showed 0 because the positions were still open. Now
both panels share a single source of truth.

Wins/losses are not derived here — SDK position_closed.pnl is null in
the mirrored events, so win rate lives in the backtest_stats card
(reference numbers) not on the live tracker.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import MWM_ROOT

log = logging.getLogger("morning-brief.trade_tracker")

VPS_LOGS = MWM_ROOT / "data" / "vps_logs"

# Must match fetchers/per_cell_tracker.ENTRY_TYPES for alignment.
ENTRY_TYPES = {"entry_market_placed", "entry_limit_placed"}

# XFA Funded account 24154823 fleet — must stay in sync with the live
# services in fetchers/per_cell_tracker.CELLS. Live Trades counts this account
# only, not the practice (19907662) cells. (Name kept as COMBINE_SERVICES for
# back-compat; the account passed off Combine to XFA Funded 2026-06-11.)
COMBINE_SERVICES = [
    "pdhr-mnq-funded-24154823",
]


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        log.warning("read failed %s: %s", path, exc)
    return out


def _parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _count_entries(since_utc: datetime) -> int:
    if not VPS_LOGS.exists():
        return 0
    now = datetime.now(timezone.utc)
    # Glob today + each day back to since_utc (inclusive) across all services
    total = 0
    day = since_utc.date()
    end_day = now.date()
    service_dirs = [VPS_LOGS / s for s in COMBINE_SERVICES]
    while day <= end_day:
        stamp = day.isoformat()
        for svc in service_dirs:
            for ev in _read_jsonl(svc / f"events_{stamp}.jsonl"):
                if ev.get("type") not in ENTRY_TYPES:
                    continue
                ts = _parse_utc(ev.get("ts_utc"))
                if ts is None or ts < since_utc:
                    continue
                total += 1
        day += timedelta(days=1)
    return total


def fetch() -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())

    daily = _count_entries(today_start)
    weekly = _count_entries(week_start)

    return {
        "daily_trades": daily,
        "daily_wins": None,
        "daily_losses": None,
        "weekly_trades": weekly,
        "weekly_wins": None,
        "weekly_losses": None,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok",
        "source": "engine_events",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch(), indent=2))
