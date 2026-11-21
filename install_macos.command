#!/bin/zsh
set -e

APP_NAME="IR/Raman Phase Finder"
APP_BUNDLE_NAME="IR Raman Phase Finder"
SOURCE_ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="$("$SOURCE_ROOT"/.venv/bin/python -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$SOURCE_ROOT/pyproject.toml" 2>/dev/null || python3 -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' "$SOURCE_ROOT/pyproject.toml" 2>/dev/null || echo "0.1.7")"
SCI_ROOT="$HOME/Library/Application Support/Sci"
INSTALLED_SOURCE_ROOT="$SCI_ROOT/apps/ir_raman_analysis_toolkit/source"
SCI_ENV="$SCI_ROOT/env"
IR_RAMAN_USER_ROOT="$SCI_ROOT/apps/ir_raman_analysis_toolkit"
SCI_LOGS="$SCI_ROOT/logs"
if [ -n "$IR_RAMAN_INSTALL_DIR" ]; then
    INSTALL_DIR="$IR_RAMAN_INSTALL_DIR"
elif [ -w "/Applications" ]; then
    INSTALL_DIR="/Applications"
else
    INSTALL_DIR="$HOME/Applications"
fi
APP_BUNDLE="$INSTALL_DIR/$APP_BUNDLE_NAME.app"
CONTENTS_DIR="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
LEGACY_BUNDLE_NAMES=(
    "IR Raman Phase Finder"
    "IR-Raman Phase Finder"
    "IR_Raman Phase Finder"
    "IR_Raman_Phase_Finder"
    "IR Raman Analysis Toolkit"
    "IR_Raman_analysis_Toolkit"
)
BUNDLE_ID="com.irraman.phasefinder.app"

cd "$SOURCE_ROOT"

echo "Installing $APP_NAME for macOS"
echo "Source folder: $SOURCE_ROOT"
echo "User runtime: $SCI_ROOT"
echo "Application folder: $INSTALL_DIR"
echo

if [ ! -d "$SOURCE_ROOT/Vibrational_Finder" ]; then
    echo "Cannot find Vibrational_Finder folder next to this installer."
    read "?Press Enter to close..."
    exit 1
fi

echo "Copying application payload..."
mkdir -p "$INSTALLED_SOURCE_ROOT"
rsync -a --delete \
    --exclude ".git/" \
    --exclude ".DS_Store" \
    --exclude "._*" \
    --exclude "__MACOSX/" \
    --exclude "__pycache__/" \
    --exclude ".pytest_cache/" \
    --exclude ".ruff_cache/" \
    --exclude ".mypy_cache/" \
    --exclude "*.pyc" \
    --exclude "*.pyo" \
    --exclude ".venv/" \
    --exclude "build/" \
    --exclude "dist/" \
    --exclude "портобл/" \
    --exclude "portable/" \
    --exclude "*.egg-info/" \
    "$SOURCE_ROOT/" "$INSTALLED_SOURCE_ROOT/"

chmod +x "$INSTALLED_SOURCE_ROOT"/install_macos.command "$INSTALLED_SOURCE_ROOT"/update_macos.command "$INSTALLED_SOURCE_ROOT"/toolkit/*.command "$INSTALLED_SOURCE_ROOT"/*.command "$INSTALLED_SOURCE_ROOT"/*.sh 2>/dev/null || true

echo "Preparing scientific Python environment..."
"$INSTALLED_SOURCE_ROOT/toolkit/setup_sci_env.command"

echo "Creating application bundle: $APP_BUNDLE"
bundle_id() {
    local bundle="$1"
    /usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$bundle/Contents/Info.plist" 2>/dev/null || true
}

for name in "${LEGACY_BUNDLE_NAMES[@]}"; do
    if [ "$INSTALL_DIR/${name}.app" != "$APP_BUNDLE" ] && [ -d "$INSTALL_DIR/${name}.app" ]; then
        rm -rf "$INSTALL_DIR/${name}.app"
    fi
done
for bundle in "$INSTALL_DIR"/*.app(N); do
    if [ "$bundle" != "$APP_BUNDLE" ] && [ "$(bundle_id "$bundle")" = "$BUNDLE_ID" ]; then
        rm -rf "$bundle"
    fi
done
if [ -d "$APP_BUNDLE" ]; then
    rm -rf "$APP_BUNDLE"
fi
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

if [ -f "$INSTALLED_SOURCE_ROOT/icon.png" ]; then
    cp "$INSTALLED_SOURCE_ROOT/icon.png" "$RESOURCES_DIR/icon.png"
    ICON_PYTHON=""
    if [ -x "$SOURCE_ROOT/.venv/bin/python" ] && "$SOURCE_ROOT/.venv/bin/python" -c 'import PIL' >/dev/null 2>&1; then
        ICON_PYTHON="$SOURCE_ROOT/.venv/bin/python"
    elif python3 -c 'import PIL' >/dev/null 2>&1; then
        ICON_PYTHON="python3"
    fi
    if [ -n "$ICON_PYTHON" ]; then
        "$ICON_PYTHON" - "$INSTALLED_SOURCE_ROOT/icon.png" "$RESOURCES_DIR/icon.icns" <<'PY'
from pathlib import Path
import sys
from PIL import Image

source = Path(sys.argv[1])
target = Path(sys.argv[2])
Image.open(source).convert("RGBA").save(
    target,
    format="ICNS",
    sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)],
)
PY
    fi
fi

ICON_PLIST=""
if [ -f "$RESOURCES_DIR/icon.icns" ]; then
    ICON_PLIST='    <key>CFBundleIconFile</key>
    <string>icon.icns</string>'
fi

cat > "$CONTENTS_DIR/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleExecutable</key>
    <string>ir-raman-phase-finder</string>
    <key>CFBundleIdentifier</key>
    <string>com.irraman.phasefinder.app</string>
$ICON_PLIST
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>$VERSION</string>
    <key>CFBundleVersion</key>
    <string>$VERSION</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

cat > "$MACOS_DIR/ir-raman-phase-finder" <<LAUNCHER
#!/bin/zsh
set -e
exec "$INSTALLED_SOURCE_ROOT/toolkit/launch_ir_raman_phase_finder_preview.command" "\$@"
LAUNCHER

chmod +x "$MACOS_DIR/ir-raman-phase-finder"
xattr -dr com.apple.quarantine "$APP_BUNDLE" >/dev/null 2>&1 || true
touch "$APP_BUNDLE" >/dev/null 2>&1 || true

LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
    "$LSREGISTER" -f "$APP_BUNDLE" >/dev/null 2>&1 || true
fi
/usr/bin/qlmanage -r cache >/dev/null 2>&1 || true
/usr/bin/killall Dock >/dev/null 2>&1 || true

echo
echo "$APP_NAME installed:"
echo "  $APP_BUNDLE"
echo
read "?Press Enter to close..."
