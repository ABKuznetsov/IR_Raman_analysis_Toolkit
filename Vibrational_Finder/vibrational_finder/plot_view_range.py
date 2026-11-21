from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


ViewRange = tuple[tuple[float, float], tuple[float, float]]
T = TypeVar("T")


def redraw_preserving_view_range(
    capture_view_range: Callable[[], ViewRange | None],
    redraw: Callable[[], T],
    restore_view_range: Callable[[ViewRange | None], None],
) -> T:
    view_range = capture_view_range()
    try:
        return redraw()
    finally:
        restore_view_range(view_range)
