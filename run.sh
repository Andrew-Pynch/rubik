#!/bin/bash
# Start the Rubik's Cube CV server with auto-reload on file changes

cd "$(dirname "$0")"

# Kill any existing server on port 8000 (cross-platform)
pids=$(lsof -ti:8000 2>/dev/null) || true
if [ -n "$pids" ]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
fi

echo "Starting server at http://localhost:8000"
echo "Auto-reload enabled - server restarts on file changes"
echo "Press Ctrl+C to stop"
echo ""

.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --reload
