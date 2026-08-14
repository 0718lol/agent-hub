#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

log() {
  printf '[agent-hub] %s\n' "$*"
}

frontend_hash() {
  {
    sha256sum frontend/package.json frontend/package-lock.json frontend/index.html
    find frontend/src frontend/public -type f -print0 | sort -z | xargs -0 sha256sum
  } | sha256sum | awk '{print $1}'
}

if [ ! -x backend/.venv/bin/python ]; then
  log "Backend dependencies are not prepared; run /workspace/.asteam/setup.sh"
  exit 1
fi

expected_requirements="$(sha256sum backend/requirements.txt | awk '{print $1}')"
installed_requirements="$(cat backend/.venv/.requirements.sha256 2>/dev/null || true)"
if [ "$expected_requirements" != "$installed_requirements" ]; then
  log "Backend dependencies are stale; run /workspace/.asteam/setup.sh"
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  log "Frontend dependencies are not prepared; run /workspace/.asteam/setup.sh"
  exit 1
fi

source_hash="$(frontend_hash)"
build_stamp="frontend/dist/.source.sha256"
built_hash="$(cat "$build_stamp" 2>/dev/null || true)"
if [ ! -f frontend/dist/index.html ] || [ "$source_hash" != "$built_hash" ]; then
  log "Building changed frontend sources"
  (cd frontend && npm run build)
  printf '%s\n' "$source_hash" > "$build_stamp"
fi

log "Starting backend server on port ${PORT}"
cd backend
exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
