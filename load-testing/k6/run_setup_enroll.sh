#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
source "../load_env.sh"

# Menyiapkan folder log jika ingin menyimpan riwayatnya
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p result/logs result/summary

: "${BASE_URL:=http://localhost:8000}"
: "${JWT_SECRET:=}"

echo "=========================================================="
echo "MAMULAI PROSES ENROLL WAJAH ROBUST (36 USERS)"
echo "Target API : $BASE_URL"
echo "=========================================================="

# Menjalankan K6 dan mengekspor ringkasan ke file JSON serta mencetak log ke terminal
k6 run --summary-export "result/summary/setup_enroll_${TS}.json" "k6/setup_enroll_faces.js" | tee "result/logs/setup_enroll_${TS}.log"

echo "=========================================================="
echo "PROSES SELESAI. Cek terminal atau folder result/logs/ untuk detail kegagalan."
echo "=========================================================="
