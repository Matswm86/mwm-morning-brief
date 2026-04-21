#!/usr/bin/env python3
"""Inspect raw judge output to diagnose parse failures."""
from __future__ import annotations
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import llm  # noqa: F401 — triggers path insertion for core/

sys.path.insert(0, str(Path.home() / "MWM-AI" / "core"))

from llm_backends import generate  # type: ignore
from memento import load_rubric  # type: ignore
from memento.judge import judge  # type: ignore

rubric = load_rubric("morning_brief")

# Fake a compressor output and a matching input
candidate = json.dumps({
    "lede": "VIX closed at 15.2, down 3.8%, as SPX gained 0.6% on soft PPI.",
    "bullets": [
        {"headline": "VIX slips sub-16", "body": "VIX 15.2 down 3.8%; realized vol tracks near 10%.",
         "url": "https://example.com/vix"},
        {"headline": "PPI lighter than expected", "body": "US PPI 0.1% MoM vs 0.3% consensus; services inflation cooling.",
         "url": "https://example.com/ppi"},
    ]
})
input_context = (
    "Items:\n"
    "1. [markets] VIX close 15.2 (-3.8%)\n   Cboe VIX closed 15.2, a 3.8% drop.\n"
    "2. [macro] US PPI 0.1% MoM\n   PPI reading below 0.3% consensus.\n"
)

print("--- JUDGE RAW OUTPUT ---")
result = judge(candidate, input_context, rubric, generate)
print("scores:", result.scores)
print("total:", result.total)
print("accept:", result.accept)
print("feedback:", result.feedback)
print("parse_error:", result.parse_error)
print("dims_covered:", result.dimensions_covered)
print("backend:", result.backend)
print()
print("--- RAW TEXT (first 800 chars) ---")
print((result.raw_text or "")[:800])
