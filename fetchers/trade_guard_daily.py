"""trade_guard_daily — Trade Environment block for the morning brief.

Runs at 05:30 UTC inside builder.py. Synthesizes a "standard setup" for
each of the two strategies (PDHR, ORB), passes it through
the deterministic rule gates + macro scorer (no LLM), and emits a
panel-ready JSON dict.

Why deterministic only? The brief runs unattended; LLM latency + budget
are wasted when the user is asleep. Per-trade LLM reasoning lives in
the `trade_guard` MCP tool the user calls live during the session.

Output:
  {
    "date": "2026-04-22",
    "per_strategy": {
      "pdhr": {"verdict": "PROCEED|CAUTION|SKIP",
                    "risk_score": int, "severity": "...",
                    "top_concern": "...", "alerts": [...]},
      "orb":      {...},
    },
    "orb_handoff": {"status": "fresh", "verdict": "OK",
                     "age_h": float, "price_drift_pct": float,
                     "next_action": "..."},
    "generated_at": "<iso>",
    "source": "trade_guard.deterministic",
    "status": "ok|warn|err",
  }

Cached on disk at data/trade_guard_daily_cache/YYYY-MM-DD.json so the
builder never blocks on import-time work.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import FRED_API_KEY, MWM_ROOT, ORB_REGIME_URL
from http_util import get_json

log = logging.getLogger("morning-brief.trade_guard_daily")

# Import pure-logic modules from the market-news server. We do NOT import
# server.py itself (heavy: qdrant, embeddings, sentence-transformers).
_MN_DIR = MWM_ROOT / "projects" / "mwm-trading" / "mcp-servers" / "market-news"
sys.path.insert(0, str(_MN_DIR))

import contextualize_macro as _cm  # type: ignore  # noqa: E402
import orb_handoff as _oh  # type: ignore  # noqa: E402
import trade_guard as _tg  # type: ignore  # noqa: E402


CACHE_DIR = MWM_ROOT / "data" / "trade_guard_daily_cache"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
GSCPI_CACHE_PATH = MWM_ROOT / "data" / "gscpi" / "gscpi_data.xlsx"
SWEEP_STATE_PATH = MWM_ROOT / "data" / "last_sweep.json"

STRATEGIES = ("pdhr", "orb")
CACHE_TTL_SEC = 3600  # rebuild at most once per hour during a single brief run


# ─── Live signal collection (cheap, cached at FRED) ──────────────────

def _fred_latest_two(sid: str) -> tuple[float | None, float | None]:
    if not FRED_API_KEY:
        return None, None
    url = f"{FRED_BASE}?series_id={sid}&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=2"
    data = get_json(url)
    if not isinstance(data, dict):
        return None, None
    obs = data.get("observations") or []

    def _parse(o):
        v = o.get("value")
        try:
            return float(v) if v not in (None, "", ".") else None
        except (TypeError, ValueError):
            return None
    latest = _parse(obs[0]) if obs else None
    prev = _parse(obs[1]) if len(obs) > 1 else None
    return latest, prev


def _orb_payload() -> dict | None:
    """Read latest ORB lock — local file first, then VPS URL."""
    local = MWM_ROOT / "projects" / "mwm-trading" / "data" / "orb_regime" / "latest.json"
    if local.exists():
        try:
            return json.loads(local.read_text())
        except Exception as exc:
            log.warning("ORB local payload unreadable: %s", exc)
    if ORB_REGIME_URL:
        data = get_json(ORB_REGIME_URL)
        if isinstance(data, dict) and data.get("schema") == "orb_regime.v1":
            return data
    return None


def _orb_age_hours(payload: dict | None) -> float | None:
    if not payload:
        return None
    ts = payload.get("ts")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def _yahoo_nq_price() -> float | None:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/NQ%3DF?range=1d&interval=5m"
    data = get_json(url)
    if not isinstance(data, dict):
        return None
    chart = (data.get("chart") or {}).get("result") or []
    if not chart:
        return None
    meta = chart[0].get("meta") or {}
    p = meta.get("regularMarketPrice") or meta.get("previousClose")
    try:
        return float(p) if p is not None else None
    except (TypeError, ValueError):
        return None


def _gscpi_z() -> float | None:
    if not GSCPI_CACHE_PATH.exists():
        return None
    try:
        import openpyxl  # type: ignore
    except ImportError:
        return None
    try:
        wb = openpyxl.load_workbook(GSCPI_CACHE_PATH, data_only=True)
        # The xlsx has a "GSCPI Monthly Data" sheet with Date, GSCPI columns.
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            # Find the column index of "GSCPI" header.
            for header_idx in range(min(10, len(rows))):
                hdr = rows[header_idx]
                if hdr and any(str(c).strip().upper() == "GSCPI" for c in hdr if c is not None):
                    gscpi_col = next(i for i, c in enumerate(hdr) if c and str(c).strip().upper() == "GSCPI")
                    last_val = None
                    for r in rows[header_idx + 1:]:
                        if r and r[gscpi_col] is not None:
                            try:
                                last_val = float(r[gscpi_col])
                            except (TypeError, ValueError):
                                continue
                    if last_val is not None:
                        return last_val
    except Exception as exc:
        log.warning("GSCPI parse failed: %s", exc)
    return None


def _last_sweep_severity() -> int | None:
    if not SWEEP_STATE_PATH.exists():
        return None
    try:
        sw = json.loads(SWEEP_STATE_PATH.read_text())
    except Exception:
        return None
    prices = (sw or {}).get("prices") or {}
    nq = (prices.get("NQ=F") or {}).get("change_pct")
    vix = (prices.get("^VIX") or {}).get("change_pct")
    sev = 0
    for v, thresh in ((abs(nq) if nq is not None else 0, [0.5, 1.0, 2.0]),
                      (abs(vix) if vix is not None else 0, [5.0, 10.0, 15.0])):
        if v >= thresh[2]:
            sev = max(sev, 3)
        elif v >= thresh[1]:
            sev = max(sev, 2)
        elif v >= thresh[0]:
            sev = max(sev, 1)
    return sev or None


def _collect_signals() -> dict[str, Any]:
    sig: dict[str, Any] = {}
    vix, vix_prev = _fred_latest_two("VIXCLS")
    if vix is not None:
        sig["vix_level"] = vix
        if vix_prev is not None:
            sig["vix_delta_1d"] = vix - vix_prev
    hy, hy_prev = _fred_latest_two("BAMLH0A0HYM2")
    if hy is not None:
        sig["hy_spread_wide"] = hy
        if hy_prev is not None:
            sig["hy_spread_delta_1d"] = hy - hy_prev
    t10y2y, _ = _fred_latest_two("T10Y2Y")
    if t10y2y is not None:
        sig["yield_curve_inv"] = t10y2y * 100.0  # % → bp
    z = _gscpi_z()
    if z is not None:
        sig["gscpi_z"] = z
    sev = _last_sweep_severity()
    if sev is not None:
        sig["sweep_severity"] = sev
    sig["calendar_high_imp"] = 0  # brief runs at 05:30 UTC; calendar lookahead happens live
    return sig


# ─── Fetch entry point ───────────────────────────────────────────────

def _shape_per_strategy(
    strategy: str, regime: str, signals: dict[str, Any], snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Run rule gates + macro scorer for one strategy. Returns panel dict."""
    rule = _tg.apply_rule_gates(
        strategy=strategy, direction="long", contracts=2,
        risk_usd=200.0, snapshot=snapshot,
    )
    macro = _cm.score(strategy=strategy, regime=regime, signals=signals)

    # Use stricter of (rule, macro recommendation).
    macro_verdict = {"proceed": "PROCEED", "reduce-size": "CAUTION",
                     "skip": "SKIP", "no-opinion": "PROCEED"}.get(
        macro["recommendation"], "PROCEED")
    final = max((rule["verdict"], macro_verdict),
                key=lambda v: {"PROCEED": 0, "CAUTION": 1, "SKIP": 2}[v])

    top_concern = (macro["top_concerns"] or [{}])[0].get("description", "")
    if not top_concern and rule["alerts"]:
        top_concern = rule["alerts"][0]
    if not top_concern:
        top_concern = "no concerns above threshold"

    return {
        "verdict": final,
        "risk_score": macro["risk_score"],
        "severity": macro["severity"],
        "top_concern": top_concern[:160],
        "alerts": rule["alerts"][:3],
        "regime": regime,
    }


def _build() -> dict[str, Any]:
    """Compute the panel block from current state. No I/O caching here."""
    payload = _orb_payload()
    age_h = _orb_age_hours(payload)
    cur_p = _yahoo_nq_price()
    handoff = _oh.classify(payload=payload, age_hours=age_h, current_price=cur_p)

    regime = ((payload or {}).get("regime") or "UNKNOWN").upper()
    signals = _collect_signals()
    snapshot = {
        "regime": regime,
        "orb_strategy_code": (payload or {}).get("strategy_code"),
        "orb_handoff_status": handoff["status"],
        "account": {},  # brief deliberately ignores live account at 05:30 UTC
        "calendar": {"next_high_impact_min": None,
                     "next_high_impact_event": None,
                     "upcoming_events": []},
        "market": {"vix_level": signals.get("vix_level")},
    }

    per_strategy: dict[str, Any] = {}
    for strat in STRATEGIES:
        try:
            per_strategy[strat] = _shape_per_strategy(strat, regime, signals, snapshot)
        except Exception as exc:
            log.warning("trade_guard_daily strategy %s failed: %s", strat, exc)
            per_strategy[strat] = {
                "verdict": "—", "risk_score": None, "severity": "—",
                "top_concern": f"computation error: {exc.__class__.__name__}",
                "alerts": [], "regime": regime,
            }

    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "per_strategy": per_strategy,
        "orb_handoff": {
            "status": handoff["status"],
            "verdict": handoff["verdict"],
            "age_h": handoff["age_h"],
            "price_drift_pct": handoff["price_drift_pct"],
            "next_action": handoff["next_action"],
        },
        "signals_present": sorted(signals.keys()),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "trade_guard.deterministic",
        "status": "ok" if signals else "warn",
    }


def _cache_path(date: str) -> Path:
    return CACHE_DIR / f"{date}.json"


def fetch() -> dict[str, Any]:
    """Builder entry point. Returns the panel dict, using on-disk cache."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache = _cache_path(today)
    if cache.exists():
        try:
            age = time.time() - cache.stat().st_mtime
            if age < CACHE_TTL_SEC:
                return json.loads(cache.read_text())
        except Exception:
            pass

    block = _build()
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(block, ensure_ascii=False, indent=2))
    except Exception as exc:
        log.warning("trade_guard_daily cache write failed: %s", exc)
    return block


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    if args.no_cache:
        block = _build()
    else:
        block = fetch()
    print(json.dumps(block, indent=2, ensure_ascii=False))
