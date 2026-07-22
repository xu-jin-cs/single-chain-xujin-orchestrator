#!/bin/bash
# Mac / Linux launcher for Xujin Workflow (local offline orchestrator).
# Auto-detects Python / dependencies and starts the Web UI on 127.0.0.1:8080.

set -e

cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Error: Python not found. Please install Python 3.10+ first."
    exit 1
fi

VENV_DIR="$ROOT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

echo "Checking dependencies..."
pip install -q -r "$ROOT_DIR/requirements.txt"

PORT=8080
WORKFLOW_ROOT="$HOME/.claude/skills"
mkdir -p "$ROOT_DIR/logs"
PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Port $PORT occupied by $PID, stopping..."
    kill $PID 2>/dev/null || true
    sleep 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Xujin Workflow Web UI"
echo "  http://127.0.0.1:$PORT/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Ctrl+C to stop."
echo ""

exec "$VENV_DIR/bin/python" -m xujin_workflow.webui --root "$WORKFLOW_ROOT" --port $PORT
