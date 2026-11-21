from __future__ import annotations

from collections.abc import Sequence

from vibrational_finder.apps.finder_gui_next import main as modular_main


def main(argv: Sequence[str] | None = None) -> int:
    """Stable release entry point for the modular spectroscopy Finder."""
    return modular_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
