from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math

from vibrational_finder.band_detection import BandDetectionOptions, detect_bands
from vibrational_finder.models import SpectralBand
from vibrational_finder.project_document import ProjectDocument
from vibrational_finder.project_model import observed_by_id


class BandController:
    """Qt-free project mutations for automatic and manual spectral bands."""

    def __init__(self, document: ProjectDocument) -> None:
        self.document = document

    @property
    def project(self):
        return self.document.state

    def _spectrum(self, spectrum_id: str):
        spectrum = observed_by_id(self.project).get(spectrum_id)
        if spectrum is None:
            raise ValueError(f"Unknown observed spectrum: {spectrum_id!r}.")
        return spectrum

    @staticmethod
    def _validated(band: SpectralBand) -> SpectralBand:
        for name in ("position", "intensity", "width", "prominence", "confidence"):
            if not math.isfinite(float(getattr(band, name))):
                raise ValueError(f"Band {name} must be finite.")
        if band.width < 0:
            raise ValueError("Band width cannot be negative.")
        if not 0 <= band.confidence <= 1:
            raise ValueError("Band confidence must be between 0 and 1.")
        return band

    def bands(self, spectrum_id: str) -> list[SpectralBand]:
        self._spectrum(spectrum_id)
        return self.project.sample_bands.get(spectrum_id, [])

    def detect(
        self,
        spectrum_id: str,
        options: BandDetectionOptions | None = None,
    ) -> list[SpectralBand]:
        return [deepcopy(band) for band in detect_bands(self._spectrum(spectrum_id), options)]

    def replace_detected(self, spectrum_id: str, bands: list[SpectralBand]) -> list[SpectralBand]:
        self._spectrum(spectrum_id)
        replacement = [deepcopy(self._validated(band)) for band in bands]
        self.project.sample_bands[spectrum_id] = replacement
        self.document.mark_changed()
        return replacement

    def add(self, spectrum_id: str, band: SpectralBand) -> SpectralBand:
        self._spectrum(spectrum_id)
        stored = deepcopy(self._validated(band))
        self.project.sample_bands.setdefault(spectrum_id, []).append(stored)
        self.document.mark_changed()
        return stored

    def update(self, spectrum_id: str, index: int, **changes: object) -> SpectralBand:
        bands = self.bands(spectrum_id)
        if not 0 <= index < len(bands):
            raise IndexError("Band row is out of range.")
        allowed = {
            "position",
            "intensity",
            "width",
            "prominence",
            "mode",
            "assignment",
            "symmetry",
            "polarization",
            "orientation",
            "source_comment",
            "confidence",
            "assigned_candidate_keys",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unknown band fields: {', '.join(sorted(unknown))}.")
        updated = self._validated(replace(bands[index], **changes))
        bands[index] = updated
        self.document.mark_changed()
        return updated

    def remove(self, spectrum_id: str, index: int) -> SpectralBand:
        bands = self.bands(spectrum_id)
        if not 0 <= index < len(bands):
            raise IndexError("Band row is out of range.")
        removed = bands.pop(index)
        self.document.mark_changed()
        return removed
