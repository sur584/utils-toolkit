#!/bin/bash
set -e
cd "$(dirname "$0")"

echo ""
echo "=========================================="
echo "  Utils Toolkit"
echo "=========================================="
echo ""

# Find Python
PY_CMD=""
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
else
    echo "[ERROR] Python not found!"
    echo ""
    echo "Please install Python 3.10+:"
    echo "  macOS:   brew install python@3.12"
    echo "  Ubuntu:  sudo apt install python3.12"
    echo "  Fedora:  sudo dnf install python3.12"
    echo ""
    exit 1
fi

echo "[OK] Found Python: $($PY_CMD --version)"
echo ""

# launcher.py handles all dependency installation
$PY_CMD launcher.py "$@"
