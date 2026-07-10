from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PlotLineStyle:
    width: float = 1.5
    color: str | None = None


@dataclass(slots=True)
class PlotMarkerStyle:
    size: int = 8
    symbol: str = "o"
    unknown_symbol: str = "t"


@dataclass(slots=True)
class PlotStyle:
    observed: PlotLineStyle = field(default_factory=lambda: PlotLineStyle(width=1.35))
    calculated: PlotLineStyle = field(default_factory=lambda: PlotLineStyle(width=1.9, color="#0b8043"))
    phase: PlotLineStyle = field(default_factory=lambda: PlotLineStyle(width=1.5))
    background: PlotLineStyle = field(default_factory=lambda: PlotLineStyle(width=1.2, color="#9aa0a6"))
    reference: PlotLineStyle = field(default_factory=lambda: PlotLineStyle(width=1.7, color="#1a73e8"))
    stick: PlotLineStyle = field(default_factory=lambda: PlotLineStyle(width=3.0))
    marker: PlotMarkerStyle = field(default_factory=lambda: PlotMarkerStyle(size=8))
