"""Rolling adaptive learning for normal household water flow."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from typing import Any


class LearningConfidence(StrEnum):
    """Confidence state for the adaptive model."""

    INSUFFICIENT = "insufficient"
    LEARNING = "learning"
    RELIABLE = "reliable"


@dataclass(slots=True, frozen=True)
class LearningSample:
    """One completed, non-suspicious water-use episode."""

    timestamp: datetime
    peak_lph: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "peak_lph": self.peak_lph,
        }


@dataclass(slots=True, frozen=True)
class LearningSnapshot:
    """Current rolling learning result."""

    learned_max_lph: float | None
    short_reference_lph: float | None
    long_reference_lph: float | None
    sample_count: int
    coverage_days: int
    age_days: int
    window_days: int
    confidence: LearningConfidence


@dataclass(slots=True)
class _Episode:
    """In-progress water-use episode; never persisted as normal evidence."""

    started_at: datetime
    peak_lph: float
    excluded: bool = False
    quiet_since: datetime | None = None


class AdaptiveFlowLearner:
    """Learn a robust rolling normal peak from completed safe episodes."""

    def __init__(
        self,
        *,
        window_days: int = 30,
        quiet_flow_lph: float = 1.0,
        quiet_seconds: float = 120.0,
    ) -> None:
        self.window_days = max(7, int(window_days))
        self.quiet_flow_lph = max(0.0, float(quiet_flow_lph))
        self.quiet_seconds = max(10.0, float(quiet_seconds))
        self.samples: list[LearningSample] = []
        self._episode: _Episode | None = None
        self._clock_utc: datetime | None = None
        self._clock_runtime: datetime | None = None
        self._rollback_samples: set[str] = set()

    def update_window(self, window_days: int, now: datetime) -> None:
        """Change the rolling window while retaining still-valid samples."""
        self.window_days = max(7, int(window_days))
        self._prune(now)

    def observe(
        self,
        now: datetime,
        flow_lph: float,
        *,
        runtime_now: datetime | None = None,
        suspicious: bool,
        high_flow_bypassed: bool,
    ) -> bool:
        """Observe a flow sample.

        Returns True when the learned sample set changed.
        """
        timing = now if runtime_now is None else runtime_now
        if runtime_now is not None:
            self.observe_clock(now, runtime_now)
        flow = max(0.0, float(flow_lph))
        changed = self._prune(now)

        if self._episode is None:
            if flow >= self.quiet_flow_lph:
                self._episode = _Episode(
                    started_at=timing,
                    peak_lph=flow,
                    excluded=suspicious or high_flow_bypassed,
                )
            return changed

        episode = self._episode
        episode.peak_lph = max(episode.peak_lph, flow)
        if suspicious or high_flow_bypassed:
            episode.excluded = True

        if flow < self.quiet_flow_lph:
            episode.quiet_since = episode.quiet_since or timing
            quiet_elapsed = (timing - episode.quiet_since).total_seconds()
            if quiet_elapsed >= self.quiet_seconds:
                if not episode.excluded and episode.peak_lph > 0:
                    self.samples.append(LearningSample(timestamp=now, peak_lph=episode.peak_lph))
                    changed = True
                self._episode = None
        else:
            episode.quiet_since = None

        return changed

    def suspend_current_episode(self) -> None:
        """Discard incomplete normal evidence at any unsafe observation boundary."""
        self._episode = None

    def reset(self) -> None:
        """Clear only the independent rolling channel and its F15 context."""
        self.samples.clear()
        self._episode = None
        self._rollback_samples.clear()
        self._clock_utc = None
        self._clock_runtime = None

    def snapshot(self, now: datetime) -> LearningSnapshot:
        """Return robust short/long references and confidence."""
        self._prune(now)
        peaks = [sample.peak_lph for sample in self.samples]
        short_cutoff = now - timedelta(days=min(7, self.window_days))
        short_peaks = [
            sample.peak_lph for sample in self.samples if sample.timestamp >= short_cutoff
        ]

        long_ref = _percentile(peaks, 0.95)
        short_ref = _percentile(short_peaks, 0.95)

        learned: float | None
        if long_ref is None:
            learned = None
        elif short_ref is None:
            learned = long_ref
        else:
            # Short-term behavior gets more weight for seasonal adaptation while
            # the long-term reference prevents abrupt drops.
            weighted = (0.65 * short_ref) + (0.35 * long_ref)
            learned = max(weighted, long_ref * 0.85)

        coverage_dates = {sample.timestamp.date() for sample in self.samples}
        coverage_days = len(coverage_dates)
        age_days = 0
        if self.samples:
            age_days = max(
                1,
                int(
                    (now - min(sample.timestamp for sample in self.samples)).total_seconds()
                    // 86400
                )
                + 1,
            )

        sample_count = len(self.samples)
        reliable_days = min(14, max(7, self.window_days // 2))
        if sample_count < 5 or coverage_days < 3:
            confidence = LearningConfidence.INSUFFICIENT
        elif sample_count < 20 or coverage_days < reliable_days:
            confidence = LearningConfidence.LEARNING
        else:
            confidence = LearningConfidence.RELIABLE

        return LearningSnapshot(
            learned_max_lph=learned,
            short_reference_lph=short_ref,
            long_reference_lph=long_ref,
            sample_count=sample_count,
            coverage_days=coverage_days,
            age_days=age_days,
            window_days=self.window_days,
            confidence=confidence,
        )

    def observe_clock(self, now: datetime, runtime_now: datetime) -> None:
        """Record rollback evidence only for samples admitted before the correction."""
        if self._clock_utc is not None and self._clock_runtime is not None:
            expected = self._clock_utc + (runtime_now - self._clock_runtime)
            # datetime resolution is one microsecond; one millisecond suppresses
            # clock-read/numeric jitter while reliably detecting a 0.5 s step.
            if now < expected - timedelta(milliseconds=1):
                self._rollback_samples.update(
                    _fingerprint(sample) for sample in self.samples if sample.timestamp > now
                )
        self._clock_utc = now
        self._clock_runtime = runtime_now
        self._trim_clock_context(now)

    def _trim_clock_context(self, now: datetime) -> None:
        """Drop identities after UTC catches up or the corresponding sample is pruned."""
        self._rollback_samples.intersection_update(
            _fingerprint(sample) for sample in self.samples if sample.timestamp > now
        )

    def to_dict(
        self, *, now: datetime | None = None, runtime_now: datetime | None = None
    ) -> dict[str, Any]:
        """Serialize Rolling only; High provenance belongs exclusively to LT."""
        if now is not None and runtime_now is not None:
            self.observe_clock(now, runtime_now)
        result = {"samples": [sample.to_dict() for sample in self.samples]}
        future = [
            sample
            for sample in self.samples
            if now is not None
            and now < sample.timestamp <= now + timedelta(days=1)
            and _fingerprint(sample) in self._rollback_samples
        ]
        if future:
            result["clock_rollback"] = {
                "observed_at": now.isoformat(),
                "valid_until": max(sample.timestamp for sample in future).isoformat(),
                "fingerprints": sorted(_fingerprint(sample) for sample in future),
            }
        return result

    def restore(self, raw: Any, now: datetime) -> None:
        """Restore valid admitted samples."""
        if not isinstance(raw, dict):
            return
        samples = raw.get("samples", [])
        if not isinstance(samples, list):
            samples = []

        valid_until = now
        fingerprints: Counter[str] = Counter()
        context = raw.get("clock_rollback")
        if isinstance(context, dict):
            try:
                observed_at = datetime.fromisoformat(context["observed_at"])
                admitted_until = datetime.fromisoformat(context["valid_until"])
                identities = context.get("fingerprints")
                if (
                    observed_at.tzinfo is not None
                    and admitted_until.tzinfo is not None
                    and observed_at <= now < admitted_until
                    and admitted_until - observed_at <= timedelta(days=1)
                    and isinstance(identities, list)
                    and len(identities) <= len(samples)
                    and all(
                        isinstance(identity, str)
                        and len(identity) == 64
                        and all(char in "0123456789abcdef" for char in identity)
                        for identity in identities
                    )
                ):
                    valid_until = admitted_until
                    fingerprints = Counter(identities)
            except KeyError, TypeError, ValueError:
                pass

        restored: list[LearningSample] = []
        for item in samples:
            if not isinstance(item, dict):
                continue
            timestamp_raw = item.get("timestamp")
            peak_raw = item.get("peak_lph")
            if not isinstance(timestamp_raw, str):
                continue
            try:
                timestamp = datetime.fromisoformat(timestamp_raw)
                peak = float(peak_raw)
            except TypeError, ValueError:
                continue
            sample = LearningSample(timestamp=timestamp, peak_lph=peak)
            if (
                timestamp.tzinfo is not None
                and isfinite(peak)
                and peak > 0
                and timestamp <= valid_until
                and (timestamp <= now or fingerprints[_fingerprint(sample)] > 0)
            ):
                restored.append(sample)
                if timestamp > now:
                    fingerprints[_fingerprint(sample)] -= 1
        self.samples = restored
        self._episode = None
        self._rollback_samples = set(fingerprints)
        self._prune(now)

    def _prune(self, now: datetime) -> bool:
        cutoff = now - timedelta(days=self.window_days)
        before = len(self.samples)
        self.samples = [sample for sample in self.samples if sample.timestamp >= cutoff]
        self._trim_clock_context(now)
        return len(self.samples) != before


def _fingerprint(sample: LearningSample) -> str:
    """Bind permission to all persisted semantic fields, never just a time range."""
    payload = json.dumps(
        {"timestamp": sample.timestamp.isoformat(), "peak_lph": float(sample.peak_lph)},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(payload.encode()).hexdigest()


def _percentile(values: list[float], quantile: float) -> float | None:
    """Return a linearly interpolated percentile without external dependencies."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
