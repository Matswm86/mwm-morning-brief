"""MGC/Gold regime — derived from Yahoo MGC=F bars, no detector service.

The NQ regime comes from Market Detector v3 (its own systemd timers). No
such detector exists for gold, so this module computes an honest, purely
price-derived outlook from 5 days of 5-minute bars: trend vs EMA20,
ATR-based volatility tier, prior-day and overnight levels. It feeds
brief.regimes.MGC for the Instrument Outlook card and is labelled as
bar-derived so nobody mistakes it for the NQ detector.

Schema matches what web/assets/outlook.js reads:
  tier, tier_caption, regime, score, direction, direction_confidence,
  volatility, generated_at, levels {pdh, pdl, on_high, on_low}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fetchers import bars as f_bars

log = logging.getLogger("morning-brief.regime_derived")

ET = ZoneInfo("America/New_York")
DEFAULT_SYMBOL = "MGC=F"
EMA_N = 20
ATR_N = 14
SLOPE_BARS = 12  # 1h of 5m bars


def _ema(values: list[float], n: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _atr(bars: list[dict], n: int) -> list[float]:
    trs = []
    for i, b in enumerate(bars):
        if i == 0:
            trs.append(b["high"] - b["low"])
            continue
        pc = bars[i - 1]["close"]
        trs.append(max(b["high"] - b["low"], abs(b["high"] - pc), abs(b["low"] - pc)))
    return _ema(trs, n)


def _levels(bars: list[dict]) -> dict:
    """Prior-ET-day high/low + overnight (18:00 ET yesterday → 09:30 ET) range."""
    by_day: dict[str, list[dict]] = {}
    for b in bars:
        d = datetime.fromtimestamp(b["time"], tz=ET)
        by_day.setdefault(d.strftime("%Y-%m-%d"), []).append(b)
    days = sorted(by_day)
    out: dict[str, float] = {}
    if len(days) >= 2:
        prior = by_day[days[-2]]
        out["pdh"] = max(b["high"] for b in prior)
        out["pdl"] = min(b["low"] for b in prior)
        out["_pdc"] = prior[-1]["close"]  # prior-day close, for day-change; stripped before display
    now_et = datetime.now(ET)
    on_bars = []
    for b in bars:
        d = datetime.fromtimestamp(b["time"], tz=ET)
        days_back = (now_et.date() - d.date()).days
        started_overnight = (days_back == 1 and d.hour >= 18) or days_back == 0
        before_rth = not (d.date() == now_et.date() and (d.hour, d.minute) >= (9, 30))
        if started_overnight and before_rth:
            on_bars.append(b)
    if on_bars:
        out["on_high"] = max(b["high"] for b in on_bars)
        out["on_low"] = min(b["low"] for b in on_bars)
    return out


def fetch(symbol: str = DEFAULT_SYMBOL) -> dict:
    payload = f_bars.fetch(symbol, "5m", "5d")
    bars = [b for b in payload["bars"] if b.get("high") is not None and b.get("low") is not None]
    if len(bars) < EMA_N + SLOPE_BARS:
        return _empty(symbol, f"only {len(bars)} bars")

    closes = [b["close"] for b in bars]
    ema = _ema(closes, EMA_N)
    atr = _atr(bars, ATR_N)

    last = closes[-1]
    ema_now, ema_then = ema[-1], ema[-1 - SLOPE_BARS]
    slope_pct = (ema_now - ema_then) / ema_then * 100.0
    dist_pct = (last - ema_now) / ema_now * 100.0

    levels = _levels(bars)
    # payload["prev_close"] over a 5d range is the close five days back —
    # use the prior ET day's last bar instead.
    prev_close = levels.pop("_pdc", None) or payload.get("prev_close") or closes[0]
    day_chg_pct = (last - prev_close) / prev_close * 100.0

    atr_hist = sorted(a for a in atr[EMA_N:] if a > 0)
    atr_med = atr_hist[len(atr_hist) // 2] if atr_hist else 0.0
    atr_ratio = (atr[-1] / atr_med) if atr_med else 1.0
    volatility = "high" if atr_ratio >= 1.5 else "low" if atr_ratio <= 0.7 else "medium"

    up = slope_pct > 0.02 and dist_pct > 0
    down = slope_pct < -0.02 and dist_pct < 0
    strength = min(1.0, abs(slope_pct) / 0.15 * 0.6 + min(abs(day_chg_pct) / 1.0, 1.0) * 0.4)
    if up:
        direction, regime = "long bias", "trend up"
    elif down:
        direction, regime = "short bias", "trend down"
    else:
        direction, regime = "chop", "range / chop"
        strength = min(strength, 0.35)

    score = round(strength * 100)
    tier = "A" if strength >= 0.65 else "B" if strength >= 0.35 else "C"
    return {
        "tier": tier,
        "tier_caption": f"{regime} {score}%",
        "regime": regime,
        "score": score,
        "direction": direction,
        "direction_confidence": round(0.3 + 0.6 * strength, 2),
        "volatility": volatility,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "levels": {k: round(v, 1) for k, v in levels.items()},
        "source": f"derived: yahoo {symbol} 5m bars (EMA20 trend + ATR14 vol)",
        "raw": {
            "slope_pct_1h": round(slope_pct, 4),
            "dist_from_ema_pct": round(dist_pct, 4),
            "day_change_pct": round(day_chg_pct, 3),
            "atr_ratio": round(atr_ratio, 2),
        },
    }


def _empty(symbol: str, reason: str) -> dict:
    return {
        "tier": None, "tier_caption": f"no data: {reason}", "regime": None,
        "score": None, "direction": "—", "direction_confidence": 0,
        "volatility": "—",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "levels": {}, "source": f"derived: yahoo {symbol}", "raw": {},
    }
