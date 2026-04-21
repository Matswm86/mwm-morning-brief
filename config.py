"""Morning-brief config — env loading + paths.

Env is read from ~/MWM-AI/.env (single source of truth). Required keys:
  GROQ_API_KEY  FINNHUB_API_KEY  FRED_API_KEY  ORB_REGIME_URL

Optional:
  BRIEF_OUT_DIR     default ~/services/morning-brief/web
  BRIEF_VPS_TARGET  rsync target, e.g. user@vps:/srv/brief
  GROQ_MODEL_BRIEF  override summariser model (default openai/gpt-oss-120b)
"""
from __future__ import annotations
import os
from pathlib import Path

HOME = Path.home()
MWM_ROOT = HOME / "MWM-AI"
ENV_FILE = MWM_ROOT / ".env"

if ENV_FILE.exists():
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
ORB_REGIME_URL = os.environ.get("ORB_REGIME_URL", "https://mwmai.no/orb-regime").strip()

VPS_TARGET = os.environ.get("BRIEF_VPS_TARGET", "").strip()  # user@host:/srv/brief
GROQ_MODEL_BRIEF = os.environ.get("GROQ_MODEL_BRIEF", "openai/gpt-oss-120b")

SUMMARY_MODEL_TASK = "reason"
USER_AGENT = "mwm-morning-brief/0.1 (+https://mwmai.no)"

SECTION_TIMEOUT_SEC = 45
HTTP_TIMEOUT_SEC = 15

SYNTHESIS_DIR = MWM_ROOT / "data" / "synthesis"
INBOX_DIR = MWM_ROOT / "notes" / "inbox"
CIP_DIR = MWM_ROOT / "data" / "cip"
