"""Lead headline rotation: varies by day and never contradicts its own numbers."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import headlines

ET = ZoneInfo("America/New_York")


def _pre(expansion: str, p50: float, norm: float) -> dict:
    return {
        "instruments": {
            "MNQ": {
                "expansion": expansion,
                "expected_range_pts": {"p50": p50},
                "median26d_pts": norm,
                "yesterday_pts": 300.0,
                "contraction_prob": {"p_wide": 0.5},
            },
            "MGC": {"expansion": "CONTRACTION", "expected_range_pts": {"p50": 80.0}},
        }
    }


def _heads(pre: dict, days: int = 30) -> list[str]:
    start = datetime(2026, 9, 29, 6, tzinfo=ET)
    return [
        headlines.compose({}, {}, pre, {}, {}, now=start + timedelta(days=i))["lead"]["headline"]
        for i in range(days)
    ]


def test_no_call_rotates_daily():
    heads = _heads(_pre("NO CALL", 360, 400))
    assert len(set(heads)) >= 8
    assert all(a != b for a, b in zip(heads, heads[1:]))


def test_wide_headline_never_quotes_a_below_norm_forecast():
    # WIDE call with p50 under the norm: the "above norm" templates must be skipped.
    for h in _heads(_pre("EXPANSION", 360, 400)):
        assert "OUTGROW" not in h and "ROOM TO RUN" not in h


def test_empty_feed_still_prints_a_headline():
    h = headlines.compose({}, {}, {}, {}, {}, now=datetime(2026, 9, 30, 6, tzinfo=ET))
    assert h["lead"]["headline"]
    assert "{" not in h["lead"]["headline"]
