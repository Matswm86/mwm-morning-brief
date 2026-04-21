#!/usr/bin/env bash
# Refresh the MNQ bars for the chart. Primary path: project-x-py (CME
# real-time via ProjectX gateway). Fallback: Yahoo (15-min delayed).
# CME Globex MNQ runs 23x5, so the systemd timer fires every 5 min Mon-Fri.
set -euo pipefail

cd "$(dirname "$0")"

PXPY="/home/mats/MWM-AI/projects/mwm-trading/.venv/bin/python"
YAHOO="/usr/bin/python3.11"
OUT="web/bars_mnq.json"

ok=false
if [[ -x "$PXPY" ]]; then
  if "$PXPY" -m fetchers.bars_pxpy --interval 5 --days 1 --write "$OUT"; then
    ok=true
  else
    echo "bars_pxpy failed (rc=$?); falling back to Yahoo" >&2
  fi
else
  echo "project-x-py venv missing at $PXPY; using Yahoo" >&2
fi

if ! $ok; then
  "$YAHOO" -m fetchers.bars --interval 5m --range 1d --write "$OUT"
fi

rsync -az "$OUT" mats@204.168.244.173:/var/www/brief/bars_mnq.json
