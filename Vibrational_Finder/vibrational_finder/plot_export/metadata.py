from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class CanvasLayer(StrEnum):
    BACKGROUND = "background"
    GRID = "grid"
    AXES = "axes"
    OBSERVED = "observed"
    PROCESSED = "processed"
    REFERENCE_PROFILE = "reference_profile"
    REFERENCE_BANDS = "reference_bands"
    REFERENCE_TICKS = "reference_ticks"
    OBSERVED_BANDS = "observed_bands"
    ASSIGNED_BANDS = "assigned_bands"
    UNASSIGNED_BANDS = "unassigned_bands"
    PEAK_LABELS = "peak_labels"
    MODE_LABELS = "mode_labels"
    ASSIGNMENT_LABELS = "assignment_labels"
    CURSOR = "cursor"
    LEGEND = "legend"


CANVAS_LAYER_ORDER = (
    CanvasLayer.BACKGROUND,
    CanvasLayer.GRID,
    CanvasLayer.AXES,
    CanvasLayer.OBSERVED,
    CanvasLayer.PROCESSED,
    CanvasLayer.REFERENCE_PROFILE,
    CanvasLayer.REFERENCE_BANDS,
    CanvasLayer.REFERENCE_TICKS,
    CanvasLayer.OBSERVED_BANDS,
    CanvasLayer.ASSIGNED_BANDS,
    CanvasLayer.UNASSIGNED_BANDS,
    CanvasLayer.PEAK_LABELS,
    CanvasLayer.MODE_LABELS,
    CanvasLayer.ASSIGNMENT_LABELS,
    CanvasLayer.CURSOR,
    CanvasLayer.LEGEND,
)


@dataclass(frozen=True, slots=True)
class CanvasItemTag:
    layer: CanvasLayer
    owner_id: str | None = None
    object_id: str | None = None
    exportable: bool = True


def tag_canvas_item(
    item,
    *,
    layer: CanvasLayer | str,
    owner_id: str | None = None,
    object_id: str | None = None,
    exportable: bool = True,
):
    normalized_layer = layer if isinstance(layer, CanvasLayer) else CanvasLayer(str(layer))
    tag = CanvasItemTag(
        layer=normalized_layer,
        owner_id=None if owner_id is None else str(owner_id),
        object_id=None if object_id is None else str(object_id),
        exportable=bool(exportable),
    )
    item._vibrational_export_tag = tag
    item._vibrational_layer = normalized_layer.value
    item._vibrational_owner_id = tag.owner_id
    return item


def canvas_item_tag(item) -> CanvasItemTag | None:
    tag = getattr(item, "_vibrational_export_tag", None)
    return tag if isinstance(tag, CanvasItemTag) else None


def stable_svg_id(*parts: str) -> str:
    identity = "\x1f".join(str(part) for part in parts)
    normalized = unicodedata.normalize("NFKD", identity).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not slug or not slug[0].isalpha():
        slug = f"item-{slug}" if slug else "item"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:52]}-{digest}"
