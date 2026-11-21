from __future__ import annotations

from dataclasses import dataclass, field

from vibrational_finder.plot_export.metadata import CanvasLayer, tag_canvas_item


class LayerName:
    OBSERVED = CanvasLayer.OBSERVED.value
    REFERENCE_PROFILE = CanvasLayer.REFERENCE_PROFILE.value
    REFERENCE_BANDS = CanvasLayer.REFERENCE_BANDS.value
    MODE_LABELS = CanvasLayer.MODE_LABELS.value
    UNASSIGNED_BANDS = CanvasLayer.UNASSIGNED_BANDS.value
    DIFFERENCE = "difference"


def tag_plot_item(item, layer: str, owner_id: str | None = None):
    try:
        return tag_canvas_item(item, layer=layer, owner_id=owner_id)
    except ValueError:
        pass
    try:
        item._vibrational_layer = layer
        item._vibrational_owner_id = owner_id
    except Exception:
        pass
    return item


@dataclass
class LayerItemRegistry:
    _items: dict[str, list] = field(default_factory=dict)

    def add(self, layer: str, item, owner_id: str | None = None):
        tag_plot_item(item, layer, owner_id)
        self._items.setdefault(layer, []).append(item)
        return item

    def items(self, layer: str) -> list:
        return list(self._items.get(layer, []))

    def remove_owner(self, plot, owner_id: str) -> int:
        removed = 0
        for layer, layer_items in list(self._items.items()):
            kept = []
            for item in layer_items:
                if getattr(item, "_vibrational_owner_id", None) != owner_id:
                    kept.append(item)
                    continue
                try:
                    plot.removeItem(item)
                except Exception:
                    pass
                removed += 1
            self._items[layer] = kept
        return removed

    def clear(self, plot) -> int:
        removed = 0
        for layer, layer_items in list(self._items.items()):
            for item in layer_items:
                try:
                    plot.removeItem(item)
                except Exception:
                    pass
                removed += 1
            self._items[layer] = []
        return removed
