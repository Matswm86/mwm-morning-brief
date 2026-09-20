"""Morning-brief config — env loading + paths.

Env is read from ~/MWM/.env (single source of truth). Required keys:
  GROQ_API_KEY  FINNHUB_API_KEY  FRED_API_KEY

Optional:
  BRIEF_OUT_DIR     default ~/MWM/projects/mwm-morning-brief/web
  BRIEF_VPS_TARGET  rsync target, e.g. user@vps:/srv/brief
  GROQ_MODEL_BRIEF  override summariser model (default openai/gpt-oss-120b)

Note: ORB_REGIME_URL is no longer used. Market Detector v3 writes local
files (data/market_regime/latest_{ldn,ny}.json) which fetchers/regime.py
reads directly. TradingView v2.5 webhook decommissioned 2026-04-27.
"""
from __future__ import annotations
import os
from pathlib import Path

HOME = Path.home()
MWM_ROOT = HOME / "MWM"
ENV_FILE = MWM_ROOT / ".env"

if not ENV_FILE.exists():
    # A missing .env silently disabled deploy + LLM for 6 days (2026-09-14..20).
    raise FileNotFoundError(f"morning-brief: env file missing: {ENV_FILE}")
else:
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SERVICE_ROOT = Path(__file__).resolve().parent
WEB_DIR = Path(os.environ.get("BRIEF_OUT_DIR", SERVICE_ROOT / "web")).resolve()
BRIEF_JSON = WEB_DIR / "brief.json"
LOG_DIR = SERVICE_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "").strip()
FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
# ORB_REGIME_URL: deprecated 2026-04-27 (TradingView decommissioned).
# Kept as empty default so legacy fetcher import doesn't break; regime.py
# now reads ~/MWM/projects/mwm-trading/data/market_regime/*.json instead.
ORB_REGIME_URL = os.environ.get("ORB_REGIME_URL", "").strip()

VPS_TARGET = os.environ.get("BRIEF_VPS_TARGET", "").strip()  # user@host:/srv/brief
GROQ_MODEL_BRIEF = os.environ.get("GROQ_MODEL_BRIEF", "openai/gpt-oss-120b")

SUMMARY_MODEL_TASK = "reason"
USER_AGENT = "mwm-morning-brief/0.1 (+https://mwmai.no)"

SECTION_TIMEOUT_SEC = 45
HTTP_TIMEOUT_SEC = 15

SYNTHESIS_DIR = MWM_ROOT / "data" / "synthesis"
INBOX_DIR = MWM_ROOT / "notes" / "inbox"
CIP_DIR = MWM_ROOT / "data" / "cip"
