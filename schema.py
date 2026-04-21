"""brief.json schema + atomic writer.

Shape (morning_brief.v1):
{
  "schema": "morning_brief.v1",
  "generated_at": "<UTC ISO8601>",
  "regime": {
    "tier": "A|B|C|null",
    "tier_caption": str,
    "session_label": str,
    "strategy_code": int,
    "volatility": str,
    "direction": str,
    "generated_at": str,
    "raw": {...}                 # passthrough from webhook (debug)
  },
  "strategy": {
    "name": str,
    "subtitle": str,
    "why": str,
    "contracts": int,
    "symbol": "MNQ"
  },
  "sections": {
    "<key>": {
      "count": int,
      "source": str,
      "status": "ok|warn|err",
      "generated_at": str,
      "lede": str,
      "bullets": [{"headline": str, "body": str, "url"?: str}]
    }, ...
  },
  "trade_guard": {                 # optional — added 2026-04-21 (Track B)
    "date": str,
    "per_strategy": {
      "liqsweep|mrb|orb": {
        "verdict": "PROCEED|CAUTION|SKIP|—",
        "risk_score": int|null,
        "severity": str,
        "top_concern": str,
        "alerts": [str],
        "regime": str,
      }
    },
    "orb_handoff": {
      "status": "fresh|mid|stale|orphaned",
      "verdict": "OK|WARN|CRITICAL|ERROR",
      "age_h": float|null,
      "price_drift_pct": float|null,
      "next_action": str,
    },
    "generated_at": str,
    "source": str,
    "status": "ok|warn|err",
  }
}
"""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_section(source: str = "—", status: str = "warn") -> dict:
    return {
        "count": 0,
        "source": source,
        "status": status,
        "generated_at": now_utc_iso(),
        "lede": "",
        "bullets": [],
    }


def build_brief(regime: dict, strategy: dict, sections: dict) -> dict:
    return {
        "schema": "morning_brief.v1",
        "generated_at": now_utc_iso(),
        "regime": regime,
        "strategy": strategy,
        "sections": sections,
    }


def atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".brief.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
