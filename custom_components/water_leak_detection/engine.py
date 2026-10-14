"""Pure detection engine for water leak detection."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import isclose, isfinite
from typing import Any
from uuid import uuid4

from .const import DETECTOR_PRIORITY, DetectorKind, DetectorPhase
from .validation import nonnegative_float, parse_datetime

# Absolute only: datetime has microsecond resolution; long gaps must not scale it.
EVIDENCE_TIME_TOLERANCE_SECONDS = 2e-6


@dataclass(slots=True)
class DetectorSettings:
    """Detector thresholds and timing."""

    slow_enabled: bool = True
    slow_threshold_lph: float = 3.0
    slow_detection_seconds: float = 3600.0
    slow_reset_seconds: float = 600.0
    low_enabled: bool = True
    low_threshold_lph: float = 150.0
    low_detection_seconds: float = 3600.0
    low_quiet_lph: float = 20.0
    low_reset_seconds: float = 180.0
    low_stability_enabled: bool = True
    low_stability_early_seconds: float = 1800.0
    low_stability_window_seconds: float = 900.0
    low_stability_relative_percent: float = 10.0
    low_stability_absolute_lph: float = 20.0
    low_stability_required_percent: float = 90.0
    high_threshold_lph: float = 600.0
    high_detection_seconds: float = 2700.0
    high_volume_l: float = 500.0
    high_quiet_lph: float = 100.0
    high_reset_seconds: float = 300.0
    burst_threshold_lph: float = 3500.0
    burst_detection_seconds: float = 30.0
    burst_reset_lph: float = 500.0
    burst_reset_seconds: float = 60.0
    burst_rate_rise_lph_10s: float = 1000.0
    burst_rate_confirm_seconds: float = 10.0
    shutoff_slow: bool = False
    shutoff_low: bool = False
    shutoff_high: bool = False
    shutoff_burst: bool = True


@dataclass(slots=True)
class DetectorRuntime:
    """Mutable state for one detector."""

    phase: DetectorPhase = DetectorPhase.IDLE
    started_at: datetime | None = None
    detected_at: datetime | None = None
    utc_started_at: datetime | None = None
    utc_detected_at: datetime | None = None
    quiet_since: datetime | None = None
    event_id: str | None = None
    start_total_l: float | None = None
    estimated_volume_l: float = 0.0
    plausible_volume_l: float = 0.0
    reason: str | None = None

    def reset(self) -> None:
        """Reset detector runtime."""
        self.phase = DetectorPhase.IDLE
        self.started_at = None
        self.detected_at = None
        self.utc_started_at = None
        self.utc_detected_at = None
        self.quiet_since = None
        self.event_id = None
        self.start_total_l = None
        self.estimated_volume_l = 0.0
        self.plausible_volume_l = 0.0
        self.reason = None


@dataclass(slots=True, frozen=True)
class DetectorTransition:
    """One detector phase transition."""

    kind: DetectorKind
    old_phase: DetectorPhase
    new_phase: DetectorPhase
    event_id: str | None
    started_at: datetime | None
    detected_at: datetime | None
    volume_l: float
    reason: str | None = None


@dataclass(slots=True)
class EngineSnapshot:
    """Current high-level engine state."""

    status: str
    alarm_active: bool
    shutoff_request: bool
    active_kind: DetectorKind | None
    active_event_id: str | None
    active_started_at: datetime | None
    active_detected_at: datetime | None
    active_volume_l: float


@dataclass(slots=True)
class DetectionEngine:
    """State machine for Slow, Low, High and Burst water events."""

    settings: DetectorSettings = field(default_factory=DetectorSettings)
    runtimes: dict[DetectorKind, DetectorRuntime] = field(
        default_factory=lambda: {kind: DetectorRuntime() for kind in DetectorKind}
    )
    last_evidence_gap: bool = False
    last_sample_at: datetime | None = None
    last_flow_lph: float | None = None
    last_total_l: float | None = None
    last_observed_total_l: float | None = None
    total_expected_l: float = 0.0

    low_stability_history: deque[tuple[float, float]] = field(default_factory=deque)
    low_stability_seconds: float = 0.0
    burst_normal_evidence_seconds: float = 0.0
    burst_rapid_evidence_seconds: float | None = None
    _burst_signature: tuple | None = None

    def _reset_burst_monitoring(self) -> None:
        """Discard unconfirmed Burst evidence; never clear a confirmed event."""
        runtime = self.runtimes[DetectorKind.BURST_LEAK]
        if runtime.phase is DetectorPhase.MONITORING:
            runtime.reset()
        self.burst_normal_evidence_seconds = 0.0
        self.burst_rapid_evidence_seconds = None

    @staticmethod
    def _burst_settings_signature(settings: DetectorSettings) -> tuple:
        return (
            settings.burst_threshold_lph, settings.burst_rate_rise_lph_10s,
            settings.burst_detection_seconds, settings.burst_rate_confirm_seconds,
        )

    def _clear_low_stability(self) -> None:
        """Discard only the continuous Low stability series, never normal progress."""
        self.low_stability_history.clear()
        self.low_stability_seconds = 0.0

    def _record_low_stability(self, flow: float, credit: float) -> None:
        """Keep the trailing window in confirmed evidence seconds, not report count.

        Like F05 integration, a credited interval belongs to the current report.
        Both endpoints must be in the Low band; a returning first report has no
        credit. Partially trim the oldest interval at the exact window boundary.
        """
        s = self.settings
        in_band = s.low_threshold_lph <= flow < s.high_threshold_lph
        if (
            not s.low_enabled
            or not s.low_stability_enabled
            or not in_band
            or self.runtimes[DetectorKind.LOW_FLOW].phase is DetectorPhase.IDLE
        ):
            self._clear_low_stability()
            return
        if self.last_flow_lph is None or not (
            s.low_threshold_lph <= self.last_flow_lph < s.high_threshold_lph
        ):
            self._clear_low_stability()
            return
        if credit <= 0:
            return
        self.low_stability_seconds += credit
        if self.low_stability_history and self.low_stability_history[-1][0] == flow:
            value, seconds = self.low_stability_history.pop()
            self.low_stability_history.append((value, seconds + credit))
        else:
            self.low_stability_history.append((flow, credit))
        excess = (
            sum(seconds for _, seconds in self.low_stability_history)
            - s.low_stability_window_seconds
        )
        while excess > 0 and self.low_stability_history:
            value, seconds = self.low_stability_history.popleft()
            removed = min(seconds, excess)
            excess -= removed
            if seconds > removed:
                self.low_stability_history.appendleft((value, seconds - removed))

    def _low_is_stable(self) -> bool:
        """Use a time-weighted median and a time-weighted in-tolerance share."""
        s = self.settings
        if (
            not s.low_stability_enabled
            or self.low_stability_seconds < s.low_stability_early_seconds
            or s.low_stability_window_seconds <= 0
        ):
            return False
        duration = sum(seconds for _, seconds in self.low_stability_history)
        if duration < s.low_stability_window_seconds:
            return False
        ordered = sorted(self.low_stability_history)
        cumulative = 0.0
        median = ordered[-1][0]
        for index, (value, seconds) in enumerate(ordered):
            cumulative += seconds
            if cumulative >= duration / 2:
                median = value
                if cumulative == duration / 2 and index + 1 < len(ordered):
                    median = (value + ordered[index + 1][0]) / 2
                break
        tolerance = max(
            s.low_stability_absolute_lph, median * s.low_stability_relative_percent / 100
        )
        stable = sum(
            seconds for value, seconds in self.low_stability_history
            if abs(value - median) <= tolerance
        )
        return stable >= duration * s.low_stability_required_percent / 100

    def update_settings(self, settings: DetectorSettings) -> None:
        """Apply updated thresholds without discarding current state."""
        if settings != self.settings:
            self._clear_low_stability()
        if self._burst_settings_signature(settings) != self._burst_settings_signature(
            self.settings
        ):
            self._reset_burst_monitoring()
            self.last_flow_lph = None
            self._burst_signature = None
        self.settings = settings

    def suspend_for_unavailable_source(self) -> None:
        """Suspend evidence timers while the source measurement is unavailable.

        Unconfirmed monitoring must not accumulate unknown time. Confirmed events
        remain active for safety, but any in-progress quiet/reset interval is
        cleared because an unavailable source is not evidence of zero flow.
        """
        self._clear_low_stability()
        self._reset_burst_monitoring()
        for runtime in self.runtimes.values():
            runtime.quiet_since = None
            if runtime.phase is DetectorPhase.MONITORING:
                runtime.reset()
        self.last_sample_at = None
        self.last_flow_lph = None
        self.reset_total_reference()

    def pause_source_evidence(self) -> None:
        """Pause the same source without invalidating confirmed Slow/Low/High time.

        Retain last_sample_at so the first returning zero-credit report shifts
        monitoring starts by exactly the unobserved duration. Burst candidates
        need continuous evidence; quiet and rate history cannot cross the gap.
        Source rebinds continue to use the separate destructive suspension.
        """
        self._clear_low_stability()
        self._reset_burst_monitoring()
        for kind, runtime in self.runtimes.items():
            runtime.quiet_since = None
            if kind is DetectorKind.BURST_LEAK and runtime.phase is DetectorPhase.MONITORING:
                runtime.reset()
        self.last_flow_lph = None
        self.reset_total_reference()

    def sample(
        self,
        now: datetime,
        flow_lph: float,
        total_l: float | None,
        *,
        high_flow_bypassed: bool = False,
        evidence_seconds: float | None = None,
        measurement_interval_seconds: float | None = None,
        total_fresh: bool = False,
        effective_high_threshold_lph: float | None = None,
        effective_burst_threshold_lph: float | None = None,
    ) -> list[DetectorTransition]:
        """Evaluate flow evidence; identical totals require explicit new-report proof."""
        if not isfinite(flow_lph) or flow_lph < 0:
            self.suspend_for_unavailable_source()
            return []
        if now.tzinfo is None:
            raise ValueError("Measurement time must be timezone-aware")
        if self.last_sample_at is not None and now < self.last_sample_at:
            return []
        if total_l is not None and (not isfinite(total_l) or total_l < 0):
            total_l = None

        self.last_evidence_gap = False
        raw_delta_seconds = 0.0
        delta_seconds = 0.0
        if self.last_sample_at is not None:
            raw_delta_seconds = max(0.0, (now - self.last_sample_at).total_seconds())
            if measurement_interval_seconds is not None:
                if not isfinite(measurement_interval_seconds) or measurement_interval_seconds < 0:
                    raise ValueError("Physical interval must be finite and nonnegative")
                # MQTT transport delay is not unobserved water use. Keep the
                # reception clock, translating existing detector anchors so
                # elapsed monitoring/quiet time follows verified physical time.
                transport_change = raw_delta_seconds - measurement_interval_seconds
                for runtime in self.runtimes.values():
                    if runtime.phase is DetectorPhase.MONITORING and runtime.started_at:
                        runtime.started_at += timedelta(seconds=transport_change)
                    if runtime.quiet_since:
                        runtime.quiet_since += timedelta(seconds=transport_change)
                raw_delta_seconds = measurement_interval_seconds
            if evidence_seconds is not None:
                credit = max(0.0, min(raw_delta_seconds, evidence_seconds))
                # datetime rounds to microseconds, while monotonic credit is a
                # float. Such rounding is not an outage. Never promote explicit
                # zero credit (the first report after a broken evidence chain).
                if credit > 0 and isclose(
                    raw_delta_seconds, credit,
                    rel_tol=0.0, abs_tol=EVIDENCE_TIME_TOLERANCE_SECONDS,
                ):
                    credit = raw_delta_seconds
                paused = raw_delta_seconds - credit
                for runtime in self.runtimes.values():
                    if runtime.phase is DetectorPhase.MONITORING and runtime.started_at:
                        runtime.started_at += timedelta(seconds=paused)
                    if paused > 0:
                        runtime.quiet_since = None
                if paused > 0:
                    self.last_evidence_gap = True
                    self._reset_burst_monitoring()
                    self._clear_low_stability()
                    self.last_flow_lph = None  # No rapid-rise evidence across an unknown gap.
                raw_delta_seconds = credit
            delta_seconds = raw_delta_seconds
            # Avoid integrating an arbitrarily large gap after HA was offline.
            delta_seconds = min(delta_seconds, 300.0)

        if delta_seconds > 0:
            for runtime in self.runtimes.values():
                if runtime.phase is not DetectorPhase.IDLE:
                    runtime.estimated_volume_l += flow_lph * delta_seconds / 3600.0
                    runtime.plausible_volume_l += (
                        max(flow_lph, self.last_flow_lph or 0) * raw_delta_seconds / 3600.0
                    )

        # Only the confirmed interval contributes; never the previous-flow maximum.
        self.total_expected_l += flow_lph * raw_delta_seconds / 3600.0
        if total_l is None:
            self.reset_total_reference()
        else:
            raw_total = total_l
            reset = (
                self.last_observed_total_l is not None
                and raw_total < self.last_observed_total_l
            )
            rebase = self.last_total_l is None or reset
            total_fresh = total_fresh or raw_total != self.last_observed_total_l
            self.last_observed_total_l = raw_total
            if rebase:
                self.last_total_l = raw_total
                self.total_expected_l = 0.0
                for runtime in self.runtimes.values():
                    if runtime.phase is not DetectorPhase.IDLE:
                        runtime.start_total_l = raw_total - runtime.estimated_volume_l
            else:
                increment = raw_total - self.last_total_l
                # The reference spans ALL flow reports since accepted progress,
                # not one interval. Oversized/quantized progress stays pending:
                # no fixed litre resolution and no rebase on every rejected step.
                upper = self.total_expected_l
                if total_fresh and increment > 0 and (
                    increment <= upper or isclose(increment, upper, rel_tol=1e-9)
                ):
                    self.last_total_l = raw_total
                    self.total_expected_l = max(0.0, self.total_expected_l - increment)
                elif increment > 0:
                    total_l = None  # Never expose unaccepted volume to detectors.
            if total_l is not None:
                for runtime in self.runtimes.values():
                    if runtime.phase is not DetectorPhase.IDLE and runtime.start_total_l is None:
                        runtime.start_total_l = raw_total - runtime.estimated_volume_l

        # Keep the legacy context argument for caller compatibility. High starts
        # exactly at the configured static threshold, including the Burst floor.
        effective_high = self.settings.high_threshold_lph
        effective_burst = (
            self.settings.burst_threshold_lph
            if effective_burst_threshold_lph is None
            else max(effective_high, float(effective_burst_threshold_lph))
        )
        signature = (effective_burst, *self._burst_settings_signature(self.settings)[1:])
        if self._burst_signature is not None and signature != self._burst_signature:
            self._reset_burst_monitoring()
            self.last_flow_lph = None
        self._burst_signature = signature

        self._record_low_stability(flow_lph, raw_delta_seconds)

        previous_flow = self.last_flow_lph
        previous_at = self.last_sample_at
        if previous_at is not None and measurement_interval_seconds is not None:
            previous_at = now - timedelta(seconds=measurement_interval_seconds)

        transitions: list[DetectorTransition] = []

        if self.settings.slow_enabled:
            transitions.extend(self._sample_slow(now, flow_lph, total_l))
        elif self.runtimes[DetectorKind.SLOW_LEAK].phase is not DetectorPhase.IDLE:
            self._append_transition(
                transitions,
                DetectorKind.SLOW_LEAK,
                DetectorPhase.IDLE,
                now=now,
                total_l=total_l,
            )

        if self.settings.low_enabled:
            transitions.extend(
                self._sample_low(
                    now,
                    flow_lph,
                    total_l,
                    self.settings.high_threshold_lph,
                )
            )
        elif self.runtimes[DetectorKind.LOW_FLOW].phase is not DetectorPhase.IDLE:
            self._append_transition(
                transitions,
                DetectorKind.LOW_FLOW,
                DetectorPhase.IDLE,
                now=now,
                total_l=total_l,
            )
        transitions.extend(
            self._sample_high(
                now,
                flow_lph,
                total_l,
                high_flow_bypassed,
                effective_high,
            )
        )
        transitions.extend(
            self._sample_burst(
                now,
                flow_lph,
                total_l,
                effective_burst,
                effective_high,
                previous_flow,
                previous_at,
                raw_delta_seconds,
            )
        )

        self.last_sample_at = now
        self.last_flow_lph = flow_lph
        return transitions

    def _transition(
        self,
        kind: DetectorKind,
        new_phase: DetectorPhase,
        *,
        now: datetime,
        total_l: float | None,
    ) -> DetectorTransition | None:
        runtime = self.runtimes[kind]
        old_phase = runtime.phase
        if old_phase is new_phase:
            return None

        if new_phase is DetectorPhase.MONITORING:
            runtime.phase = new_phase
            runtime.started_at = now
            runtime.detected_at = None
            runtime.quiet_since = None
            runtime.event_id = None
            runtime.start_total_l = total_l
            runtime.estimated_volume_l = 0.0
            runtime.plausible_volume_l = 0.0
        elif new_phase is DetectorPhase.ACTIVE:
            runtime.phase = new_phase
            runtime.detected_at = now
            runtime.quiet_since = None
            runtime.event_id = self._new_event_id(kind, now)
        else:
            transition = DetectorTransition(
                kind=kind,
                old_phase=old_phase,
                new_phase=new_phase,
                event_id=runtime.event_id,
                started_at=runtime.utc_started_at or runtime.started_at,
                detected_at=runtime.utc_detected_at or runtime.detected_at,
                volume_l=self._event_volume(runtime, total_l),
                reason=runtime.reason,
            )
            runtime.reset()
            return transition

        return DetectorTransition(
            kind=kind,
            old_phase=old_phase,
            new_phase=new_phase,
            event_id=runtime.event_id,
            started_at=runtime.utc_started_at or runtime.started_at,
            detected_at=runtime.utc_detected_at or runtime.detected_at,
            volume_l=self._event_volume(runtime, total_l),
            reason=runtime.reason,
        )

    def _append_transition(
        self,
        out: list[DetectorTransition],
        kind: DetectorKind,
        new_phase: DetectorPhase,
        *,
        now: datetime,
        total_l: float | None,
    ) -> bool:
        """Append a transition when one occurred."""
        transition = self._transition(
            kind, new_phase, now=now, total_l=total_l
        )
        if transition is None:
            return False
        out.append(transition)
        return True

    @staticmethod
    def _new_event_id(kind: DetectorKind, now: datetime) -> str:
        return f"{kind.value}_{now.strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:6]}"

    @staticmethod
    def _elapsed(now: datetime, start: datetime | None) -> float:
        if start is None:
            return 0.0
        return max(0.0, (now - start).total_seconds())

    def apply_controls(
        self, now: datetime, *, high_flow_bypassed: bool
    ) -> list[DetectorTransition]:
        """Apply non-measurement controls without reusing a cached flow sample."""
        transitions: list[DetectorTransition] = []
        if not self.settings.low_enabled or not self.settings.low_stability_enabled:
            self._clear_low_stability()
        disabled = {
            DetectorKind.SLOW_LEAK: not self.settings.slow_enabled,
            DetectorKind.LOW_FLOW: not self.settings.low_enabled,
            DetectorKind.HIGH_FLOW: high_flow_bypassed,
        }
        for kind, reset in disabled.items():
            if reset:
                self._append_transition(
                    transitions, kind, DetectorPhase.IDLE, now=now, total_l=None
                )
        return transitions

    def reset_total_reference(self) -> None:
        """Forget a disconnected/reset meter without clearing active safety."""
        self.last_total_l = None
        self.last_observed_total_l = None
        self.total_expected_l = 0.0

    def _event_volume(self, runtime: DetectorRuntime, total_l: float | None) -> float:
        if (
            total_l is not None and total_l == self.last_total_l
            and runtime.start_total_l is not None
        ):
            delta = total_l - runtime.start_total_l
            if delta >= 0:
                return max(delta, runtime.estimated_volume_l)
        return runtime.estimated_volume_l

    def rebind_sources(self) -> None:
        """Keep confirmed safety states but discard evidence from another meter."""
        self.suspend_for_unavailable_source()
        for runtime in self.runtimes.values():
            runtime.start_total_l = None

    def active_events(self) -> dict[str, DetectorKind]:
        """Return every confirmed event, independently of display priority."""
        return {
            runtime.event_id: kind
            for kind, runtime in self.runtimes.items()
            if runtime.phase is DetectorPhase.ACTIVE and runtime.event_id
        }

    def _sample_slow(
        self, now: datetime, flow: float, total_l: float | None
    ) -> list[DetectorTransition]:
        kind = DetectorKind.SLOW_LEAK
        runtime = self.runtimes[kind]
        s = self.settings
        out: list[DetectorTransition] = []

        if runtime.phase is DetectorPhase.IDLE:
            if s.slow_threshold_lph <= flow < s.low_threshold_lph:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.MONITORING,
                    now=now,
                    total_l=total_l,
                )
            return out

        if runtime.phase is DetectorPhase.MONITORING:
            # Slow leak intentionally requires continuous low-band flow. A normal
            # larger draw interrupts the evidence window but does not clear an
            # already confirmed Slow Leak.
            if flow < s.slow_threshold_lph or flow >= s.low_threshold_lph:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.IDLE,
                    now=now,
                    total_l=total_l,
                )
            elif self._elapsed(now, runtime.started_at) >= s.slow_detection_seconds:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.ACTIVE,
                    now=now,
                    total_l=total_l,
                )
            return out

        if flow < s.slow_threshold_lph:
            runtime.quiet_since = runtime.quiet_since or now
            if self._elapsed(now, runtime.quiet_since) >= s.slow_reset_seconds:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.IDLE,
                    now=now,
                    total_l=total_l,
                )
        else:
            runtime.quiet_since = None
        return out

    def _sample_low(
        self,
        now: datetime,
        flow: float,
        total_l: float | None,
        high_threshold_lph: float,
    ) -> list[DetectorTransition]:
        kind = DetectorKind.LOW_FLOW
        runtime = self.runtimes[kind]
        s = self.settings
        out: list[DetectorTransition] = []

        if runtime.phase is DetectorPhase.IDLE:
            if s.low_threshold_lph <= flow < high_threshold_lph:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.MONITORING,
                    now=now,
                    total_l=total_l,
                )
            return out

        if (
            runtime.phase is DetectorPhase.MONITORING
            and flow >= high_threshold_lph
        ):
            self._append_transition(
                out,
                kind,
                DetectorPhase.IDLE,
                now=now,
                total_l=total_l,
            )
            return out

        if flow < s.low_quiet_lph:
            runtime.quiet_since = runtime.quiet_since or now
            if self._elapsed(now, runtime.quiet_since) >= s.low_reset_seconds:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.IDLE,
                    now=now,
                    total_l=total_l,
                )
                return out
        else:
            runtime.quiet_since = None

        if (
            runtime.phase is DetectorPhase.MONITORING
            and (
                self._elapsed(now, runtime.started_at) >= s.low_detection_seconds
                or self._low_is_stable()
            )
        ):
            self._append_transition(
                out,
                kind,
                DetectorPhase.ACTIVE,
                now=now,
                total_l=total_l,
            )
        return out

    def _sample_high(
        self,
        now: datetime,
        flow: float,
        total_l: float | None,
        bypassed: bool,
        high_threshold_lph: float,
    ) -> list[DetectorTransition]:
        kind = DetectorKind.HIGH_FLOW
        runtime = self.runtimes[kind]
        s = self.settings
        out: list[DetectorTransition] = []

        if bypassed:
            if runtime.phase is not DetectorPhase.IDLE:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.IDLE,
                    now=now,
                    total_l=total_l,
                )
            return out

        if runtime.phase is DetectorPhase.IDLE:
            if flow >= high_threshold_lph:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.MONITORING,
                    now=now,
                    total_l=total_l,
                )
            return out

        if flow < s.high_quiet_lph:
            runtime.quiet_since = runtime.quiet_since or now
            if self._elapsed(now, runtime.quiet_since) >= s.high_reset_seconds:
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.IDLE,
                    now=now,
                    total_l=total_l,
                )
                return out
        else:
            runtime.quiet_since = None

        if runtime.phase is DetectorPhase.MONITORING:
            volume = self._event_volume(runtime, total_l)
            if (
                self._elapsed(now, runtime.started_at) >= s.high_detection_seconds
                or volume >= s.high_volume_l
            ):
                self._append_transition(
                    out,
                    kind,
                    DetectorPhase.ACTIVE,
                    now=now,
                    total_l=total_l,
                )
        return out

    def _sample_burst(
        self,
        now: datetime,
        flow: float,
        total_l: float | None,
        burst_threshold_lph: float,
        high_threshold_lph: float,
        previous_flow: float | None,
        previous_at: datetime | None,
        evidence_seconds: float,
    ) -> list[DetectorTransition]:
        kind = DetectorKind.BURST_LEAK
        runtime = self.runtimes[kind]
        s = self.settings
        out: list[DetectorTransition] = []

        rise_lph_10s = 0.0
        if previous_flow is not None and previous_at is not None:
            elapsed = (now - previous_at).total_seconds()
            if 0 < elapsed <= 60:
                rise_lph_10s = max(0.0, flow - previous_flow) * 10.0 / elapsed

        absolute_candidate = flow >= burst_threshold_lph
        rapid_candidate = (
            rise_lph_10s >= s.burst_rate_rise_lph_10s
            and absolute_candidate
        )

        if runtime.phase is DetectorPhase.IDLE:
            if (
                absolute_candidate
                and self._append_transition(
                    out,
                    kind,
                    DetectorPhase.MONITORING,
                    now=now,
                    total_l=total_l,
                )
            ):
                self.burst_normal_evidence_seconds = 0.0
                self.burst_rapid_evidence_seconds = 0.0 if rapid_candidate else None
                runtime.reason = "rapid_rise" if rapid_candidate else "absolute_flow"
            return out

        if runtime.phase is DetectorPhase.MONITORING:
            if not absolute_candidate:
                self._append_transition(
                    out, kind, DetectorPhase.IDLE, now=now, total_l=total_l
                )
                self._reset_burst_monitoring()
                return out
            self.burst_normal_evidence_seconds += evidence_seconds
            if self.burst_rapid_evidence_seconds is not None:
                self.burst_rapid_evidence_seconds += evidence_seconds
            elif rapid_candidate:
                # Qualification starts here: previous normal evidence is never
                # backdated into the additional accelerated confirmation path.
                self.burst_rapid_evidence_seconds = 0.0
            normal_ready = self.burst_normal_evidence_seconds >= s.burst_detection_seconds
            rapid_ready = (
                self.burst_rapid_evidence_seconds is not None
                and self.burst_rapid_evidence_seconds >= s.burst_rate_confirm_seconds
            )
            if normal_ready or rapid_ready:
                rapid_deadline = (
                    self.burst_normal_evidence_seconds - self.burst_rapid_evidence_seconds
                    + s.burst_rate_confirm_seconds
                ) if self.burst_rapid_evidence_seconds is not None else float("inf")
                runtime.reason = (
                    "rapid_rise" if rapid_ready and rapid_deadline < s.burst_detection_seconds
                    else "absolute_flow"
                )
                self._append_transition(
                    out, kind, DetectorPhase.ACTIVE, now=now, total_l=total_l
                )
            return out

        if flow < s.burst_reset_lph:
            runtime.quiet_since = runtime.quiet_since or now
            if self._elapsed(now, runtime.quiet_since) >= s.burst_reset_seconds:
                self._append_transition(
                    out, kind, DetectorPhase.IDLE, now=now, total_l=total_l
                )
        else:
            runtime.quiet_since = None
        return out

    def snapshot(self, total_l: float | None = None) -> EngineSnapshot:
        """Return high-level state derived from detector runtimes."""
        active_kind = self._highest_kind(DetectorPhase.ACTIVE)
        monitoring_kind = self._highest_kind(DetectorPhase.MONITORING)

        if active_kind is not None:
            status = active_kind.value
        elif monitoring_kind is not None:
            status = f"{monitoring_kind.value}_monitoring"
        else:
            status = "idle"

        runtime = self.runtimes[active_kind] if active_kind is not None else None
        return EngineSnapshot(
            status=status,
            alarm_active=active_kind is not None,
            shutoff_request=self._shutoff_request(),
            active_kind=active_kind,
            active_event_id=runtime.event_id if runtime else None,
            active_started_at=(runtime.utc_started_at or runtime.started_at) if runtime else None,
            active_detected_at=(
                runtime.utc_detected_at or runtime.detected_at
            ) if runtime else None,
            active_volume_l=(
                self._event_volume(runtime, total_l) if runtime is not None else 0.0
            ),
        )

    def _highest_kind(self, phase: DetectorPhase) -> DetectorKind | None:
        found = [kind for kind in DETECTOR_PRIORITY if self.runtimes[kind].phase is phase]
        return found[-1] if found else None

    def _shutoff_request(self) -> bool:
        mapping = {
            DetectorKind.SLOW_LEAK: self.settings.shutoff_slow,
            DetectorKind.LOW_FLOW: self.settings.shutoff_low,
            DetectorKind.HIGH_FLOW: self.settings.shutoff_high,
            DetectorKind.BURST_LEAK: self.settings.shutoff_burst,
        }
        return any(
            runtime.phase is DetectorPhase.ACTIVE and mapping[kind]
            for kind, runtime in self.runtimes.items()
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize runtime state for HA Store."""
        return {
            "last_sample_at": self.last_sample_at.isoformat()
            if self.last_sample_at
            else None,
            "last_flow_lph": self.last_flow_lph,
            "runtimes": {
                kind.value: {
                    "phase": runtime.phase.value,
                    "confirmed_active": runtime.phase is DetectorPhase.ACTIVE,
                    "started_at": (runtime.utc_started_at or runtime.started_at).isoformat()
                    if runtime.started_at or runtime.utc_started_at
                    else None,
                    "detected_at": (runtime.utc_detected_at or runtime.detected_at).isoformat()
                    if runtime.detected_at or runtime.utc_detected_at
                    else None,
                    "quiet_since": runtime.quiet_since.isoformat()
                    if runtime.quiet_since
                    else None,
                    "event_id": runtime.event_id,
                    "start_total_l": runtime.start_total_l,
                    "estimated_volume_l": runtime.estimated_volume_l,
                    "plausible_volume_l": runtime.plausible_volume_l,
                    "reason": runtime.reason,
                }
                for kind, runtime in self.runtimes.items()
            },
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore confirmed events without treating offline time as evidence."""
        # A restart creates an observation gap. Never integrate that gap and never
        # let a pre-restart MONITORING or quiet/reset timer mature while HA was
        # offline. Confirmed ACTIVE events are retained for safety.
        self._clear_low_stability()
        self._reset_burst_monitoring()
        self.last_sample_at = None
        self.last_flow_lph = None
        self.reset_total_reference()
        runtime_data = data.get("runtimes", {})
        if not isinstance(runtime_data, dict):
            return
        for kind in DetectorKind:
            raw = runtime_data.get(kind.value)
            if not isinstance(raw, dict):
                continue

            invalid_phase = False
            try:
                phase = DetectorPhase(raw.get("phase", DetectorPhase.IDLE.value))
            except (TypeError, ValueError):
                phase = DetectorPhase.IDLE
                invalid_phase = True

            runtime = self.runtimes[kind]
            event_id = raw.get("event_id")
            valid_id = (
                isinstance(event_id, str)
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", event_id) is not None
            )
            detected = parse_datetime(raw.get("detected_at"))
            started = parse_datetime(raw.get("started_at"))
            confirmed = raw.get("confirmed_active") is True or phase is DetectorPhase.ACTIVE or (
                valid_id and detected is not None
            ) or (
                (invalid_phase or phase is DetectorPhase.IDLE)
                and detected is not None and started is not None
            )
            if not confirmed:
                runtime.reset()
                continue

            runtime.phase = DetectorPhase.ACTIVE
            runtime.started_at = parse_datetime(raw.get("started_at"))
            runtime.detected_at = parse_datetime(raw.get("detected_at"))
            runtime.utc_started_at = runtime.started_at
            runtime.utc_detected_at = runtime.detected_at
            runtime.quiet_since = None
            runtime.event_id = (
                raw.get("event_id")
                if valid_id
                else self._new_event_id(kind, datetime.now().astimezone())
            )
            runtime.start_total_l = nonnegative_float(raw.get("start_total_l"))
            runtime.estimated_volume_l = (
                nonnegative_float(raw.get("estimated_volume_l")) or 0.0
            )
            runtime.plausible_volume_l = (
                nonnegative_float(raw.get("plausible_volume_l")) or runtime.estimated_volume_l
            )
            runtime.reason = (
                raw.get("reason") if isinstance(raw.get("reason"), str) else None
            )
