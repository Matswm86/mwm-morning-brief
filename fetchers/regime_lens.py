"""Regime Lens v1 object for the brief: the 09:25 ET (15:25 Oslo) pre-open read.

Reads data/cockpit/regime_lens.json, written by
projects/mwm-trading/research/regime-lens/live_producer.py on a systemd timer at
09:26 ET. Nothing is fitted here. Two pre-registered survivors only:

  vol_regime  Target B, next-RTH range above/below the trailing-20d median.
              65.2% over 5y vs 58.9% persistence; 67.2% on a frozen forward test.
  dol_draw    Target C', which of PDH / PDL is touched FIRST during RTH.
              87.4% on decided days (5y, n=1120 of 1246 = 89.9% of sessions).

Trend/chop and direction are structurally absent from the artifact: both were
measured null (E 54.3%, D 49.7%) and are not emitted.

HONESTY REQUIREMENT, enforced here rather than left to the panel. The 87.4%
headline is a measurement artifact, found 2026-08-22 by sweep_quality.py: on
494 of 1256 judgment-window sessions (39.3%) price at 09:24 already sits BEYOND
PDH or PDL, so that level is touched the instant RTH opens and "first touch" is
settled before the session starts. Those days score 99.8% and drag the headline
up. On the sessions where price sits BETWEEN the two levels the same rule scores
77.6% (n=635 decided, 90% CI 74.8-80.2), unconditional 64.7%.

This fetcher emits NO CALL when today is one of the already-decided sessions,
and quotes 77.6% and never 87.4% when it does call.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("morning-brief.lens")

_ROOT = Path(os.environ.get("MWM_AI_ROOT", Path.home() / "MWM"))  # ~/MWM-AI is gone on this box
SRC = _ROOT / "data" / "cockpit" / "regime_lens.json"
STALE_HOURS = 20.0

# Measured on the locked 5y judgment window (dol_geometry.json, judge_5y).
ACC_INSIDE_5Y = 0.776        # n=635 decided, price between PDL and PDH at 09:24
ACC_INSIDE_CI90 = [0.748, 0.802]
ACC_INSIDE_N = 635
ACC_INSIDE_UNCOND = 0.647    # counting inside sessions that never touch either
P_INSIDE = 0.607             # 762 of 1256 sessions are callable at all
ACC_HEADLINE_ARTIFACT = 0.8741   # provenance only, never quoted as the rate


def _vol_block(d: dict) -> dict:
    v = d.get("vol_regime") or {}
    if not v:
        return {"status": "unavailable"}
    p, thr = v.get("p_high_range"), v.get("threshold")
    emp = v.get("confidence_empirical") or {}
    return {
        "status": "ok",
        "call": "WIDE" if v.get("pred_high_range") else "NARROW",
        "meaning": (
            "today's RTH range lands ABOVE the trailing-20-session median"
            if v.get("pred_high_range")
            else "today's RTH range lands BELOW the trailing-20-session median"
        ),
        "p_high_range": p,
        "threshold": thr,
        "edge": round(abs(p - thr), 3) if p is not None and thr is not None else None,
        "bucket_hit_rate": emp.get("hit_rate"),
        "bucket_n": emp.get("n"),
        "bucket_ci90": emp.get("ci90"),
        "bucket_rank": emp.get("bucket_rank"),
        "track_record": {"hit_rate": 0.652, "years": 5},
    }


def _dol_block(d: dict) -> dict:
    g = (d.get("dol") or {}).get("dol_draw_bias") or d.get("dol_draw_bias") or {}
    if not g:
        return {"status": "unavailable"}
    px, pdh, pdl = g.get("px_0924"), g.get("pdh"), g.get("pdl")
    # Recomputed here rather than trusted from the artifact, so an older producer
    # that predates the guard still gets filtered instead of publishing a number.
    inside = g.get("inside_prior_range")
    if inside is None and None not in (px, pdh, pdl):
        inside = bool(pdl < px < pdh)
    call = g.get("draw_call_nearer_level") if inside else None
    out = {
        "status": "ok",
        "callable": bool(inside),
        "call": call,
        "state_0924": g.get("state_0924"),
        "pdh": pdh,
        "pdl": pdl,
        "px_0924": px,
        "dist_pdh_atr": g.get("dist_pdh_atr"),
        "dist_pdl_atr": g.get("dist_pdl_atr"),
        "acc_inside_5y": ACC_INSIDE_5Y,
        "acc_inside_ci90": ACC_INSIDE_CI90,
        "acc_inside_n": ACC_INSIDE_N,
        "acc_uncond": ACC_INSIDE_UNCOND,
        "p_callable": P_INSIDE,
    }
    # 2026-09-23: the nearer-level rate equals what a random walk predicts from the
    # two distances alone (77.8% vs 77.8%, n=631 inside-range days, 2021-26), so the
    # card is geometry, not a read of the market. The producer now publishes that
    # random-walk probability for today (dol_draw_bias.geometry.p_called_first).
    geo = g.get("geometry") or {}
    geo_p = geo.get("p_called_first") if inside else None
    out["geometry_p"] = geo_p
    if inside:
        out["meaning"] = f"{call} is touched before {'PDL' if call == 'PDH' else 'PDH'} during RTH"
        today = (
            f"From the two distances alone a random walk puts it at {geo_p:.0%} today. "
            if isinstance(geo_p, (int, float))
            else ""
        )
        out["basis"] = (
            f"{today}Over five years the nearer level came first {ACC_INSIDE_5Y:.0%} of "
            "the time, the same rate a random walk gives, so this is distance "
            "geometry, not a read of the market."
        )
    else:
        side = "PDH" if (px is not None and pdh is not None and px >= pdh) else "PDL"
        out["meaning"] = "NO CALL"
        out["no_call_reason"] = g.get("no_call_reason") or (
            f"price already sits beyond {side} at 09:24, so {side} is touched at the "
            "open and the call is settled before the session starts"
        )
        out["basis"] = (
            "Price opened past one of the levels, so today's answer is fixed before "
            "the bell. No call on days like this."
        )
    return out


def fetch() -> dict:
    if not SRC.exists():
        return {"status": "unavailable", "error": f"no artifact at {SRC}"}
    try:
        d = json.loads(SRC.read_text())
    except (OSError, ValueError) as e:
        return {"status": "unavailable", "error": f"{type(e).__name__}: {e}"}

    age_h = None
    try:
        age_h = (datetime.now(UTC) - datetime.fromisoformat(d["generated_at"])).total_seconds() / 3600.0
    except (KeyError, ValueError):
        pass

    out = {
        "status": "ok" if d.get("status") in ("LIVE", "GREY") else "unavailable",
        "schema": d.get("schema"),
        "generated_at": d.get("generated_at"),
        "decision_time_oslo": "15:25",
        "decision_time_et": "09:25",
        "session": d.get("last_session"),
        "read_type": d.get("read_type"),
        "data_source": "session bars",  # internal feed names stay off the public artifact
        "lens_status": d.get("status"),
        "grey_reason": d.get("grey_reason"),
        "age_hours": round(age_h, 1) if age_h is not None else None,
        "stale": bool(age_h is not None and age_h > STALE_HOURS),
        "vol_regime": _vol_block(d),
        "dol_draw": _dol_block(d),
        # Public strings only. brief.mwmai.no is on the open web: validation
        # history, killed targets, gate backtests and PF figures stay in
        # FINDINGS.md and the handoff, never in a shipped artifact.
        "caveat": "Size of the day and which prior level comes first. Not a direction call.",
    }
    log.info("regime lens: %s vol=%s dol=%s callable=%s", out["lens_status"],
             out["vol_regime"].get("call"), out["dol_draw"].get("call"),
             out["dol_draw"].get("callable"))
    return out
