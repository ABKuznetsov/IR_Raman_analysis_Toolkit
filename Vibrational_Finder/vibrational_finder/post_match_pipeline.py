from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from vibrational_finder.models import ReferenceSpectrum, VibrationalMatchResult


@dataclass(slots=True)
class PostMatchOutcome:
    key: str
    added: bool


@dataclass(slots=True)
class CandidateRemovalOutcome:
    key: str
    removed: bool


@dataclass(slots=True)
class CandidateClearOutcome:
    removed_count: int


@dataclass(slots=True)
class CandidatePreviewOutcome:
    key: str
    overlay_drawn: bool


@dataclass(slots=True)
class ReferencePreviewOutcome:
    overlay_drawn: bool


def _true_key(_: str) -> bool:
    return True


def _no_key(_: str) -> None:
    return None


def _no_result(_: VibrationalMatchResult) -> None:
    return None


def _no_reference(_: ReferenceSpectrum) -> None:
    return None


def _false_key(_: str) -> bool:
    return False


def _zero() -> int:
    return 0


def _noop() -> None:
    return None


@dataclass(slots=True)
class VibrationalPostMatchPipeline:
    """Stages that run after selected vibrational candidates change."""

    add_selected_result: Callable[[VibrationalMatchResult], bool]
    show_selected_result: Callable[[VibrationalMatchResult], None]
    ensure_candidate_color: Callable[[str], str]
    refresh_selected_table: Callable[[], None]
    refresh_reference_card: Callable[[VibrationalMatchResult], None]
    save_profile_state: Callable[[], None]
    redraw_selected_references: Callable[[], None]
    refresh_match_evidence: Callable[[VibrationalMatchResult], None] = field(default=_no_result)
    refresh_unassigned_bands: Callable[[], None] = field(default=_noop)
    remove_selected_result: Callable[[str], bool] = field(default=_false_key)
    hide_selected_result: Callable[[str], None] = field(default=_no_key)
    remove_candidate_color: Callable[[str], None] = field(default=_no_key)
    clear_selected_results: Callable[[], int] = field(default=_zero)
    clear_match_evidence: Callable[[], None] = field(default=_noop)
    clear_reference_card: Callable[[], None] = field(default=_noop)
    set_preview_result: Callable[[VibrationalMatchResult], None] = field(default=_no_result)
    clear_preview_result: Callable[[], None] = field(default=_noop)
    set_preview_reference: Callable[[ReferenceSpectrum], None] = field(default=_no_reference)
    is_candidate_visible: Callable[[str], bool] = field(default=_true_key)
    redraw_preview_base: Callable[[], None] = field(default=_noop)
    draw_preview_overlay: Callable[[VibrationalMatchResult], None] = field(default=_no_result)
    draw_reference_preview_overlay: Callable[[ReferenceSpectrum], None] = field(default=_no_reference)

    def candidate_added(self, result: VibrationalMatchResult) -> PostMatchOutcome:
        key = result.candidate.key
        added = bool(self.add_selected_result(result))
        self.show_selected_result(result)
        self.ensure_candidate_color(key)
        self.refresh_selected_table()
        self.refresh_match_evidence(result)
        self.refresh_reference_card(result)
        self.refresh_unassigned_bands()
        self.save_profile_state()
        self.redraw_selected_references()
        return PostMatchOutcome(key=key, added=added)

    def candidate_removed(self, key: str) -> CandidateRemovalOutcome:
        removed = bool(self.remove_selected_result(key))
        if not removed:
            return CandidateRemovalOutcome(key=key, removed=False)
        self.hide_selected_result(key)
        self.remove_candidate_color(key)
        self.refresh_selected_table()
        self.clear_match_evidence()
        self.clear_reference_card()
        self.refresh_unassigned_bands()
        self.save_profile_state()
        self.redraw_selected_references()
        return CandidateRemovalOutcome(key=key, removed=True)

    def candidates_cleared(self) -> CandidateClearOutcome:
        removed_count = int(self.clear_selected_results())
        if removed_count <= 0:
            return CandidateClearOutcome(removed_count=0)
        self.refresh_selected_table()
        self.clear_match_evidence()
        self.clear_reference_card()
        self.refresh_unassigned_bands()
        self.save_profile_state()
        self.redraw_selected_references()
        return CandidateClearOutcome(removed_count=removed_count)

    def candidate_previewed(self, result: VibrationalMatchResult) -> CandidatePreviewOutcome:
        key = result.candidate.key
        self.set_preview_result(result)
        self.refresh_match_evidence(result)
        self.redraw_preview_base()
        overlay_drawn = not bool(self.is_candidate_visible(key))
        if overlay_drawn:
            self.draw_preview_overlay(result)
        self.refresh_reference_card(result)
        return CandidatePreviewOutcome(key=key, overlay_drawn=overlay_drawn)

    def preview_cleared(self) -> None:
        self.clear_preview_result()
        self.clear_match_evidence()
        self.redraw_preview_base()
        self.clear_reference_card()

    def reference_previewed(self, reference: ReferenceSpectrum) -> ReferencePreviewOutcome:
        self.set_preview_reference(reference)
        self.clear_match_evidence()
        self.redraw_preview_base()
        self.draw_reference_preview_overlay(reference)
        return ReferencePreviewOutcome(overlay_drawn=True)
