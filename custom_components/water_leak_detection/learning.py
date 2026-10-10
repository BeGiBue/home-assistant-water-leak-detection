"""Rolling adaptive learning for normal household water flow."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from typing import Any

HIGH_NORMAL_REQUIRED_EPISODES = 3
HIGH_NORMAL_PEAK_RATIO = Decimal("1.15")
MAX_HIGH_NORMAL_HISTORY = 4096


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
        self._high_episode: _Episode | None = None
        self._high_blocked = False
        self._high_quiet_since: datetime | None = None
        self.pending_high_candidates: list[LearningSample] = []
        self.confirmed_high_history: list[LearningSample] = []
        self._rollback_high_pending: set[str] = set()
        self._rollback_high_confirmed: set[str] = set()
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
                    self.samples.append(
                        LearningSample(timestamp=now, peak_lph=episode.peak_lph)
                    )
                    changed = True
                self._episode = None
        else:
            episode.quiet_since = None

        return changed

    def observe_high(
        self,
        now: datetime,
        flow_lph: float,
        *,
        runtime_now: datetime,
        started: bool,
        finished: bool,
        disqualified: bool,
        evidence_gap: bool = False,
        quiet_flow_lph: float = 100.0,
        reset_seconds: float = 300.0,
    ) -> bool:
        """Track only an actual High IDLE→MONITORING→physical-IDLE episode.

        The manager supplies detector transitions and the engine's authoritative
        evidence-gap decision. After rejection, monitoring cannot start another
        candidate until a new IDLE→MONITORING transition occurs.
        """
        self.observe_clock(now, runtime_now)
        if not isfinite(flow_lph) or flow_lph < 0:
            self.suspend_high_episode()
            self._high_quiet_since = None
            return False
        if disqualified:
            self.suspend_high_episode()
        if evidence_gap:
            self._high_quiet_since = None
        if self._high_blocked:
            # Bypass forces High IDLE. Its cancellation must not turn the same
            # ongoing consumption into a fresh learnable episode. Require the
            # configured physical High quiet reset, on valid reports only.
            if flow_lph < quiet_flow_lph:
                self._high_quiet_since = self._high_quiet_since or runtime_now
                if (runtime_now - self._high_quiet_since).total_seconds() >= reset_seconds:
                    self._high_blocked = False
                    self._high_quiet_since = None
            else:
                self._high_quiet_since = None
            return False
        if started:
            self._high_episode = _Episode(started_at=runtime_now, peak_lph=flow_lph)
        episode = self._high_episode
        if episode is None:
            return False
        episode.peak_lph = max(episode.peak_lph, flow_lph)
        if not finished:
            return False
        self._high_episode = None
        return self.add_high_candidate(now, episode.peak_lph)

    def suspend_high_episode(self) -> None:
        """Permanently reject this High episode, without touching normal history."""
        self._high_episode = None
        if not self._high_blocked:
            self._high_quiet_since = None
        self._high_blocked = True

    def add_high_candidate(self, now: datetime, peak_lph: float) -> bool:
        """Admit only a completed safe episode to the confirmation gate."""
        if now.tzinfo is None or not isfinite(peak_lph) or peak_lph <= 0:
            return False
        now = now.astimezone(UTC)
        self._prune(now)
        sample = LearningSample(now, peak_lph)
        identity = _fingerprint(sample)
        if any(
            _fingerprint(existing) == identity
            for existing in (
                *self.pending_high_candidates, *self.confirmed_high_history, *self.samples
            )
        ):
            return False
        self.pending_high_candidates.append(sample)
        self._prune(now)
        self._promote_high_candidates(now)
        return True

    def _promote_high_candidates(self, now: datetime) -> None:
        """Find all valid sorted bands, without greedy order-dependent grouping.

        Each admitted member belongs to a band of at least three distinct episodes
        whose max <= min * 1.15. Overlapping bands may confirm different levels.
        Decimal comparison includes the exact 15% boundary without a fuzzy band.
        """
        ordered = sorted(
            (*self.pending_high_candidates, *self.confirmed_high_history),
            key=lambda sample: (sample.peak_lph, sample.timestamp),
        )
        peaks = [Decimal(str(sample.peak_lph)) for sample in ordered]
        right = 0
        eligible_until = -1
        admitted: set[str] = set()
        for left, sample in enumerate(ordered):
            while right < len(ordered) and peaks[right] <= peaks[left] * HIGH_NORMAL_PEAK_RATIO:
                right += 1
            if right - left >= HIGH_NORMAL_REQUIRED_EPISODES:
                eligible_until = right - 1
            if left <= eligible_until:
                admitted.add(_fingerprint(sample))
        pending: list[LearningSample] = []
        existing = {_fingerprint(sample) for sample in self.samples}
        for sample in self.pending_high_candidates:
            identity = _fingerprint(sample)
            if identity not in admitted:
                pending.append(sample)
                continue
            if identity not in existing:
                self.samples.append(sample)  # Preserve the original completion timestamp.
                existing.add(identity)
            self.confirmed_high_history.append(sample)
            if sample.timestamp > now and identity in self._rollback_high_pending:
                # Move the existing F15 permission with the original identity.
                self._rollback_samples.add(identity)
                self._rollback_high_confirmed.add(identity)
        self.pending_high_candidates = pending
        self._trim_clock_context(now)

    def suspend_current_episode(self) -> None:
        """Discard an incomplete episode after source unavailability/restart."""
        self._episode = None
        self.suspend_high_episode()
        self._high_quiet_since = None

    def reset(self) -> None:
        """Clear all learned history."""
        self.samples.clear()
        self._episode = None
        self._rollback_samples.clear()
        self.pending_high_candidates.clear()
        self.confirmed_high_history.clear()
        self._high_episode = None
        self._high_blocked = False
        self._high_quiet_since = None
        self._rollback_high_pending.clear()
        self._rollback_high_confirmed.clear()
        self._clock_utc = None
        self._clock_runtime = None

    def snapshot(self, now: datetime) -> LearningSnapshot:
        """Return robust short/long references and confidence."""
        self._prune(now)
        peaks = [sample.peak_lph for sample in self.samples]
        short_cutoff = now - timedelta(days=min(7, self.window_days))
        short_peaks = [
            sample.peak_lph
            for sample in self.samples
            if sample.timestamp >= short_cutoff
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
                    (
                        now - min(sample.timestamp for sample in self.samples)
                    ).total_seconds()
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
                self._rollback_high_pending.update(
                    _fingerprint(sample) for sample in self.pending_high_candidates
                    if sample.timestamp > now
                )
                self._rollback_high_confirmed.update(
                    _fingerprint(sample) for sample in self.confirmed_high_history
                    if sample.timestamp > now
                )
        self._clock_utc = now
        self._clock_runtime = runtime_now
        self._trim_clock_context(now)

    def _trim_clock_context(self, now: datetime) -> None:
        """Drop identities after UTC catches up or the corresponding sample is pruned."""
        self._rollback_samples.intersection_update(
            _fingerprint(sample) for sample in self.samples if sample.timestamp > now
        )
        self._rollback_high_pending.intersection_update(
            _fingerprint(sample) for sample in self.pending_high_candidates
            if sample.timestamp > now
        )
        self._rollback_high_confirmed.intersection_update(
            _fingerprint(sample) for sample in self.confirmed_high_history if sample.timestamp > now
        )

    def to_dict(
        self, *, now: datetime | None = None, runtime_now: datetime | None = None
    ) -> dict[str, Any]:
        """Serialize normal samples and completed High confirmation histories.

        The in-progress episode is intentionally not persisted because an
        incomplete pre-restart episode is not trustworthy learning evidence.
        """
        if now is not None and runtime_now is not None:
            self.observe_clock(now, runtime_now)
        result = {
            "samples": [sample.to_dict() for sample in self.samples],
            "pending_high_candidates": [
                sample.to_dict() for sample in self.pending_high_candidates
            ],
            "confirmed_high_history": [sample.to_dict() for sample in self.confirmed_high_history],
        }
        future = [
            sample for sample in self.samples
            if now is not None and now < sample.timestamp <= now + timedelta(days=1)
            and _fingerprint(sample) in self._rollback_samples
        ]
        high_pending_future = [
            sample for sample in self.pending_high_candidates
            if now is not None and now < sample.timestamp <= now + timedelta(days=1)
            and _fingerprint(sample) in self._rollback_high_pending
        ]
        high_confirmed_future = [
            sample for sample in self.confirmed_high_history
            if now is not None and now < sample.timestamp <= now + timedelta(days=1)
            and _fingerprint(sample) in self._rollback_high_confirmed
        ]
        if future or high_pending_future or high_confirmed_future:
            result["clock_rollback"] = {
                "observed_at": now.isoformat(),
                "valid_until": max(
                    sample.timestamp for sample in (
                        *future, *high_pending_future, *high_confirmed_future
                    )
                ).isoformat(),
                "fingerprints": sorted(_fingerprint(sample) for sample in future),
                "high_pending_fingerprints": sorted(
                    _fingerprint(sample) for sample in high_pending_future
                ),
                "high_confirmed_fingerprints": sorted(
                    _fingerprint(sample) for sample in high_confirmed_future
                ),
            }
        return result

    def restore(self, raw: Any, now: datetime) -> None:
        """Restore valid admitted samples."""
        self._high_episode = None
        self._high_blocked = True
        self._high_quiet_since = None
        self.pending_high_candidates.clear()
        self.confirmed_high_history.clear()
        self._rollback_high_pending.clear()
        self._rollback_high_confirmed.clear()
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
                        isinstance(identity, str) and len(identity) == 64
                        and all(char in "0123456789abcdef" for char in identity)
                        for identity in identities
                    )
                ):
                    valid_until = admitted_until
                    fingerprints = Counter(identities)
            except (KeyError, TypeError, ValueError):
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
            except (TypeError, ValueError):
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
        context = raw.get("clock_rollback")
        self.pending_high_candidates, self._rollback_high_pending = _restore_high_records(
            raw.get("pending_high_candidates"), context, "high_pending_fingerprints", now,
            cutoff=now - timedelta(days=self.window_days)
        )
        self.confirmed_high_history, self._rollback_high_confirmed = _restore_high_records(
            raw.get("confirmed_high_history"), context, "high_confirmed_fingerprints", now,
            cutoff=now - timedelta(days=self.window_days)
        )
        # A confirmed history record must still have its admitted normal sample.
        admitted = {_fingerprint(sample) for sample in self.samples}
        self.confirmed_high_history = [
            sample for sample in self.confirmed_high_history if _fingerprint(sample) in admitted
        ]
        confirmed = {_fingerprint(sample) for sample in self.confirmed_high_history}
        # Defensively remove duplicate admitted High records in a damaged store;
        # keep legacy normal-sample semantics and fingerprints otherwise intact.
        seen_high: set[str] = set()
        unique_samples: list[LearningSample] = []
        for sample in self.samples:
            identity = _fingerprint(sample)
            if identity in confirmed:
                if identity in seen_high:
                    continue
                seen_high.add(identity)
            unique_samples.append(sample)
        self.samples = unique_samples
        self.pending_high_candidates = [
            sample for sample in self.pending_high_candidates
            if _fingerprint(sample) not in confirmed and _fingerprint(sample) not in admitted
        ]
        # Validate and deduplicate both complete inputs before the shared
        # chronological window/limit selection; input order is not trusted.
        self._prune(now)

    def _prune(self, now: datetime) -> bool:
        cutoff = now - timedelta(days=self.window_days)
        before = len(self.samples)
        self.samples = [sample for sample in self.samples if sample.timestamp >= cutoff]
        before_high = len(self.pending_high_candidates) + len(self.confirmed_high_history)
        admitted_high = set(self.samples)
        history = sorted(
            (
                (sample, confirmed)
                for records, confirmed in (
                    (self.pending_high_candidates, False), (self.confirmed_high_history, True)
                )
                for sample in records if sample.timestamp >= cutoff
                and (not confirmed or sample in admitted_high)
            ),
            key=lambda item: (item[0].timestamp, item[0].peak_lph, item[1]),
        )[-MAX_HIGH_NORMAL_HISTORY:]
        self.pending_high_candidates = [sample for sample, confirmed in history if not confirmed]
        self.confirmed_high_history = [sample for sample, confirmed in history if confirmed]
        self._trim_clock_context(now)
        return len(self.samples) != before or len(history) != before_high


def _restore_high_records(
    records: Any, context: Any, identity_key: str, now: datetime, *, cutoff: datetime
) -> tuple[list[LearningSample], set[str]]:
    """Restore bounded optional history using the same F15 identity permissions.

    Permissions are scoped separately to pending and confirmed records; neither
    the normal-sample list nor another High list opens a future time range.
    """
    if not isinstance(records, list):
        return [], set()
    valid_until = now
    identities: Counter[str] = Counter()
    if isinstance(context, dict):
        try:
            observed_at = datetime.fromisoformat(context["observed_at"])
            admitted_until = datetime.fromisoformat(context["valid_until"])
            allowed = context.get(identity_key)
            if (
                observed_at.tzinfo is not None and admitted_until.tzinfo is not None
                and observed_at <= now < admitted_until
                and admitted_until - observed_at <= timedelta(days=1)
                and isinstance(allowed, list) and len(allowed) <= len(records)
                and all(
                    isinstance(identity, str) and len(identity) == 64
                    and all(char in "0123456789abcdef" for char in identity)
                    for identity in allowed
                )
            ):
                valid_until = admitted_until
                identities = Counter(allowed)
        except (KeyError, TypeError, ValueError):
            pass
    restored: list[LearningSample] = []
    seen: set[str] = set()
    future: set[str] = set()
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("timestamp"), str):
            continue
        try:
            timestamp = datetime.fromisoformat(item["timestamp"])
            if timestamp.tzinfo is None:
                continue
            timestamp = timestamp.astimezone(UTC)
            if isinstance(item.get("peak_lph"), bool):
                continue
            peak = float(item["peak_lph"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if timestamp.tzinfo is None or not isfinite(peak) or peak <= 0 or timestamp > valid_until:
            continue
        sample = LearningSample(timestamp, peak)
        identity = _fingerprint(sample)
        if timestamp < cutoff or identity in seen or (
            timestamp > now and identities[identity] <= 0
        ):
            continue
        restored.append(sample)
        seen.add(identity)
        if timestamp > now:
            identities[identity] -= 1
            future.add(identity)
    return restored, future


def _fingerprint(sample: LearningSample) -> str:
    """Bind permission to all persisted semantic fields, never just a time range."""
    payload = json.dumps(
        {"timestamp": sample.timestamp.isoformat(), "peak_lph": float(sample.peak_lph)},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
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
