#!/usr/bin/env bash
# Refresh the MNQ bars for the chart. Run every 5 min during market hours
# (CME Globex MNQ is 23×5 — use full weekday coverage 00:05 Mon → 23:55 Fri).
set -euo pipefail

cd "$(dirname "$0")"

/usr/bin/python3.11 -m fetchers.bars --interval 5m --range 1d --write web/bars_mnq.json

# Only rsync the bars file (keep small & fast)
rsync -az web/bars_mnq.json mats@204.168.244.173:/var/www/brief/bars_mnq.json
