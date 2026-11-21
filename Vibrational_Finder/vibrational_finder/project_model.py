from __future__ import annotations

from collections import defaultdict
import hashlib

from finder_core.models import SignalKind
from vibrational_finder.models import ObservedSpectrum
from vibrational_finder.project_series import new_project_object_id, normalized_spectrum_order, prune_series_memberships
from vibrational_finder.project_state import VibrationalProjectState


def stable_spectrum_id(*identity_parts: object) -> str:
    identity = "\x1f".join(str(part) for part in identity_parts)
    return f"spectrum-{hashlib.sha256(identity.encode('utf-8', errors='surrogatepass')).hexdigest()[:32]}"


def observed_spectra(state: VibrationalProjectState) -> list[ObservedSpectrum]:
    """Return every observed spectrum once, honoring the mixed project order."""
    available = [*state.raman_spectra, *state.ftir_spectra]
    first_by_id: dict[str, ObservedSpectrum] = {}
    for spectrum in available:
        first_by_id.setdefault(spectrum.id, spectrum)
    result: list[ObservedSpectrum] = []
    seen_objects: set[int] = set()
    for spectrum_id in state.spectrum_order_ids:
        spectrum = first_by_id.get(spectrum_id)
        if spectrum is not None and id(spectrum) not in seen_objects:
            result.append(spectrum)
            seen_objects.add(id(spectrum))
    for spectrum in available:
        if id(spectrum) not in seen_objects:
            result.append(spectrum)
            seen_objects.add(id(spectrum))
    return result


def observed_by_id(state: VibrationalProjectState) -> dict[str, ObservedSpectrum]:
    result: dict[str, ObservedSpectrum] = {}
    for spectrum in [*state.raman_spectra, *state.ftir_spectra]:
        result.setdefault(spectrum.id, spectrum)
    return result


def original_observed_for(
    state: VibrationalProjectState,
    spectrum_id: str,
) -> ObservedSpectrum | None:
    """Resolve both current ID keys and source-path keys written by older IRFF files."""
    spectrum = observed_by_id(state).get(spectrum_id)
    if spectrum is None:
        return None
    for key in (spectrum.id, spectrum.source_path, f"{spectrum.kind.value}:{spectrum.source_path}"):
        if key and key in state.original_observed:
            return state.original_observed[key]
    for original in state.original_observed.values():
        if original.id == spectrum.id:
            return original
        if spectrum.source_path and original.source_path == spectrum.source_path:
            return original
    return None


def spectrum_identity_aliases(spectrum: ObservedSpectrum) -> tuple[str, ...]:
    aliases: list[str] = []
    for value in (
        spectrum.id,
        f"{spectrum.kind.value}:{spectrum.source_path}" if spectrum.source_path else "",
        spectrum.source_path,
    ):
        text = str(value).strip()
        if text and text not in aliases:
            aliases.append(text)
    return tuple(aliases)


def normalize_project_state(state: VibrationalProjectState) -> VibrationalProjectState:
    """Repair portable cross-references around stable, unique spectrum IDs in place."""
    physical = [*state.raman_spectra, *state.ftir_spectra]
    canonical_by_old_id: dict[str, str] = {}
    occupied: set[str] = set()
    for spectrum in physical:
        old_id = str(spectrum.id).strip()
        if old_id and old_id not in occupied:
            canonical = old_id
        else:
            canonical = new_project_object_id("spectrum")
            while canonical in occupied:
                canonical = new_project_object_id("spectrum")
        if old_id:
            canonical_by_old_id.setdefault(old_id, canonical)
        spectrum.id = canonical
        occupied.add(canonical)

    for spectrum in state.raman_spectra:
        spectrum.kind = SignalKind.RAMAN
    for spectrum in state.ftir_spectra:
        spectrum.kind = SignalKind.FTIR

    alias_targets: dict[str, set[str]] = defaultdict(set)
    for spectrum in physical:
        for alias in spectrum_identity_aliases(spectrum):
            alias_targets[alias].add(spectrum.id)
    resolver = dict(canonical_by_old_id)
    for alias, targets in alias_targets.items():
        if len(targets) == 1:
            resolver.setdefault(alias, next(iter(targets)))

    def resolve(value: object) -> str | None:
        text = str(value).strip()
        return resolver.get(text) if text else None

    valid_ids = [spectrum.id for spectrum in physical]
    remapped_order = [resolved for item in state.spectrum_order_ids if (resolved := resolve(item)) is not None]
    state.spectrum_order_ids = normalized_spectrum_order(remapped_order, valid_ids)

    for series in state.series:
        series.spectrum_ids = [
            resolved for item in series.spectrum_ids if (resolved := resolve(item)) is not None
        ]
    prune_series_memberships(state.series, valid_ids)

    active = resolve(state.active_spectrum_key) if state.active_spectrum_key is not None else None
    state.active_spectrum_key = active or (state.spectrum_order_ids[0] if state.spectrum_order_ids else None)
    state.active_profile_spectrum_key = (
        resolve(state.active_profile_spectrum_key) if state.active_profile_spectrum_key is not None else None
    )
    state.visible_observed_keys = {
        resolved for item in state.visible_observed_keys if (resolved := resolve(item)) is not None
    }

    metadata: dict[str, dict[str, str]] = {}
    for key, value in state.sample_metadata.items():
        canonical = resolve(key)
        if canonical is not None:
            metadata.setdefault(canonical, {}).update(value)
    state.sample_metadata = metadata

    bands = {}
    for key, value in state.sample_bands.items():
        canonical = resolve(key)
        if canonical is not None:
            bands.setdefault(canonical, []).extend(value)
    state.sample_bands = bands

    profiles = {}
    for key, value in state.profile_states.items():
        canonical = resolve(key)
        if canonical is None or canonical in profiles:
            continue
        if value.spectrum is not None:
            value.spectrum.id = canonical
        profiles[canonical] = value
    state.profile_states = profiles
    return state
