#!/usr/bin/env python3
"""A/B test: single-shot vs memento judge-loop on live research items.

Pulls today's research fetcher output, runs both paths, prints side-by-side
JSON + a diff summary. Does NOT touch brief.json. Exit 0 always.
"""
from __future__ import annotations
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from fetchers import research as f_research
import llm


def _run(label: str, items: list[dict]) -> dict:
    print(f"\n=== {label} ===", flush=True)
    out = llm.summarise("Research", items, max_bullets=5)
    print(json.dumps(out, indent=2, ensure_ascii=False), flush=True)
    return out


def main() -> int:
    raw = f_research.fetch()
    items = raw.get("items") or []
    print(f"research fetcher: {len(items)} items, source={raw.get('source')}")
    if not items:
        print("no items; cannot A/B")
        return 0

    os.environ["BRIEF_MEMENTO"] = "0"
    llm.USE_MEMENTO = False
    baseline = _run("BASELINE (single-shot)", items)

    os.environ["BRIEF_MEMENTO"] = "1"
    llm.USE_MEMENTO = True
    memento = _run("MEMENTO (judge-loop max 2 iters)", items)

    print("\n=== DIFF SUMMARY ===")
    b_n = len(baseline.get("bullets") or [])
    m_n = len(memento.get("bullets") or [])
    b_lede = (baseline.get("lede") or "").strip()
    m_lede = (memento.get("lede") or "").strip()
    print(f"bullets: baseline={b_n}  memento={m_n}")
    print(f"lede baseline: {b_lede!r}")
    print(f"lede memento:  {m_lede!r}")
    print(f"lede changed: {b_lede != m_lede}")

    # Per-bullet headline compare
    b_heads = [b.get("headline", "") for b in (baseline.get("bullets") or [])]
    m_heads = [b.get("headline", "") for b in (memento.get("bullets") or [])]
    changed = sum(1 for a, b in zip(b_heads, m_heads) if a != b) + abs(len(b_heads) - len(m_heads))
    print(f"headline diffs: {changed}/{max(len(b_heads), len(m_heads))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
