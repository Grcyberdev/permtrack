#!/bin/bash

# =====================================================================
# Permit Scraper & Mobile Dashboard - Auto-Startup Runner
# =====================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Initializing Permit Scraper & Dashboard environment..."

# 1. Virtual Environment Setup
if [ ! -d "env" ]; then
    echo "📦 Creating Python virtual environment (env)..."
    python3 -m venv env
fi

echo "🔄 Activating virtual environment..."
source env/bin/activate

echo "⬇️  Installing/Verifying Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 2. Cloudflare Tunnel Verification
echo "🛡️  Checking for Cloudflare Tunnel client (cloudflared)..."
if ! command -v cloudflared &> /dev/null; then
    echo "⚠️  'cloudflared' not found in system PATH."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "💡 Detect macOS. Attempting to install via Homebrew..."
        if command -v brew &> /dev/null; then
            brew install cloudflared
        else
            echo "❌ Homebrew is not installed. Please install Homebrew first, or download cloudflared manually from:"
            echo "   https://github.com/cloudflare/cloudflared/releases"
        fi
    else
        echo "❌ Please download and install cloudflared manually on your system from:"
        echo "   https://github.com/cloudflare/cloudflared/releases"
    fi
fi

# 3. Port Configuration
PORT=8080

# Clean up any stale uvicorn/fastapi process on port 8080
STALE_PID=$(lsof -t -i:$PORT)
if [ ! -z "$STALE_PID" ]; then
    echo "🧹 Port $PORT is occupied. Terminating stale process (PID: $STALE_PID)..."
    kill -9 $STALE_PID
    sleep 1
fi

# 4. Start FastAPI Server
echo "⚡ Starting FastAPI Dashboard server on port $PORT..."
python app.py &
FASTAPI_PID=$!

# Ensure FastAPI terminates when script exits
trap "echo '🛑 Terminating FastAPI and Tunnel processes...'; kill $FASTAPI_PID; exit" INT TERM EXIT

sleep 2

# 5. Launch Cloudflare Quick Tunnel
if command -v cloudflared &> /dev/null; then
    echo "🌐 Starting Cloudflare Quick Tunnel for port $PORT..."
    echo "====================================================================="
    echo "👇 COPY AND OPEN THIS SECURE HTTPS URL ON YOUR PHONE OR LAPTOP:"
    echo "====================================================================="
    cloudflared tunnel --url http://localhost:$PORT
else
    echo "====================================================================="
    echo "⚠️  Cloudflare Quick Tunnel could not be started because cloudflared is missing."
    echo "👉 You can still access the dashboard on your LOCAL network at:"
    echo "   http://$(ipconfig getifaddr en0):$PORT  (or your local Mac IP)"
    echo "====================================================================="
    
    # Keep script alive waiting for FastAPI
    wait $FASTAPI_PID
fi
