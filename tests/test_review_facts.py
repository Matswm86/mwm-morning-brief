"""The analyst column must never contradict the session table it was given.

Every case here is the real 2026-10-20 incident: the Groq free tier returned 429
on qwen/qwen3.8-27b three times, the lane silently fell back to
openai/gpt-oss-20b, and that weaker model wrote "MNQ fell 1.11%" for a session
the table records as +1.13%. It reached the validator only because the model
also omitted the "---" separator, so the copy was rejected on a formatting
technicality rather than on being wrong.
"""

from fetchers.review import _fact_conflicts

FACTS = {
    "yesterday": {
        "weekday": "Monday",
        "date": "2026-10-19",
        "mnq": {"move_pct": 1.13, "range_pts": 757.5},
        "mgc": {"move_pct": -0.49, "range_pts": 35.0},
        "mattered": True,
        "stories": [],
    },
    "week": [],
}


def test_clean_copy_passes():
    good = (
        "MNQ rose 1.13% on Monday with a 757.5-point range. "
        "MGC fell 0.49%, and nothing on the wire explained either move."
    )
    assert _fact_conflicts(good, FACTS) == []


def test_inverted_direction_is_caught():
    bad = "MNQ fell 1.13% on Monday. MGC slipped 0.49% on safe-haven demand."
    out = _fact_conflicts(bad, FACTS)
    assert any("says down" in c and c.startswith("MNQ") for c in out), out


def test_wrong_magnitude_is_caught():
    """The exact 2026-10-20 failure: 1.11% written for a 1.13% session."""
    bad = "MNQ fell 1.11% on Monday. MGC slipped 0.49%."
    out = _fact_conflicts(bad, FACTS)
    assert any("none of" in c and c.startswith("MNQ") for c in out), out


def test_a_near_match_does_not_satisfy_the_exact_number_rule():
    """1.1 must not be accepted as a match for 1.13 by way of rounding."""
    bad = "MNQ rose 1.1% on Monday. MGC fell 0.49%."
    out = _fact_conflicts(bad, FACTS)
    assert any("none of" in c and c.startswith("MNQ") for c in out), out


def test_inverted_gold_is_caught():
    bad = "MNQ rose 1.13%. Gold gained 0.49% on safe-haven demand."
    out = _fact_conflicts(bad, FACTS)
    assert any(c.startswith("MGC") and "says up" in c for c in out), out


def test_a_trailing_zero_value_accepts_the_short_form():
    facts = {
        "yesterday": {"mnq": {"move_pct": 1.10}, "mgc": {"move_pct": -0.40}},
        "week": [],
    }
    assert _fact_conflicts("MNQ rose 1.1% and MGC fell 0.4%.", facts) == []


def test_a_flat_session_is_not_a_direction_conflict():
    facts = {
        "yesterday": {"mnq": {"move_pct": 0.0}, "mgc": {"move_pct": 0.0}},
        "week": [],
    }
    assert _fact_conflicts("MNQ closed unchanged at 0.00%. MGC was flat at 0.00%.", facts) == []


def test_a_missing_instrument_is_reported_not_ignored():
    out = _fact_conflicts("Gold was quiet yesterday and nothing else moved.", FACTS)
    assert any(c.startswith("MNQ") for c in out), out
