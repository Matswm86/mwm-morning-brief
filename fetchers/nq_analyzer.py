"""NQ analyzer → brief. Reads the newest analyzer run (weekahead.json, schema weekahead.v1,
produced by ~/MWM-AI/projects/mwm-trading/research/nq-analyzer/run.py), publishes the
edition data into web/nq/ (builder-written, so the rsync --delete is safe) and returns a
small card-ready block for brief["nq"] (front-page lead board).

Honesty rules (mirrors play.js):
  * A run older than STALE_HOURS on a weekday is marked stale → the front page greys the board.
  * If the analyst layer failed the block still ships (status=fallback) with rule labels and
    watchdog-only verdicts; the page says so. Never a blank card, never yesterday-as-today.
  * Nothing here gates anything. Advisory only.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger("morning-brief.nq")

WS = Path(os.environ.get("MWM_AI_ROOT", Path.home() / "MWM-AI"))
RUNS = WS / "data" / "nq-analyzer" / "runs"
STALE_HOURS = 30
KEEP_DATED = 14
EDITION_HREF = "week-ahead.html"


def _newest_run() -> Path | None:
    if not RUNS.exists():
        return None
    cands = sorted(
        (p for p in RUNS.iterdir() if p.is_dir() and (p / "weekahead.json").exists()),
        key=lambda p: p.name,
        reverse=True,
    )
    return cands[0] if cands else None


def _hours_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600
    except ValueError:
        return None


def _publish(run_dir: Path, wa: dict, web_dir: Path) -> dict:
    """Copy edition data + raw report into web/nq/. Returns hrefs (relative to web/)."""
    out = web_dir / "nq"
    out.mkdir(parents=True, exist_ok=True)
    date = (wa.get("meta") or {}).get("run_date") or run_dir.name
    dated_json = out / f"weekahead-{date}.json"
    shutil.copyfile(run_dir / "weekahead.json", dated_json)
    shutil.copyfile(run_dir / "weekahead.json", out / "weekahead-latest.json")
    hrefs = {"json": "nq/weekahead-latest.json", "json_dated": f"nq/{dated_json.name}",
             "edition": EDITION_HREF}
    rep = run_dir / "report.html"
    if rep.exists():
        shutil.copyfile(rep, out / f"report-{date}.html")
        shutil.copyfile(rep, out / "report-latest.html")
        hrefs["report"] = "nq/report-latest.html"
        hrefs["report_dated"] = f"nq/report-{date}.html"
    # prune dated files beyond KEEP_DATED (newest kept)
    for pat in ("weekahead-????-??-??.json", "report-????-??-??.html"):
        files = sorted(out.glob(pat), reverse=True)
        for f in files[KEEP_DATED:]:
            f.unlink(missing_ok=True)
    return hrefs


def fetch(web_dir: Path | None = None) -> dict:
    run_dir = _newest_run()
    if run_dir is None:
        return {"status": "unavailable", "error": f"no analyzer run with weekahead.json under {RUNS}"}
    try:
        wa = json.loads((run_dir / "weekahead.json").read_text())
    except (OSError, ValueError) as e:
        return {"status": "unavailable", "error": f"{e.__class__.__name__}: {e}", "run_dir": str(run_dir)}
    meta = wa.get("meta") or {}
    hrefs = {"json": "nq/weekahead-latest.json", "edition": EDITION_HREF}
    if web_dir is not None:
        try:
            hrefs = _publish(run_dir, wa, web_dir)
        except OSError as e:
            log.error("nq publish failed: %s", e)
    age_h = _hours_since(meta.get("generated_at"))
    weekday = dt.datetime.now(dt.timezone.utc).weekday() < 5
    stale = bool(age_h is not None and age_h > STALE_HOURS and weekday)
    mnq = wa.get("mnq") or {}
    au = wa.get("audit") or {}
    verdicts = []
    for v in wa.get("strategyVerdicts") or []:
        verdicts.append({
            "name": v.get("name"),
            "key": v.get("key"),
            "instrument": v.get("instrument"),
            "word": v.get("word"),
            "confidence": v.get("confidence"),
            "why": v.get("why"),
            "watchdog": v.get("watchdog"),
            "watchdogStatus": v.get("watchdogStatus"),
        })
    return {
        "status": "carried"
        if meta.get("carried")
        else "ok"
        if meta.get("analyst_ok")
        else "fallback",
        "carried": meta.get("carried"),
        "schema": wa.get("schema"),
        "run_date": meta.get("run_date"),
        "mode": meta.get("mode"),
        "generated_at": meta.get("generated_at"),
        "week_monday": meta.get("week_monday"),
        "week_friday": meta.get("week_friday"),
        "age_hours": round(age_h, 1) if age_h is not None else None,
        "stale": stale,
        "analyst_model": meta.get("analyst_model"),
        "analyst_error": meta.get("analyst_error"),
        "validation": (meta.get("validation") or {}).get("verdict"),
        "outlook": {
            "call": mnq.get("call"),
            "confidence": mnq.get("confidence"),
            "one_line": mnq.get("oneLiner"),
            "facts": mnq.get("oneLinerFacts") or [],
            "expected_range": mnq.get("expectedRange"),
            "range_call": mnq.get("rangeCall") or {},
            "range_forecast": mnq.get("rangeForecast") or {},
            "direction_call": mnq.get("directionCall") or {},
            "labels": mnq.get("labels") or {},
        },
        "mgc": {
            "status": (wa.get("mgc") or {}).get("status"),
            "call": (wa.get("mgc") or {}).get("call"),
            "confidence": (wa.get("mgc") or {}).get("confidence"),
            "one_line": (wa.get("mgc") or {}).get("oneLiner"),
            "facts": (wa.get("mgc") or {}).get("oneLinerFacts") or [],
            "expected_range": (wa.get("mgc") or {}).get("expectedRange"),
            "range_call": (wa.get("mgc") or {}).get("rangeCall") or {},
            "range_forecast": (wa.get("mgc") or {}).get("rangeForecast") or {},
            "direction_call": (wa.get("mgc") or {}).get("directionCall") or {},
            "labels": (wa.get("mgc") or {}).get("labels") or {},
        },
        "strategy_verdicts": verdicts,
        "audit": {
            "ok": au.get("ok"),
            "model": au.get("model"),
            "verdict": au.get("verdict"),
            "quality_0_10": au.get("quality_0_10"),
            "n_issues": len(au.get("issues") or []),
            "applied": au.get("applied"),
            "summary": au.get("summary"),
        } if au else None,
        "eyebrow": meta.get("eyebrow"),
        "advisory": meta.get("advisory"),
        "hrefs": hrefs,
    }
