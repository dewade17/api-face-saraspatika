#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
source "./load_env.sh"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p result/logs result/summary

: "${BASE_URL:=http://localhost:8000}"
: "${JWT_SECRET:=}"
: "${CHECKIN_POLL_TIMEOUT_SEC:=60}"

k6 run --summary-export "result/summary/peak_checkout_${TS}.json" "k6/absensi_peak_checkout.js" | tee "result/logs/peak_checkout_${TS}.log"
