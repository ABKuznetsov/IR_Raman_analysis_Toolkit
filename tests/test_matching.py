from __future__ import annotations

from finder_core.models import SignalKind
from vibrational_finder.matching import MatchingOptions, rank_candidates
from vibrational_finder.models import CompoundCandidate, ObservedSpectrum, ReferenceSpectrum


def test_rank_candidates_prefers_matching_reference() -> None:
    x = [100, 110, 120, 130, 140, 150, 160]
    observed = ObservedSpectrum(x=x, y=[0, 1, 0, 0.8, 0, 0.4, 0], kind=SignalKind.RAMAN)
    good = CompoundCandidate(
        key="good",
        source="test",
        entry_id="good",
        name="Good",
        kind=SignalKind.RAMAN,
        reference=ReferenceSpectrum(x=x, y=[0, 0.9, 0, 0.7, 0, 0.3, 0], kind=SignalKind.RAMAN),
    )
    bad = CompoundCandidate(
        key="bad",
        source="test",
        entry_id="bad",
        name="Bad",
        kind=SignalKind.RAMAN,
        reference=ReferenceSpectrum(x=x, y=[1, 0, 0.7, 0, 0.5, 0, 0], kind=SignalKind.RAMAN),
    )
    results = rank_candidates(observed, [bad, good], MatchingOptions(max_shift_cm1=0, tolerance_cm1=5))
    assert results[0].candidate.key == "good"
    assert results[0].score.combined > results[1].score.combined
