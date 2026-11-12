#!/usr/bin/env bash
# Запуск конвейера из bash (Git Bash / WSL / Linux / macOS).
# Использование: ./run.sh "путь_к_папке_с_билетами" [--dry-run]
set -euo pipefail

# Python с установленными библиотеками: python3 или python из PATH.
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

if [ $# -lt 1 ]; then
    echo "Использование: $0 --from \"путь_к_билетам\" --out \"путь_к_результату\" [--dry-run]"
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/src/run.py" "$@"
