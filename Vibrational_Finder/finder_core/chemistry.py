from __future__ import annotations

import re
from collections.abc import Iterable


_ELEMENT_RE = re.compile(r"[A-Z][a-z]?")


def parse_formula_elements(formula: str) -> set[str]:
    return set(_ELEMENT_RE.findall(formula or ""))


def parse_element_query(query: str | Iterable[str]) -> set[str]:
    if isinstance(query, str):
        return set(_ELEMENT_RE.findall(query))
    return {item for item in query if item}


def formula_contains_elements(formula: str, required: str | Iterable[str]) -> bool:
    required_elements = parse_element_query(required)
    if not required_elements:
        return True
    return required_elements.issubset(parse_formula_elements(formula))
