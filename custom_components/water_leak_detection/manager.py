"""Runtime manager for Water Leak Guard."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_FINAL_WRITE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_state_report_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BURST_DETECTION_SEC,
    CONF_BURST_LEARNED_MULTIPLIER,
    CONF_BURST_RATE_CONFIRM_SEC,
    CONF_BURST_RATE_RISE_LPH_10S,
    CONF_BURST_RESET_LPH,
    CONF_BURST_RESET_SEC,
    CONF_BURST_THRESHOLD_LPH,
    CONF_BYPASS_DEFAULT_MIN,
    CONF_FLOW_ENTITY,
    CONF_HIGH_DETECTION_MIN,
    CONF_HIGH_QUIET_LPH,
    CONF_HIGH_RESET_MIN,
    CONF_HIGH_THRESHOLD_LPH,
    CONF_HIGH_VOLUME_L,
    CONF_HYDRAULIC_BURST_FRACTION,
    CONF_LEARNING_WINDOW_DAYS,
    CONF_LOW_DETECTION_MIN,
    CONF_LOW_ENABLED,
    CONF_LOW_QUIET_LPH,
    CONF_LOW_RESET_MIN,
    CONF_LOW_STABILITY_ABSOLUTE_LPH,
    CONF_LOW_STABILITY_ENABLED,
    CONF_LOW_STABILITY_RELATIVE_PERCENT,
    CONF_LOW_STABILITY_REQUIRED_PERCENT,
    CONF_LOW_THRESHOLD_LPH,
    CONF_MANUAL_MAX_FLOW_LPH,
    CONF_PIPE_DIAMETER_MM,
    CONF_SHUTOFF_BURST,
    CONF_SHUTOFF_HIGH,
    CONF_SHUTOFF_LOW,
    CONF_SHUTOFF_SLOW,
    CONF_SLOW_DETECTION_MIN,
    CONF_SLOW_ENABLED,
    CONF_SLOW_RESET_MIN,
    CONF_SLOW_THRESHOLD_LPH,
    CONF_SOURCE_GAP_EXPLICIT,
    CONF_SOURCE_MAX_AGE_SEC,
    CONF_STATIC_PRESSURE_BAR,
    CONF_TOTAL_ENTITY,
    DEFAULT_BURST_DETECTION_SEC,
    DEFAULT_BURST_LEARNED_MULTIPLIER,
    DEFAULT_BURST_RATE_CONFIRM_SEC,
    DEFAULT_BURST_RATE_RISE_LPH_10S,
    DEFAULT_BURST_RESET_LPH,
    DEFAULT_BURST_RESET_SEC,
    DEFAULT_BURST_THRESHOLD_LPH,
    DEFAULT_BYPASS_DEFAULT_MIN,
    DEFAULT_HIGH_DETECTION_MIN,
    DEFAULT_HIGH_QUIET_LPH,
    DEFAULT_HIGH_RESET_MIN,
    DEFAULT_HIGH_THRESHOLD_LPH,
    DEFAULT_HIGH_VOLUME_L,
    DEFAULT_HYDRAULIC_BURST_FRACTION,
    DEFAULT_LEARNING_WINDOW_DAYS,
    DEFAULT_LOW_DETECTION_MIN,
    DEFAULT_LOW_ENABLED,
    DEFAULT_LOW_QUIET_LPH,
    DEFAULT_LOW_RESET_MIN,
    DEFAULT_LOW_STABILITY_ABSOLUTE_LPH,
    DEFAULT_LOW_STABILITY_ENABLED,
    DEFAULT_LOW_STABILITY_RELATIVE_PERCENT,
    DEFAULT_LOW_STABILITY_REQUIRED_PERCENT,
    DEFAULT_LOW_THRESHOLD_LPH,
    DEFAULT_MANUAL_MAX_FLOW_LPH,
    DEFAULT_PIPE_DIAMETER_MM,
    DEFAULT_SHUTOFF_BURST,
    DEFAULT_SHUTOFF_HIGH,
    DEFAULT_SHUTOFF_LOW,
    DEFAULT_SHUTOFF_SLOW,
    DEFAULT_SLOW_DETECTION_MIN,
    DEFAULT_SLOW_ENABLED,
    DEFAULT_SLOW_RESET_MIN,
    DEFAULT_SLOW_THRESHOLD_LPH,
    DEFAULT_SOURCE_MAX_AGE_SEC,
    DEFAULT_STATIC_PRESSURE_BAR,
    DOMAIN,
    EVENT_LEAK_ENDED,
    EVENT_LEAK_STARTED,
    EVENT_SHUTOFF_CLEARED,
    EVENT_SHUTOFF_REQUESTED,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
    TICK_SECONDS,
    DetectorKind,
    DetectorPhase,
)
from .engine import DetectionEngine, DetectorSettings, DetectorTransition
from .evidence import SourceEvidence
from .hydraulic import hydraulic_reference_flow_lph
from .learning import AdaptiveFlowLearner, LearningConfidence, LearningSnapshot
from .low_flow_options import low_stability_minutes
from .notifications import NotificationController
from .units import UnsupportedUnitError, normalize_flow_lph, normalize_volume_l
from .validation import nonnegative_float, parse_datetime

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[], None]


@dataclass(slots=True, frozen=True)
class AdaptiveThresholds:
    """Current adaptive thresholds and their reference context."""

    normal_reference_lph: float | None
    hydraulic_reference_lph: float
    effective_high_lph: float
    effective_burst_lph: float


class WaterLeakManager:
    """Coordinate HA source entities, persistence and the pure detector engine."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.flow_entity_id: str = entry.data[CONF_FLOW_ENTITY]
        self.total_entity_id: str | None = entry.data.get(CONF_TOTAL_ENTITY) or None
        self.engine = DetectionEngine(self._settings_from_options())
        self.learner = AdaptiveFlowLearner(
            window_days=int(
                entry.options.get(
                    CONF_LEARNING_WINDOW_DAYS,
                    DEFAULT_LEARNING_WINDOW_DAYS,
                )
            )
        )
        self.current_flow_lph: float | None = None
        self.current_total_l: float | None = None
        self.source_available = False
        self.bypass_until = None
        self._listeners: set[Listener] = set()
        self._unsubs: list[Callable[[], None]] = []
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}.{entry.entry_id}"
        )
        self._last_shutoff_request = False
        self._closed = False
        self._save_handle: asyncio.TimerHandle | None = None
        self._save_task: asyncio.Task | None = None
        self._flow_evidence = SourceEvidence()
        self._total_signature = None
        self._total_state: State | None = None
        self._total_report_pending = False
        self._bypass_deadline: float | None = None
        self._restored_elapsed: dict[str, tuple[float, float]] = {}
        self._clock_origin = dt_util.utcnow()
        self._monotonic_origin = monotonic()
        self.notifications = NotificationController(
            hass,
            entry,
            self,
            self._notification_state_changed,
        )

    async def async_setup(self) -> None:
        """Restore persisted state and start tracking source entities."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            engine_data = stored.get("engine")
            if isinstance(engine_data, dict):
                self.engine.restore(engine_data)
            sources = stored.get("sources")
            if sources != self._source_identity():
                # Legacy stores have no source identity: retain confirmed alarms,
                # but never apply an unverified old meter baseline.
                self.engine.rebind_sources()
                self.learner.reset()
            self.notifications.restore(stored.get("acknowledgements"))
            if sources == self._source_identity():
                self.learner.restore(stored.get("learning"), dt_util.utcnow())
            bypass_until = stored.get("bypass_until")
            if isinstance(bypass_until, str):
                parsed = parse_datetime(bypass_until)
                if parsed is not None and parsed > dt_util.utcnow():
                    self.bypass_until = parsed
                    self._bypass_deadline = monotonic() + (
                        parsed - dt_util.utcnow()
                    ).total_seconds()
            self._restored_elapsed = {
                event_id: (0.0, monotonic()) for event_id in self.engine.active_events()
            }
            elapsed = stored.get("event_elapsed_seconds", {})
            if isinstance(elapsed, dict):
                for event_id, value in elapsed.items():
                    duration = nonnegative_float(value)
                    if event_id in self.engine.active_events() and duration is not None:
                        self._restored_elapsed[event_id] = (duration, monotonic())

        # Every startup is an observation boundary. Reuse the learner's
        # configured physical quiet reset before admitting any new High episode.
        self.learner.suspend_high_episode()
        self._last_shutoff_request = False
        await self.notifications.async_setup()

        entities = [self.flow_entity_id]
        if self.total_entity_id:
            entities.append(self.total_entity_id)
        source_unsub = async_track_state_change_event(
            self.hass, entities, self._async_source_changed
        )
        report_unsub = async_track_state_report_event(
            self.hass, entities, self._same_value_reported
        )

        @callback
        def unsubscribe_sources():
            source_unsub()
            report_unsub()

        self._unsubs.append(unsubscribe_sources)
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._async_tick, timedelta(seconds=TICK_SECONDS)
            )
        )
        self._unsubs.append(self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_FINAL_WRITE, self._async_final_write
        ))
        await self.async_refresh()
        self._handle_shutoff_transition()
        await self.notifications.async_retry_pending()

    async def async_unload(self, *, save: bool = True) -> None:
        """Stop listeners and save current runtime state."""
        self._closed = True
        if self._save_handle is not None:
            self._save_handle.cancel()
            self._save_handle = None
        await self.notifications.async_unload()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._save_task is not None:
            await self._save_task
        if save:
            await self._store.async_save(self._serialize())

    async def _async_final_write(self, _event: Event) -> None:
        if self._save_handle is not None:
            self._save_handle.cancel()
            self._save_handle = None
        await self._store.async_save(self._serialize())

    @callback
    def async_add_listener(self, listener: Listener) -> Callable[[], None]:
        """Register an entity update listener."""
        self._listeners.add(listener)

        @callback
        def _remove() -> None:
            self._listeners.discard(listener)

        return _remove

    @callback
    def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _same_value_reported(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        state = self.hass.states.get(entity_id)
        if (
            not self._closed and state is not None and state is event.data.get("new_state")
            and state.last_reported == event.data.get("last_reported")
        ):
            if entity_id == self.flow_entity_id:
                self._flow_evidence.report(monotonic())
            elif entity_id == self.total_entity_id:
                self._total_report_pending = True
            self.hass.async_create_task(self.async_refresh())

    async def _async_source_changed(self, event: Event) -> None:
        if self._closed:
            return
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        # Object identity rejects superseded queued events, even after UTC rollback.
        if new_state is not self.hass.states.get(entity_id):
            return
        if entity_id == self.flow_entity_id and not self._usable_state(new_state):
            self._suspend_source()
        elif entity_id == self.total_entity_id:
            try:
                if not self._usable_source_state(new_state):
                    raise ValueError("Optional total source unavailable")
                normalize_volume_l(
                    float(new_state.state), new_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                )
            except (TypeError, ValueError, UnsupportedUnitError):
                # Remember an outage even if it occurs between two Flow reports.
                self.engine.reset_total_reference()
                self.current_total_l = None
        await self.async_refresh()

    async def _async_tick(self, _now) -> None:
        if not self._closed:
            self._flow_evidence.credited_seconds = 0.0
            await self.async_refresh(allow_measurement=False)
            await self.notifications.async_retry_pending()

    async def async_refresh(self, *, allow_measurement: bool = True) -> None:
        """Evaluate fresh reports; ticks only apply controls and source status."""
        if self._closed:
            return
        self._apply_controls()
        flow_state = self.hass.states.get(self.flow_entity_id)
        if not self._usable_source_state(flow_state):
            self._suspend_source()
            return
        fresh = False
        if allow_measurement:
            fresh, _ = self._flow_evidence.observe(
                flow_state, monotonic(), self.source_max_age_seconds
            )
        if not fresh:
            if self._flow_evidence.expired(monotonic(), self.source_max_age_seconds):
                self.source_available = False
                for runtime in self.engine.runtimes.values():
                    runtime.quiet_since = None
                self.learner.suspend_current_episode()
                self._notify_listeners()
            return

        try:
            flow = normalize_flow_lph(
                float(flow_state.state),
                flow_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            )
        except (TypeError, ValueError, UnsupportedUnitError) as err:
            _LOGGER.warning(
                "Unable to normalize flow source %s: %s", self.flow_entity_id, err
            )
            self._suspend_source()
            return

        total: float | None = None
        total_fresh = False
        if self.total_entity_id:
            total_state = self.hass.states.get(self.total_entity_id)
            signature = (id(total_state), total_state.last_reported) if total_state else None
            total_fresh = signature != self._total_signature or self._total_report_pending
            self._total_signature = signature
            self._total_state = total_state
            self._total_report_pending = False
            if self._usable_source_state(total_state):
                try:
                    total = normalize_volume_l(
                        float(total_state.state),
                        total_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
                    )
                except (TypeError, ValueError, UnsupportedUnitError) as err:
                    _LOGGER.debug(
                        "Unable to normalize optional total source %s: %s",
                        self.total_entity_id,
                        err,
                    )

        self.source_available = True
        self.current_flow_lph = flow
        self.current_total_l = total
        # Detector intervals use process timing; event labels and historical
        # learning timestamps independently use actual UTC.
        now = self.timer_now
        thresholds = self.adaptive_thresholds(dt_util.utcnow())
        bypass_active = self.high_flow_bypass_active
        transitions = self.engine.sample(
            now,
            flow,
            total,
            high_flow_bypassed=bypass_active,
            evidence_seconds=self._flow_evidence.credited_seconds,
            total_fresh=total_fresh,
            effective_high_threshold_lph=thresholds.effective_high_lph,
            effective_burst_threshold_lph=thresholds.effective_burst_lph,
        )
        self._handle_transitions(transitions)
        self._handle_shutoff_transition()

        snapshot = self.engine.snapshot(total)
        suspicious = (
            snapshot.alarm_active
            or self.engine.runtimes[DetectorKind.HIGH_FLOW].phase
            is not DetectorPhase.IDLE
            or self.engine.runtimes[DetectorKind.BURST_LEAK].phase
            is not DetectorPhase.IDLE
        )
        learning_changed = self.learner.observe(
            dt_util.utcnow(),
            flow,
            runtime_now=now,
            suspicious=suspicious,
            high_flow_bypassed=bypass_active,
        )
        high_started = any(
            transition.kind is DetectorKind.HIGH_FLOW
            and transition.old_phase is DetectorPhase.IDLE
            and transition.new_phase is DetectorPhase.MONITORING
            for transition in transitions
        )
        high_finished = any(
            transition.kind is DetectorKind.HIGH_FLOW
            and transition.old_phase is DetectorPhase.MONITORING
            and transition.new_phase is DetectorPhase.IDLE
            for transition in transitions
        )
        high_changed = self.learner.observe_high(
            dt_util.utcnow(), flow, runtime_now=now,
            started=high_started, finished=high_finished,
            disqualified=(
                snapshot.alarm_active or bypass_active or self.engine.last_evidence_gap
                or self.engine.runtimes[DetectorKind.BURST_LEAK].phase is not DetectorPhase.IDLE
                or any(
                    transition.kind is DetectorKind.BURST_LEAK
                    and transition.new_phase is not DetectorPhase.IDLE
                    for transition in transitions
                )
            ),
            evidence_gap=self.engine.last_evidence_gap,
            quiet_flow_lph=self.engine.settings.high_quiet_lph,
            reset_seconds=self.engine.settings.high_reset_seconds,
        )
        self._schedule_save()
        if learning_changed or high_changed:
            _LOGGER.debug(
                "Adaptive learning updated: %s",
                self.learner.snapshot(dt_util.utcnow()),
            )
        self._notify_listeners()

    def _apply_controls(self) -> None:
        if self.high_flow_bypass_active or self.engine.active_events():
            self.learner.suspend_high_episode()
        transitions = self.engine.apply_controls(
            self.timer_now, high_flow_bypassed=self.high_flow_bypass_active
        )
        self._handle_transitions(transitions)
        self._handle_shutoff_transition()
        if transitions:
            self._notify_listeners()

    def _source_identity(self) -> dict[str, str | None]:
        return {"flow": self.flow_entity_id, "total": self.total_entity_id}

    @property
    def source_max_age_seconds(self) -> float:
        """Use unlimited report gaps for the previously persisted 30-second default."""
        configured = max(
            0.0,
            float(self.entry.options.get(CONF_SOURCE_MAX_AGE_SEC, DEFAULT_SOURCE_MAX_AGE_SEC)),
        )
        if configured == 30 and not self.entry.options.get(CONF_SOURCE_GAP_EXPLICIT, False):
            return 0.0
        return configured

    def _usable_source_state(self, state: State | None) -> bool:
        if not self._usable_state(state):
            return False
        registered = er.async_get(self.hass).async_get(state.entity_id)
        return registered is None or registered.platform != DOMAIN

    @property
    def timer_now(self):
        """Engine's process-local time axis; never follows wall clock corrections."""
        return self._clock_origin + timedelta(seconds=monotonic() - self._monotonic_origin)

    def event_elapsed_seconds(self, event_id: str | None) -> float:
        if event_id in self._restored_elapsed:
            duration, received = self._restored_elapsed[event_id]
            return duration + max(0, monotonic() - received)
        for runtime in self.engine.runtimes.values():
            if runtime.event_id == event_id and runtime.started_at is not None:
                return max(0, (self.timer_now - runtime.started_at).total_seconds())
        return 0.0

    def _suspend_source(self) -> None:
        self._flow_evidence.interrupt()
        self.source_available = False
        self.current_flow_lph = None
        self.current_total_l = None
        self.engine.pause_source_evidence()
        self.learner.suspend_current_episode()
        self._schedule_save()
        self._notify_listeners()

    @staticmethod
    def _usable_state(state: State | None) -> bool:
        return state is not None and state.state not in (
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
            "",
        )

    @property
    def high_flow_bypass_active(self) -> bool:
        """Return whether the High Flow bypass is currently active."""
        if self.bypass_until is None:
            return False
        if self._bypass_deadline is None:
            self._bypass_deadline = monotonic() + max(
                0, (self.bypass_until - dt_util.utcnow()).total_seconds()
            )
        if self._bypass_deadline <= monotonic():
            self.bypass_until = None
            self._bypass_deadline = None
            self._schedule_save()
            return False
        return True

    @property
    def bypass_remaining_seconds(self) -> int:
        """Return remaining bypass duration in seconds."""
        if not self.high_flow_bypass_active or self.bypass_until is None:
            return 0
        return max(0, int(self._bypass_deadline - monotonic()))

    @property
    def bypass_default_minutes(self) -> float:
        """Return configured default bypass duration."""
        return float(
            self.entry.options.get(CONF_BYPASS_DEFAULT_MIN, DEFAULT_BYPASS_DEFAULT_MIN)
        )

    async def async_start_bypass(self, duration_minutes: float | None = None) -> None:
        """Start or restart the High Flow bypass."""
        minutes = (
            self.bypass_default_minutes if duration_minutes is None else duration_minutes
        )
        minutes = max(1.0, min(float(minutes), 24.0 * 60.0))
        self.bypass_until = dt_util.utcnow() + timedelta(minutes=minutes)
        self._bypass_deadline = monotonic() + minutes * 60
        await self.async_refresh()
        await self._store.async_save(self._serialize())

    async def async_cancel_bypass(self) -> None:
        """Cancel the High Flow bypass."""
        self.bypass_until = None
        self._bypass_deadline = None
        await self.async_refresh()
        await self._store.async_save(self._serialize())

    async def async_set_detector_enabled(self, detector: str, enabled: bool) -> None:
        """Enable or disable one user-switchable detector."""
        key = {
            "slow": CONF_SLOW_ENABLED,
            "low": CONF_LOW_ENABLED,
        }.get(detector)
        if key is None:
            raise ValueError(f"Unsupported detector toggle: {detector}")

        options = dict(self.entry.options)
        options[key] = bool(enabled)
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.apply_options()
        await self.async_refresh()

    async def async_set_bypass_default_minutes(self, minutes: float) -> None:
        """Update the default bypass duration from the Number entity."""
        options = dict(self.entry.options)
        options[CONF_BYPASS_DEFAULT_MIN] = max(1.0, min(float(minutes), 1440.0))
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.apply_options()
        self._notify_listeners()

    @callback
    def apply_options(self) -> None:
        """Apply config entry options without destroying runtime state."""
        self.engine.update_settings(self._settings_from_options())
        self.learner.update_window(
            int(
                self.entry.options.get(
                    CONF_LEARNING_WINDOW_DAYS,
                    DEFAULT_LEARNING_WINDOW_DAYS,
                )
            ),
            dt_util.utcnow(),
        )
        self.notifications.reload_recipients()
        self._apply_controls()
        if not self._closed:
            self.hass.async_create_task(self.notifications.async_retry_pending())
        self._schedule_save()
        self._notify_listeners()

    def _settings_from_options(self) -> DetectorSettings:
        opt = self.entry.options
        early_minutes, window_minutes = low_stability_minutes(opt)
        return DetectorSettings(
            slow_enabled=bool(opt.get(CONF_SLOW_ENABLED, DEFAULT_SLOW_ENABLED)),
            slow_threshold_lph=float(
                opt.get(CONF_SLOW_THRESHOLD_LPH, DEFAULT_SLOW_THRESHOLD_LPH)
            ),
            slow_detection_seconds=float(
                opt.get(CONF_SLOW_DETECTION_MIN, DEFAULT_SLOW_DETECTION_MIN)
            )
            * 60,
            slow_reset_seconds=float(
                opt.get(CONF_SLOW_RESET_MIN, DEFAULT_SLOW_RESET_MIN)
            )
            * 60,
            low_enabled=bool(opt.get(CONF_LOW_ENABLED, DEFAULT_LOW_ENABLED)),
            low_threshold_lph=float(
                opt.get(CONF_LOW_THRESHOLD_LPH, DEFAULT_LOW_THRESHOLD_LPH)
            ),
            low_detection_seconds=float(
                opt.get(CONF_LOW_DETECTION_MIN, DEFAULT_LOW_DETECTION_MIN)
            )
            * 60,
            low_quiet_lph=max(1.0, float(
                opt.get(CONF_LOW_QUIET_LPH, DEFAULT_LOW_QUIET_LPH)
            )),
            low_reset_seconds=float(
                opt.get(CONF_LOW_RESET_MIN, DEFAULT_LOW_RESET_MIN)
            )
            * 60,
            low_stability_enabled=bool(
                opt.get(CONF_LOW_STABILITY_ENABLED, DEFAULT_LOW_STABILITY_ENABLED)
            ),
            low_stability_early_seconds=early_minutes * 60,
            low_stability_window_seconds=window_minutes * 60,
            low_stability_relative_percent=float(
                opt.get(CONF_LOW_STABILITY_RELATIVE_PERCENT, DEFAULT_LOW_STABILITY_RELATIVE_PERCENT)
            ),
            low_stability_absolute_lph=float(
                opt.get(CONF_LOW_STABILITY_ABSOLUTE_LPH, DEFAULT_LOW_STABILITY_ABSOLUTE_LPH)
            ),
            low_stability_required_percent=float(
                opt.get(CONF_LOW_STABILITY_REQUIRED_PERCENT, DEFAULT_LOW_STABILITY_REQUIRED_PERCENT)
            ),
            high_threshold_lph=float(
                opt.get(CONF_HIGH_THRESHOLD_LPH, DEFAULT_HIGH_THRESHOLD_LPH)
            ),
            high_detection_seconds=float(
                opt.get(CONF_HIGH_DETECTION_MIN, DEFAULT_HIGH_DETECTION_MIN)
            )
            * 60,
            high_volume_l=float(opt.get(CONF_HIGH_VOLUME_L, DEFAULT_HIGH_VOLUME_L)),
            high_quiet_lph=max(1.0, float(
                opt.get(CONF_HIGH_QUIET_LPH, DEFAULT_HIGH_QUIET_LPH)
            )),
            high_reset_seconds=float(
                opt.get(CONF_HIGH_RESET_MIN, DEFAULT_HIGH_RESET_MIN)
            )
            * 60,
            burst_threshold_lph=float(
                opt.get(CONF_BURST_THRESHOLD_LPH, DEFAULT_BURST_THRESHOLD_LPH)
            ),
            burst_detection_seconds=float(
                opt.get(CONF_BURST_DETECTION_SEC, DEFAULT_BURST_DETECTION_SEC)
            ),
            burst_reset_lph=max(1.0, float(
                opt.get(CONF_BURST_RESET_LPH, DEFAULT_BURST_RESET_LPH)
            )),
            burst_reset_seconds=float(
                opt.get(CONF_BURST_RESET_SEC, DEFAULT_BURST_RESET_SEC)
            ),
            burst_rate_rise_lph_10s=float(
                opt.get(
                    CONF_BURST_RATE_RISE_LPH_10S,
                    DEFAULT_BURST_RATE_RISE_LPH_10S,
                )
            ),
            burst_rate_confirm_seconds=float(
                opt.get(
                    CONF_BURST_RATE_CONFIRM_SEC,
                    DEFAULT_BURST_RATE_CONFIRM_SEC,
                )
            ),
            shutoff_slow=bool(
                opt.get(CONF_SHUTOFF_SLOW, DEFAULT_SHUTOFF_SLOW)
            ),
            shutoff_low=bool(opt.get(CONF_SHUTOFF_LOW, DEFAULT_SHUTOFF_LOW)),
            shutoff_high=bool(
                opt.get(CONF_SHUTOFF_HIGH, DEFAULT_SHUTOFF_HIGH)
            ),
            shutoff_burst=bool(
                opt.get(CONF_SHUTOFF_BURST, DEFAULT_SHUTOFF_BURST)
            ),
        )

    @property
    def learning_snapshot(self) -> LearningSnapshot:
        """Return the current adaptive-learning state."""
        return self.learner.snapshot(dt_util.utcnow())

    def adaptive_thresholds(self, now=None) -> AdaptiveThresholds:
        """Return static High and adaptive Burst thresholds from safe context."""
        now = now or dt_util.utcnow()
        learning = self.learner.snapshot(now)
        opt = self.entry.options

        pipe_mm = float(
            opt.get(CONF_PIPE_DIAMETER_MM, DEFAULT_PIPE_DIAMETER_MM)
        )
        pressure_bar = float(
            opt.get(CONF_STATIC_PRESSURE_BAR, DEFAULT_STATIC_PRESSURE_BAR)
        )
        hydraulic_reference = hydraulic_reference_flow_lph(
            pipe_mm,
            pressure_bar,
        )
        base_burst = float(
            opt.get(CONF_BURST_THRESHOLD_LPH, DEFAULT_BURST_THRESHOLD_LPH)
        )
        hydraulic_fraction = float(
            opt.get(
                CONF_HYDRAULIC_BURST_FRACTION,
                DEFAULT_HYDRAULIC_BURST_FRACTION,
            )
        )
        hydraulic_burst_ceiling = max(
            base_burst,
            hydraulic_reference * hydraulic_fraction,
        )

        manual_reference = float(
            opt.get(CONF_MANUAL_MAX_FLOW_LPH, DEFAULT_MANUAL_MAX_FLOW_LPH)
        )
        references: list[float] = []
        if manual_reference > 0:
            references.append(manual_reference)

        if learning.learned_max_lph is not None:
            if learning.confidence is LearningConfidence.RELIABLE:
                references.append(learning.learned_max_lph)
            elif learning.confidence is LearningConfidence.LEARNING:
                # During the learning phase, let the model influence thresholds
                # gradually instead of immediately trusting the full learned peak.
                references.append(learning.learned_max_lph * 0.85)

        normal_reference = max(references) if references else None

        base_high = float(
            opt.get(CONF_HIGH_THRESHOLD_LPH, DEFAULT_HIGH_THRESHOLD_LPH)
        )
        effective_high = base_high

        burst_multiplier = float(
            opt.get(
                CONF_BURST_LEARNED_MULTIPLIER,
                DEFAULT_BURST_LEARNED_MULTIPLIER,
            )
        )
        learned_burst_candidate = (
            max(base_burst, normal_reference * burst_multiplier)
            if normal_reference is not None
            else base_burst
        )
        capped_burst = min(learned_burst_candidate, hydraulic_burst_ceiling)
        # Keep Burst safely above High while still respecting the hydraulic
        # plausibility ceiling established above.
        effective_burst = max(
            base_burst,
            capped_burst,
            effective_high * 1.10,
        )
        effective_burst = min(effective_burst, hydraulic_burst_ceiling)

        return AdaptiveThresholds(
            normal_reference_lph=normal_reference,
            hydraulic_reference_lph=hydraulic_reference,
            effective_high_lph=effective_high,
            effective_burst_lph=effective_burst,
        )

    async def async_reset_learning(self) -> None:
        """Clear all admitted adaptive learning samples."""
        self.learner.reset()
        await self._store.async_save(self._serialize())
        self._notify_listeners()

    def _handle_transitions(self, transitions: list[DetectorTransition]) -> None:
        for transition in transitions:
            runtime = self.engine.runtimes[transition.kind]
            if transition.new_phase is DetectorPhase.MONITORING:
                runtime.utc_started_at = dt_util.utcnow()
            elif transition.new_phase is DetectorPhase.ACTIVE:
                runtime.utc_started_at = runtime.utc_started_at or dt_util.utcnow()
                runtime.utc_detected_at = dt_util.utcnow()
            if transition.new_phase is DetectorPhase.ACTIVE or (
                transition.old_phase is DetectorPhase.ACTIVE
            ):
                self._schedule_save(urgent=True)
            if transition.new_phase is DetectorPhase.ACTIVE:
                self.hass.bus.async_fire(
                    EVENT_LEAK_STARTED,
                    self._event_payload(transition),
                )
            elif transition.old_phase is DetectorPhase.ACTIVE:
                self.hass.bus.async_fire(
                    EVENT_LEAK_ENDED,
                    self._event_payload(transition),
                )

    def _handle_shutoff_transition(self) -> None:
        current = self.engine.snapshot(self.current_total_l).shutoff_request
        if current == self._last_shutoff_request:
            return
        self._last_shutoff_request = current
        self._schedule_save(urgent=True)
        snapshot = self.engine.snapshot(self.current_total_l)
        runtime = (
            self.engine.runtimes[snapshot.active_kind]
            if snapshot.active_kind is not None
            else None
        )
        self.hass.bus.async_fire(
            EVENT_SHUTOFF_REQUESTED if current else EVENT_SHUTOFF_CLEARED,
            {
                "config_entry_id": self.entry.entry_id,
                "status": snapshot.status,
                "type": (
                    snapshot.active_kind.value
                    if snapshot.active_kind is not None
                    else None
                ),
                "event_id": snapshot.active_event_id,
                "flow_lph": self.current_flow_lph,
                "volume_l": round(snapshot.active_volume_l, 3),
                "reason": runtime.reason if runtime is not None else None,
            },
        )

    def _event_payload(self, transition: DetectorTransition) -> dict[str, Any]:
        runtime = self.engine.runtimes[transition.kind]
        started = transition.started_at
        detected = transition.detected_at
        if runtime.event_id == transition.event_id:
            started = runtime.utc_started_at or started
            detected = runtime.utc_detected_at or detected
        return {
            "config_entry_id": self.entry.entry_id,
            "type": transition.kind.value,
            "event_id": transition.event_id,
            "phase": transition.new_phase.value,
            "flow_lph": self.current_flow_lph,
            "volume_l": round(transition.volume_l, 3),
            "started_at": started.isoformat()
            if started
            else None,
            "detected_at": detected.isoformat()
            if detected
            else None,
            "reason": transition.reason,
        }

    def _serialize(self) -> dict[str, Any]:
        return {
            "sources": self._source_identity(),
            "engine": self.engine.to_dict(),
            "bypass_until": (
                dt_util.utcnow() + timedelta(seconds=max(0, self._bypass_deadline - monotonic()))
            ).isoformat() if self.high_flow_bypass_active else None,
            "event_elapsed_seconds": {
                event_id: self.event_elapsed_seconds(event_id)
                for event_id in self.engine.active_events()
            },
            "acknowledgements": self.notifications.to_dict(),
            "learning": self.learner.to_dict(now=dt_util.utcnow(), runtime_now=self.timer_now),
        }

    @callback
    def _notification_state_changed(self) -> None:
        """Persist acknowledgement changes and refresh exposed entities."""
        self._schedule_save(urgent=True)
        self._notify_listeners()

    @callback
    def _schedule_save(self, *, urgent: bool = False) -> None:
        """Coalesce writes with a fixed deadline, never a sliding debounce."""
        if self._closed:
            return
        deadline = self.hass.loop.time() + (1 if urgent else 10)
        if self._save_handle is not None:
            if self._save_handle.when() <= deadline:
                return
            self._save_handle.cancel()
        self._save_handle = self.hass.loop.call_at(deadline, self._start_save)

    @callback
    def _start_save(self) -> None:
        self._save_handle = None
        self._save_task = self.hass.async_create_task(self._async_save())

    async def _async_save(self) -> None:
        await self._store.async_save(self._serialize())
