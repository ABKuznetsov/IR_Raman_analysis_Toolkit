from __future__ import annotations

from collections import defaultdict
from xml.dom import minidom

import pyqtgraph as pg

from .metadata import CanvasLayer, stable_svg_id
from .options import PlotExportFormat, PlotExportOptions
from .snapshot import CanvasItemSnapshot, FrozenCanvas
from .svg_items import namespace_svg_fragment, render_item_svg, split_axis_fragment
from .text_outlines import apply_svg_text_mode


SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"


_LAYER_LABELS = {
    CanvasLayer.BACKGROUND: "Background",
    CanvasLayer.GRID: "Grid",
    CanvasLayer.AXES: "Axes",
    CanvasLayer.OBSERVED: "Observed",
    CanvasLayer.PROCESSED: "Processed",
    CanvasLayer.REFERENCE_PROFILE: "Reference profile",
    CanvasLayer.REFERENCE_BANDS: "Reference bands",
    CanvasLayer.REFERENCE_TICKS: "Reference ticks below spectrum",
    CanvasLayer.OBSERVED_BANDS: "Observed bands",
    CanvasLayer.ASSIGNED_BANDS: "Assigned bands",
    CanvasLayer.UNASSIGNED_BANDS: "Unassigned bands",
    CanvasLayer.PEAK_LABELS: "Peak labels",
    CanvasLayer.MODE_LABELS: "Mode labels",
    CanvasLayer.ASSIGNMENT_LABELS: "Assignment labels",
    CanvasLayer.CURSOR: "Cursor",
    CanvasLayer.LEGEND: "Legend",
}


def _number(value: float) -> str:
    rounded = round(float(value), 8)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:g}"


class LayeredSvgExporter:
    def render(self, snapshot: FrozenCanvas, options: PlotExportOptions) -> bytes:
        if options.format is not PlotExportFormat.SVG:
            raise ValueError("LayeredSvgExporter requires SVG options")
        width = int(snapshot.canvas_size_px.width())
        height = int(snapshot.canvas_size_px.height())
        if width <= 0 or height <= 0:
            raise ValueError("Frozen canvas dimensions must be positive")

        document = minidom.Document()
        root = document.createElement("svg")
        root.setAttribute("xmlns", SVG_NS)
        root.setAttribute("xmlns:inkscape", INKSCAPE_NS)
        root.setAttribute("width", f"{_number(options.width_mm)}mm")
        root.setAttribute("height", f"{_number(options.height_mm)}mm")
        root.setAttribute("viewBox", f"0 0 {width} {height}")
        root.setAttribute("version", "1.1")
        document.appendChild(root)
        definitions = document.createElement("defs")
        root.appendChild(definitions)

        background_group = self._group(document, "Background", "background")
        background = document.createElement("rect")
        background.setAttribute("x", "0")
        background.setAttribute("y", "0")
        background.setAttribute("width", str(width))
        background.setAttribute("height", str(height))
        color = snapshot.background.color()
        background.setAttribute("fill", color.name())
        background.setAttribute("fill-opacity", _number(color.alphaF()))
        background_group.appendChild(background)
        root.appendChild(background_group)

        item_snapshots = self._top_level_items(snapshot.export_items())
        rendered: dict[CanvasLayer, list[tuple[CanvasItemSnapshot, object]]] = defaultdict(list)
        for item_snapshot in sorted(item_snapshots, key=lambda item: (item.z_value, -item.scene_index)):
            fragment = render_item_svg(
                item_snapshot,
                root_item=snapshot.plot_item,
                canvas_size=(width, height),
            )
            prefix = stable_svg_id(
                item_snapshot.tag.layer.value,
                item_snapshot.tag.owner_id or "",
                item_snapshot.tag.object_id or type(item_snapshot.item).__name__,
            )
            if isinstance(item_snapshot.item, pg.AxisItem):
                axis_fragment, grid_fragment = split_axis_fragment(
                    fragment,
                    grid_enabled=item_snapshot.item.grid is not False,
                )
                self._append_fragment(document, definitions, axis_fragment, f"{prefix}-axis")
                rendered[CanvasLayer.AXES].append((item_snapshot, axis_fragment.node))
                if grid_fragment is not None:
                    self._append_fragment(document, definitions, grid_fragment, f"{prefix}-grid")
                    rendered[CanvasLayer.GRID].append((item_snapshot, grid_fragment.node))
                continue
            self._append_fragment(document, definitions, fragment, prefix)
            rendered[item_snapshot.tag.layer].append((item_snapshot, fragment.node))

        self._append_simple_layer(document, root, rendered, CanvasLayer.GRID)
        self._append_simple_layer(document, root, rendered, CanvasLayer.AXES)
        self._append_owned_layer(document, root, rendered, CanvasLayer.OBSERVED, "Observed")
        self._append_simple_layer(document, root, rendered, CanvasLayer.PROCESSED)
        self._append_reference_layers(document, root, rendered)
        self._append_owned_layer(document, root, rendered, CanvasLayer.REFERENCE_TICKS,
                                 _LAYER_LABELS[CanvasLayer.REFERENCE_TICKS])
        self._append_band_layers(document, root, rendered)
        self._append_label_layers(document, root, rendered)
        self._append_simple_layer(document, root, rendered, CanvasLayer.CURSOR)
        self._append_simple_layer(document, root, rendered, CanvasLayer.LEGEND)
        apply_svg_text_mode(root, options.svg_text_mode)
        return document.toxml(encoding="utf-8")

    @staticmethod
    def _top_level_items(items: tuple[CanvasItemSnapshot, ...]) -> list[CanvasItemSnapshot]:
        by_item = {item.item: item for item in items}
        top_level: list[CanvasItemSnapshot] = []
        for item_snapshot in items:
            parent = item_snapshot.item.parentItem()
            nested = False
            while parent is not None:
                if parent in by_item:
                    nested = True
                    break
                parent = parent.parentItem()
            if not nested:
                top_level.append(item_snapshot)
        return top_level

    @staticmethod
    def _append_fragment(document, definitions, fragment, prefix: str) -> None:
        namespace_svg_fragment(fragment.node, fragment.definitions, prefix)
        for definition in fragment.definitions:
            definition_copy = definition.cloneNode(True)
            definitions.appendChild(document.importNode(definition_copy, True))

    @staticmethod
    def _group(document, label: str, *identity: str, as_layer: bool = True):
        group = document.createElement("g")
        group.setAttribute("id", stable_svg_id(*identity, label))
        if as_layer:
            group.setAttribute("inkscape:groupmode", "layer")
        group.setAttribute("inkscape:label", label)
        return group

    def _append_simple_layer(self, document, root, rendered, layer: CanvasLayer) -> None:
        entries = rendered.get(layer, [])
        if not entries:
            return
        group = self._group(document, _LAYER_LABELS[layer], layer.value)
        for _snapshot, node in entries:
            group.appendChild(document.importNode(node, True))
        root.appendChild(group)

    def _append_owned_layer(self, document, root, rendered, layer: CanvasLayer, label: str) -> None:
        entries = rendered.get(layer, [])
        if not entries:
            return
        group = self._group(document, label, layer.value)
        owners: dict[str, list[object]] = defaultdict(list)
        for item_snapshot, node in entries:
            owners[item_snapshot.tag.owner_id or "Unowned"].append(node)
        for owner, nodes in owners.items():
            owner_group = self._group(document, owner, layer.value, owner, as_layer=False)
            for node in nodes:
                owner_group.appendChild(document.importNode(node, True))
            group.appendChild(owner_group)
        root.appendChild(group)

    def _append_reference_layers(self, document, root, rendered) -> None:
        layers = (CanvasLayer.REFERENCE_PROFILE, CanvasLayer.REFERENCE_BANDS)
        entries = [entry for layer in layers for entry in rendered.get(layer, [])]
        if not entries:
            return
        group = self._group(document, "References", "references")
        owners: dict[str, dict[CanvasLayer, list[object]]] = defaultdict(lambda: defaultdict(list))
        for layer in layers:
            for item_snapshot, node in rendered.get(layer, []):
                owners[item_snapshot.tag.owner_id or "Unowned"][layer].append(node)
        for owner, layer_nodes in owners.items():
            owner_group = self._group(document, owner, "references", owner, as_layer=False)
            for layer in layers:
                nodes = layer_nodes.get(layer, [])
                if not nodes:
                    continue
                layer_group = self._group(
                    document,
                    _LAYER_LABELS[layer],
                    "references",
                    owner,
                    layer.value,
                    as_layer=False,
                )
                for node in nodes:
                    layer_group.appendChild(document.importNode(node, True))
                owner_group.appendChild(layer_group)
            group.appendChild(owner_group)
        root.appendChild(group)

    def _append_band_layers(self, document, root, rendered) -> None:
        layers = (CanvasLayer.OBSERVED_BANDS, CanvasLayer.ASSIGNED_BANDS, CanvasLayer.UNASSIGNED_BANDS)
        if not any(rendered.get(layer) for layer in layers):
            return
        group = self._group(document, "Bands", "bands")
        for layer in layers:
            entries = rendered.get(layer, [])
            if not entries:
                continue
            layer_group = self._group(
                document,
                _LAYER_LABELS[layer],
                "bands",
                layer.value,
                as_layer=False,
            )
            owners: dict[str, list[object]] = defaultdict(list)
            for item_snapshot, node in entries:
                owners[item_snapshot.tag.owner_id or "Unowned"].append(node)
            for owner, nodes in owners.items():
                owner_group = self._group(
                    document,
                    owner,
                    "bands",
                    layer.value,
                    owner,
                    as_layer=False,
                )
                for node in nodes:
                    owner_group.appendChild(document.importNode(node, True))
                layer_group.appendChild(owner_group)
            group.appendChild(layer_group)
        root.appendChild(group)

    def _append_label_layers(self, document, root, rendered) -> None:
        layers = (CanvasLayer.PEAK_LABELS, CanvasLayer.MODE_LABELS, CanvasLayer.ASSIGNMENT_LABELS)
        if not any(rendered.get(layer) for layer in layers):
            return
        group = self._group(document, "Labels", "labels")
        for layer in layers:
            entries = rendered.get(layer, [])
            if not entries:
                continue
            layer_group = self._group(
                document,
                _LAYER_LABELS[layer],
                "labels",
                layer.value,
                as_layer=False,
            )
            for _snapshot, node in entries:
                layer_group.appendChild(document.importNode(node, True))
            group.appendChild(layer_group)
        root.appendChild(group)
