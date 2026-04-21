"""trade_tracker — Live trade count from TopstepX practice account.

Fetches today's and this week's completed trades.
Cached on disk (4h TTL) — brief builds hourly-ish, no need to hammer the API.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from config import MWM_ROOT

log = logging.getLogger("morning-brief.trade_tracker")

API_BASE = "https://api.topstepx.com"

# Credentials loaded from trading project .env (rotated regularly)
_TRADING_ENV = MWM_ROOT / "projects" / "mwm-trading" / ".env"


def _load_trading_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not _TRADING_ENV.exists():
        return env
    for line in _TRADING_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


_TRADING_ENV_CACHE: dict[str, str] = {}


def _creds() -> tuple[str, str, int]:
    global _TRADING_ENV_CACHE
    if not _TRADING_ENV_CACHE:
        _TRADING_ENV_CACHE = _load_trading_env()
    env = _TRADING_ENV_CACHE
    api_key = env.get("PROJECT_X_API_KEY", "")
    username = env.get("PROJECT_X_USERNAME", "matswm86")
    account_id = int(env.get("PROJECT_X_ACCOUNT_ID", "19907662"))
    return api_key, username, account_id

CACHE_DIR = MWM_ROOT / "data" / "trade_tracker_cache"
CACHE_TTL_SEC = 4 * 3600

_session: dict = {"token": None, "expires": 0.0}


def _authenticate() -> str | None:
    if _session["token"] and time.time() < _session["expires"]:
        return _session["token"]
    api_key, username, _ = _creds()
    if not api_key:
        log.warning("PROJECT_X_API_KEY not found in trading .env")
        return None
    try:
        r = requests.post(
            f"{API_BASE}/api/Auth/loginKey",
            json={"userName": username, "apiKey": api_key},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("success", True) is False and data.get("token"):
            pass
        token = data.get("token")
        if not token:
            log.warning("Auth returned no token: errorCode=%s", data.get("errorCode"))
            return None
        _session["token"] = token
        _session["expires"] = time.time() + 3500
        return token
    except Exception as exc:
        log.warning("TopstepX auth failed: %s", exc)
        return None


def _post(endpoint: str, payload: dict) -> dict:
    token = _authenticate()
    if not token:
        return {"error": "auth failed"}
    try:
        r = requests.post(
            f"{API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.warning("TopstepX %s failed: %s", endpoint, exc)
        return {"error": str(exc)}


def _parse_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _count(trades: list[dict], start: datetime) -> dict:
    total = wins = losses = 0
    for t in trades:
        ts = _parse_dt(
            t.get("timestamp") or t.get("closedAt") or t.get("createdAt")
        )
        if not ts or ts < start:
            continue
        total += 1
        pnl = 0.0
        try:
            pnl = float(t.get("pnl") or t.get("realizedPnl") or 0)
        except (TypeError, ValueError):
            pass
        if pnl >= 0:
            wins += 1
        else:
            losses += 1
    return {"total": total, "wins": wins, "losses": losses}


def _build() -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())

    _, _, account_id = _creds()
    data = _post("/api/Trade/search", {"accountId": account_id})
    if "error" in data:
        return {
            "daily_trades": None, "daily_wins": None, "daily_losses": None,
            "weekly_trades": None, "weekly_wins": None, "weekly_losses": None,
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "error",
            "error": data["error"],
        }

    if isinstance(data, dict) and not data.get("success", True):
        return {
            "daily_trades": 0, "daily_wins": 0, "daily_losses": 0,
            "weekly_trades": 0, "weekly_wins": 0, "weekly_losses": 0,
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "ok",
        }
    trades = data if isinstance(data, list) else data.get("trades", data.get("items", []))
    trades = [t for t in trades if isinstance(t, dict)]

    daily = _count(trades, today_start)
    weekly = _count(trades, week_start)

    return {
        "daily_trades": daily["total"],
        "daily_wins": daily["wins"],
        "daily_losses": daily["losses"],
        "weekly_trades": weekly["total"],
        "weekly_wins": weekly["wins"],
        "weekly_losses": weekly["losses"],
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "ok",
    }


def fetch() -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / "latest.json"

    if cache.exists():
        try:
            if time.time() - cache.stat().st_mtime < CACHE_TTL_SEC:
                return json.loads(cache.read_text())
        except Exception:
            pass

    block = _build()
    try:
        cache.write_text(json.dumps(block, ensure_ascii=False, indent=2))
    except Exception as exc:
        log.warning("trade_tracker cache write failed: %s", exc)
    return block


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    result = fetch()
    print(json.dumps(result, indent=2))
