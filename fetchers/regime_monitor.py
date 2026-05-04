"""Long-term regime monitor — SPX trend, VIX + term structure, credit,
yield curve → classifies macro regime + strategy-edge badge.

Motivation: iFVG+LiqSweep backtests disintegrated pre-2018. The tripwires
here flag when the current regime looks structurally similar to that
period so the user can drop size or pause the strategy.

Sources (all free):
  - FRED:  VIXCLS (spot VIX daily since 1990), BAMLH0A0HYM2 (HY OAS),
           T10Y2Y (10y-2y spread)
  - Yahoo: ^GSPC (SPX for trend + realized vol), ^VIX3M (term structure)

Output: web/regime.json — consumed by web/assets/regime.js +
web/assets/vix_chart.js.

Usage:
  python3 -m fetchers.regime_monitor --write web/regime.json
  python3 -m fetchers.regime_monitor --stdout         # debug
"""
from __future__ import annotations
import argparse
import json
import logging
import math
import statistics
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from config import FRED_API_KEY
from http_util import get_json

log = logging.getLogger("morning-brief.regime_monitor")

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

VIX_HISTORY_START = "2012-01-01"   # matches brief-era chart shading
VIX_TRIPWIRE_DAYS = 5
VIX_TRIPWIRE_LEVEL = 25.0
HY_WIDE_THRESHOLD = 5.0            # OAS % (500 bps)
SMA_TREND_SLOPE_WINDOW = 20        # bars to measure slope direction

STRATEGY_ERA_START = "2018-03-01"  # iFVG+LiqSweep validated era


# ----- FRED --------------------------------------------------------

def _fred_series(sid: str, start: str | None = None,
                 retries: int = 3) -> list[tuple[str, float]]:
    if not FRED_API_KEY:
        log.warning("FRED_API_KEY missing — skipping %s", sid)
        return []
    params = {
        "series_id": sid,
        "api_key": FRED_API_KEY,
        "file_type": "json",
    }
    if start:
        params["observation_start"] = start
    # FRED returns transient 5xx during midnight UTC maintenance windows.
    # Retry with backoff before giving up — see 2026-04-30 incident where
    # VIXCLS+HYOAS both 500'd at 22:00 UTC and emptied the regime panel.
    data = None
    for attempt in range(retries):
        data = get_json(FRED_BASE, params=params, timeout=20)
        if data and "observations" in data:
            break
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    if not data or "observations" not in data:
        return []
    out: list[tuple[str, float]] = []
    for obs in data["observations"]:
        v = obs.get("value", ".")
        if v in (".", None, ""):
            continue
        try:
            out.append((obs["date"], float(v)))
        except (ValueError, TypeError):
            continue
    return out


# ----- Yahoo -------------------------------------------------------

def _yahoo_daily(symbol: str, range_: str = "1y") -> list[tuple[int, float]]:
    """Returns [(epoch_sec, close), ...] sorted ascending."""
    data = get_json(
        YAHOO_BASE.format(sym=symbol),
        params={"interval": "1d", "range": range_, "includePrePost": "false"},
        timeout=20,
    )
    if not data:
        return []
    try:
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        c = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return []
    out: list[tuple[int, float]] = []
    for t, px in zip(ts, c):
        if px is None:
            continue
        out.append((int(t), float(px)))
    return out


# ----- Computation -------------------------------------------------

def _sma(vals: list[float], window: int) -> float | None:
    if len(vals) < window:
        return None
    return sum(vals[-window:]) / window


def _slope_state(vals: list[float], window: int = SMA_TREND_SLOPE_WINDOW) -> str:
    if len(vals) < window + 1:
        return "flat"
    recent = vals[-1]
    prior = vals[-1 - window]
    pct = (recent - prior) / prior * 100 if prior else 0
    if pct > 0.5:
        return "rising"
    if pct < -0.5:
        return "falling"
    return "flat"


def _realized_vol_20d(closes: list[float]) -> float | None:
    if len(closes) < 21:
        return None
    window = closes[-21:]
    rets = [math.log(window[i] / window[i - 1]) for i in range(1, len(window))]
    try:
        s = statistics.stdev(rets)
    except statistics.StatisticsError:
        return None
    return s * math.sqrt(252) * 100  # annualized %


def _trend_block(spx_bars: list[tuple[int, float]]) -> dict:
    closes = [c for _, c in spx_bars]
    last = closes[-1] if closes else None
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    above50 = last is not None and sma50 is not None and last > sma50
    above200 = last is not None and sma200 is not None and last > sma200

    # Compute 50DMA slope over last 20d
    sma50_series = [
        sum(closes[i - 50 + 1: i + 1]) / 50 for i in range(49, len(closes))
    ] if len(closes) >= 50 else []
    slope = _slope_state(sma50_series) if sma50_series else "flat"

    if above50 and above200 and slope == "rising":
        state = "uptrend"
    elif not above50 and not above200 and slope == "falling":
        state = "downtrend"
    elif above200 and not above50:
        state = "pullback"
    elif not above200 and above50:
        state = "bounce"
    else:
        state = "range"

    return {
        "spx_last": round(last, 2) if last else None,
        "sma50": round(sma50, 2) if sma50 else None,
        "sma200": round(sma200, 2) if sma200 else None,
        "above_50": above50,
        "above_200": above200,
        "sma50_slope": slope,
        "state": state,
    }


def _vol_block(vix_history: list[tuple[str, float]],
               spx_bars: list[tuple[int, float]],
               vix3m_bars: list[tuple[int, float]]) -> dict:
    vix_last = vix_history[-1][1] if vix_history else None

    rv = _realized_vol_20d([c for _, c in spx_bars])
    ratio = (vix_last / rv) if (vix_last and rv) else None
    if ratio is None:
        tone = "—"
    elif ratio >= 1.4:
        tone = "fear premium"
    elif ratio <= 0.95:
        tone = "complacency"
    else:
        tone = "neutral"

    vix3m = vix3m_bars[-1][1] if vix3m_bars else None
    ts_ratio = (vix_last / vix3m) if (vix_last and vix3m) else None
    if ts_ratio is None:
        ts_state = "—"
    elif ts_ratio > 1.0:
        ts_state = "backwardation"
    else:
        ts_state = "contango"

    # Consecutive days VIX above tripwire (from tail of full history)
    above = 0
    for _, v in reversed(vix_history):
        if v >= VIX_TRIPWIRE_LEVEL:
            above += 1
        else:
            break

    return {
        "vix_spot": round(vix_last, 2) if vix_last else None,
        "rv_20d": round(rv, 2) if rv else None,
        "ratio": round(ratio, 2) if ratio else None,
        "tone": tone,
        "term_structure": {
            "vix": round(vix_last, 2) if vix_last else None,
            "vix3m": round(vix3m, 2) if vix3m else None,
            "ratio": round(ts_ratio, 3) if ts_ratio else None,
            "state": ts_state,
        },
        "vix_days_above_25": above,
    }


def _credit_block(hy_series: list[tuple[str, float]],
                  t10y2y_series: list[tuple[str, float]]) -> dict:
    hy_last = hy_series[-1][1] if hy_series else None
    hy_1mo_ago = None
    if hy_series:
        cutoff = (datetime.strptime(hy_series[-1][0], "%Y-%m-%d")
                  - timedelta(days=30))
        for d, v in reversed(hy_series):
            if datetime.strptime(d, "%Y-%m-%d") <= cutoff:
                hy_1mo_ago = v
                break
    delta_1mo = (hy_last - hy_1mo_ago) if (hy_last and hy_1mo_ago) else None

    if delta_1mo is None:
        direction = "—"
    elif delta_1mo > 0.1:
        direction = "widening"
    elif delta_1mo < -0.1:
        direction = "tightening"
    else:
        direction = "flat"

    t10y2y_last = t10y2y_series[-1][1] if t10y2y_series else None
    inverted = (t10y2y_last is not None and t10y2y_last < 0)

    return {
        "hy_oas": round(hy_last, 2) if hy_last else None,
        "hy_oas_1mo_ago": round(hy_1mo_ago, 2) if hy_1mo_ago else None,
        "delta_1mo": round(delta_1mo, 3) if delta_1mo is not None else None,
        "direction": direction,
        "t10y2y": round(t10y2y_last, 2) if t10y2y_last else None,
        "inverted": inverted,
    }


def _tripwires(trend: dict, vol: dict, credit: dict) -> dict:
    vix_25 = vol.get("vix_days_above_25", 0) >= VIX_TRIPWIRE_DAYS
    vix_bw = vol.get("term_structure", {}).get("state") == "backwardation"
    hy_wide = (
        credit.get("hy_oas") is not None
        and credit["hy_oas"] >= HY_WIDE_THRESHOLD
        and credit.get("direction") == "widening"
    )
    curve = (
        credit.get("inverted")
        and trend.get("above_200") is False
    )
    active = int(vix_25) + int(vix_bw) + int(hy_wide) + int(curve)

    if active >= 3:
        flag = "red"
    elif active == 2:
        flag = "amber"
    elif active == 1:
        flag = "amber"
    else:
        flag = "green"

    return {
        "vix_25_5d": vix_25,
        "vix_backwardated": vix_bw,
        "hy_wide_and_widening": hy_wide,
        "curve_inv_below_200sma": curve,
        "count_active": active,
        "edge_flag": flag,
    }


def _verdict(trend: dict, vol: dict, credit: dict, tripwires: dict) -> dict:
    above50 = trend.get("above_50")
    above200 = trend.get("above_200")
    ts = vol.get("term_structure", {}).get("state")
    vix = vol.get("vix_spot") or 0
    hy_dir = credit.get("direction")
    inverted = credit.get("inverted")

    if above200 and above50 and ts == "contango" and vix < 20 and hy_dir != "widening":
        regime = "Bull · Low-Vol"
    elif above200 and above50 and (vix >= 20 or ts == "backwardation"):
        regime = "Bull · Volatile"
    elif not above200 and ts == "backwardation" and (hy_dir == "widening" or inverted):
        regime = "Bear · Stress"
    elif above200 and not above50 or (vix >= 25 and hy_dir == "widening"):
        regime = "Transition · Fragility"
    elif not above200 and not above50:
        regime = "Bear · Stress"
    else:
        regime = "Mixed"

    parts = []
    parts.append("above" if above50 else "below")
    parts.append("50d,")
    parts.append("above" if above200 else "below")
    parts.append("200d;")
    parts.append(f"VIX {vix:.1f} ({ts});")
    parts.append(f"HY {hy_dir};")
    parts.append("curve inverted" if inverted else "curve positive")
    rationale = " ".join(parts)

    return {
        "regime": regime,
        "strategy_edge": tripwires["edge_flag"],
        "rationale": rationale,
    }


# ----- Main --------------------------------------------------------

def fetch() -> dict:
    log.info("regime_monitor: pulling FRED + Yahoo ...")

    vix_history = _fred_series("VIXCLS", start=VIX_HISTORY_START)
    now_utc = datetime.now(timezone.utc)
    hy_series = _fred_series("BAMLH0A0HYM2",
                             start=(now_utc - timedelta(days=90)).strftime("%Y-%m-%d"))
    t10y2y_series = _fred_series("T10Y2Y",
                                 start=(now_utc - timedelta(days=14)).strftime("%Y-%m-%d"))

    spx_bars = _yahoo_daily("^GSPC", range_="1y")
    vix3m_bars = _yahoo_daily("^VIX3M", range_="1mo")

    trend = _trend_block(spx_bars)
    vol = _vol_block(vix_history, spx_bars, vix3m_bars)
    credit = _credit_block(hy_series, t10y2y_series)
    tripwires = _tripwires(trend, vol, credit)
    verdict = _verdict(trend, vol, credit, tripwires)

    vix_chart = [
        {"time": _iso_to_epoch(d), "value": round(v, 2)}
        for d, v in vix_history
        if v is not None
    ]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy_era_start": STRATEGY_ERA_START,
        "trend": trend,
        "vol": vol,
        "credit": credit,
        "tripwires": tripwires,
        "verdict": verdict,
        "vix_history": vix_chart,
    }


def _iso_to_epoch(date_str: str) -> int:
    return int(datetime.strptime(date_str, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp())


def _load_prior(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _merge_with_prior(payload: dict, prior: dict | None) -> dict:
    """If the live FRED fetch dropped VIX (transient 5xx), keep the prior
    regime.json's vix_history / vix_spot / credit blocks rather than
    overwriting brief.mwmai.no with empties. Trend (Yahoo SPX) and
    Yahoo VIX3M term-structure remain authoritative because Yahoo
    didn't fail — only FRED did.
    """
    if not prior:
        return payload
    new_vix = payload.get("vix_history") or []
    if not new_vix and prior.get("vix_history"):
        payload["vix_history"] = prior["vix_history"]
        log.warning("regime_monitor: VIXCLS empty — preserved prior vix_history (%d bars)",
                    len(prior["vix_history"]))
    # If vol.vix_spot is None but prior has one, splice prior vol back in.
    vol = payload.get("vol") or {}
    if vol.get("vix_spot") is None and (prior.get("vol") or {}).get("vix_spot") is not None:
        # Keep the live RV20/term-structure from Yahoo, but restore VIX spot
        # + tone + ratio from the last-good FRED snapshot.
        prior_vol = prior["vol"]
        for k in ("vix_spot", "ratio", "tone", "vix_days_above_25"):
            if vol.get(k) in (None, "—") and prior_vol.get(k) is not None:
                vol[k] = prior_vol[k]
        # Patch term_structure.vix (FRED-derived) if missing.
        ts = vol.get("term_structure") or {}
        prior_ts = prior_vol.get("term_structure") or {}
        if ts.get("vix") is None and prior_ts.get("vix") is not None:
            ts["vix"] = prior_ts["vix"]
            # Recompute ratio/state if vix3m is present in current payload.
            if ts.get("vix3m"):
                ts_ratio = ts["vix"] / ts["vix3m"]
                ts["ratio"] = round(ts_ratio, 3)
                ts["state"] = "backwardation" if ts_ratio > 1.0 else "contango"
        vol["term_structure"] = ts
        payload["vol"] = vol
        log.warning("regime_monitor: VIX spot missing — preserved prior vol block")
    # If credit (HY OAS) failed, splice prior credit.
    credit = payload.get("credit") or {}
    if credit.get("hy_oas") is None and (prior.get("credit") or {}).get("hy_oas") is not None:
        # Keep curve fields from current; restore HY fields from prior.
        prior_credit = prior["credit"]
        for k in ("hy_oas", "hy_oas_1mo_ago", "delta_1mo", "direction"):
            if credit.get(k) in (None, "—") and prior_credit.get(k) is not None:
                credit[k] = prior_credit[k]
        payload["credit"] = credit
        log.warning("regime_monitor: HY OAS missing — preserved prior credit block")
    # Recompute tripwires + verdict from the merged blocks so the panel
    # stays consistent.
    payload["tripwires"] = _tripwires(payload["trend"], payload["vol"], payload["credit"])
    payload["verdict"] = _verdict(payload["trend"], payload["vol"], payload["credit"],
                                   payload["tripwires"])
    return payload


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", type=Path,
                    default=Path(__file__).resolve().parents[1] / "web" / "regime.json")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    payload = fetch()
    prior = _load_prior(args.write)
    payload = _merge_with_prior(payload, prior)
    if args.stdout:
        print(json.dumps(payload, indent=2))
        return 0
    _write(args.write, payload)
    log.info(
        "wrote regime.json — regime=%s edge=%s tripwires=%d vix=%s",
        payload["verdict"]["regime"],
        payload["verdict"]["strategy_edge"],
        payload["tripwires"]["count_active"],
        payload["vol"].get("vix_spot"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
