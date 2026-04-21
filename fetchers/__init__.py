"""Per-section fetchers.

Each fetcher exposes `fetch()` returning either:
  - list[dict]  — raw items that the orchestrator will summarise via llm.summarise
  - dict        — pre-shaped section payload (skip Groq pass)

Raw-item dict keys (at least one of):
  headline/title, body/summary/description, url, source
"""
