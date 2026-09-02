#!/usr/bin/env python3
"""selfcalib v2 — apply selfcalib_rubric.yaml to compute per-dim pcts.

Spec: ~/MWM-AI/plans/selfcalib-bar-v2-rubric-2026-05-05.md

Reads:
  - selfcalib_rubric.yaml (per-dim signal weights + thresholds)
  - signal sources (CIP journal, policy_state.db, file existences, ...)
  - selfcalib_state.json (current manual state — for override field + diff base)

Writes (--write only):
  - selfcalib_state_proposed.json (parallel to selfcalib_state.json, fetcher unchanged)
  - data/sccs/selfcalib_calibration.jsonl append (Q4 calibration log: rubric vs override gap)

Default = --diff: prints per-dim comparison vs current manual pcts. No file writes.

Frozen-on-missing: if any signal returns None, the dim reports the prior pct
unchanged with frozen_reason annotation. Never silent-downgrades.

Override behavior (Q4 ratified 05-05): when state file's pct_override is set on
a dim, the rubric output is computed and logged but the override wins. Bar
uses override visually; tooltip surfaces (override, rubric, gap); gap is logged
to selfcalib_calibration.jsonl per build.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from config import MWM_ROOT, SERVICE_ROOT

log = logging.getLogger("selfcalib.recompute")

RUBRIC_FILE = SERVICE_ROOT / "selfcalib_rubric.yaml"
STATE_FILE = SERVICE_ROOT / "selfcalib_state.json"
PROPOSED_FILE = SERVICE_ROOT / "selfcalib_state_proposed.json"
WEB_PROPOSED_FILE = SERVICE_ROOT / "web" / "selfcalib_proposed.json"
CALIBRATION_LOG = MWM_ROOT / "data" / "sccs" / "selfcalib_calibration.jsonl"


# ============================================================
# Signal implementations
# ============================================================
# Each signal: (params: dict, ctx: dict) -> int|None
#   ctx provides shared state (e.g., resolved repo paths)
#   returns 0-100 score, or None if frozen (signal source unavailable)


def _file_age_days(p: Path) -> float | None:
    if not p.exists():
        return None
    age_sec = datetime.now(timezone.utc).timestamp() - p.stat().st_mtime
    return age_sec / 86_400


def _ramp_fresh(age_days: float | None, fresh: int, stale: int = 0) -> int:
    if age_days is None:
        return 0
    if age_days <= fresh:
        return 100
    if stale and age_days >= stale:
        return 0
    if stale:
        # linear ramp fresh→stale
        return max(0, int(100 * (1 - (age_days - fresh) / (stale - fresh))))
    return max(0, int(100 - (age_days - fresh) * 5))


def _journalctl_lines(unit: str, since_days: int) -> list[str] | None:
    try:
        out = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                unit,
                "--since",
                f"{since_days} days ago",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return None
        return out.stdout.splitlines()
    except Exception as e:
        log.warning("journalctl %s failed: %s", unit, e)
        return None


def _systemd_active(unit: str) -> bool | None:
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() == "active"
    except Exception:
        return None


def _sqlite_count(db: Path, sql: str) -> int | None:
    if not db.exists():
        return None
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0
    except Exception as e:
        log.warning("sqlite query failed on %s: %s", db, e)
        return None


# ----- D1 signals -----


def signal_cip_fires_landed(p: dict, ctx: dict) -> int | None:
    lines = _journalctl_lines("mwm-cip.service", p.get("window_days", 30))
    if lines is None:
        return None
    green = sum(1 for ln in lines if "rc=0" in ln or "fire complete" in ln.lower())
    return min(100, int(green / max(1, p.get("target", 4)) * 100))


def signal_automation_chain_active(p: dict, ctx: dict) -> int | None:
    """Score 0-100 by checking each timer fired recently AND last result was success.

    Most services in the chain are oneshot (cron-style), so is-active reports
    'inactive' between fires. We instead query Result + LastTriggerUSec on the
    paired timer to detect 'fired recently and cleanly'.
    """
    services = p.get("services", [])
    fresh_days = int(p.get("fresh_days", 8))
    if not services:
        return None
    healthy = 0
    for unit in services:
        try:
            # last result of the service unit
            res = subprocess.run(
                [
                    "systemctl",
                    "--user",
                    "show",
                    unit,
                    "-p",
                    "Result",
                    "-p",
                    "ActiveState",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
            result_ok = "Result=success" in res
            active_now = "ActiveState=active" in res

            # timer freshness (if a paired timer exists)
            timer = unit.replace(".service", ".timer")
            tres = subprocess.run(
                ["systemctl", "--user", "show", timer, "-p", "LastTriggerUSec"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
            timer_fresh = False
            for line in tres.splitlines():
                if line.startswith("LastTriggerUSec=") and "n/a" not in line:
                    # parse e.g. "LastTriggerUSec=Sun 2026-05-04 04:00:00 UTC"
                    val = line.split("=", 1)[1].strip()
                    if val and val != "0":
                        try:
                            # rough parse — strip weekday + tz, take "YYYY-MM-DD"
                            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", val)
                            if m:
                                trig = datetime(
                                    int(m.group(1)),
                                    int(m.group(2)),
                                    int(m.group(3)),
                                    tzinfo=timezone.utc,
                                )
                                age_days = (
                                    datetime.now(timezone.utc) - trig
                                ).total_seconds() / 86_400
                                if age_days <= fresh_days:
                                    timer_fresh = True
                        except Exception:
                            pass
                    break

            # service counts as healthy if (recently fired & clean result) OR (currently active & clean)
            if (timer_fresh and result_ok) or (active_now and result_ok):
                healthy += 1
        except Exception as e:
            log.warning("automation chain query failed for %s: %s", unit, e)
            return None  # frozen on query failure
    return int(healthy / len(services) * 100)


def signal_any_file_grep(p: dict, ctx: dict) -> int | None:
    """file_grep_present but tries multiple candidate paths; first match wins."""
    patterns = p.get("patterns", [])
    if not patterns:
        return None
    for rel in p.get("candidate_paths", []):
        path = MWM_ROOT / rel
        if not path.exists():
            continue
        try:
            text = path.read_text()
        except Exception:
            continue
        matches = [bool(re.search(re.escape(pat), text, re.I)) for pat in patterns]
        if p.get("require_all", False):
            if all(matches):
                return 100
        else:
            if any(matches):
                return 100
    return 0


def signal_bocpd_subsystem_health(p: dict, ctx: dict) -> int | None:
    db = MWM_ROOT / p["db_relpath"]
    if not db.exists():
        return 0
    age = _file_age_days(db)
    rows = _sqlite_count(db, "SELECT COUNT(*) FROM bocpd_state") or 0
    if rows == 0:
        return 0
    if age is not None and age < p.get("fresh_days", 8):
        return 100
    return 50


def signal_synthesis_freshness(p: dict, ctx: dict) -> int | None:
    synth = MWM_ROOT / "data" / "synthesis"
    if not synth.exists():
        return None
    newest_age = None
    for sub in synth.iterdir():
        if not sub.is_dir():
            continue
        for f in sub.glob("*.md"):
            age = _file_age_days(f)
            if age is not None and (newest_age is None or age < newest_age):
                newest_age = age
    if newest_age is None:
        return 0
    return _ramp_fresh(newest_age, p.get("fresh_days", 8), stale=30)


def signal_memento_judge_active(p: dict, ctx: dict) -> int | None:
    mdir = MWM_ROOT / "data" / "memento"
    if not mdir.exists():
        return 0
    files = list(mdir.glob("*.jsonl"))
    if not files:
        return 0
    newest = max(files, key=lambda f: f.stat().st_mtime)
    age = _file_age_days(newest)
    if age is None:
        return 0
    has_accept = False
    cutoff = datetime.now(timezone.utc) - timedelta(days=p.get("window_days", 30))
    for f in files:
        if f.stat().st_mtime < cutoff.timestamp():
            continue
        try:
            with f.open() as fh:
                for ln in fh:
                    if '"accepted": true' in ln or '"accept": true' in ln:
                        has_accept = True
                        break
        except Exception:
            continue
        if has_accept:
            break
    if has_accept and age < p.get("fresh_days", 8):
        return 100
    if age < p.get("fresh_days", 8):
        return 50
    return 0


# ----- D2 signals -----


def signal_policy_state_rows(p: dict, ctx: dict) -> int | None:
    db = MWM_ROOT / p["db_relpath"]
    rows = _sqlite_count(db, f"SELECT COUNT(*) FROM {p.get('table', 'policy_state')}")
    if rows is None:
        return None
    floor = p.get("floor", 30)
    ceiling = p.get("ceiling", 100)
    if rows < floor:
        return 0
    return min(100, int((rows - floor) * 100 / max(1, ceiling - floor)) + 0)


def signal_conformal_cal_rows(p: dict, ctx: dict) -> int | None:
    f = MWM_ROOT / p["jsonl_relpath"]
    if not f.exists():
        return 0
    try:
        n = sum(1 for _ in f.open())
    except Exception:
        return None
    return min(100, int(n / max(1, p.get("target", 30)) * 100))


def signal_eval_gold_runs(p: dict, ctx: dict) -> int | None:
    eval_dir = MWM_ROOT / "data" / "eval"
    if not eval_dir.exists():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - p.get("window_days", 30) * 86_400
    count = sum(
        1 for f in eval_dir.glob("eval_gold_*.json") if f.stat().st_mtime > cutoff
    )
    return min(100, count * int(100 / max(1, p.get("target_runs", 4))))


def signal_bernstein_gate_fires(p: dict, ctx: dict) -> int | None:
    lines = _journalctl_lines("mwm-cip.service", p.get("window_days", 30))
    if lines is None:
        return None
    fires = sum(1 for ln in lines if re.search(r"bernstein", ln, re.I))
    return min(100, fires * int(100 / max(1, p.get("target_fires", 5))))


def signal_forward_sufficiency_active(p: dict, ctx: dict) -> int | None:
    rubric = MWM_ROOT / p["rubric_relpath"]
    if not rubric.exists():
        return 0
    try:
        data = json.loads(rubric.read_text())
    except Exception:
        return None
    dims = data.get("dimensions", [])
    threshold = data.get("total_threshold") or data.get("threshold") or 0
    if len(dims) >= p.get("min_dims", 6) and threshold >= p.get("min_threshold", 42):
        return 100
    return 0


def signal_honeypot_abstain_rate(p: dict, ctx: dict) -> int | None:
    """F23: load-bearing falsifiability test for hallucination-control track.

    Reads the latest run summary from honeypot_results.jsonl (one record per
    run, appended). Returns 0 at floor (default 0.20), 100 at ceiling
    (default 0.80, the F23 acceptance gate). Linear ramp between.

    None when the results file is missing — selfcalib treats None as frozen
    (use prior pct + flag frozen_reason). This is intentional: pre-baseline
    we don't want a fake 0 score dragging D2 down.
    """
    f = MWM_ROOT / p["jsonl_relpath"]
    if not f.exists():
        return None
    last = None
    try:
        with f.open() as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    last = json.loads(ln)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return None
    if last is None:
        return None
    rates = last.get("rates") or {}
    rate = rates.get("abstain")
    if rate is None:
        return None
    try:
        rate_f = float(rate)
    except (TypeError, ValueError):
        return None
    floor = float(p.get("floor", 0.20))
    ceiling = float(p.get("ceiling", 0.80))
    if rate_f <= floor:
        return 0
    if rate_f >= ceiling:
        return 100
    span = ceiling - floor
    if span <= 0:
        return 100
    return int((rate_f - floor) / span * 100)


# ----- D3 signals -----


def signal_memento_acceptance_curve(p: dict, ctx: dict) -> int | None:
    mdir = MWM_ROOT / "data" / "memento"
    if not mdir.exists():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - p.get("window_days", 30) * 86_400
    accept = 0
    total = 0
    for f in mdir.glob("*.jsonl"):
        if f.stat().st_mtime < cutoff:
            continue
        try:
            with f.open() as fh:
                for ln in fh:
                    if '"accept' in ln or '"reject' in ln:
                        total += 1
                        if '"accepted": true' in ln or '"accept": true' in ln:
                            accept += 1
        except Exception:
            continue
    if total == 0:
        return 0
    rate = accept / total
    return min(100, int(rate * 200))  # 50% accept = 100


def signal_file_grep_present(p: dict, ctx: dict) -> int | None:
    path = MWM_ROOT / p["path_relpath"]
    if not path.exists():
        return 0
    try:
        text = path.read_text()
    except Exception:
        return None
    patterns = p.get("patterns", [])
    if not patterns:
        return None
    matches = [bool(re.search(re.escape(pat), text, re.I)) for pat in patterns]
    if p.get("require_all", False):
        return 100 if all(matches) else 0
    return 100 if any(matches) else 0


def signal_f3_dowhy_status(p: dict, ctx: dict) -> int | None:
    path = MWM_ROOT / p["path_relpath"]
    if not path.exists():
        return 0
    # File exists = at minimum dry-mode shipped (per F3 ship 05-01)
    return 100


def signal_f18_dry_run_active(p: dict, ctx: dict) -> int | None:
    expected = str(p.get("expected", "1"))
    actual = os.environ.get(p["env_var"], "")
    in_env = actual == expected
    # also check the .env file directly since the script may run outside the cip service env
    env_file = MWM_ROOT / ".env"
    in_file = False
    if env_file.exists():
        for ln in env_file.read_text().splitlines():
            if ln.strip().startswith(f"{p['env_var']}={expected}"):
                in_file = True
                break
    if in_env and in_file:
        return 100
    if in_env or in_file:
        return 50
    return 0


# ----- D4 signals -----


def signal_file_fresh(p: dict, ctx: dict) -> int | None:
    path = MWM_ROOT / p["path_relpath"]
    age = _file_age_days(path)
    if age is None:
        return 0
    return _ramp_fresh(age, p.get("fresh_days", 7), stale=p.get("stale_days", 0))


def signal_policy_state_cell_diversity(p: dict, ctx: dict) -> int | None:
    db = MWM_ROOT / p["db_relpath"]
    if not db.exists():
        return 0
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            # tolerate either schema with regime_label column or without
            cols = [r[1] for r in conn.execute("PRAGMA table_info(policy_state)")]
            if "regime_label" in cols and "tier" in cols:
                row = conn.execute(
                    "SELECT COUNT(DISTINCT regime_label || '|' || COALESCE(tier,'')) "
                    "FROM policy_state WHERE regime_label IS NOT NULL"
                ).fetchone()
                distinct = int(row[0] or 0)
            elif "regime_label" in cols:
                row = conn.execute(
                    "SELECT COUNT(DISTINCT regime_label) FROM policy_state "
                    "WHERE regime_label IS NOT NULL"
                ).fetchone()
                distinct = int(row[0] or 0)
            else:
                distinct = 0
    except Exception as e:
        log.warning("cell_diversity query failed: %s", e)
        return None
    return min(100, int(distinct / max(1, p.get("target_cells", 3)) * 100))


def signal_sqlite_recent_positive(p: dict, ctx: dict) -> int | None:
    """Share of the last ``n`` rows (by ``order_col`` desc) with ``column`` > 0.
    D4 `reward_channel_alive`: utility_tracker.sweep_log — 2 consecutive
    zero-`useful` sweeps = dead reward channel (typed `utility_channel_silent`)."""
    db = MWM_ROOT / p["db_relpath"]
    if not db.exists():
        return 0
    n = int(p.get("n", 2))
    table, col, order_col = p["table"], p["column"], p.get("order_col", "id")
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                f"SELECT {col} FROM {table} ORDER BY {order_col} DESC LIMIT {n}"
            ).fetchall()
    except Exception as e:
        log.warning("sqlite_recent_positive failed on %s: %s", db, e)
        return None
    if not rows:
        return 0
    return int(sum(1 for (v,) in rows if (v or 0) > 0) * 100 / n)


def signal_file_present(p: dict, ctx: dict) -> int | None:
    if "candidate_paths" in p:
        for rel in p["candidate_paths"]:
            if (MWM_ROOT / rel).exists():
                return 100
        return 0
    if "glob_relpath" in p:
        # split first non-glob ancestor + glob remainder
        glob = p["glob_relpath"]
        base = MWM_ROOT
        # naive: pass through to Path.glob
        matches = list(base.glob(glob))
        return 100 if matches else 0
    return None


# ----- D5 signals -----


def signal_prompt_cache_active(p: dict, ctx: dict) -> int | None:
    """Search just .py files under core/, skip .venv/__pycache__/.git."""
    root = MWM_ROOT / p.get("root_relpath", "core")
    if not root.exists():
        return 0
    pattern = p.get("pattern", "cache_control")
    skip_dirs = {".venv", "__pycache__", ".git", "node_modules"}
    try:
        for path in root.rglob("*.py"):
            if any(part in skip_dirs for part in path.parts):
                continue
            try:
                if pattern in path.read_text(errors="ignore"):
                    return 100
            except Exception:
                continue
        return 0
    except Exception:
        return None


def signal_rtk_proxy_live(p: dict, ctx: dict) -> int | None:
    try:
        which = subprocess.run(
            ["which", "rtk"], capture_output=True, text=True, timeout=5
        )
        if which.returncode != 0 or not which.stdout.strip():
            return 0
        gain = subprocess.run(
            ["rtk", "gain"], capture_output=True, text=True, timeout=10
        )
        return 100 if gain.returncode == 0 else 50
    except Exception:
        return None


# ----- D6 signals -----


def signal_handoff_files_count(p: dict, ctx: dict) -> int | None:
    mdir = MWM_ROOT / "memory"
    if not mdir.exists():
        return 0
    count = sum(1 for _ in mdir.glob("handoff-*.md"))
    return min(100, int(count / max(1, p.get("target", 30)) * 100))


def signal_cip_synthesis_writeback(p: dict, ctx: dict) -> int | None:
    synth = MWM_ROOT / "data" / "synthesis"
    if not synth.exists():
        return 0
    files = list(synth.glob("cross-domain-*.md"))
    if not files:
        return 0
    newest = max(files, key=lambda f: f.stat().st_mtime)
    age = _file_age_days(newest)
    return _ramp_fresh(age, p.get("fresh_days", 8), stale=p.get("stale_days", 15))


def signal_dev_digest_freshness(p: dict, ctx: dict) -> int | None:
    inbox = MWM_ROOT / "notes" / "inbox"
    if not inbox.exists():
        return 0
    candidates = list(inbox.glob("*dev-digest*.md")) + list(
        inbox.glob("*dev_digest*.md")
    )
    if not candidates:
        return 0
    newest = max(candidates, key=lambda f: f.stat().st_mtime)
    age = _file_age_days(newest)
    return _ramp_fresh(age, p.get("fresh_days", 3), stale=p.get("stale_days", 7))


def signal_book_summaries_handoff_indexed(p: dict, ctx: dict) -> int | None:
    # proxy via local file count since Qdrant query is heavier
    mdir = MWM_ROOT / "memory"
    archive = mdir / "archive"
    count = sum(1 for _ in mdir.glob("handoff-*.md")) + sum(
        1 for _ in archive.glob("handoff-*.md")
    )
    target = p.get("target_count", 70)
    return min(100, int(count / max(1, target) * 100))


# ----- v3 outcome signals (2026-09-02) -----
# The v2 signals mostly count that an artifact EXISTS (rows, files, grep
# hits); the 09-02 audit showed those saturate on degenerate data (constant
# calibration predictor, dead proposer's leftover files, 0/51 gate accepts).
# The signals below read OUTCOMES against a null: reliability G, keep z-score
# vs a noise bootstrap, mutation persistence, real gate accepts, failed
# units, backend outages, timers that are actually enabled.


def _read_jsonl_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        log.warning("jsonl read failed %s: %s", path, e)
    return rows


def _latest_gstudy(p: dict) -> dict | None:
    rows = _read_jsonl_rows(MWM_ROOT / p.get("jsonl_relpath", "data/sccs/f18_gstudy.jsonl"))
    return rows[-1] if rows else None


def _linear(x: float, lo: float, hi: float) -> int:
    """0 at lo, 100 at hi, clamped, linear between."""
    if hi == lo:
        return 100 if x >= hi else 0
    return int(round(max(0.0, min(1.0, (x - lo) / (hi - lo))) * 100))


def signal_failed_user_units(p: dict, ctx: dict) -> int | None:
    """100 minus `per_unit` per failed mwm-* user unit (D1). Reads the same
    `systemctl --user --failed` the 09-02 audit found 9 units on."""
    try:
        out = subprocess.run(
            ["systemctl", "--user", "--failed", "--plain", "--no-legend"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    prefix = p.get("prefix", "mwm-")
    n = sum(1 for ln in out.stdout.splitlines() if ln.strip().startswith(prefix))
    ctx["failed_user_units"] = n
    return max(0, 100 - int(p.get("per_unit", 12)) * n)


def signal_anomaly_kinds_absent(p: dict, ctx: dict) -> int | None:
    """100 when none of `kinds` appears in anomalies.jsonl within
    `window_days`; minus `per_event` per occurrence (floored at 0)."""
    path = MWM_ROOT / p.get("jsonl_relpath", "data/runners/anomalies.jsonl")
    if not path.exists():
        return None
    kinds = set(p.get("kinds", []))
    cutoff = datetime.now(timezone.utc) - timedelta(days=float(p.get("window_days", 7)))
    n = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not any(f'"{k}"' in line for k in kinds):
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("kind") not in kinds:
                    continue
                try:
                    ts = datetime.fromisoformat(str(r.get("ts", "")).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    n += 1
    except OSError:
        return None
    ctx[f"anomaly_count:{p.get('signal_note', ','.join(sorted(kinds)))}"] = n
    return max(0, 100 - int(p.get("per_event", 25)) * n)


def signal_local_llm_live(p: dict, ctx: dict) -> int | None:
    """Ollama answering on its port (the fallback every weekly loop relies on
    when the Pro Max window is exhausted). 100 up / 0 down; never frozen."""
    import urllib.request

    url = p.get("url", "http://localhost:11434/api/tags")
    try:
        with urllib.request.urlopen(url, timeout=float(p.get("timeout_s", 3))) as r:
            return 100 if r.status == 200 else 0
    except Exception:
        return 0


def signal_gstudy_G(p: dict, ctx: dict) -> int | None:
    """Best F18 reliability coefficient across active skills, linear from
    `lo` (0) to `hi` (100). Source: latest data/sccs/f18_gstudy.jsonl row."""
    row = _latest_gstudy(p)
    if row is None:
        return 0
    exclude = set(p.get("exclude_skills", []))
    gs = [v.get("G", 0.0) for k, v in (row.get("skills") or {}).items() if k not in exclude]
    if not gs:
        return 0
    stat = max(gs) if p.get("aggregate", "max") == "max" else sum(gs) / len(gs)
    ctx["gstudy_G"] = stat
    return _linear(float(stat), float(p.get("lo", 0.30)), float(p.get("hi", 0.55)))


def signal_gstudy_keep_z(p: dict, ctx: dict) -> int | None:
    """z of observed F18 keeps against the null-keep bootstrap through the
    gate named by `which` (legacy floor or honest range). z <= lo → 0,
    z >= hi → 100. A null that never accepts (sd 0) with observed keeps > 0
    cannot be scored on z; that case returns 0 (the keeps happened under a
    gate the null says accepts nothing → they are not evidence)."""
    row = _latest_gstudy(p)
    if row is None:
        return 0
    nk = row.get(p.get("which", "null_keeps_legacy")) or row.get("null_keeps") or {}
    z = nk.get("z")
    ctx["gstudy_keep_z"] = z
    if z is None:
        return 0
    return _linear(float(z), float(p.get("lo", 1.0)), float(p.get("hi", 3.0)))


def signal_gstudy_persistence(p: dict, ctx: dict) -> int | None:
    """Share of applied F18 gains that survived to the next cycle's baseline."""
    row = _latest_gstudy(p)
    if row is None:
        return 0
    pers = row.get("persistence") or {}
    rate = pers.get("persistence_rate")
    ctx["gstudy_persistence"] = rate
    if rate is None:
        return 0
    return int(round(float(rate) * 100))


def signal_gate_real_accepts(p: dict, ctx: dict) -> int | None:
    """mutation_decision rows in `window_days` whose gate verdict was a real
    bound pass (reason in `ok_reasons`), not the naive-delta or
    range-floor artifact. 0 accepts → 0; `target` accepts → 100."""
    path = MWM_ROOT / "data" / "runners" / "anomalies.jsonl"
    if not path.exists():
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=float(p.get("window_days", 30)))
    ok = set(p.get("ok_reasons", ["ok", "heavy_tail_mom_ok"]))
    n = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if '"mutation_decision"' not in line or '"gate_verdict"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    ts = datetime.fromisoformat(str(r.get("ts", "")).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
                gv = r.get("gate_verdict") or (r.get("extra") or {}).get("gate_verdict") or {}
                if r.get("kept") and gv.get("reason") in ok:
                    n += 1
    except OSError:
        return None
    ctx["gate_real_accepts"] = n
    return min(100, int(n / max(1, int(p.get("target", 2))) * 100))


def signal_calibration_predictor_sd(p: dict, ctx: dict) -> int | None:
    """Spread of the first-pass predictor (predicted_score/max_total) in
    judge_calibration.jsonl over `window_days`. A constant predictor (sd≈0,
    the 09-02 finding) carries no calibration information → 0; sd >= `hi`
    → 100."""
    path = MWM_ROOT / p.get("jsonl_relpath", "data/sccs/judge_calibration.jsonl")
    rows = _read_jsonl_rows(path)
    if not rows:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=float(p.get("window_days", 90)))
    xs: list[float] = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(str(r.get("timestamp") or r.get("ts") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        mt = r.get("max_total") or 0
        if mt:
            xs.append(float(r.get("predicted_score") or 0) / float(mt))
    if len(xs) < int(p.get("min_rows", 10)):
        return 0
    mean = sum(xs) / len(xs)
    sd = (sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
    ctx["calibration_predictor_sd"] = round(sd, 4)
    return _linear(sd, 0.0, float(p.get("hi", 0.15)))


def signal_timer_enabled_and_output_fresh(p: dict, ctx: dict) -> int | None:
    """A weekly producer is only credited while its timer is ENABLED and its
    newest output is fresh. Disabled timer → 0 regardless of leftover files
    (the 08-30 proposer kill left three priority-*.md files that the v2
    `file_present` signal kept scoring at 100)."""
    unit = p["timer_unit"]
    try:
        out = subprocess.run(
            ["systemctl", "--user", "is-enabled", unit],
            capture_output=True,
            text=True,
            timeout=5,
        )
        enabled = out.stdout.strip() == "enabled"
    except Exception:
        return None
    if not enabled:
        return 0
    matches = list(MWM_ROOT.glob(p["glob_relpath"]))
    if not matches:
        return 25
    newest = max(matches, key=lambda f: f.stat().st_mtime)
    age = _file_age_days(newest)
    return _ramp_fresh(age, p.get("fresh_days", 8), stale=p.get("stale_days", 21))


def signal_boundary_flux_axes(p: dict, ctx: dict) -> int | None:
    """Share of applicable F19 boundary-flux axes passing on the latest row."""
    rows = _read_jsonl_rows(MWM_ROOT / p.get("jsonl_relpath", "data/sccs/boundary_flux.jsonl"))
    if not rows:
        return 0
    axes = (rows[-1].get("axes") or {}).values()
    applicable = [a for a in axes if a.get("applicable")]
    if not applicable:
        return 0
    passed = sum(1 for a in applicable if a.get("pass"))
    ctx["boundary_flux_axes"] = f"{passed}/{len(applicable)}"
    return int(round(passed / len(applicable) * 100))


# ============================================================
# Registry + dispatcher
# ============================================================

SIGNAL_REGISTRY = {
    # D1
    "cip_fires_landed": signal_cip_fires_landed,
    "automation_chain_active": signal_automation_chain_active,
    "bocpd_subsystem_health": signal_bocpd_subsystem_health,
    "synthesis_freshness": signal_synthesis_freshness,
    "memento_judge_active": signal_memento_judge_active,
    # D2
    "policy_state_rows": signal_policy_state_rows,
    "conformal_cal_rows": signal_conformal_cal_rows,
    "eval_gold_runs": signal_eval_gold_runs,
    "bernstein_gate_fires": signal_bernstein_gate_fires,
    "forward_sufficiency_active": signal_forward_sufficiency_active,
    "honeypot_abstain_rate": signal_honeypot_abstain_rate,
    # D3
    "memento_acceptance_curve": signal_memento_acceptance_curve,
    "file_grep_present": signal_file_grep_present,
    "any_file_grep": signal_any_file_grep,
    "f3_dowhy_status": signal_f3_dowhy_status,
    "f18_dry_run_active": signal_f18_dry_run_active,
    # D4 + reused
    "file_fresh": signal_file_fresh,
    "policy_state_cell_diversity": signal_policy_state_cell_diversity,
    "file_present": signal_file_present,
    "sqlite_recent_positive": signal_sqlite_recent_positive,
    # D5
    "prompt_cache_active": signal_prompt_cache_active,
    "rtk_proxy_live": signal_rtk_proxy_live,
    # v3 outcome signals (2026-09-02)
    "failed_user_units": signal_failed_user_units,
    "anomaly_kinds_absent": signal_anomaly_kinds_absent,
    "local_llm_live": signal_local_llm_live,
    "gstudy_G": signal_gstudy_G,
    "gstudy_keep_z": signal_gstudy_keep_z,
    "gstudy_persistence": signal_gstudy_persistence,
    "gate_real_accepts": signal_gate_real_accepts,
    "calibration_predictor_sd": signal_calibration_predictor_sd,
    "timer_enabled_and_output_fresh": signal_timer_enabled_and_output_fresh,
    "boundary_flux_axes": signal_boundary_flux_axes,
    # D6
    "handoff_files_count": signal_handoff_files_count,
    "cip_synthesis_writeback": signal_cip_synthesis_writeback,
    "dev_digest_freshness": signal_dev_digest_freshness,
    "book_summaries_handoff_indexed": signal_book_summaries_handoff_indexed,
}


def evaluate_dimension(dim: dict, ctx: dict) -> tuple[int | None, list[dict]]:
    """Return (rubric_pct or None if frozen, per-signal trace)."""
    weighted_sum = 0.0
    weight_total = 0.0
    trace = []
    frozen_signals = []
    for sig in dim.get("signals", []):
        name = sig["name"]
        weight = float(sig.get("weight", 0))
        params = sig.get("params", {}) or {}
        sig_id = sig.get("signal_id", name)
        fn = SIGNAL_REGISTRY.get(name)
        if fn is None:
            trace.append(
                {
                    "id": sig_id,
                    "weight": weight,
                    "score": None,
                    "reason": "unknown_signal",
                }
            )
            frozen_signals.append(sig_id)
            continue
        try:
            score = fn(params, ctx)
        except Exception as e:
            log.warning("signal %s raised: %s", sig_id, e)
            score = None
        if score is None:
            frozen_signals.append(sig_id)
            trace.append(
                {"id": sig_id, "weight": weight, "score": None, "reason": "frozen"}
            )
            continue
        score = max(0, min(100, int(score)))
        weighted_sum += score * weight
        weight_total += weight
        trace.append({"id": sig_id, "weight": weight, "score": score})
    if frozen_signals and weight_total < 0.5:
        # too much frozen — overall dim frozen
        return None, trace
    if weight_total == 0:
        return None, trace
    # if some signals frozen but ≥50% weight present, normalize over present weight
    rubric_pct = int(round(weighted_sum / weight_total))
    return rubric_pct, trace


def main():
    parser = argparse.ArgumentParser(description="Recompute selfcalib bar from rubric.")
    parser.add_argument(
        "--write", action="store_true", help="Write proposed JSON + calibration log."
    )
    parser.add_argument("--rubric", default=str(RUBRIC_FILE))
    parser.add_argument("--state", default=str(STATE_FILE))
    parser.add_argument("--out", default=str(PROPOSED_FILE))
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    with open(args.rubric) as f:
        rubric = yaml.safe_load(f)

    state_path = Path(args.state)
    if state_path.exists():
        current_state = json.loads(state_path.read_text())
    else:
        current_state = {"dimensions": []}
    current_by_id = {d["id"]: d for d in current_state.get("dimensions", [])}

    ctx: dict = {}
    out_dims = []
    calibration_rows = []

    print(
        f"\n{'Dim':4} {'Manual':>7} {'Rubric':>7} {'Override':>9} {'Final':>7}  Frozen-or-Notes"
    )
    print("-" * 78)

    for dim in rubric.get("dimensions", []):
        did = dim["id"]
        rubric_pct, trace = evaluate_dimension(dim, ctx)
        cur = current_by_id.get(did, {})
        manual_pct = int(cur.get("pct", 0))
        override = cur.get("pct_override")  # may be None
        frozen_reason = dim.get("frozen_reason")

        if rubric_pct is None:
            final_pct = manual_pct
            note = "rubric frozen → using manual"
        elif override is not None:
            final_pct = int(override)
            gap = final_pct - rubric_pct
            note = f"override active, gap={gap:+d}pp"
            calibration_rows.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "dim": did,
                    "override": final_pct,
                    "rubric": rubric_pct,
                    "gap": gap,
                }
            )
        else:
            final_pct = rubric_pct
            note = ""
        if frozen_reason and override is None and rubric_pct is None:
            note = frozen_reason

        out_dim = dict(cur)
        out_dim.update(
            {
                "id": did,
                "label": dim.get("label", cur.get("label", did)),
                "weight": dim.get("weight", cur.get("weight", 0)),
                "rubric_pct": rubric_pct,
                "pct": final_pct,
                "pct_override": override,
                "frozen_reason": frozen_reason
                if (rubric_pct is None or override is not None)
                else None,
                "signal_trace": trace,
            }
        )
        out_dims.append(out_dim)

        rubric_disp = f"{rubric_pct}" if rubric_pct is not None else "FROZ"
        ovr_disp = f"{int(override)}" if override is not None else "-"
        print(
            f"{did:4} {manual_pct:>7} {rubric_disp:>7} {ovr_disp:>9} {final_pct:>7}  {note}"
        )

    total_w = sum(d["weight"] for d in out_dims) or 1
    rubric_agg = sum(d["weight"] * d["pct"] for d in out_dims) / total_w
    manual_agg = (
        sum(
            d["weight"] * current_by_id.get(d["id"], {}).get("pct", 0) for d in out_dims
        )
        / total_w
    )
    print("-" * 78)
    print(
        f"AGG  {manual_agg:>7.2f} {rubric_agg:>7.2f}  Δ={rubric_agg - manual_agg:+.2f}pp"
    )

    if not args.write:
        print("\n(diff-only mode; pass --write to emit selfcalib_state_proposed.json)")
        return 0

    proposed = {
        "as_of": date.today().isoformat(),
        "target_state": current_state.get("target_state", ""),
        "target_state_no": current_state.get("target_state_no", ""),
        "subtitle": current_state.get("subtitle", ""),
        "dimensions": out_dims,
        "aggregate_pct": round(rubric_agg, 2),
        "rubric_schema_version": rubric.get("schema_version", 1),
    }
    Path(args.out).write_text(json.dumps(proposed, indent=2))
    print(f"\nwrote {args.out}")

    # Mirror to web/ so the brief's rsync pipeline picks it up at next refresh
    # (or when builder.py runs end-of-cycle). Served at brief.mwmai.no/selfcalib_proposed.json.
    try:
        WEB_PROPOSED_FILE.parent.mkdir(parents=True, exist_ok=True)
        WEB_PROPOSED_FILE.write_text(json.dumps(proposed, indent=2))
        print(f"wrote {WEB_PROPOSED_FILE}")
    except Exception as e:
        log.warning("web mirror write failed: %s", e)

    if calibration_rows:
        CALIBRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CALIBRATION_LOG.open("a") as f:
            for row in calibration_rows:
                f.write(json.dumps(row) + "\n")
        print(f"appended {len(calibration_rows)} calibration rows to {CALIBRATION_LOG}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
