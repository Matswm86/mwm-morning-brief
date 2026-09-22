"""per_cell_tracker — activity breakdown for the live funded cells.

Reads JSONL event logs from ~/MWM/data/vps_logs/<svc>/ (populated by the
mwm-brief-vps-logs-sync.timer which rsyncs from VPS every 5 min).

For each cell produces: symbol, contracts, window, trade-day status,
bars/signals/entries/fills counts, in-position flag, last heartbeat age,
and a status pill (active | in_position | armed | off-day | stale | error).

Known limitations:
  - order_filled events have null price/side/size (SDK doesn't populate them).
    Use entry event's engine_entry_price as fill-price proxy.
  - position_closed.pnl is null — don't attempt per-cell PnL, use TopstepX
    aggregate trade count for that (fetchers/trade_tracker.py).
  - liqsweep-v10 has no config_locked.json — schema hardcoded below.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from config import MWM_ROOT

log = logging.getLogger("morning-brief.per_cell_tracker")

VPS_LOGS = MWM_ROOT / "data" / "vps_logs"

# Funded PDHR runner directory under vps_logs. Carries the broker account id,
# so it is read from BRIEF_FUNDED_SERVICE in ~/MWM/.env rather than committed.
FUNDED_PDHR_SERVICE = os.environ.get("BRIEF_FUNDED_SERVICE", "")

# Display metadata per service. `window` is a short human label; `tz` is used
# for DOW evaluation when the config omits it (MNQ orbaron services).
# Live fleet = the PDHR cell on the funded account (MNQ 5ct,
# RTH-only). LiqSweep was retired fleet-wide 2026-06-22 (overnight loss blew
# XFA) and PARKED; PDHR (Prior-Day H/L break-and-retest) replaced it on all
# three funded accounts. The practice cells are intentionally excluded — this
# panel mirrors the real-money fleet only.
CELLS: list[dict[str, Any]] = [
    {
        "service": FUNDED_PDHR_SERVICE,
        "label": "PDHR MNQ",
        "engine": "pdhr",
        "window": "RTH",
        "tz": "America/New_York",
        # PDHR runs RTH-only, no DOW filter; hardcode schema.
        "default_symbol": "MNQ",
        "default_contracts": 5,
        "default_timeframe": "1min",
        "trade_dow": [True] * 7,
    },
]

STALE_SEC = 15 * 60  # heartbeat missing more than 15 min → stale

# Entry-placement event types. Orbaron runners emit entry_market_placed;
# liqsweep uses entry_limit_placed.
ENTRY_TYPES = {"entry_market_placed", "entry_limit_placed"}


def _read_jsonl(path: Path) -> list[dict]:
    """Parse a JSONL file, tolerating NaN tokens (liqsweep engine snapshots)."""
    out: list[dict] = []
    if not path.exists():
        return out
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


def _load_events_window(svc_dir: Path, now_utc: datetime) -> list[dict]:
    """Load events from today's file + yesterday's tail (covers UTC rollover)."""
    today = now_utc.date()
    yesterday = today - timedelta(days=1)
    events: list[dict] = []
    events.extend(_read_jsonl(svc_dir / f"events_{yesterday.isoformat()}.jsonl"))
    events.extend(_read_jsonl(svc_dir / f"events_{today.isoformat()}.jsonl"))
    return events


def _any_startup_exists(svc_dir: Path) -> bool:
    """Services that haven't restarted since deploy have their startup event in an
    older log. Scan all mirrored files for at least one startup event."""
    for f in sorted(svc_dir.glob("events_*.jsonl"), reverse=True):
        for ev in _read_jsonl(f):
            if ev.get("type") == "startup":
                return True
    return False


def _load_config(svc_dir: Path) -> dict:
    cfg_path = svc_dir / "config_locked.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text())
    except Exception as exc:
        log.warning("config parse failed %s: %s", cfg_path, exc)
        return {}


def _latest(events: list[dict], event_type: str) -> dict | None:
    for ev in reversed(events):
        if ev.get("type") == event_type:
            return ev
    return None


def _parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def _today_local(tz_name: str, now_utc: datetime) -> date:
    try:
        return now_utc.astimezone(ZoneInfo(tz_name)).date()
    except Exception:
        return now_utc.date()


def _is_trade_dow_today(trade_dow: list[bool], tz_name: str, now_utc: datetime) -> bool:
    if not trade_dow or len(trade_dow) != 7:
        return True
    local_today = _today_local(tz_name, now_utc)
    # Python: Monday=0 … Sunday=6. Config order is [Mon, Tue, Wed, Thu, Fri, Sat, Sun].
    return bool(trade_dow[local_today.weekday()])


def _count_today(events: list[dict], now_utc: datetime, predicate) -> int:
    today = now_utc.date()
    n = 0
    for ev in events:
        ts = _parse_utc(ev.get("ts_utc"))
        if ts is None or ts.date() != today:
            continue
        if predicate(ev):
            n += 1
    return n


def _last_trade_info(events: list[dict], now_utc: datetime) -> tuple[float | None, str | None]:
    """Return (engine_entry_price, ts_utc_iso) of most recent entry today."""
    today = now_utc.date()
    for ev in reversed(events):
        if ev.get("type") not in ENTRY_TYPES:
            continue
        ts = _parse_utc(ev.get("ts_utc"))
        if ts is None or ts.date() != today:
            continue
        price = ev.get("engine_entry_price")
        if price is None:
            price = ev.get("price")  # liqsweep entry_limit_placed carries `price`
        return (price, ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return (None, None)


def _derive_in_position(hb: dict | None) -> bool:
    if not hb:
        return False
    engine = hb.get("engine") or {}
    if engine.get("in_position") is True:
        return True
    # liqsweep uses pos_dir != 0 instead of in_position
    if engine.get("pos_dir") not in (None, 0):
        return True
    # Orders armed = effectively in-position (entry filled, SL/TP pending)
    active = hb.get("active_orders") or {}
    if active.get("sl") or active.get("tp"):
        return True
    return False


def _derive_status(
    *,
    startup_ok: bool,
    hb_age_s: float | None,
    is_trade_dow: bool,
    entries_today: int,
    closes_today: int,
    in_position: bool,
    engine: str,
) -> tuple[str, str]:
    """Return (status_code, human_detail)."""
    if not startup_ok:
        return ("error", "no startup event")
    if hb_age_s is None:
        return ("error", "no heartbeat")
    if hb_age_s > STALE_SEC:
        mins = int(hb_age_s / 60)
        return ("stale", f"no heartbeat in {mins}m")
    if in_position:
        return ("in_position", "trade active")
    if entries_today > 0 and closes_today >= entries_today:
        return ("active", f"fired {entries_today}× today")
    if entries_today > 0:
        return ("active", f"fired {entries_today}× (pending close)")
    if not is_trade_dow and engine != "liqsweep-v10":
        return ("off_day", "DOW filter excludes today")
    return ("armed", "scanning")


def _cell_payload(meta: dict, now_utc: datetime) -> dict:
    svc = meta["service"]
    svc_dir = VPS_LOGS / svc
    cfg = _load_config(svc_dir)
    events = _load_events_window(svc_dir, now_utc)

    # Symbol/contracts/timeframe: config wins, fallback to latest startup, fallback to defaults.
    latest_startup = _latest(events, "startup")
    symbol = (
        cfg.get("live_contract")
        or cfg.get("symbol")
        or (latest_startup or {}).get("contract")
        or meta.get("default_symbol", "—")
    )
    contracts = (
        cfg.get("contracts")
        or (latest_startup or {}).get("size")
        or meta.get("default_contracts", 1)
    )
    timeframe = (
        cfg.get("timeframe")
        or (latest_startup or {}).get("timeframe")
        or meta.get("default_timeframe", "—")
    )

    trade_dow = cfg.get("trade_dow") or meta.get("trade_dow") or [True] * 7
    # For orbaron MNQ services the trade_dow is only in startup.engine_cfg
    if not cfg.get("trade_dow") and latest_startup:
        startup_cfg = latest_startup.get("engine_cfg") or {}
        if startup_cfg.get("trade_dow"):
            trade_dow = startup_cfg["trade_dow"]

    is_trade_dow = _is_trade_dow_today(trade_dow, meta["tz"], now_utc)

    hb = _latest(events, "heartbeat")
    hb_ts = _parse_utc((hb or {}).get("ts_utc"))
    hb_age_s = (now_utc - hb_ts).total_seconds() if hb_ts else None

    bars_today = _count_today(events, now_utc, lambda e: e.get("type") == "bar")
    # entries_today: count distinct entry_* events on TODAY UTC
    entries_today = _count_today(events, now_utc, lambda e: e.get("type") in ENTRY_TYPES)
    fills_today = _count_today(events, now_utc, lambda e: e.get("type") == "order_filled")
    closes_today = _count_today(events, now_utc, lambda e: e.get("type") == "position_closed")

    # signals_today: prefer the engine counter from the most recent heartbeat
    # (runner tracks this); fallback to entries_today.
    signals_today = (hb or {}).get("engine", {}).get("signals_today")
    if signals_today is None:
        signals_today = entries_today

    in_pos = _derive_in_position(hb)
    last_price, last_ts = _last_trade_info(events, now_utc)

    startup_ok = latest_startup is not None or _any_startup_exists(svc_dir)

    status, detail = _derive_status(
        startup_ok=startup_ok,
        hb_age_s=hb_age_s,
        is_trade_dow=is_trade_dow,
        entries_today=entries_today,
        closes_today=closes_today,
        in_position=in_pos,
        engine=meta["engine"],
    )

    return {
        "service": svc,
        "label": meta["label"],
        "engine": meta["engine"],
        "symbol": symbol,
        "contracts": int(contracts) if contracts is not None else None,
        "timeframe": timeframe,
        "window": meta["window"],
        "tz": meta["tz"],
        "is_trade_dow_today": is_trade_dow,
        "trade_dow": trade_dow,
        "bars_today": bars_today,
        "signals_today": int(signals_today) if signals_today is not None else 0,
        "entries_today": entries_today,
        "fills_today": fills_today,
        "closes_today": closes_today,
        "in_position": in_pos,
        "last_heartbeat_utc": hb_ts.strftime("%Y-%m-%dT%H:%M:%SZ") if hb_ts else None,
        "last_heartbeat_age_s": int(hb_age_s) if hb_age_s is not None else None,
        "last_trade_price": last_price,
        "last_trade_time_utc": last_ts,
        "status": status,
        "status_detail": detail,
    }


def _summary(cells: list[dict]) -> dict:
    counts = {
        "active": 0,
        "in_position": 0,
        "armed": 0,
        "off_day": 0,
        "stale": 0,
        "error": 0,
    }
    for c in cells:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    alive = sum(1 for c in cells if c["status"] not in ("stale", "error"))
    return {
        "total": len(cells),
        "alive": alive,
        **counts,
    }


def _last_sync_utc() -> str | None:
    marker = VPS_LOGS / ".last_sync"
    if not marker.exists():
        return None
    try:
        return marker.read_text().strip()
    except Exception:
        return None


def fetch() -> dict:
    now_utc = datetime.now(UTC)
    cells: list[dict] = []
    for meta in CELLS:
        try:
            cells.append(_cell_payload(meta, now_utc))
        except Exception as exc:
            log.exception("cell %s failed", meta["service"])
            cells.append(
                {
                    "service": meta["service"],
                    "label": meta["label"],
                    "status": "error",
                    "status_detail": f"fetch raised: {type(exc).__name__}",
                }
            )

    return {
        "status": "ok",
        "cells": cells,
        "summary": _summary(cells),
        "last_sync_utc": _last_sync_utc(),
        "generated_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(fetch(), indent=2, default=str))
