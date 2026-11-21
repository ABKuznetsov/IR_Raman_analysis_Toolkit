from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def finite_extent(values, fallback: tuple[float, float] = (0.0, 1.0)) -> tuple[float, float]:
    array = np.asarray(list(values), dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return fallback
    low = float(np.nanmin(finite))
    high = float(np.nanmax(finite))
    if high <= low:
        low -= 0.5
        high += 0.5
    return low, high


def boxes_overlap(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
    return not (
        first[2] <= second[0]
        or second[2] <= first[0]
        or first[3] <= second[1]
        or second[3] <= first[1]
    )


@dataclass(slots=True)
class LabelPlacement:
    x: float
    y: float
    box: tuple[float, float, float, float]


@dataclass
class LabelBoxPlacer:
    boxes: list[tuple[float, float, float, float]] = field(default_factory=list)

    def clear(self) -> None:
        self.boxes.clear()

    def place(
        self,
        position: float,
        top: float,
        text: str,
        *,
        place_below: bool,
        x_span: float,
        y_min: float,
        y_max: float,
    ) -> LabelPlacement:
        y_span = max(y_max - y_min, 1.0e-9)
        text_lines = str(text).splitlines() or [str(text)]
        width = max(x_span * (0.018 + 0.006 * max(len(line) for line in text_lines)), x_span * 0.028)
        height = y_span * (0.038 + 0.026 * max(len(text_lines) - 1, 0))
        base_offset = y_span * 0.028
        row_step = y_span * 0.052
        directions = [-1] if place_below else [1]
        directions.extend([1, -1] if place_below else [-1, 1])
        for direction in directions:
            for row in range(8):
                label_y = top + direction * (base_offset + row * row_step)
                box = (
                    position - width * 0.5,
                    label_y - height * 0.5,
                    position + width * 0.5,
                    label_y + height * 0.5,
                )
                if any(boxes_overlap(box, occupied) for occupied in self.boxes):
                    continue
                self.boxes.append(box)
                return LabelPlacement(position, label_y, box)
        fallback_y = top + (-1 if place_below else 1) * (base_offset + 8 * row_step)
        box = (
            position - width * 0.5,
            fallback_y - height * 0.5,
            position + width * 0.5,
            fallback_y + height * 0.5,
        )
        self.boxes.append(box)
        return LabelPlacement(position, fallback_y, box)
