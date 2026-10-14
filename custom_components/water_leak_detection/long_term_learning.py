"""Independent, bounded, non-expiring confirmed High-normal learning (F04 V3)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any

from .source_identity import new_id, valid_id
from .validation import nonnegative_float, parse_datetime

LONG_TERM_REQUIRED_EPISODES = 3
LONG_TERM_PEAK_RATIO = Decimal("1.15")
LONG_TERM_MULTIPLIER = 1.20
MAX_LONG_TERM_HISTORY = 4096
MAX_ADMISSION_BASE_LPH = 50000.0


@dataclass(frozen=True, slots=True)
class HighEpisode:
    """One independently observed completion, bound to source and learning epoch."""

    episode_id: str
    source_generation: str
    learning_epoch: str
    timestamp: datetime
    peak_lph: float

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "source_generation": self.source_generation,
            "learning_epoch": self.learning_epoch,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "peak_lph": float(self.peak_lph),
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return sha256(payload.encode()).hexdigest()

    @classmethod
    def parse(cls, raw: Any) -> HighEpisode | None:
        if not isinstance(raw, dict) or not all(
            valid_id(raw.get(key)) for key in ("episode_id", "source_generation", "learning_epoch")
        ):
            return None
        timestamp = parse_datetime(raw.get("timestamp"))
        peak = nonnegative_float(raw.get("peak_lph"))
        if timestamp is None or peak is None or not 0 < peak < MAX_ADMISSION_BASE_LPH:
            return None
        return cls(
            raw["episode_id"], raw["source_generation"], raw["learning_epoch"], timestamp, peak
        )


class LongTermHighLearner:
    """High episode gate and monotonic summary; never inject into Rolling samples."""

    def __init__(self, source_generation: str, learning_epoch: str) -> None:
        self.source_generation = source_generation
        self.learning_epoch = learning_epoch
        self.pending_high_candidates: list[HighEpisode] = []
        self.confirmed_high_history: list[HighEpisode] = []
        self.confirmed_long_term_normal_max_lph: float | None = None
        self._promotion_id: str | None = None
        self._summary_admission_base: float | None = None
        self._high_episode: tuple[str, float] | None = None
        self._high_blocked = True
        self._high_quiet_since: datetime | None = None
        self._clock_utc: datetime | None = None
        self._clock_runtime: datetime | None = None
        self._future: dict[str, set[str]] = {"pending": set(), "confirmed": set()}
        self._conflicted_ids: set[str] = set()

    def suspend_high_episode(self) -> None:
        """Require the complete configured physical reset after an unsafe boundary."""
        self._high_episode = None
        if not self._high_blocked:
            self._high_quiet_since = None
        self._high_blocked = True

    def suspend_current_episode(self) -> None:
        self.suspend_high_episode()
        self._high_quiet_since = None

    def observe_high(
        self,
        now: datetime,
        flow_lph: float,
        *,
        runtime_now: datetime,
        started: bool,
        finished: bool,
        disqualified: bool,
        configured_burst_base: float,
        evidence_gap: bool = False,
        quiet_flow_lph: float = 100.0,
        reset_seconds: float = 300.0,
    ) -> bool:
        """Only real manager reports advance the shared High quiet/blocked guard."""
        self.observe_clock(now, runtime_now)
        flow = nonnegative_float(flow_lph)
        if flow is None:
            self.suspend_current_episode()
            return False
        if disqualified or evidence_gap:
            self.suspend_high_episode()
        if evidence_gap:
            self._high_quiet_since = None
        if self._high_blocked:
            if flow < quiet_flow_lph:
                self._high_quiet_since = self._high_quiet_since or runtime_now
                if (runtime_now - self._high_quiet_since).total_seconds() >= reset_seconds:
                    self._high_blocked = False
                    self._high_quiet_since = None
            else:
                self._high_quiet_since = None
            return False
        if started:
            self._high_episode = (new_id(), flow)
        if self._high_episode is None:
            return False
        episode_id, peak = self._high_episode
        peak = max(peak, flow)
        self._high_episode = (episode_id, peak)
        if not finished:
            return False
        self._high_episode = None
        return self.add_candidate(now, peak, configured_burst_base, episode_id=episode_id)

    def add_candidate(
        self,
        now: datetime,
        peak_lph: float,
        configured_burst_base: float,
        *,
        episode_id: str | None = None,
    ) -> bool:
        """Admit a clean completion once; callers cannot reuse confirmed episodes."""
        record = HighEpisode.parse(
            {
                "episode_id": new_id() if episode_id is None else episode_id,
                "source_generation": self.source_generation,
                "learning_epoch": self.learning_epoch,
                "timestamp": now.isoformat(),
                "peak_lph": peak_lph,
            }
        )
        if record is None or not record.peak_lph < configured_burst_base:
            return False
        if record.peak_lph <= (self.confirmed_long_term_normal_max_lph or 0):
            return False
        if record.episode_id in self._conflicted_ids:
            return False
        for old in (*self.pending_high_candidates, *self.confirmed_high_history):
            if old.episode_id != record.episode_id:
                continue
            if old != record:
                self._conflicted_ids.add(record.episode_id)
                self.pending_high_candidates = [
                    r for r in self.pending_high_candidates if r.episode_id != record.episode_id
                ]
                self.confirmed_high_history = [
                    r for r in self.confirmed_high_history if r.episode_id != record.episode_id
                ]
            return False
        self.pending_high_candidates.append(record)
        self.maintain(now, configured_burst_base)
        return True

    def maintain(
        self, now: datetime, configured_burst_base: float, *, promote: bool = True
    ) -> None:
        """Revalidate current admission, future trust and the shared deterministic cap."""
        self.pending_high_candidates = [
            r
            for r in self.pending_high_candidates
            if r.peak_lph < configured_burst_base
            and r.peak_lph > (self.confirmed_long_term_normal_max_lph or 0)
            and (r.timestamp <= now or r.fingerprint in self._future["pending"])
        ]
        self.confirmed_high_history = [
            r
            for r in self.confirmed_high_history
            if r.timestamp <= now or r.fingerprint in self._future["confirmed"]
        ]
        combined = sorted(
            [(r, "pending") for r in self.pending_high_candidates]
            + [(r, "confirmed") for r in self.confirmed_high_history],
            key=lambda item: (item[0].timestamp, item[0].peak_lph, item[0].episode_id, item[1]),
        )[-MAX_LONG_TERM_HISTORY:]
        self.pending_high_candidates = [r for r, role in combined if role == "pending"]
        self.confirmed_high_history = [r for r, role in combined if role == "confirmed"]
        if promote:
            before = self.confirmed_long_term_normal_max_lph
            self._promote(now)
            if self.confirmed_long_term_normal_max_lph != before:
                self._summary_admission_base = configured_burst_base
        self._trim_future(now)
        self._conflicted_ids = set(sorted(self._conflicted_ids)[-MAX_LONG_TERM_HISTORY:])

    def _promote(self, now: datetime) -> None:
        # Only fresh Pending members above the existing summary can confirm an
        # increase. Union of all valid bands avoids greedy overlap consumption.
        ordered = sorted(
            (r for r in self.pending_high_candidates if r.timestamp <= now),
            key=lambda r: (r.peak_lph, r.timestamp, r.episode_id),
        )
        peaks = [Decimal(str(r.peak_lph)) for r in ordered]
        right = 0
        eligible_until = -1
        admitted: set[str] = set()
        for left, record in enumerate(ordered):
            while right < len(ordered) and peaks[right] <= peaks[left] * LONG_TERM_PEAK_RATIO:
                right += 1
            if right - left >= LONG_TERM_REQUIRED_EPISODES:
                eligible_until = right - 1
            if left <= eligible_until:
                admitted.add(record.episode_id)
        promoted = [r for r in ordered if r.episode_id in admitted]
        if not promoted:
            return
        self.confirmed_long_term_normal_max_lph = max(r.peak_lph for r in promoted)
        self._promotion_id = new_id()
        self.confirmed_high_history.extend(promoted)
        self.pending_high_candidates = [
            r
            for r in self.pending_high_candidates
            if r.episode_id not in admitted and r.peak_lph > self.confirmed_long_term_normal_max_lph
        ]

    def observe_clock(self, now: datetime, runtime_now: datetime) -> None:
        """F15: exact per-role authorization, bounded to one observed rollback day."""
        if self._clock_utc is not None and self._clock_runtime is not None:
            expected = self._clock_utc + (runtime_now - self._clock_runtime)
            if now < expected - timedelta(milliseconds=1):
                for role, records in self._roles():
                    self._future[role].update(
                        r.fingerprint
                        for r in records
                        if now < r.timestamp <= now + timedelta(days=1)
                    )
        self._clock_utc, self._clock_runtime = now, runtime_now
        # A >1-day correction never leaves indefinitely future evidence behind.
        for role, records in self._roles():
            records[:] = [
                r
                for r in records
                if r.timestamp <= now
                or (r.timestamp <= now + timedelta(days=1) and r.fingerprint in self._future[role])
            ]
        self._trim_future(now)

    def _roles(self):
        return (
            ("pending", self.pending_high_candidates),
            ("confirmed", self.confirmed_high_history),
        )

    def _trim_future(self, now: datetime) -> None:
        for role, records in self._roles():
            self._future[role].intersection_update(
                r.fingerprint for r in records if r.timestamp > now
            )

    def to_dict(self, *, now: datetime, runtime_now: datetime) -> dict:
        self.observe_clock(now, runtime_now)
        raw = {
            "schema_version": 2,
            "source_generation": self.source_generation,
            "learning_epoch": self.learning_epoch,
            "confirmed_long_term_normal_max_lph": self.confirmed_long_term_normal_max_lph,
            "summary_confirmed": self.confirmed_long_term_normal_max_lph is not None,
            "promotion_id": self._promotion_id,
            "summary_admission_base_lph": self._summary_admission_base,
            "pending_high_candidates": [r.to_dict() for r in self.pending_high_candidates],
            "confirmed_high_history": [r.to_dict() for r in self.confirmed_high_history],
            "quarantined_episode_ids": sorted(self._conflicted_ids),
        }
        future = [
            r
            for role, records in self._roles()
            for r in records
            if r.fingerprint in self._future[role]
        ]
        if future:
            raw["clock_rollback"] = {
                "observed_at": now.isoformat(),
                "valid_until": max(r.timestamp for r in future).isoformat(),
                "high_pending_fingerprints": sorted(self._future["pending"]),
                "high_confirmed_fingerprints": sorted(self._future["confirmed"]),
            }
        return raw

    def restore(self, raw: Any, now: datetime, configured_burst_base: float) -> None:
        """Validate all inputs before cap; never derive a summary from History."""
        self.__init__(self.source_generation, self.learning_epoch)
        if not isinstance(raw, dict) or (
            raw.get("source_generation") != self.source_generation
            or raw.get("learning_epoch") != self.learning_epoch
        ):
            return
        conflicts = raw.get("quarantined_episode_ids")
        if isinstance(conflicts, list):
            self._conflicted_ids = set(
                sorted({x for x in conflicts if valid_id(x)})[-MAX_LONG_TERM_HISTORY:]
            )
        summary = nonnegative_float(raw.get("confirmed_long_term_normal_max_lph"))
        anchor = nonnegative_float(raw.get("summary_admission_base_lph"))
        if (
            raw.get("schema_version") == 2
            and raw.get("summary_confirmed") is True
            and summary is not None
            and anchor is not None
            and 0 < summary < anchor <= MAX_ADMISSION_BASE_LPH
            and valid_id(raw.get("promotion_id"))
        ):
            self.confirmed_long_term_normal_max_lph = summary
            self._promotion_id = raw["promotion_id"]
            self._summary_admission_base = anchor
        inputs = []
        for role, field in (
            ("pending", "pending_high_candidates"),
            ("confirmed", "confirmed_high_history"),
        ):
            records = raw.get(field)
            if not isinstance(records, list):
                continue
            permitted, until = _permissions(raw.get("clock_rollback"), role, len(records), now)
            for item in records:
                record = HighEpisode.parse(item)
                if record is not None:
                    inputs.append(
                        (
                            record,
                            role,
                            record.timestamp <= now
                            or (record.timestamp <= until and record.fingerprint in permitted),
                        )
                    )
        # Detect identity conflicts BEFORE generation/base/future filters. Any
        # two different semantic contents invalidate every variant of that ID.
        by_id: dict[str, set[str]] = {}
        for r, _, _ in inputs:
            by_id.setdefault(r.episode_id, set()).add(r.fingerprint)
        self._conflicted_ids.update(key for key, values in by_id.items() if len(values) != 1)
        accepted: dict[str, tuple[HighEpisode, str]] = {}
        for record, role, authorized in inputs:
            if (
                record.episode_id in self._conflicted_ids
                or not authorized
                or record.source_generation != self.source_generation
                or record.learning_epoch != self.learning_epoch
            ):
                continue
            if role == "confirmed" and (
                self.confirmed_long_term_normal_max_lph is None
                or record.peak_lph > self.confirmed_long_term_normal_max_lph
            ):
                continue
            if record.episode_id not in accepted or role == "confirmed":
                accepted[record.episode_id] = (record, role)
        for record, role in accepted.values():
            target = (
                self.pending_high_candidates if role == "pending" else self.confirmed_high_history
            )
            target.append(record)
            if record.timestamp > now:
                self._future[role].add(record.fingerprint)
        self.maintain(now, configured_burst_base, promote=False)

    def promote(self, now: datetime, configured_burst_base: float) -> None:
        """Recheck current anchor at UTC catch-up, never trust future history."""
        before = self.confirmed_long_term_normal_max_lph
        self.maintain(now, configured_burst_base)
        if self.confirmed_long_term_normal_max_lph != before:
            self._summary_admission_base = configured_burst_base


def _permissions(context, role: str, count: int, now: datetime) -> tuple[set[str], datetime]:
    if not isinstance(context, dict):
        return set(), now
    start = parse_datetime(context.get("observed_at"))
    end = parse_datetime(context.get("valid_until"))
    values = context.get(f"high_{role}_fingerprints")
    if (
        start is None
        or end is None
        or not start <= now < end
        or end - start > timedelta(days=1)
        or not isinstance(values, list)
        or len(values) > count
        or any(
            not isinstance(v, str) or len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
            for v in values
        )
    ):
        return set(), now
    return set(values), end
