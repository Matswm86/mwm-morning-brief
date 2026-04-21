"""Thin wrapper around core/llm_backends for per-section summarisation.

Reuses the task-routed Groq/Ollama client so API-key handling, reasoning-
model overhead, <think> stripping, and fallback chain stay centralised.

Summarisation runs through core/memento (iterative compress-with-judge,
Microsoft Research 2026). Paper-reported 28%->92% pass-rate lift on a
comparable rubric. Set BRIEF_MEMENTO=0 in env to bypass the judge loop
and restore single-shot Groq summarisation (for A/B testing).
"""
from __future__ import annotations
import json
import logging
import os
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

try:
    from memento import (  # type: ignore
        MORNING_BRIEF_CHECKS,
        CompressionResult,
        compress_with_judge,
        load_rubric,
    )
    _RUBRIC = load_rubric("morning_brief")
    _CHECKS = list(MORNING_BRIEF_CHECKS)
except Exception as e:  # pragma: no cover
    compress_with_judge = None  # type: ignore
    _RUBRIC = None
    _CHECKS = None
    logging.getLogger("morning-brief.llm").warning("memento unavailable: %s", e)

log = logging.getLogger("morning-brief.llm")

USE_MEMENTO = os.environ.get("BRIEF_MEMENTO", "1") != "0"

SUMMARY_SYSTEM = (
    "You are the editor of a trader's morning briefing. "
    "Condense the provided items into a short lede (one sentence, ≤22 words, "
    "crisp and factual) and 3–5 bullet points. Each bullet has a short "
    "headline (≤6 words) and a body (≤22 words). Prefer numbers, names, and "
    "concrete facts over adjectives. Never invent items not in the input. "
    "Every bullet MUST include an integer `source_idx` equal to the 1-based "
    "number of the input item it was derived from. If a bullet fuses two "
    "items, pick the most load-bearing item's number. "
    "Reply with JSON only, matching this schema exactly: "
    '{"lede": "...", "bullets": [{"headline": "...", "body": "...", "url": "...", "source_idx": 1}]}'
)


def summarise(section_label: str, items: list[dict], max_bullets: int = 5) -> dict:
    """Turn raw fetcher items into {lede, bullets}. Fail-open to raw items.

    Path A (default): core/memento compress-with-judge loop, up to 2
    refinements against the morning_brief rubric. Deterministic checks
    (URL provenance, source_idx, bullet/lede length) run BEFORE the LLM
    judge and short-circuit failed iterations with targeted feedback.
    Path B (BRIEF_MEMENTO=0, or memento import failed): legacy single-shot.
    """
    if not items:
        return {"lede": "", "bullets": []}
    if _llm_generate is None:
        return _fallback(items, max_bullets)

    user_prompt = _render_prompt(section_label, items, max_bullets)

    if USE_MEMENTO and compress_with_judge is not None and _RUBRIC is not None:
        text = _run_memento(section_label, user_prompt, num_items=len(items[:30]))
    else:
        text = _run_single_shot(user_prompt)

    if not text or not text.strip():
        return _fallback(items, max_bullets)
    return _parse_brief_json(text, items, max_bullets)


def _run_memento(section_label: str, user_prompt: str, *, num_items: int) -> str:
    """Iterative compress-with-judge loop. Returns best candidate text."""

    def compressor(feedback_suffix: str):
        prompt = user_prompt + feedback_suffix if feedback_suffix else user_prompt
        return _llm_generate(
            system_prompt=SUMMARY_SYSTEM,
            user_prompt=prompt,
            task=SUMMARY_MODEL_TASK,
            max_tokens=900,
            temperature=0.2,
        )

    def judge_llm(*, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float):
        # Bulk tier (llama-3.1-8b-instant) for the judge: the task is
        # rubric-scoring over ~2k input tokens, which 8b handles fine and
        # avoids contention with the compressor on the reason-tier 120b.
        return _llm_generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task="bulk",
            max_tokens=max_tokens,
            temperature=temperature,
        )

    try:
        result: CompressionResult = compress_with_judge(  # type: ignore[misc]
            input_context=user_prompt,
            rubric=_RUBRIC,
            compressor_fn=compressor,
            llm_fn=judge_llm,
            max_iterations=2,
            checks=_CHECKS,
            check_meta={"num_items": num_items},
        )
    except Exception as e:
        log.warning("%s memento loop failed, falling back single-shot: %s", section_label, e)
        return _run_single_shot(user_prompt)

    checks_info = ""
    if result.check_failures:
        checks_info = f" checks_failed={len(result.check_failures)}"
    log.info(
        "%s memento: accepted=%s iters=%d score=%d/%d backend=%s%s",
        section_label, result.accepted, result.iterations,
        result.best_score, _RUBRIC.max_total, result.compressor_backend,
        checks_info,
    )
    return result.text


def _run_single_shot(user_prompt: str) -> str:
    try:
        result = _llm_generate(
            system_prompt=SUMMARY_SYSTEM,
            user_prompt=user_prompt,
            task=SUMMARY_MODEL_TASK,
            max_tokens=900,
            temperature=0.2,
        )
        return getattr(result, "text", "") or ""
    except Exception as e:
        log.warning("single-shot summarise failed: %s", e)
        return ""


def _parse_brief_json(text: str, items: list[dict], max_bullets: int) -> dict:
    data = _extract_json(text)
    if not isinstance(data, dict) or "bullets" not in data:
        return _fallback(items, max_bullets)
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
        src_idx = b.get("source_idx")
        try:
            if src_idx is not None and 1 <= int(src_idx) <= len(items):
                out["source_idx"] = int(src_idx)
        except (TypeError, ValueError):
            pass
        cleaned.append(out)
    lede = str(data.get("lede", "")).strip()[:240]
    return {"lede": lede, "bullets": cleaned}


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
