#!/usr/bin/env bash
# upload.sh — Activate tools-env and run upload.py
# All arguments are forwarded to upload.py.
#
# Usage:
#   ./upload.sh
#   ./upload.sh --ignore .micropicoignore
#   ./upload.sh --port /dev/ttyACM0
#   ./upload.sh --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# VENV="/home/ciaran-otter/tools-env"
VENV="tools-venv"

source "$VENV/bin/activate"
python3 "$SCRIPT_DIR/upload.py" "$@"
deactivate
