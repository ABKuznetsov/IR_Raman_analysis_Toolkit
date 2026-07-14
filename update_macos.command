#!/bin/zsh
set -e

APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_ROOT"

echo "Updating IR/Raman Phase Finder from GitHub..."

if [ -d ".git" ]; then
    if ! command -v git >/dev/null 2>&1; then
        echo "Git was not found."
        echo "Install Git or Xcode Command Line Tools, then run this script again:"
        echo "  xcode-select --install"
        read "?Press Enter to close..."
        exit 1
    fi

    git fetch origin
    git pull --ff-only origin main

    echo
    echo "Updating Python environment after GitHub update..."
    "$APP_ROOT/toolkit/setup_sci_env.command"

    echo
    echo "Update complete."
    read "?Press Enter to close..."
    exit 0
fi

echo
echo "This installed app is not a Git checkout."
echo "Checking the GitHub release manifest for a macOS installer..."

PYTHON=""
for candidate in \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3" \
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3" \
    "/usr/bin/python3" \
    "python3"
do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Python was not found, so the update manifest cannot be read automatically."
    echo "Open the latest release manually:"
    echo "https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases/latest"
    read "?Press Enter to close..."
    exit 1
fi

UPDATE_INFO="$("$PYTHON" - "$APP_ROOT" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

app_root = Path(sys.argv[1])
manifest_path = app_root / "toolkit" / "manifest.json"
app_json_path = app_root / "Vibrational_Finder" / "app.json"
app_id = "ir_raman_phase_finder"

def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}

def version_parts(value: str):
    result = []
    for chunk in value.replace("-", ".").split("."):
        result.append(int(chunk) if chunk.isdigit() else chunk.lower())
    return result

def newer(left: str, right: str) -> bool:
    a = version_parts(left)
    b = version_parts(right)
    for index in range(max(len(a), len(b))):
        av = a[index] if index < len(a) else 0
        bv = b[index] if index < len(b) else 0
        if av == bv:
            continue
        if isinstance(av, int) and isinstance(bv, int):
            return av > bv
        return str(av) > str(bv)
    return False

def fetch_json(url: str) -> dict:
    request = Request(str(url), headers={"User-Agent": "IR-Raman-Phase-Finder-macOS-Updater"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8-sig"))
    except Exception as urllib_error:
        curl = "/usr/bin/curl"
        if not Path(curl).exists():
            curl = "curl"
        result = subprocess.run(
            [curl, "-L", "--fail", "--silent", "--show-error", "--max-time", "20", str(url)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"urllib failed: {urllib_error}; curl failed: {detail}")
        return json.loads(result.stdout.decode("utf-8-sig"))

manifest = load(manifest_path)
app_json = load(app_json_path)
local_version = str(app_json.get("version") or "0.0.0")
app_info = (manifest.get("apps") or {}).get(app_id, {})
remote_url = app_info.get("update_manifest_url") or app_info.get("manifest_url")
release_url = app_info.get("release_url") or "https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases/latest"
if not remote_url:
    print(f"error\tNo update manifest URL configured.\t{release_url}")
    raise SystemExit(0)

try:
    remote = fetch_json(str(remote_url))
except Exception as exc:
    print(f"error\tCould not read update manifest: {exc}\t{release_url}")
    raise SystemExit(0)

remote_app = remote
if isinstance(remote.get("apps"), dict) and app_id in remote["apps"]:
    remote_app = remote["apps"][app_id]

latest = str(remote_app.get("version") or local_version)
if not newer(latest, local_version):
    print(f"current\t{local_version}\t{release_url}")
    raise SystemExit(0)

installer_url = ""
sha = ""
for asset in remote_app.get("assets", []) or []:
    name = str(asset.get("name", "")).lower()
    platform = str(asset.get("platform", "")).lower()
    if "macos" in platform or name.endswith((".pkg", ".dmg")):
        installer_url = str(asset.get("url") or "")
        sha = str(asset.get("sha256") or "")
        break
if not installer_url:
    installer_url = str(remote_app.get("macos_installer_url") or "")
    sha = str(remote_app.get("macos_installer_sha256") or "")
if not installer_url:
    print(f"manual\t{latest}\t{release_url}")
else:
    print(f"installer\t{latest}\t{installer_url}\t{sha}")
PY
)"

STATUS="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $1}')"

if [ "$STATUS" = "current" ]; then
    CURRENT="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $2}')"
    echo "Already up to date. Current version: $CURRENT"
    read "?Press Enter to close..."
    exit 0
fi

if [ "$STATUS" = "manual" ]; then
    LATEST="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $2}')"
    RELEASE_URL="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $3}')"
    echo "Version $LATEST is available, but no macOS installer URL is listed."
    echo "Opening release page:"
    echo "$RELEASE_URL"
    open "$RELEASE_URL" >/dev/null 2>&1 || true
    read "?Press Enter to close..."
    exit 0
fi

if [ "$STATUS" = "error" ]; then
    MESSAGE="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $2}')"
    RELEASE_URL="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $3}')"
    echo "$MESSAGE"
    echo "Opening release page:"
    echo "$RELEASE_URL"
    open "$RELEASE_URL" >/dev/null 2>&1 || true
    read "?Press Enter to close..."
    exit 1
fi

LATEST="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $2}')"
INSTALLER_URL="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $3}')"
SHA256_EXPECTED="$(printf "%s" "$UPDATE_INFO" | awk -F '\t' '{print $4}')"
UPDATE_DIR="$HOME/Library/Application Support/Sci/updates"
mkdir -p "$UPDATE_DIR"
INSTALLER_PATH="$UPDATE_DIR/$(basename "${INSTALLER_URL%%\?*}")"
if [ -z "$(basename "$INSTALLER_PATH")" ]; then
    INSTALLER_PATH="$UPDATE_DIR/IR_Raman_Phase_Finder_macOS_${LATEST}.pkg"
fi

echo "Downloading version $LATEST:"
echo "$INSTALLER_URL"
curl -L --fail --retry 3 --connect-timeout 30 -o "$INSTALLER_PATH" "$INSTALLER_URL"

if [ -n "$SHA256_EXPECTED" ]; then
    SHA256_ACTUAL="$(shasum -a 256 "$INSTALLER_PATH" | awk '{print $1}')"
    if [ "$SHA256_ACTUAL" != "$SHA256_EXPECTED" ]; then
        echo "Checksum mismatch."
        echo "Expected: $SHA256_EXPECTED"
        echo "Actual:   $SHA256_ACTUAL"
        rm -f "$INSTALLER_PATH"
        read "?Press Enter to close..."
        exit 1
    fi
fi

echo
echo "Opening macOS installer:"
echo "$INSTALLER_PATH"
open "$INSTALLER_PATH"
read "?Press Enter to close..."
