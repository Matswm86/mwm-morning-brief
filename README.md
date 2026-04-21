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
    └── assets/          # style.css, app.js, chart.js, lightweight-charts.js
```

Runtime outputs (`web/brief.json`, `web/bars_mnq.json`, `logs/`) are
gitignored — they're regenerated each build.

## Schedule (Europe/Oslo)

| When | Unit |
|---|---|
| every 5 min Mon–Fri | `mwm-brief-bars-refresh.timer` → MNQ candles |
| 07:30 daily | `mwm-morning-brief.timer` → full rebuild + rsync |

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

Env (from `~/MWM-AI/.env`):

- `GROQ_API_KEY` — summariser (openai/gpt-oss-120b → llama-3.3-70b fallback)
- `FINNHUB_API_KEY` — market news
- `FRED_API_KEY` — macro
- `BRIEF_VPS_TARGET` — rsync dest (e.g. `user@host:/srv/brief`)

## Sources

- **Market**: Yahoo quotes (NQ=F, ES=F, GC=F, ^VIX, ^TNX, DX-Y.NYB) + Finnhub
- **Regime**: local `data/market_regime/latest_{ldn,ny}.json` written by
  `market_detector` package (see `projects/mwm-trading/`)
- **Geopolitics / Tech / Research**: inbox notes + arXiv q-fin + GDELT
- **System**: docker ps · systemd user units · VPS pings · nightly diff review
