"""System health fetcher — docker + systemd user units + CIP + diff-review tail + 24h git commit rollup."""
from __future__ import annotations
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from config import MWM_ROOT, CIP_DIR, INBOX_DIR
from http_util import get_text

# Repos scanned for the "commits last 24h" tracker. Each is either an
# absolute path or relative to MWM_ROOT. Non-existent paths are skipped
# silently so adding/removing a project doesn't break the builder.
GIT_REPOS: list[tuple[str, Path]] = [
    ("mwm-trading",     MWM_ROOT / "projects" / "mwm-trading"),
    ("mwm-creative",    MWM_ROOT / "projects" / "mwm-creative"),
    ("mwm-saas",        MWM_ROOT / "projects" / "mwm-saas"),
    ("mwm-sentinel",    MWM_ROOT / "projects" / "mwm-sentinel"),
    ("mwm-lab",         MWM_ROOT / "projects" / "mwm-lab"),
    ("mwm-infra",       MWM_ROOT / "mwm-infrastructure"),
    ("morning-brief",   Path.home() / "services" / "morning-brief"),
    ("oso-sync",        MWM_ROOT / "projects" / "oso-sync"),
    ("vibeos",          MWM_ROOT / "projects" / "vibeos"),
    ("knowledge-viz",   MWM_ROOT / "projects" / "knowledge-viz"),
]

log = logging.getLogger("morning-brief.system")

SYSTEMD_UNITS = [
    "mwm-webhook-orb.service",
    "mwm-market-news-webhook-orb.service",
    "mwm-market-news-verify-predictions.timer",
    "mwm-market-detector-ldn.timer",
    "mwm-market-detector-ny.timer",
    "mwm-brief-bars-refresh.timer",
]

VPS_PING_URLS = [
    ("mwmai.no",   "https://mwmai.no/"),
    ("columbus",   "https://columbus.mwmai.no/"),
    ("pytor",      "https://pytor.mwmai.no/"),
]


def _docker_ps() -> list[dict]:
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--format", "{{.Names}}|{{.Status}}"],
            text=True, timeout=5,
        )
    except Exception as e:
        log.debug("docker ps failed: %s", e)
        return [{"headline": "Docker", "body": "unreachable from builder", "source": "docker"}]
    items = []
    for line in out.strip().splitlines():
        if "|" not in line:
            continue
        name, status = line.split("|", 1)
        ok = status.startswith("Up")
        items.append({
            "headline": f"{name} {'up' if ok else 'DOWN'}",
            "body": status[:120],
            "source": "docker",
        })
    return items


def _systemd_status(unit: str) -> dict | None:
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "is-active", unit],
            text=True, timeout=4,
        ).strip()
    except subprocess.CalledProcessError as e:
        out = (e.output or "").strip() or "inactive"
    except Exception:
        return None
    return {
        "headline": f"{unit.rsplit('.', 1)[0]} {out}",
        "body": "systemd user unit",
        "source": "systemd",
    }


def _vps_ping() -> list[dict]:
    import requests
    items = []
    for label, url in VPS_PING_URLS:
        try:
            r = requests.head(url, timeout=6, allow_redirects=True)
            ok = 200 <= r.status_code < 400
            items.append({
                "headline": f"{label} {r.status_code}",
                "body": url,
                "source": "vps",
            })
        except Exception as e:
            items.append({
                "headline": f"{label} DOWN",
                "body": str(e)[:140],
                "source": "vps",
            })
    return items


def _cip_tail() -> list[dict]:
    log_path = CIP_DIR / "cip-outcomes.jsonl"
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()[-5:]
    except Exception:
        return []
    out = []
    for line in lines:
        if not line.strip():
            continue
        out.append({
            "headline": "CIP outcome",
            "body": line[:260],
            "source": "cip",
        })
    return out


def _github_commits_24h() -> dict | None:
    """Rollup of commits landed in the last 24h across known mwm-* repos.

    Uses local git log (not GitHub API) — every repo is checked out
    locally and nightly sync pushes to origin, so the local count is
    the authoritative commit count. Repos not on disk are skipped.
    """
    totals: list[tuple[str, int]] = []
    grand = 0
    for name, path in GIT_REPOS:
        if not (path / ".git").exists():
            continue
        try:
            out = subprocess.check_output(
                ["git", "-C", str(path), "log", "--since=24 hours ago",
                 "--pretty=format:%h"],
                text=True, timeout=5, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.debug("git log %s failed: %s", name, e)
            continue
        n = sum(1 for ln in out.splitlines() if ln.strip())
        if n > 0:
            totals.append((name, n))
            grand += n
    if not totals and grand == 0:
        return {
            "headline": "GitHub 24h: 0 commits",
            "body": "no repo activity in the last 24h",
            "source": "git",
        }
    # Sort busiest first, cap body length
    totals.sort(key=lambda x: -x[1])
    repo_list = ", ".join(f"{n} {c}" for n, c in totals)
    return {
        "headline": f"GitHub 24h: {grand} commits across {len(totals)} repos",
        "body": repo_list[:260],
        "source": "git",
    }


def _diff_review_tail(cap: int = 1) -> list[dict]:
    """Pick up the latest daily-diff-review note(s) — nightly codebase audit."""
    if not INBOX_DIR.exists():
        return []
    hits = sorted(INBOX_DIR.glob("daily-diff-review-*.md"),
                  key=lambda p: p.stat().st_mtime, reverse=True)[:cap]
    out: list[dict] = []
    for p in hits:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        head_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        headline = head_m.group(1).strip() if head_m else p.stem
        body = ""
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para or para.startswith("#") or para.startswith("---"):
                continue
            body = re.sub(r"\s+", " ", para)[:260]
            break
        out.append({
            "headline": headline[:180],
            "body": body,
            "source": "diff-review",
        })
    return out


def _summarise_items(items: list[dict], label: str) -> dict:
    """Collapse N items into one headline with a compact body."""
    lines = [it.get("headline", "") for it in items if it.get("headline")]
    ok = sum(1 for ln in lines if " up" in ln or " active" in ln or ln.endswith(" 200"))
    total = len(lines)
    return {
        "headline": f"{label}: {ok}/{total} healthy",
        "body": ", ".join(lines)[:240],
        "source": items[0].get("source", "") if items else "",
    }


def fetch() -> dict:
    # Ordered so the first 5 bullets (raw-mode cap) carry the signals the
    # user cares about most: github activity, latest diff review, CIP tail,
    # then infra rollups.
    items: list[dict] = []
    gh = _github_commits_24h()
    if gh:
        items.append(gh)
    items.extend(_diff_review_tail())  # cap=1 default
    items.extend(_cip_tail()[:1])
    docker = _docker_ps()
    if docker:
        items.append(_summarise_items(docker, "Containers"))
    unit_items = [s for s in (_systemd_status(u) for u in SYSTEMD_UNITS) if s]
    if unit_items:
        items.append(_summarise_items(unit_items, "Services"))
    vps = _vps_ping()
    if vps:
        items.append(_summarise_items(vps, "Sites"))

    # Overall status: err if any DOWN, warn if any "inactive"/"failed", else ok
    status = "ok"
    blob = " ".join((i.get("headline", "") + " " + i.get("body", "")) for i in items).lower()
    if "down" in blob or "failed" in blob:
        status = "err"
    elif "inactive" in blob or "unknown" in blob:
        status = "warn"

    return {
        "items": items,
        "count": len(items),
        "source": "docker · systemd · VPS ping",
        "status": status,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
