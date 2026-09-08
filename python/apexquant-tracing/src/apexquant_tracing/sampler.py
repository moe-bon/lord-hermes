from __future__ import annotations


class DeterministicSampler:
    def __init__(self, sample_ratio: float) -> None:
        if sample_ratio < 0 or sample_ratio > 1:
            raise ValueError("sample_ratio must be between 0 and 1")

        self._ratio = sample_ratio

    @property
    def ratio(self) -> float:
        return self._ratio

    def should_sample(self, trace_id: str) -> bool:
        if self._ratio <= 0:
            return False

        if self._ratio >= 1:
            return True

        if len(trace_id) != 32:
            return False

        try:
            value = int(trace_id[:8], 16)
        except ValueError:
            return False

        threshold = int(self._ratio * 0xFFFFFFFF)

        return value <= threshold