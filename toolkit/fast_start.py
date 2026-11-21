"""Check an existing runtime cheaply and exec the native IR/Raman window."""
from __future__ import annotations

import argparse
from importlib.util import find_spec
import os
from pathlib import Path
import sys


NEEDS_SETUP = 75
CORE_MODULES = ("numpy", "scipy", "pyqtgraph", "PySide6")
ENTRY_MODULE = "vibrational_finder.apps.finder_gui_release"


def runtime_ready() -> bool:
    if not (3, 11) <= sys.version_info[:2] < (3, 13):
        return False
    # Do not load Qt or scientific extensions in a second process. Parquet
    # and the other optional readers must not prevent an offline launch.
    return all(find_spec(name) is not None for name in CORE_MODULES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--logs-root", type=Path)
    args, arguments = parser.parse_known_args()
    if not runtime_ready():
        return NEEDS_SETUP
    if args.probe:
        return 0
    if not args.data_root or not args.logs_root:
        parser.error("--data-root and --logs-root are required")

    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    data = Path(env.get("IR_RAMAN_DATA_DIR") or args.data_root)
    logs = Path(env.get("IR_RAMAN_LOG_DIR") or args.logs_root)
    data.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    env.update(PYTHONDONTWRITEBYTECODE="1", IR_RAMAN_DATA_DIR=str(data), IR_RAMAN_LOG_DIR=str(logs))
    env.setdefault("IR_RAMAN_PHASE_FINDER_CACHE_DIR", str(data / "cache"))
    env.setdefault("MPLCONFIGDIR", str(data.parent / "matplotlib"))
    env.setdefault("QT_MAC_WANTS_LAYER", "1")
    env.setdefault("IR_RAMAN_CHECK_UPDATES", "1")
    sources = str(root / "Vibrational_Finder")
    env["PYTHONPATH"] = sources + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.pop("IR_RAMAN_PHASE_FINDER_PREPARED_FILE", None)
    env.pop("IR_RAMAN_PHASE_FINDER_SHOW_SIGNAL_FILE", None)
    os.execve(sys.executable, [sys.executable, "-m", ENTRY_MODULE, *arguments], env)


if __name__ == "__main__":
    raise SystemExit(main())
