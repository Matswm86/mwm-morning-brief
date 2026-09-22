#!/usr/bin/env bash
# sync_vps_logs.sh — pull JSONL event logs from VPS practice services.
# Writes to ~/MWM/data/vps_logs/<svc>/events_*.jsonl (local mirror).
#
# Invoked by mwm-brief-vps-logs-sync.timer every 5 min.
# Idempotent — rsync handles deltas.
set -euo pipefail

# Host comes from BRIEF_VPS_HOST in ~/MWM/.env (user@host). Nothing hardcoded.
VPS="${BRIEF_VPS_HOST:-$(sed -n "s/^BRIEF_VPS_HOST=//p" "$HOME/MWM/.env" 2>/dev/null | tr -d "\"'" )}"
if [ -z "$VPS" ]; then echo "BRIEF_VPS_HOST unset in ~/MWM/.env" >&2; exit 1; fi
LOCAL_ROOT="$HOME/MWM/data/vps_logs"

# Current live VPS cells (verified 2026-06-22). LiqSweep retired fleet-wide
# 2026-06-22 (3 liqsweep services stopped+disabled, removed here — their dirs
# are no longer rsync'd); the funded fleet now runs the PDHR cell below. 5
# legacy orbaron ORB cells retired 06-03 were already removed.
SERVICES=(
  "${BRIEF_FUNDED_SERVICE:-$(sed -n "s/^BRIEF_FUNDED_SERVICE=//p" "$HOME/MWM/.env" 2>/dev/null | tr -d "\"'" )}"
  orb-breakout-mnq-combine
  orbaron-orbc3-practice
  orbaron-orbc5-practice
  orbaron-spot-a-prac
  orbaron-mgc-asia-bnredge
  orbaron-mgc-tokyo-bnredge-prac
  orbaron-mgc-london-bnredge-prac
  orbaron-mnq-frankfurt-bnredge-prac
  vp-survivors-practice
  ovb-mnq-prac
  ovb-mgc-prac
  ovb-m2k-prac
)

mkdir -p "$LOCAL_ROOT"

for svc in "${SERVICES[@]}"; do
  mkdir -p "$LOCAL_ROOT/$svc"
  rsync -az --timeout=20 \
    --include='events_*.jsonl' \
    --include='config_locked.json' \
    --exclude='*' \
    "$VPS:~/services/$svc/logs/" \
    "$LOCAL_ROOT/$svc/" 2>&1 || echo "WARN: $svc sync failed, continuing"
  rsync -az --timeout=20 --ignore-missing-args \
    "$VPS:~/services/$svc/config_locked.json" \
    "$LOCAL_ROOT/$svc/config_locked.json" 2>&1 || true
done

# Regime Lens artifact (written on the VPS by mwm-regime-lens.timer at
# ~09:26 ET) — mirrored locally so pre_market_report + local tools read it.
mkdir -p "$HOME/MWM/data/cockpit"
rsync -az --timeout=20 --ignore-missing-args \
  "$VPS:~/MWM/data/cockpit/regime_lens.json" \
  "$HOME/MWM/data/cockpit/regime_lens.json" 2>&1 || echo "WARN: regime_lens sync failed, continuing"

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$LOCAL_ROOT/.last_sync"
