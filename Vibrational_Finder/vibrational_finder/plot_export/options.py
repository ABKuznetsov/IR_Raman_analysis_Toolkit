from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class PlotExportFormat(StrEnum):
    SVG = "svg"
    PDF = "pdf"
    PNG = "png"
    JPG = "jpg"


class SvgTextMode(StrEnum):
    EDITABLE = "editable"
    CURVES = "curves"


@dataclass(frozen=True, slots=True)
class PlotExportOptions:
    format: PlotExportFormat
    width_mm: float
    height_mm: float
    dpi: int = 600
    jpeg_quality: int = 95
    svg_text_mode: SvgTextMode = SvgTextMode.EDITABLE

    def __post_init__(self) -> None:
        for field_name in ("width_mm", "height_mm"):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{field_name} must be a finite positive number")
        if not 72 <= int(self.dpi) <= 2400:
            raise ValueError("dpi must be between 72 and 2400")
        if not 1 <= int(self.jpeg_quality) <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")

    @classmethod
    def for_canvas(
        cls,
        format: PlotExportFormat,
        *,
        canvas_width_px: int,
        canvas_height_px: int,
        width_mm: float | None = None,
        dpi: int = 600,
        jpeg_quality: int = 95,
        svg_text_mode: SvgTextMode = SvgTextMode.EDITABLE,
    ) -> PlotExportOptions:
        if canvas_width_px <= 0:
            raise ValueError("canvas_width_px must be positive")
        if canvas_height_px <= 0:
            raise ValueError("canvas_height_px must be positive")
        target_width_mm = float(width_mm) if width_mm is not None else canvas_width_px / 96.0 * 25.4
        target_height_mm = target_width_mm * canvas_height_px / canvas_width_px
        return cls(
            format=format,
            width_mm=target_width_mm,
            height_mm=target_height_mm,
            dpi=dpi,
            jpeg_quality=jpeg_quality,
            svg_text_mode=svg_text_mode,
        )

    def pixel_size(self) -> tuple[int, int]:
        pixels_per_mm = self.dpi / 25.4
        return (
            max(1, round(self.width_mm * pixels_per_mm)),
            max(1, round(self.height_mm * pixels_per_mm)),
        )
