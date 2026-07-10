from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from finder_core.models import MatchScore, SignalTrace

CandidateT = TypeVar("CandidateT")
ResultT = TypeVar("ResultT")


class Preprocessor(ABC):
    @abstractmethod
    def run(self, trace: SignalTrace) -> SignalTrace:
        raise NotImplementedError


class FeatureDetector(ABC):
    @abstractmethod
    def detect(self, trace: SignalTrace) -> list:
        raise NotImplementedError


class SpectrumMatcher(ABC, Generic[CandidateT, ResultT]):
    @abstractmethod
    def score(self, observed: SignalTrace, candidate: CandidateT) -> ResultT:
        raise NotImplementedError


def weighted_score(
    *,
    position: float,
    intensity: float,
    correlation: float,
    coverage: float,
    weights: tuple[float, float, float, float] = (0.35, 0.2, 0.3, 0.15),
) -> MatchScore:
    total = sum(weights) or 1.0
    combined = (
        weights[0] * position
        + weights[1] * intensity
        + weights[2] * correlation
        + weights[3] * coverage
    ) / total
    return MatchScore(
        combined=max(0.0, min(100.0, combined)),
        position=max(0.0, min(100.0, position)),
        intensity=max(0.0, min(100.0, intensity)),
        correlation=max(0.0, min(100.0, correlation)),
        coverage=max(0.0, min(100.0, coverage)),
    )
