"""Thin wrapper around core/llm_backends for per-section summarisation.

Reuses the task-routed Groq/Ollama client so API-key handling, reasoning-
model overhead, <think> stripping, and fallback chain stay centralised.
"""
from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from typing import Any

from config import MWM_ROOT, SUMMARY_MODEL_TASK

sys.path.insert(0, str(MWM_ROOT / "core"))
try:
    from llm_backends import generate as _llm_generate  # type: ignore
except Exception as e:  # pragma: no cover
    _llm_generate = None
    logging.getLogger("morning-brief.llm").warning("llm_backends unavailable: %s", e)

log = logging.getLogger("morning-brief.llm")

SUMMARY_SYSTEM = (
    "You are the editor of a trader's morning briefing. "
    "Condense the provided items into a short lede (one sentence, ≤22 words, "
    "crisp and factual) and 3–5 bullet points. Each bullet has a short "
    "headline (≤6 words) and a body (≤22 words). Prefer numbers, names, and "
    "concrete facts over adjectives. Never invent items not in the input. "
    "Reply with JSON only, matching this schema exactly: "
    '{"lede": "...", "bullets": [{"headline": "...", "body": "...", "url": "..." }]}'
)


def summarise(section_label: str, items: list[dict], max_bullets: int = 5) -> dict:
    """Turn raw fetcher items into {lede, bullets} via Groq. Fail-open to raw."""
    if not items:
        return {"lede": "", "bullets": []}
    if _llm_generate is None:
        return _fallback(items, max_bullets)

    user_prompt = _render_prompt(section_label, items, max_bullets)
    try:
        result = _llm_generate(
            system_prompt=SUMMARY_SYSTEM,
            user_prompt=user_prompt,
            task=SUMMARY_MODEL_TASK,
            max_tokens=900,
            temperature=0.2,
        )
        text = getattr(result, "text", "") or ""
        if not text.strip():
            return _fallback(items, max_bullets)
        data = _extract_json(text)
        if not isinstance(data, dict) or "bullets" not in data:
            return _fallback(items, max_bullets)
        # Trim + validate
        bullets = data.get("bullets") or []
        if not isinstance(bullets, list):
            bullets = []
        cleaned: list[dict] = []
        for b in bullets[:max_bullets]:
            if not isinstance(b, dict):
                continue
            hd = str(b.get("headline", "")).strip()[:120]
            bd = str(b.get("body", "")).strip()[:280]
            url = str(b.get("url", "")).strip()[:400]
            if not hd and not bd:
                continue
            out = {"headline": hd, "body": bd}
            if url.startswith("http"):
                out["url"] = url
            cleaned.append(out)
        lede = str(data.get("lede", "")).strip()[:240]
        return {"lede": lede, "bullets": cleaned}
    except Exception as e:
        log.warning("%s summarise failed: %s", section_label, e)
        return _fallback(items, max_bullets)


def _fallback(items: list[dict], max_bullets: int) -> dict:
    out: list[dict] = []
    for it in items[:max_bullets]:
        hd = str(it.get("headline") or it.get("title") or "").strip()[:120]
        bd = str(it.get("body") or it.get("summary") or it.get("description") or "").strip()[:280]
        if not hd and not bd:
            continue
        row = {"headline": hd, "body": bd}
        url = str(it.get("url") or "").strip()
        if url.startswith("http"):
            row["url"] = url
        out.append(row)
    return {"lede": "", "bullets": out}


def _render_prompt(label: str, items: list[dict], max_bullets: int) -> str:
    lines = [f"Section: {label}", f"Target: lede + up to {max_bullets} bullets.", "", "Items:"]
    for i, it in enumerate(items[:30], 1):
        hd = it.get("headline") or it.get("title") or ""
        bd = it.get("body") or it.get("summary") or it.get("description") or ""
        url = it.get("url") or ""
        src = it.get("source") or ""
        lines.append(f"{i}. [{src}] {hd}")
        if bd:
            lines.append(f"   {bd[:400]}")
        if url:
            lines.append(f"   url: {url}")
    lines.append("")
    lines.append("Return JSON only, no prose or code fences.")
    return "\n".join(lines)


def _extract_json(text: str) -> Any:
    """Best-effort JSON extraction from model output."""
    s = text.strip()
    if s.startswith("```"):
        # strip ```json ... ```
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines)
    try:
        return json.loads(s)
    except Exception:
        # Try to locate first {...} balanced block
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(s[start : end + 1])
            except Exception:
                return None
        return None
