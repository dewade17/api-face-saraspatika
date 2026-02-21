#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
source "./load_env.sh"

TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p result/logs result/summary

: "${BASE_URL:=http://localhost:8000}"
: "${JWT_SECRET:=}"
: "${SOAK_DURATION:=15m}"
: "${SOAK_PACE_SEC:=5}"

k6 run --summary-export "result/summary/soak_${TS}.json" "k6/absensi_soak.js" | tee "result/logs/soak_${TS}.log"
