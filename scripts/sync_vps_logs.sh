#!/usr/bin/env bash
# sync_vps_logs.sh — pull JSONL event logs from VPS practice services.
# Writes to ~/MWM-AI/data/vps_logs/<svc>/events_*.jsonl (local mirror).
#
# Invoked by mwm-brief-vps-logs-sync.timer every 5 min.
# Idempotent — rsync handles deltas.
set -euo pipefail

VPS="mats@204.168.244.173"
LOCAL_ROOT="$HOME/MWM-AI/data/vps_logs"

# Current live VPS cells (verified 2026-06-22). LiqSweep retired fleet-wide
# 2026-06-22 (3 liqsweep services stopped+disabled, removed here — their dirs
# are no longer rsync'd); the funded fleet now runs the PDHR cell below. 5
# legacy orbaron ORB cells retired 06-03 were already removed.
SERVICES=(
  pdhr-mnq-funded-24154823
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
mkdir -p "$HOME/MWM-AI/data/cockpit"
rsync -az --timeout=20 --ignore-missing-args \
  "$VPS:~/MWM-AI/data/cockpit/regime_lens.json" \
  "$HOME/MWM-AI/data/cockpit/regime_lens.json" 2>&1 || echo "WARN: regime_lens sync failed, continuing"

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$LOCAL_ROOT/.last_sync"
