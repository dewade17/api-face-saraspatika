#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
source "./load_env.sh"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p result/logs result/summary

: "${BASE_URL:=http://localhost:8000}"
: "${JWT_SECRET:=}"

k6 run --summary-export "result/summary/peak_checkin_${TS}.json" "k6/absensi_peak_checkin.js" | tee "result/logs/peak_checkin_${TS}.log"
