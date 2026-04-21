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
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

# Local
from config import BRIEF_JSON, LOG_DIR, VPS_TARGET, WEB_DIR
from schema import build_brief, atomic_write, empty_section, now_utc_iso
from fetchers import regime as f_regime
from fetchers import calibration as f_calibration
from fetchers import market as f_market
from fetchers import geopolitics as f_geo
from fetchers import tech_ai as f_tech
from fetchers import research as f_research
from fetchers import consciousness as f_conscious
from fetchers import system as f_system
from fetchers import trade_guard_daily as f_trade_guard
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
    ("market",        "Market",                   f_market),
    ("geopolitics",   "Geopolitics",              f_geo),
    ("tech_ai",       "Tech & AI / Claude / LLM", f_tech),
    ("research",      "Research",                 f_research),
    ("consciousness", "Consciousness & Resonance", f_conscious),
    ("system",        "System Health",            f_system),
]

# Sections whose raw items are already card-ready — skipping the LLM keeps
# numeric timeframe captions (e.g. "+0.28% vs prev close") intact.
SKIP_LLM_SECTIONS = {"market", "system"}


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
            "session_label": "ORB v2.5", "strategy_code": None, "volatility": "—",
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

    try:
        calibration = f_calibration.fetch()
    except Exception as e:
        log.exception("calibration fetch failed")
        calibration = {"status": "error", "n": 0, "error": str(e)}
    regime["calibration"] = calibration

    try:
        trade_guard = f_trade_guard.fetch()
    except Exception as e:
        log.exception("trade_guard_daily fetch failed")
        trade_guard = {"status": "error", "error": str(e), "per_strategy": {}, "orb_handoff": {}}

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

    brief = build_brief(regime=regime, strategy=strategy, sections=sections)
    brief["trade_guard"] = trade_guard
    return brief


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

    if VPS_TARGET and not args.no_deploy:
        try:
            _rsync_to_vps()
        except Exception:
            log.error("rsync to VPS failed (brief.json still local):\n%s", traceback.format_exc())
            return 2
    return 0


def _rsync_to_vps() -> None:
    """Push the whole web/ tree to BRIEF_VPS_TARGET. Atomic at file level via --inplace --partial."""
    cmd = [
        "rsync", "-az", "--delete",
        "--exclude=.*",
        f"{WEB_DIR}/",
        VPS_TARGET,
    ]
    log.info("rsync → %s", VPS_TARGET)
    subprocess.run(cmd, check=True, timeout=60)


if __name__ == "__main__":
    sys.exit(main())
