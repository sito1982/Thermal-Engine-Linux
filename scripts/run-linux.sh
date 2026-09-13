#!/usr/bin/env bash
#
# Lanza Thermal Engine Studio usando el entorno virtual creado por install-linux.sh.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "ERROR: no existe el entorno virtual (.venv)."
    echo "Ejecuta primero: ./scripts/install-linux.sh"
    exit 1
fi

exec "$VENV_DIR/bin/python" "$PROJECT_DIR/main.py" "$@"
