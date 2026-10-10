#!/usr/bin/env bash
# setup.sh - macOS/Linux one-shot setup for agent_knowledge_self_built
# Usage:
#   bash setup.sh
#   bash setup.sh 8001

set -euo pipefail

port="${1:-8000}"
proj="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$proj"

echo ""
echo "==> project dir: $proj"

# 1. python
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.10+ and re-run."
  exit 1
fi
echo "==> python: $(python3 --version)"

# 2. venv
venv=".venv"
if [ ! -d "$venv" ]; then
  echo "==> creating venv..."
  python3 -m venv "$venv"
else
  echo "==> venv exists, reuse."
fi
# shellcheck disable=SC1091
source "$venv/bin/activate"

# 3. install deps
echo "==> installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4. .env
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "==> .env created from .env.example, edit it with your keys."
else
  echo "==> .env exists, keep current."
fi

# 5. init db + seed docs
echo "==> initializing db and docs..."
python scripts/seed_documents.py
python -c "from store.session import init_db; from config import settings; init_db(settings.SQLITE_PATH); print('db ready')"

# 6. ingest
echo "==> ingesting RAG..."
python -m rag.ingest_main

# 7. start service
if lsof -ti ":$port" >/dev/null 2>&1; then
  echo "==> stopping service on port $port ..."
  kill "$(lsof -ti ":$port")" 2>/dev/null || true
  sleep 1
fi

echo "==> starting service on port $port ..."
python -m app.main >/dev/null 2>&1 &
svc_pid="$!"

ready=0
for _ in $(seq 1 40); do
  sleep 0.5
  if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
done

echo ""
if [ "$ready" -eq 1 ]; then
  echo "==> setup complete: http://127.0.0.1:$port"
  echo "    service PID: $svc_pid"
  echo "    next steps:"
  echo "      1) edit .env with your OPENAI_API_KEY / LLM_MODEL"
  echo "      2) re-run bash setup.sh after changing .env"
else
  echo "==> startup timed out; check the service log and retry."
  exit 1
fi
