#!/usr/bin/env bash
# ==============================================================================
# Clips X VPS Production Starter (Port 2100)
# ==============================================================================

set -e
cd "$(dirname "$0")"

export PORT="${PORT:-2100}"
export HOST="${HOST:-0.0.0.0}"

echo "=================================================="
echo "          Starting Clips X on VPS"
echo "  URL: http://m2.obsidianhosting.in:${PORT}"
echo "=================================================="

# 1. Check Python
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" &> /dev/null; then
    if command -v python &> /dev/null; then
        PYTHON_BIN="python"
    else
        echo "[ERROR] Python 3 is required. Please install python3 (e.g. sudo apt install -y python3 python3-venv python3-pip)"
        exit 1
    fi
fi

# 2. Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "[INFO] Installing ffmpeg..."
    sudo apt-get update && sudo apt-get install -y ffmpeg || true
fi

# 3. Create Virtualenv if not present
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment (.venv)..."
    "$PYTHON_BIN" -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

# 4. Run Server
echo "[OK] Launching Clips X on http://${HOST}:${PORT}..."
exec .venv/bin/python -m studio.server
