#!/bin/zsh
set -e

TOOLKIT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$TOOLKIT_ROOT"

find_python() {
    for candidate in \
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \
        "/usr/local/bin/python3" \
        "/opt/homebrew/bin/python3" \
        "/usr/bin/python3" \
        "python3"
    do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys; raise SystemExit(not (sys.version_info >= (3, 11) and sys.version_info < (3, 13)))" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then
    echo "Could not find Python >=3.11,<3.13."
    read "?Press Enter to close..."
    exit 1
fi

echo "Creating/updating .venv with $PYTHON"
"$PYTHON" -m venv .venv
".venv/bin/python" -m pip install --upgrade pip
".venv/bin/python" -m pip install -e ".[formats]"

echo
echo "Environment is ready."
echo "Run the app with ./run_finder.command"
read "?Press Enter to close..."
