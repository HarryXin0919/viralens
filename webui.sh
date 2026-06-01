#!/usr/bin/env bash
# ============================================================
#  viralens - one-click launcher (macOS / Linux)
#  Run:  ./webui.sh   (first time: chmod +x webui.sh)
#  Opens the viralens control panel in your browser. On first
#  run it installs the dependencies needed for fetching/analysis.
#  Everything runs locally (UI binds to 127.0.0.1); nothing is uploaded.
# ============================================================
set -e
cd "$(dirname "$0")"

# --- find Python 3 ---
PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
    echo "[!] Python 3.10+ not found. Install from https://www.python.org/downloads/ and run again."
    exit 1
fi

# --- one-time: install fetch/analysis dependencies ---
if [ ! -f ".viralens_deps_ok" ]; then
    echo "[*] First run: installing dependencies (one-time, needs internet)..."
    if "$PY" -m pip install -r requirements.txt; then
        echo done > .viralens_deps_ok
    else
        echo "[!] Dependency install failed. The UI will still open, but"
        echo "    fetching/analysis may not work until dependencies install."
    fi
fi

echo "[*] Starting viralens - your browser will open automatically..."
exec "$PY" scripts/app.py
