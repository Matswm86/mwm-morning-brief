# Morning Brief

Daily trader's dashboard at [brief.mwmai.no](https://brief.mwmai.no/).

Builds a single-page briefing (`web/brief.json` + `web/index.html`) from
local state + public APIs + Groq-summarised news, then rsyncs the `web/`
tree to the Hetzner VPS.

## Layout

```
morning-brief/
├── builder.py           # orchestrator — fetch, summarise, atomic write, rsync
├── config.py            # env/paths (reads ~/MWM-AI/.env)
├── schema.py            # brief.json shape + empty-section helpers
├── strategy.py          # regime → strategy picker (ORB / LiqSweep / FLAT)
├── llm.py               # Groq summarisation wrapper (reuses core/llm_backends)
├── http_util.py         # shared requests.get wrapper
├── bar_refresh.sh       # 5-min MNQ candle refresh + rsync
├── fetchers/            # per-section fetchers (market, system, research, …)
├── systemd/             # user-level timers + services
└── web/                 # rsync'd to VPS
    ├── index.html
    └── assets/          # style.css, app.js, chart.js, lightweight-charts.js,
                         # tracker.js (live trades), backtest_stats.js (strategy perf)
```

Runtime outputs (`web/brief.json`, `web/bars_mnq.json`, `logs/`) are
gitignored — they're regenerated each build.

## Schedule (Europe/Oslo)

| When | Unit |
|---|---|
| every 5 min Mon–Fri | `mwm-brief-bars-refresh.timer` → MNQ candles (project-x-py primary, Yahoo fallback) |
| 05:30 + 17:30 UTC | `mwm-morning-brief.timer` → full rebuild + rsync (12h cadence so selfcalib + live trades stay fresh) |
| 08:15 Mon–Fri | `mwm-morning-brief-post-ldn.timer` → rebuild after LDN market-detector fires (same-day LDN tile) |
| 15:00 Mon–Fri | `mwm-morning-brief-post-ny.timer` → rebuild after NY market-detector fires (same-day NY tile) |
| daily | `mwm-brief-regime.timer` → regime monitor refresh (VIX chart + 4-row regime panel) |

## Build manually

```bash
cd ~/services/morning-brief
python3 builder.py                 # build + rsync
python3 builder.py --no-llm        # skip Groq
python3 builder.py --dry-run       # stdout only
python3 builder.py --no-deploy     # build locally, don't rsync
```

## Dependencies

Python 3.11, `requests`, `pandas` (via the shared `projects/mwm-trading`
venv is fine). Also reads `~/MWM-AI/core/llm_backends.py` for the Groq
client.

## Quality layer (Memento)

All Groq-summarised bullets pass through `core/memento/compress_with_judge` before
being written to `brief.json`. Five deterministic checks run first (JSONSchema,
URL provenance, source_idx presence, lede length, bullet length), then an LLM judge
scores the output on a rubric. Bullets that fail are compressed/rejected before rsync.
Requires `source_idx` on every bullet (wired in `llm.py` 2026-04-21).

## Self-calibration progress (SCCS-tracked)

The hero's "Self-calibrating research-and-trading organism" bar is a **6-segment
weighted progress readout** of how far the surrounding system is from full
self-calibration. Source of truth = `selfcalib_state.json` (hand-tuned pcts,
weights, keywords). On every build, `fetchers/selfcalib.py` enriches with
freshness signals (`as_of`, `last_shipped` per dim from handoff filename
scan, auto-flipped `status_badge`) and writes `web/selfcalib.json` atomically.

Pcts are **not auto-bumped** — they're revised manually after CIP weekly review or
when a master-queue milestone closes. See [`handoff-brief-selfcalib-shipped-2026-04-24.md`](https://github.com/Matswm86/mwm-infrastructure/blob/master/memory/handoff-brief-selfcalib-shipped-2026-04-24.md)
for the design rationale (38.25% honest baseline beats 70% vibes).

**Current aggregate (2026-04-27): 54.25%** — D1 Closed-loop 97 · D2 Outcome-grounded 50 · D3 Bounded self-mod 60 · D4 Autonomous prio 13 · D5 Cost gov 35 · D6 Continuity 65.
SCCS Foundation track milestones M0 (F1 policy_state on all 5 entry points) and
M1 (F2 ADWIN + CIP signal #14) closed 04-26→04-27; F4 Empirical Bernstein gate
wired into CIP commit path; F4.5 Conformal Phase 1 cal-data logger live.

## SCCS F1 — policy_state logging

Each build records one row to `~/MWM-AI/data/sccs/policy_state.db` with
`entry_point=morning_brief`, `regime_label`, `rubric_weights` (strategy
picker decision), `model_tier`, and `retrieval_config` (sections + LLM toggles).
Best-effort — missing `sccs` package or DB errors are logged at DEBUG and never
break the build. Disable with `SCCS_OFF=1`. See `core/sccs/` in the
[`mwm-infrastructure`](https://github.com/Matswm86/mwm-infrastructure) repo.

Env (from `~/MWM-AI/.env`):

- `GROQ_API_KEY` — summariser (openai/gpt-oss-120b → llama-3.3-70b fallback)
- `FINNHUB_API_KEY` — market news
- `FRED_API_KEY` — macro
- `BRIEF_VPS_TARGET` — rsync dest (e.g. `user@host:/srv/brief`)
- `PROJECT_X_API_KEY` / `PROJECT_X_USERNAME` / `PROJECT_X_ACCOUNT_ID` — from
  `projects/mwm-trading/.env`, used by `trade_tracker` for live trade counts

## Sources

- **Market**: project-x-py CME real-time bars (MNQ M26, zero delay) + Yahoo quotes (NQ=F, ES=F, GC=F, ^VIX, ^TNX, DX-Y.NYB) + Finnhub
- **Regime**: local `data/market_regime/latest_{ldn,ny}.json` written by
  `market_detector` package (see `projects/mwm-trading/`); long-term VIX chart
  (2012+) + 4-row regime panel (trend/vol/credit/tripwires) + edge badge (green/amber/red)
  via `fetchers/regime_monitor.py` + `fetchers/regime.py`
- **Trade Environment**: `trade_guard`, `contextualize_macro`, `check_orb_handoff_status`
  (market-news Track B tools) — verdict + risk bars + ORB handoff via `fetchers/trade_guard_daily.py`
- **Live Trades**: today + this-week trade counts (W/L split) from TopstepX practice account
  `19907662` via `fetchers/trade_tracker.py` — `/api/Trade/search`, 4h disk cache at
  `data/trade_tracker_cache/`. Auth reads `PROJECT_X_API_KEY` + `PROJECT_X_USERNAME` from
  `projects/mwm-trading/.env`.
- **Strategy Performance**: iFVG LiqSweep v10 (arm=12) + ORB layered backtest stats
  normalized to $50k / 2ct MNQ reference (ORB scaled 5ct/$1M → 2ct/$50k by factor 0.4) via
  `fetchers/backtest_stats.py`. Reads
  `data/backtest/results/liqsweep_v10/v10_arm12_confirm_summary.json` and
  `data/backtest/results/orb_layered/layer3_bucket945_orb110_tueoff_summary.json`.
- **Geopolitics / Tech / Research**: arXiv q-fin + GDELT (Obsidian inbox removed 2026-04-21 — privacy fix)
- **System**: docker ps · systemd user units · VPS pings · nightly diff review
