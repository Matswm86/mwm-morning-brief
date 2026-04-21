"""System health fetcher — docker + systemd user units + CIP + diff-review tail."""
from __future__ import annotations
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from config import MWM_ROOT, CIP_DIR, INBOX_DIR
from http_util import get_text

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


def _diff_review_tail(cap: int = 2) -> list[dict]:
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
    # Ordered so the first 5 bullets (raw mode) always carry the signal the
    # user cares about most: nightly diff review, then CIP, then rollups.
    items: list[dict] = []
    items.extend(_diff_review_tail())
    items.extend(_cip_tail()[:2])
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
