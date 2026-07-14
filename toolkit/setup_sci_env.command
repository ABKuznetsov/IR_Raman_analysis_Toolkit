#!/bin/zsh
set -e

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCI_ROOT="$HOME/Library/Application Support/Sci"
SCI_ENV="$SCI_ROOT/env"
SCI_LOGS="$SCI_ROOT/logs"
LOG_FILE="$SCI_LOGS/ir_raman_setup.log"

mkdir -p "$SCI_ROOT" "$SCI_LOGS"

echo "[$(date)] Starting IR/Raman Sci setup" > "$LOG_FILE"
echo "Application root: $APP_ROOT" >> "$LOG_FILE"
echo "Sci root: $SCI_ROOT" >> "$LOG_FILE"

find_python() {
    for candidate in \
        "/opt/homebrew/bin/python3" \
        "/usr/local/bin/python3" \
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" \
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \
        "/opt/homebrew/bin/python3.12" \
        "/opt/homebrew/bin/python3.11" \
        "/usr/local/bin/python3.12" \
        "/usr/local/bin/python3.11" \
        "/usr/bin/python3" \
        "python3"
    do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)" >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then
    echo "Compatible Python was not found."
    echo "Install Python 3.11 or 3.12 from https://www.python.org/downloads/macos/"
    echo "or with Homebrew: brew install python@3.12"
    echo "Python 3.11/3.12 not found." >> "$LOG_FILE"
    exit 1
fi

echo "Using Python: $PYTHON"
echo "Using Python: $PYTHON" >> "$LOG_FILE"

if [ -x "$SCI_ENV/bin/python" ] && ! "$SCI_ENV/bin/python" -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)" >/dev/null 2>&1; then
    echo "Existing Sci environment uses an incompatible Python. Recreating it..."
    echo "Removing incompatible venv at $SCI_ENV" >> "$LOG_FILE"
    rm -rf "$SCI_ENV"
fi

if [ ! -x "$SCI_ENV/bin/python" ]; then
    echo "Creating Sci environment..."
    echo "Creating venv at $SCI_ENV" >> "$LOG_FILE"
    "$PYTHON" -m venv "$SCI_ENV" >> "$LOG_FILE" 2>&1
fi

if [ ! -x "$SCI_ENV/bin/python" ]; then
    echo "Failed to create Sci environment."
    echo "venv creation failed." >> "$LOG_FILE"
    exit 1
fi

echo "Upgrading pip and build tools..."
echo "Upgrading pip and build tools..." >> "$LOG_FILE"
"$SCI_ENV/bin/python" -m pip install --disable-pip-version-check --timeout 60 --retries 3 --prefer-binary --upgrade pip setuptools wheel >> "$LOG_FILE" 2>&1

if [ ! -f "$APP_ROOT/pyproject.toml" ]; then
    echo "pyproject.toml was not found: $APP_ROOT/pyproject.toml"
    echo "pyproject.toml was not found." >> "$LOG_FILE"
    exit 1
fi

echo "Installing IR/Raman Phase Finder requirements..."
echo "Installing IR/Raman Phase Finder requirements..." >> "$LOG_FILE"
"$SCI_ENV/bin/python" -m pip install --disable-pip-version-check --timeout 60 --retries 3 --prefer-binary --upgrade "${APP_ROOT}[formats]" >> "$LOG_FILE" 2>&1

echo "[$(date)] IR/Raman Sci setup complete." >> "$LOG_FILE"
echo "Sci environment is ready."
