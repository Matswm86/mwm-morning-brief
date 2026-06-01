#!/usr/bin/env bash
# sync_vps_logs.sh — pull JSONL event logs from VPS practice services.
# Writes to ~/MWM-AI/data/vps_logs/<svc>/events_*.jsonl (local mirror).
#
# Invoked by mwm-brief-vps-logs-sync.timer every 5 min.
# Idempotent — rsync handles deltas.
set -euo pipefail

VPS="mats@204.168.244.173"
LOCAL_ROOT="$HOME/MWM-AI/data/vps_logs"

SERVICES=(
  liqsweep-v10-mnq-combine
  liqsweep-v10-mgc-combine
  orb-breakout-mnq-combine
  orbaron-practice
  orbaron-pm-practice
  orbaron-rth-15m-practice
  orbaron-mgc-asia-practice
  orbaron-mgc-rth-practice
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

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$LOCAL_ROOT/.last_sync"
