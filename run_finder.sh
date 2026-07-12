#!/usr/bin/env bash
set -euo pipefail

TOOLKIT_ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="$TOOLKIT_ROOT/Vibrational_Finder"
cd "$TOOLKIT_ROOT"
export PYTHONPATH="$APP_ROOT${PYTHONPATH+:$PYTHONPATH}"
export QT_OPENGL=software
export QT_QUICK_BACKEND=software

find_python() {
    local candidates=(
        "$HOME/Library/Application Support/XRD_Toolkit/env/bin/python"
        "../XRD/XRD_Analysis_Toolkit/.venv/bin/python"
        "$HOME/Yandex.Disk.localized/Python/XRD/XRD_Analysis_Toolkit/.venv/bin/python"
        ".venv/bin/python"
        "/usr/local/bin/python3"
        "/opt/homebrew/bin/python3"
        "/usr/bin/python3"
        "python3"
    )

    local candidate
    for candidate in "${candidates[@]}"; do
        if { [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; } && "$candidate" -c "import PySide6, numpy, scipy, pyqtgraph, pybaselines, certifi, pyreadr, rdata, ijson" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then
    if [ ! -x ".venv/bin/python" ]; then
        echo "XRD Toolkit environment was not found. Creating local IR/Raman Phase Finder .venv..."
        "$TOOLKIT_ROOT/setup_env.sh"
    fi
    PYTHON="$(find_python || true)"
fi

if [ -z "$PYTHON" ]; then
    echo "Could not find a Python with required packages: PySide6, numpy, scipy, pyqtgraph."
    echo "Run ./setup_env.sh first to create .venv, or install the project dependencies into Python 3.11+."
    exit 1
fi

"$PYTHON" -m vibrational_finder.apps.finder_gui "$@"
