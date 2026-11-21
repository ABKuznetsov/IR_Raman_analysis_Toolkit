from __future__ import annotations

import os
from pathlib import Path


def app_cache_dir(app_name: str = "ir_raman_analysis_toolkit") -> Path:
    configured = os.environ.get("IR_RAMAN_PHASE_FINDER_CACHE_DIR")
    if configured:
        root = Path(configured)
    elif os.environ.get("IR_RAMAN_DATA_DIR"):
        root = Path(os.environ["IR_RAMAN_DATA_DIR"]) / "cache"
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"]) / "Sci" / "apps" / "ir_raman_analysis_toolkit" / "data" / "cache"
    else:
        root = Path.home() / ".cache" / app_name
    root.mkdir(parents=True, exist_ok=True)
    return root
