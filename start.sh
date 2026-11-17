#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

log() {
  printf '[agent-hub-workbench] %s\n' "$*"
}

hash_cmd() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$@"
  else
    shasum -a 256 "$@"
  fi
}

frontend_hash() {
  {
    hash_cmd frontend/package.json frontend/package-lock.json frontend/index.html
    find frontend/src frontend/public -type f -print0 | sort -z | xargs -0 -n 50 shasum -a 256 2>/dev/null || find frontend/src frontend/public -type f -print0 | sort -z | xargs -0 sha256sum
  } | hash_cmd | awk '{print $1}'
}

if [ ! -x backend/.venv/bin/python ]; then
  log "Backend .venv not found at backend/.venv; create one and install backend/requirements.txt first."
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  log "Frontend dependencies not found; run 'cd frontend && npm ci --legacy-peer-deps' first."
  exit 1
fi

source_hash="$(frontend_hash)"
build_stamp="frontend/dist/.source.sha256"
built_hash="$(cat "$build_stamp" 2>/dev/null || true)"
if [ ! -f frontend/dist/index.html ] || [ "$source_hash" != "$built_hash" ]; then
  log "Building frontend workbench UI..."
  (cd frontend && npm run build)
  mkdir -p frontend/dist
  printf '%s\n' "$source_hash" > "$build_stamp"
fi

PORT="${PORT:-8000}"
HOST="${AGENTHUB_HOST:-127.0.0.1}"
export AGENTHUB_MODE="${AGENTHUB_MODE:-workbench}"
export AGENTHUB_WORKBENCH_MODE="${AGENTHUB_WORKBENCH_MODE:-true}"
export AGENTHUB_HOST="${HOST}"
log "Starting Personal Workbench (mode=${AGENTHUB_MODE}) on http://${HOST}:${PORT}"
cd backend
exec .venv/bin/python -m uvicorn app.main:app --host "${HOST}" --port "${PORT}"
