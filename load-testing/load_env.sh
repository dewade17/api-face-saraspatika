#!/usr/bin/env bash
set -euo pipefail

# Optional override:
#   ENV_FILE=/path/to/.env ./run_peak_checkin.sh
if [[ -n "${ENV_FILE:-}" ]]; then
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  else
    echo "ENV_FILE tidak ditemukan: $ENV_FILE" >&2
  fi
else
  LOADER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  for candidate in "$LOADER_DIR/../../.env" "$LOADER_DIR/../.env" "$LOADER_DIR/.env"; do
    if [[ -f "$candidate" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "$candidate"
      set +a
      break
    fi
  done
fi

# Mapping env project -> env load-testing.
: "${BASE_URL:=${NEXT_PUBLIC_API_BASE_URL:-${NEXT_PUBLIC_API_FACE_URL:-${APP_URL:-http://localhost:8000}}}}"
export BASE_URL
