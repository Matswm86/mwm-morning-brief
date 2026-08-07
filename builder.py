#!/usr/bin/env python3
"""Morning-brief builder — orchestrates fetchers + Groq + atomic write.

Usage:
  python3 builder.py              # build and write web/brief.json
  python3 builder.py --dry-run    # build and print to stdout, do not write
  python3 builder.py --no-llm     # skip Groq, use raw-item fallback

Exit codes:
  0 success (brief.json replaced atomically)
  1 unexpected error (brief.json untouched)
"""
from __future__ import annotations
import argparse
import logging
import os
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

# SCCS F1 — path-import shim. morning-brief lives outside the MWM-AI
# workspace (~/services/morning-brief), so we expose MWM-AI/core/ to
# resolve `from sccs import ...`. Failure is non-fatal — the import
# block below tolerates a missing sccs install.
_MWM_CORE = "/home/mats/MWM-AI/core"
if os.path.isdir(_MWM_CORE) and _MWM_CORE not in sys.path:
    sys.path.insert(0, _MWM_CORE)
try:
    from sccs import PolicyState as _SccsPolicyState, record as _sccs_record  # type: ignore
    _SCCS_AVAILABLE = True
except Exception:
    _SccsPolicyState = None  # type: ignore
    _sccs_record = None  # type: ignore
    _SCCS_AVAILABLE = False

try:
    from sccs.conformal import wrap_metric as _sccs_wrap_metric  # type: ignore
    _SCCS_CONFORMAL_AVAILABLE = True
except Exception:
    _sccs_wrap_metric = None  # type: ignore
    _SCCS_CONFORMAL_AVAILABLE = False

# Local
from config import BRIEF_JSON, LOG_DIR, VPS_TARGET, WEB_DIR
from schema import build_brief, atomic_write, empty_section, now_utc_iso
from fetchers import regime as f_regime
from fetchers import trading_news as f_trading_news
from fetchers import event_calendar as f_event_calendar
from fetchers import regime_derived as f_regime_derived
from fetchers import calibration as f_calibration
from fetchers import market as f_market
from fetchers import geopolitics as f_geo
from fetchers import tech_ai as f_tech
from fetchers import research as f_research
from fetchers import consciousness as f_conscious
from fetchers import system as f_system
from fetchers import gold as f_gold
from fetchers import selfcalib as f_selfcalib
import strategy as strategy_picker
import llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "builder.log"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("morning-brief.builder")


SECTIONS = [
    ("trading_news",  "Trading News · 24h",       f_trading_news),
    ("event_calendar", "Scheduled · US macro",    f_event_calendar),
    ("market",        "Market",                   f_market),
    ("gold",          "Gold & Metals",            f_gold),
    ("geopolitics",   "Geopolitics",              f_geo),
    ("tech_ai",       "Tech & AI / Claude / LLM", f_tech),
    ("research",      "Research",                 f_research),
    ("consciousness", "Consciousness & Resonance", f_conscious),
    ("system",        "System Health",            f_system),
]

# Sections whose raw items are already card-ready — skipping the LLM keeps
# numeric timeframe captions (e.g. "+0.28% vs prev close") intact.
# event_calendar joins them: an LLM paraphrase of "CPI, Wed 08:30 ET" is a
# chance to get a time wrong, and a wrong release time is worse than no card.
SKIP_LLM_SECTIONS = {"market", "system", "event_calendar"}


def _run_section(key: str, label: str, mod, use_llm: bool) -> tuple[str, dict]:
    """Fetch + (optionally) summarise one section."""
    try:
        raw = mod.fetch()
    except Exception as e:
        log.exception("fetch failed for %s", key)
        return key, {**empty_section(source=f"err:{type(e).__name__}", status="err"),
                     "lede": f"fetch failed: {e.__class__.__name__}"}

    items = raw.get("items") or []
    payload = {
        "count": raw.get("count", len(items)),
        "source": raw.get("source", "—"),
        "status": raw.get("status", "ok"),
        "generated_at": raw.get("generated_at", now_utc_iso()),
    }

    section_use_llm = use_llm and key not in SKIP_LLM_SECTIONS
    if section_use_llm and items:
        summary = llm.summarise(label, items, max_bullets=5)
        payload["lede"] = summary.get("lede", "")
        payload["bullets"] = summary.get("bullets", [])
    else:
        payload["lede"] = ""
        # Convert items directly
        bullets = []
        for it in items[:5]:
            hd = str(it.get("headline") or it.get("title") or "").strip()[:120]
            bd = str(it.get("body") or it.get("summary") or "").strip()[:260]
            url = str(it.get("url") or "").strip()
            if not hd and not bd:
                continue
            row = {"headline": hd, "body": bd}
            if url.startswith("http"):
                row["url"] = url
            bullets.append(row)
        payload["bullets"] = bullets

    # The trading wire renders the raw items itself (each line names the
    # instrument it bears on and the driver family that qualified it), so those
    # fields must survive the generic card payload rather than being collapsed
    # into LLM bullets.
    if key == "trading_news":
        payload["items"] = items
        payload["instrument_counts"] = raw.get("instrument_counts", {})
        payload["window_hours"] = raw.get("window_hours")

    # Same reasoning for the Regime block's schedule tier: events.js renders the
    # rows itself (ET + Oslo times, impact, instrument) and must be able to tell
    # "nothing scheduled" from "the scrape broke", so error/fomc survive too.
    if key == "event_calendar":
        payload["items"] = items
        payload["fomc"] = raw.get("fomc", {})
        payload["horizon_days"] = raw.get("horizon_days")
        if raw.get("error"):
            payload["error"] = raw["error"]

    return key, payload


def build(use_llm: bool = True) -> dict:
    log.info("morning-brief build starting (use_llm=%s)", use_llm)

    # Regime first — it's fast and also seeds strategy_picker
    try:
        regime = f_regime.fetch()
    except Exception as e:
        log.exception("regime fetch failed")
        regime = {
            "tier": None, "tier_caption": f"error: {e.__class__.__name__}",
            "session_label": "Market Detector v3", "strategy_code": None, "volatility": "—",
            "direction": "—", "regime": None, "score": None, "contracts": 0,
            "age_hours": None, "generated_at": "", "raw": {},
        }
    try:
        strategy = strategy_picker.pick(regime)
    except Exception as e:
        log.exception("strategy pick failed")
        strategy = {"name": "Error", "subtitle": str(e)[:80],
                    "why": "Strategy picker raised. Check builder logs.",
                    "contracts": 0, "symbol": "MNQ"}

    regimes: dict[str, dict] = {}
    for code, sym in (("MNQ", "NQ=F"), ("MGC", "MGC=F")):
        try:
            regimes[code] = f_regime_derived.fetch(sym)
        except Exception:
            log.exception("regime_derived fetch failed for %s", code)

    try:
        calibration = f_calibration.fetch()
    except Exception as e:
        log.exception("calibration fetch failed")
        calibration = {"status": "error", "n": 0, "error": str(e)}
    regime["calibration"] = calibration

    # ─── SCCS F1: log policy_state once per build ──────────────────────
    # entry_point=morning_brief. regime_label = VIX/regime tier from the
    # fetcher; rubric_weights = strategy picker decision; extra carries
    # llm/deploy toggles + section list for downstream filtering.
    _log_morning_brief_policy_state(regime, strategy, use_llm)

    # Account-facing fetchers (trade_guard, trade_tracker, backtest_stats,
    # per_cell_tracker) removed 2026-08-07 — the public brief carries no
    # own-account data. Their modules stay in fetchers/ for local use.
    try:
        selfcalib = f_selfcalib.fetch()
    except Exception as e:
        log.exception("selfcalib fetch failed")
        selfcalib = {"status": f"err:{e.__class__.__name__}", "dimensions": []}

    sections: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(SECTIONS)) as pool:
        futures = {pool.submit(_run_section, k, lbl, mod, use_llm): k
                   for k, lbl, mod in SECTIONS}
        for fut in as_completed(futures):
            try:
                k, payload = fut.result()
                sections[k] = payload
                log.info("%-14s count=%-3d status=%-4s bullets=%d",
                         k, payload["count"], payload["status"], len(payload["bullets"]))
            except Exception:
                k = futures[fut]
                log.exception("section %s raised at future level", k)
                sections[k] = empty_section(status="err")

    brief = build_brief(regime=regime, sections=sections)
    if regimes:
        brief["regimes"] = regimes
    brief["_selfcalib"] = selfcalib  # kept on brief for diagnostics; web reads /selfcalib.json
    brief["_sccs"] = _sccs_brief_block()
    return brief


def _sccs_brief_block() -> dict:
    """SCCS F4.5 — emit conformal-wrapped judge accept-rate on brief.json.

    Reads ``data/sccs/judge_calibration.jsonl`` (memento second-pass
    residuals; both passes LLM-based so residuals are correlated and
    ACI's empirical-coverage tracker is the kill criterion). Point
    estimate = 1 − mean(residual) over the most recent rows; wrap with
    DtACI to get a 90%-coverage half-width. Tagged ``method="point"``
    when N < MIN_N_CAL (currently 30).

    SCCS_F45_CONFORMAL_LIVE=0 disables the metric (returns
    {"method": "off"}); the default is on once the cal-log has cleared
    MIN_N_CAL, which it has as of 2026-05-05 (N=35).

    Best-effort, never raises — brief.json must build even if the
    cal-log is missing.
    """
    if os.environ.get("SCCS_F45_CONFORMAL_LIVE", "1") == "0":
        return {"judge_score_ci": {"method": "off"}}
    if not _SCCS_CONFORMAL_AVAILABLE:
        return {"judge_score_ci": {"method": "unavailable"}}
    try:
        cal_path = "/home/mats/MWM-AI/data/sccs/judge_calibration.jsonl"
        if not os.path.isfile(cal_path):
            return {"judge_score_ci": {"method": "no_cal_log"}}
        residuals: list[float] = []
        import json as _json
        with open(cal_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                r = row.get("residual")
                if r is None:
                    continue
                residuals.append(float(r))
        # First-cycle miscoverage_history is empty on purpose: ACI's
        # online α update needs past wrapped-interval coverage events
        # (did the realized residual fall outside the previous interval),
        # which only exist after the first wrap is rendered. Future
        # cycles will append to data/sccs/conformal_coverage.jsonl and
        # feed it back here; for now ACI collapses to split conformal at
        # the nominal α.
        wrapped = _sccs_wrap_metric(
            point=1.0 - (sum(residuals) / len(residuals)) if residuals else 0.0,
            cal_residuals=residuals,
            method="aci",
            miscoverage_history=[],
            clip_to=(0.0, 1.0),
        )
        wrapped["source_jsonl"] = "data/sccs/judge_calibration.jsonl"
        return {"judge_score_ci": wrapped}
    except Exception as e:  # pragma: no cover
        log.debug("sccs conformal wrap failed (non-fatal): %s", e)
        return {"judge_score_ci": {"method": "error", "error": str(e)[:200]}}


def _log_morning_brief_policy_state(regime: dict, strategy: dict, use_llm: bool) -> None:
    """Best-effort SCCS F1 logger; missing sccs or DB errors must not break the build."""
    if not _SCCS_AVAILABLE or os.environ.get("SCCS_OFF", "0") == "1":
        return
    try:
        regime_label = (
            regime.get("regime")
            or regime.get("tier_caption")
            or regime.get("session_label")
            or "unknown"
        )
        if regime.get("volatility") and regime["volatility"] != "—":
            regime_label = f"{regime_label}|vol:{regime['volatility']}"
        _sccs_record(_SccsPolicyState(
            entry_point="morning_brief",
            retrieval_config={
                "sections": [k for k, _, _ in SECTIONS],
                "skip_llm_sections": sorted(SKIP_LLM_SECTIONS),
                "use_llm": bool(use_llm),
            },
            rubric_weights={
                "strategy_name": strategy.get("name"),
                "strategy_code": regime.get("strategy_code"),
                "contracts": strategy.get("contracts"),
                "symbol": strategy.get("symbol"),
                "tier": regime.get("tier"),
                "score": regime.get("score"),
            },
            model_tier="groq:summarise" if use_llm else "no_llm",
            regime_label=str(regime_label)[:120],
            extra={
                "direction": regime.get("direction"),
                "age_hours": regime.get("age_hours"),
                "calibration_n": (regime.get("calibration") or {}).get("n"),
            },
        ))
    except Exception as e:  # pragma: no cover
        log.debug(f"sccs policy_state log failed (non-fatal): {type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Morning-brief builder")
    ap.add_argument("--dry-run", action="store_true", help="do not write brief.json")
    ap.add_argument("--no-llm", action="store_true", help="skip Groq summarisation")
    ap.add_argument("--no-deploy", action="store_true", help="skip rsync to BRIEF_VPS_TARGET")
    args = ap.parse_args()

    try:
        brief = build(use_llm=not args.no_llm)
    except Exception:
        log.error("build raised:\n%s", traceback.format_exc())
        return 1

    if args.dry_run:
        import json as _json
        sys.stdout.write(_json.dumps(brief, indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0

    try:
        atomic_write(BRIEF_JSON, brief)
    except Exception:
        log.error("atomic_write failed:\n%s", traceback.format_exc())
        return 1

    log.info("brief written: %s", BRIEF_JSON)

    # Selfcalib bar writes to its own artifact so JS can fetch it
    # independently of the heavier brief.json.
    sc = brief.get("_selfcalib") or {}
    if sc.get("dimensions"):
        try:
            atomic_write(WEB_DIR / "selfcalib.json", sc)
            log.info("selfcalib written: agg=%s  dims=%d",
                     sc.get("aggregate_pct"), len(sc["dimensions"]))
        except Exception:
            log.error("selfcalib atomic_write failed:\n%s", traceback.format_exc())

    if VPS_TARGET and not args.no_deploy:
        try:
            _rsync_to_vps()
        except Exception:
            log.error("rsync to VPS failed (brief.json still local):\n%s", traceback.format_exc())
            return 2
    return 0


def _rsync_to_vps() -> None:
    """Push the whole web/ tree to BRIEF_VPS_TARGET. Atomic at file level via --inplace --partial."""
    # --delete would remove artifacts written into the webroot by OTHER
    # producers. nowcast.json is published straight to /var/www/brief by the
    # VPS regime-nowcast timer and has no local counterpart, so a plain
    # --delete erased it on every build (hit 2026-08-07). Protect any such
    # foreign artifact explicitly; add to this list when a new producer starts
    # writing into the webroot.
    cmd = [
        "rsync", "-az", "--delete",
        "--exclude=.*",
        "--filter=protect nowcast.json",
        f"{WEB_DIR}/",
        VPS_TARGET,
    ]
    log.info("rsync → %s", VPS_TARGET)
    subprocess.run(cmd, check=True, timeout=60)


if __name__ == "__main__":
    sys.exit(main())
