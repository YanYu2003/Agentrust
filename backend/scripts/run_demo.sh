#!/usr/bin/env bash
set -euo pipefail
# Cycle 4: IAM + 3 agents + optional Dashboard + demo scripts

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="python3"; fi

PIDS=""

cleanup() {
  echo ""
  echo "Stopping background jobs..."
  # shellcheck disable=SC2086
  for pid in $PIDS; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup INT TERM EXIT

echo "========================================"
echo " Agentrust one-click demo (Cycle 4)"
echo " Backend: $ROOT"
echo "========================================"

"$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000 &
PIDS="$PIDS $!"

sleep 2
"$PY" -m uvicorn agents.enterprise_data_agent:app --host 127.0.0.1 --port 8001 &
PIDS="$PIDS $!"
"$PY" -m uvicorn agents.external_search_agent:app --host 127.0.0.1 --port 8002 &
PIDS="$PIDS $!"
"$PY" -m uvicorn agents.doc_helper_agent:app --host 127.0.0.1 --port 8003 &
PIDS="$PIDS $!"

sleep 4

if command -v npm >/dev/null 2>&1; then
  ( cd "$ROOT/../dashboard" && npm run dev ) &
  PIDS="$PIDS $!"
else
  echo "WARN: npm not found — skip dashboard."
fi

"$PY" "$ROOT/scripts/wait_health.py" "http://127.0.0.1:8000/health" 90

if [[ "${SKIP_DEMOS:-}" != "1" ]]; then
  "$PY" "$ROOT/scripts/demo_cycle4_normal.py"
  "$PY" "$ROOT/scripts/demo_cycle4_abnormal.py"
fi

echo ""
echo "Services running. Open http://localhost:5173"
echo "Feishu scopes template: $ROOT/scripts/feishu_app_scopes.cycle4.template.json"
echo "Press Ctrl+C to stop."

wait
