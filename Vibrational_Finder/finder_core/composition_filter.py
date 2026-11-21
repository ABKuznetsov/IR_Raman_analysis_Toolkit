from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from finder_core.chemistry import parse_formula_elements


class CompositionFilterMode(str, Enum):
    ONLY = "only"
    CONTAINS = "contains"


@dataclass(slots=True)
class CompositionFilter:
    mode: CompositionFilterMode = CompositionFilterMode.ONLY
    selected_elements: set[str] = field(default_factory=set)
    selected_order: list[str] = field(default_factory=list)

    def toggle(self, element: str, mode: CompositionFilterMode) -> None:
        if mode is not self.mode:
            self.clear()
            self.mode = mode
        if element in self.selected_elements:
            self.selected_elements.remove(element)
            self.selected_order.remove(element)
            return
        self.selected_elements.add(element)
        self.selected_order.append(element)

    def clear(self) -> None:
        self.selected_elements.clear()
        self.selected_order.clear()

    def set_mode(self, mode: CompositionFilterMode) -> None:
        self.mode = mode

    def paint(self, elements: list[str], mode: CompositionFilterMode, *, selected: bool) -> None:
        if mode is not self.mode:
            self.clear()
            self.mode = mode
        for element in dict.fromkeys(elements):
            if selected and element not in self.selected_elements:
                self.selected_elements.add(element)
                self.selected_order.append(element)
            elif not selected and element in self.selected_elements:
                self.selected_elements.remove(element)
                self.selected_order.remove(element)

    def copy(self) -> CompositionFilter:
        return CompositionFilter(
            mode=self.mode,
            selected_elements=set(self.selected_elements),
            selected_order=list(self.selected_order),
        )

    def formula_query(self) -> str:
        return " ".join(self.selected_order)

    def button_state(self, element: str) -> str:
        if element not in self.selected_elements:
            return "neutral"
        return self.mode.value

    def summary(self) -> str:
        if not self.selected_elements:
            return "Mode: no element restriction"
        elements = ", ".join(sorted(self.selected_elements))
        if self.mode is CompositionFilterMode.ONLY:
            return f"Mode: Only these elements — {elements}; no additional elements"
        return f"Mode: Contains these elements — {elements}; additional elements allowed"

    def matches_formula(self, formula: str) -> bool:
        if not self.selected_elements:
            return True
        formula_elements = parse_formula_elements(formula)
        if not formula_elements:
            return False
        if self.mode is CompositionFilterMode.ONLY:
            return formula_elements == self.selected_elements
        return self.selected_elements.issubset(formula_elements)
