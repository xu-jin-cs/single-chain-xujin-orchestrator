#!/bin/bash
# Mac one-click launcher for Xujin Workflow (local offline orchestrator).
# Double-click this file to start the Web UI and open Chrome.

set -e

cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"
VENV_DIR="$ROOT_DIR/.venv"
WEB_UI_PORT=8080
URL="http://127.0.0.1:${WEB_UI_PORT}/"
WORKFLOW_ROOT="$HOME/.claude/skills"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Xujin Workflow Launcher"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "Error: virtual environment not found at $VENV_DIR"
    echo "Please run start.sh first to set up the environment."
    exit 1
fi

mkdir -p "$ROOT_DIR/logs"
PID=$(lsof -ti :$WEB_UI_PORT 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Port $WEB_UI_PORT occupied by $PID, stopping..."
    kill $PID 2>/dev/null || true
    sleep 1
fi

echo "Starting Web UI on $URL ..."
nohup python -m xujin_workflow.webui --root "$WORKFLOW_ROOT" --port $WEB_UI_PORT \
    > "$ROOT_DIR/logs/webui.log" 2>&1 &
WEB_UI_PID=$!
echo "Web UI PID: $WEB_UI_PID"
echo "Log: $ROOT_DIR/logs/webui.log"

echo "Waiting for Web UI to be ready..."
for i in {1..30}; do
    if curl -s "$URL" >/dev/null 2>&1; then
        echo "Web UI is ready."
        break
    fi
    sleep 1
done

if command -v open >/dev/null 2>&1; then
    echo "Opening Google Chrome..."
    open -a "Google Chrome" "$URL"
else
    echo "Cannot open browser automatically. Please visit: $URL"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Web UI: $URL"
echo "  Workflow root: $WORKFLOW_ROOT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

read -n 1 -s -r -p "Press any key to close this window..."
