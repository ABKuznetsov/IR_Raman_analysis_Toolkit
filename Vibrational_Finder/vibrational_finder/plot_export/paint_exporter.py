from __future__ import annotations

import os
import uuid
from pathlib import Path

from PySide6.QtCore import QByteArray, QFile, QIODevice, QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QImage, QImageWriter, QPageLayout, QPageSize, QPainter, QPdfWriter

from .options import PlotExportFormat, PlotExportOptions
from .snapshot import FrozenCanvas
from .svg_exporter import LayeredSvgExporter


_FORMAT_SUFFIXES = {
    PlotExportFormat.SVG: {".svg"},
    PlotExportFormat.PDF: {".pdf"},
    PlotExportFormat.PNG: {".png"},
    PlotExportFormat.JPG: {".jpg", ".jpeg"},
}

_MAGIC = {
    PlotExportFormat.SVG: (b"<?xml", b"<svg"),
    PlotExportFormat.PDF: (b"%PDF-",),
    PlotExportFormat.PNG: (b"\x89PNG\r\n\x1a\n",),
    PlotExportFormat.JPG: (b"\xff\xd8\xff",),
}


def _paint_scene(snapshot: FrozenCanvas, painter: QPainter, target: QRectF) -> None:
    snapshot.export_items()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    snapshot.scene.render(
        painter,
        target,
        snapshot.source_rect,
        Qt.AspectRatioMode.IgnoreAspectRatio,
    )


def render_raster(snapshot: FrozenCanvas, options: PlotExportOptions) -> QImage:
    if options.format not in {PlotExportFormat.PNG, PlotExportFormat.JPG}:
        raise ValueError("render_raster requires PNG or JPG options")
    width, height = options.pixel_size()
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    if image.isNull():
        raise MemoryError(f"Could not allocate {width}x{height} export image")
    # AxisItem creates tick text during painting. Use the live canvas's logical
    # DPI for that paint pass; the requested publication DPI is metadata and is
    # applied only after QPainter has finished.
    image.setDotsPerMeterX(round(float(snapshot.widget.logicalDpiX()) / 0.0254))
    image.setDotsPerMeterY(round(float(snapshot.widget.logicalDpiY()) / 0.0254))
    image.fill(snapshot.background.color())
    painter = QPainter(image)
    try:
        _paint_scene(
            snapshot,
            painter,
            QRectF(0.0, 0.0, float(width), float(height)),
        )
    finally:
        painter.end()
    dots_per_metre = round(options.dpi / 0.0254)
    image.setDotsPerMeterX(dots_per_metre)
    image.setDotsPerMeterY(dots_per_metre)
    return image


def _write_raster_image(image: QImage, options: PlotExportOptions, destination: Path) -> None:
    encoding = b"png" if options.format is PlotExportFormat.PNG else b"jpg"
    writer = QImageWriter(str(destination), QByteArray(encoding))
    if options.format is PlotExportFormat.JPG:
        writer.setQuality(options.jpeg_quality)
    if not writer.write(image):
        raise RuntimeError(f"Could not encode {options.format.value.upper()}: {writer.errorString()}")


def write_vector_pdf(snapshot: FrozenCanvas, options: PlotExportOptions, device: QIODevice) -> None:
    if options.format is not PlotExportFormat.PDF:
        raise ValueError("write_vector_pdf requires PDF options")
    snapshot.export_items()
    writer = QPdfWriter(device)
    # PDF geometry is vector and resolution-independent. Matching the live
    # device's logical DPI keeps dynamically painted axis text WYSIWYG.
    writer.setResolution(max(72, int(snapshot.widget.logicalDpiX())))
    page_size = QPageSize(
        QSizeF(options.width_mm, options.height_mm),
        QPageSize.Unit.Millimeter,
        "Publication figure",
        QPageSize.SizeMatchPolicy.ExactMatch,
    )
    writer.setPageSize(page_size)
    writer.setPageMargins(QMarginsF(0.0, 0.0, 0.0, 0.0), QPageLayout.Unit.Millimeter)
    painter = QPainter(writer)
    if not painter.isActive():
        raise RuntimeError("Could not start PDF painter")
    try:
        target = QRectF(0.0, 0.0, float(writer.width()), float(writer.height()))
        painter.fillRect(target, snapshot.background)
        _paint_scene(
            snapshot,
            painter,
            target,
        )
    finally:
        painter.end()
    del writer


def _write_svg(snapshot: FrozenCanvas, options: PlotExportOptions, destination: Path) -> None:
    data = LayeredSvgExporter().render(snapshot, options)
    file = QFile(str(destination))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Truncate):
        raise OSError(file.errorString())
    try:
        if file.write(data) != len(data) or not file.flush():
            raise OSError(file.errorString())
    finally:
        file.close()


def _write_pdf(snapshot: FrozenCanvas, options: PlotExportOptions, destination: Path) -> None:
    file = QFile(str(destination))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly | QIODevice.OpenModeFlag.Truncate):
        raise OSError(file.errorString())
    try:
        write_vector_pdf(snapshot, options, file)
        if not file.flush():
            raise OSError(file.errorString())
    finally:
        file.close()


def _validate_output(destination: Path, format: PlotExportFormat) -> None:
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("Exporter produced an empty file")
    prefix = destination.read_bytes()[:16].lstrip()
    if not any(prefix.startswith(magic) for magic in _MAGIC[format]):
        raise RuntimeError(f"Exporter produced an invalid {format.value.upper()} file")


def export_frozen_canvas(
    snapshot: FrozenCanvas,
    options: PlotExportOptions,
    destination: str | Path,
) -> None:
    destination = Path(destination)
    if destination.suffix.lower() not in _FORMAT_SUFFIXES[options.format]:
        allowed = ", ".join(sorted(_FORMAT_SUFFIXES[options.format]))
        raise ValueError(f"Destination suffix must be {allowed} for {options.format.value.upper()}")
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        if options.format in {PlotExportFormat.PNG, PlotExportFormat.JPG}:
            _write_raster_image(render_raster(snapshot, options), options, temporary)
        elif options.format is PlotExportFormat.PDF:
            _write_pdf(snapshot, options, temporary)
        elif options.format is PlotExportFormat.SVG:
            _write_svg(snapshot, options, temporary)
        else:  # pragma: no cover - PlotExportFormat is exhaustive
            raise ValueError(f"Unsupported export format: {options.format}")
        _validate_output(temporary, options.format)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
