#!/usr/bin/env bash
# Refresh MNQ + MGC bars for the charts. Primary path: project-x-py (CME
# real-time via ProjectX gateway, PRAC account from mwm-trading/.env).
# Fallback: Yahoo (15-min delayed). CME Globex runs 23x5, so the systemd
# timer fires every 5 min Mon-Fri.
set -uo pipefail

cd "$(dirname "$0")"

PXPY="$HOME/MWM/projects/mwm-trading/.venv/bin/python"
YAHOO="/usr/bin/python3.11"

refresh_symbol() {
  local px_sym="$1" yahoo_sym="$2" out="$3"
  local ok=false
  if [[ -x "$PXPY" ]]; then
    if "$PXPY" -m fetchers.bars_pxpy --symbol "$px_sym" --interval 5 --days 1 --write "$out"; then
      ok=true
    else
      echo "bars_pxpy $px_sym failed (rc=$?); falling back to Yahoo" >&2
    fi
  else
    echo "project-x-py venv missing at $PXPY; using Yahoo" >&2
  fi
  if ! $ok; then
    "$YAHOO" -m fetchers.bars --symbol "$yahoo_sym" --interval 5m --range 1d --write "$out" || return 1
  fi
  return 0
}

# Prior-session highs/lows (the liquidity pools drawn on the MNQ chart).
# Needs ~16 days of bars, so it fetches its own history rather than reusing
# the 1-day bars above.
refresh_session_levels() {
  local out="web/session_levels_mnq.json"
  if [[ -x "$PXPY" ]] && "$PXPY" -m fetchers.session_levels --source pxpy --write "$out"; then
    return 0
  fi
  echo "session_levels pxpy path failed; falling back to Yahoo" >&2
  "$YAHOO" -m fetchers.session_levels --source yahoo --write "$out" || return 1
}

rc=0
refresh_symbol MNQ NQ=F  web/bars_mnq.json || rc=1
refresh_symbol MGC MGC=F web/bars_mgc.json || rc=1
refresh_session_levels || rc=1

# Deploy target comes from BRIEF_VPS_TARGET in ~/MWM/.env (user@host:/path),
# the same key config.py reads. No host is hardcoded here.
BRIEF_VPS_TARGET="${BRIEF_VPS_TARGET:-$(sed -n "s/^BRIEF_VPS_TARGET=//p" "$HOME/MWM/.env" 2>/dev/null | tr -d "\"'" )}"
if [ -z "$BRIEF_VPS_TARGET" ]; then
  echo "WARN: BRIEF_VPS_TARGET unset, skipping deploy" >&2
else
  rsync -az web/bars_mnq.json web/bars_mgc.json web/session_levels_mnq.json \
    "$BRIEF_VPS_TARGET/" || rc=1
fi
exit $rc
