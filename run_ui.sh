#!/usr/bin/env bash
# Запуск UI-режима из bash (Git Bash / WSL / Linux / macOS).
set -euo pipefail

if [ -z "${PYTHON:-}" ]; then
    PYTHON=""
    for c in python3 python; do
        if command -v "$c" >/dev/null 2>&1; then
            PYTHON="$c"
            break
        fi
    done
fi
if [ -z "$PYTHON" ]; then
    echo "Python не найден в PATH. Установите Python 3.10+." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$PYTHON" "$SCRIPT_DIR/src/ui.py" "$@"
