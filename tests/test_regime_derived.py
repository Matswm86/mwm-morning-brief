"""Regression tests for the derived MNQ/MGC regime block.

Pins the 2026-08-21 defect: a +1.00% up day was certifying a "trend down 100%"
call because the confidence term used |day_change| with no sign check.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from fetchers import regime_derived as rd

ET = ZoneInfo("America/New_York")


def _bars(closes: list[float], start_et: dt.datetime, spread: float = 1.0) -> list[dict]:
    """5m bars from a close path; high/low bracket each close by `spread`."""
    return [
        {
            "time": int((start_et + dt.timedelta(minutes=5 * i)).timestamp()),
            "open": c,
            "high": c + spread,
            "low": c - spread,
            "close": c,
        }
        for i, c in enumerate(closes)
    ]


def _run(bars: list[dict], monkeypatch) -> dict:
    monkeypatch.setattr(rd.f_bars, "fetch", lambda *a, **k: {"bars": bars, "prev_close": bars[0]["close"]})
    return rd.fetch("TEST=F")


def test_up_day_never_certifies_a_down_trend(monkeypatch):
    """The exact live shape: 1h slope down, day change strongly up.

    Old code returned regime='trend down', score=100, confidence=0.9.
    """
    start = dt.datetime(2026, 8, 20, 18, 0, tzinfo=ET)
    # Day one: flat base so the prior-day close is well defined.
    day1 = _bars([100.0] * 80, start)
    # Day two: rallies hard off the prior close, then pulls back over the last hour.
    start2 = dt.datetime(2026, 8, 21, 4, 0, tzinfo=ET)
    up_leg = [100.0 + 0.03 * i for i in range(60)]      # to ~101.8
    pullback = [up_leg[-1] - 0.02 * i for i in range(20)]  # last hour drifts down
    day2 = _bars(up_leg + pullback, start2)
    out = _run(day1 + day2, monkeypatch)

    assert out["raw"]["day_change_pct"] > 0.5, out["raw"]
    assert out["raw"]["slope_pct_1h"] < 0, out["raw"]
    assert out["regime"] != "trend down", f"up day still labelled {out['tier_caption']}"
    assert out["direction"] != "short bias"
    assert out["score"] <= 35, out["tier_caption"]
    assert out["raw"]["day_conflict"] is True


def test_agreeing_day_and_slope_still_scores_high(monkeypatch):
    start = dt.datetime(2026, 8, 20, 18, 0, tzinfo=ET)
    day1 = _bars([100.0] * 80, start)
    start2 = dt.datetime(2026, 8, 21, 4, 0, tzinfo=ET)
    day2 = _bars([100.0 + 0.03 * i for i in range(80)], start2)
    out = _run(day1 + day2, monkeypatch)

    assert out["regime"] == "trend up", out["tier_caption"]
    assert out["raw"]["day_conflict"] is False
    assert out["score"] >= 65, out["tier_caption"]
    assert out["direction"] == "long bias"


def test_down_day_with_down_slope_is_a_down_trend(monkeypatch):
    start = dt.datetime(2026, 8, 20, 18, 0, tzinfo=ET)
    day1 = _bars([100.0] * 80, start)
    start2 = dt.datetime(2026, 8, 21, 4, 0, tzinfo=ET)
    day2 = _bars([100.0 - 0.03 * i for i in range(80)], start2)
    out = _run(day1 + day2, monkeypatch)

    assert out["regime"] == "trend down", out["tier_caption"]
    assert out["direction"] == "short bias"
    assert out["score"] >= 65


def test_strength_is_bounded(monkeypatch):
    """Slope term alone used to be unbounded before the final min()."""
    start = dt.datetime(2026, 8, 20, 18, 0, tzinfo=ET)
    day1 = _bars([100.0] * 80, start)
    start2 = dt.datetime(2026, 8, 21, 4, 0, tzinfo=ET)
    day2 = _bars([100.0 + 0.5 * i for i in range(80)], start2)
    out = _run(day1 + day2, monkeypatch)
    assert 0 <= out["score"] <= 100
    assert 0.3 <= out["direction_confidence"] <= 0.9


def test_volatility_baseline_is_phase_matched(monkeypatch):
    """Overnight bars must not set the RTH baseline (and vice versa)."""
    start = dt.datetime(2026, 8, 18, 0, 0, tzinfo=ET)
    closes = []
    for i in range(1200):
        t = start + dt.timedelta(minutes=5 * i)
        et = t.astimezone(ET)
        rth = (9, 30) <= (et.hour, et.minute) < (16, 0)
        closes.append(100.0 + (i % 2) * (3.0 if rth else 0.2))
    bars = _bars(closes, start, spread=0.05)
    monkeypatch.setattr(rd.f_bars, "fetch", lambda *a, **k: {"bars": bars, "prev_close": 100.0})
    out = rd.fetch("TEST=F")
    assert out["raw"]["vol_basis"].startswith("phase-matched"), out["raw"]["vol_basis"]
    # A synthetic session that is identical every day must not read as high vol.
    assert out["volatility"] == "medium", out["raw"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
