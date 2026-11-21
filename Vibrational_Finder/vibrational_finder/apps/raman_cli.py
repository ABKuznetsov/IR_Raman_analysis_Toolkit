from __future__ import annotations

from finder_core.models import SignalKind
from vibrational_finder.apps.finder_cli import run_single_kind


def main() -> int:
    return run_single_kind(SignalKind.RAMAN)


if __name__ == "__main__":
    raise SystemExit(main())
