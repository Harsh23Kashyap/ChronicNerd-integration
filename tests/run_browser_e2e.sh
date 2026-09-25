#!/usr/bin/env bash
# Runs the real-Chrome end-to-end test: real FastAPI app, real MySQL, real
# sessions/SSE; only the external science APIs are stubbed.
# Needs MySQL env (host, port, user, password, database) and node deps.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
PY=${PYTHON:-python3}
export ALLOWED_ORIGINS=http://localhost:18080 OPENAI_API_KEY=${OPENAI_API_KEY:-test-key}
# A previous run's servers may still be shutting down; stop them and wait until the ports are free.
pkill -f 'tests/browser_test_server.py' 2>/dev/null || true
pkill -f 'http.server 18080' 2>/dev/null || true
for _ in $(seq 1 30); do
  curl -s -o /dev/null http://localhost:8000/health || curl -s -o /dev/null http://localhost:18080/ || break
  sleep 0.5
done
$PY tests/browser_test_server.py > /tmp/chronicnerd-e2e-api.log 2>&1 &
API=$!
(cd dietnerd-website && exec $PY -m http.server 18080 --bind 127.0.0.1 > /tmp/chronicnerd-e2e-web.log 2>&1) &
WEB=$!
trap 'kill $API $WEB 2>/dev/null || true; wait $API $WEB 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do curl -sf http://localhost:8000/health >/dev/null && curl -sf http://localhost:18080/login.html >/dev/null && break; sleep 0.5; done
node tests/browser_e2e.js
