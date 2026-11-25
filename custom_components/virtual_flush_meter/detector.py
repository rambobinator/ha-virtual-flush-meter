"""Flush detection logic, independent from Home Assistant (stdlib only).

Detection v2: sliding-window amplitude, no per-step rate gate (a rate between
two samples depends on how often the probe reports, which made v1 miss
flushes).

- Start: an event starts as soon as the value moves at least
  ``start_threshold`` away from a calm value seen within the last ``window``
  minutes, in either direction. Samples older than the end of the previous
  event never serve as calm value.
- Available gap: calm value minus the cold mains reference (rolling minimum
  of the samples before the event, over ``cold_water_window`` hours).
- Count: the excursion must go towards the mains reference (downwards) and
  reach ``min(min_amplitude, gap_fraction x gap)``. Ambient drift always goes
  the other way (towards ambient), so it is never counted.
- Noise floor: if the gap is below ``min_gap``, the event is "blind" and is
  never counted: missing a flush beats counting noise.
- End: ``debounce`` minutes without a new extreme, or ``window`` minutes after
  the start. A new flush cannot be counted less than ``debounce`` minutes after
  the start of the previous one.
- Outliers: a single point more than ``outlier_threshold`` away from the
  previous one is held until the next sample: dropped if the signal comes back,
  accepted if it stays (continuity).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

EVENT_FLUSH = "flush"  # a new flush has been counted
EVENT_END = "end"  # the current counted flush event is over

DOWN = -1
UP = 1

_EPSILON = 1e-9


@dataclass
class _Event:
    start: datetime
    calm: float
    direction: int
    extreme: float
    extreme_ts: datetime
    gap: float
    threshold: float
    blind: bool
    counted: bool = False

    @property
    def amplitude(self) -> float:
        return abs(self.extreme - self.calm)


class FlushDetector:
    """Turn a stream of (timestamp, temperature) samples into flush events."""

    def __init__(
        self,
        *,
        start_threshold: float,
        min_amplitude: float,
        gap_fraction: float,
        min_gap: float,
        window: float,
        debounce: float,
        cold_water_window: float,
        outlier_threshold: float,
    ) -> None:
        self._start_threshold = start_threshold
        self._min_amplitude = min_amplitude
        self._gap_fraction = gap_fraction
        self._min_gap = min_gap
        self._window = timedelta(minutes=window)
        self._debounce = timedelta(minutes=debounce)
        # An event needs a non-zero quiet period to end, even with debounce = 0.
        self._quiet = timedelta(minutes=max(debounce, 1))
        self._cold_window = timedelta(hours=cold_water_window)
        self._outlier = outlier_threshold

        self._last: tuple[datetime, float] | None = None
        self._pending: tuple[datetime, float] | None = None
        self._event: _Event | None = None
        self._last_event: _Event | None = None
        self._last_flush: datetime | None = None
        self._calm_since: datetime | None = None
        self._history: deque[tuple[datetime, float]] = deque()

    @property
    def in_flush(self) -> bool:
        """True while a counted flush event is in progress."""
        return self._event is not None and self._event.counted

    @property
    def cold_water(self) -> float | None:
        """Rolling minimum of accepted samples over the cold water window."""
        if not self._history:
            return None
        return min(value for _, value in self._history)

    @property
    def deadline(self) -> datetime | None:
        """When the current event ends if no further sample extends it."""
        if self._event is None:
            return None
        return min(self._event.extreme_ts + self._quiet, self._event.start + self._window)

    @property
    def diagnostics(self) -> dict[str, float | bool | str | None]:
        """Figures of the current or last event, to help tune the thresholds."""
        event = self._last_event
        if event is None:
            return {}
        return {
            "last_event_start": event.start.isoformat(),
            "last_event_direction": "down" if event.direction == DOWN else "up",
            "calm_value": round(event.calm, 2),
            "available_gap": round(event.gap, 2),
            "amplitude_threshold": round(event.threshold, 2),
            "amplitude": round(event.amplitude, 2),
            "blind": event.blind,
            "counted": event.counted,
        }

    def seed_history(self, samples: list[tuple[datetime, float]]) -> None:
        """Pre-fill the cold water history (e.g. from the recorder at startup).

        Seeded samples only feed the mains reference: they never count as a
        flush nor serve as calm value.
        """
        for ts, value in sorted(samples):
            self._history.append((ts, value))
        if self._history:
            last_ts = self._history[-1][0]
            self._prune(last_ts)
            # Strictly after the last seeded sample: none of them can be calm.
            after_seed = last_ts + timedelta(microseconds=1)
            self._calm_since = max(self._calm_since or after_seed, after_seed)

    def expire(self, now: datetime) -> list[str]:
        """End the current event if its deadline has passed."""
        deadline = self.deadline
        if deadline is None or now < deadline:
            return []
        counted = self._event.counted
        self._event = None
        self._calm_since = deadline
        return [EVENT_END] if counted else []

    def process(self, ts: datetime, value: float) -> list[str]:
        """Feed one sample and return the events it triggers."""
        events = self.expire(ts)

        if self._last is None:
            return events + self._accept(ts, value)

        if self._pending is not None:
            pending_ts, pending_value = self._pending
            self._pending = None
            if abs(value - self._last[1]) >= abs(value - pending_value):
                # The signal stayed near the jump: it was real.
                events += self._accept(pending_ts, pending_value)
            # Otherwise the signal came back: drop the isolated spike.

        if abs(value - self._last[1]) > self._outlier + _EPSILON:
            self._pending = (ts, value)
            return events

        return events + self._accept(ts, value)

    def _prune(self, now: datetime) -> None:
        cutoff = now - self._cold_window
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

    def _accept(self, ts: datetime, value: float) -> list[str]:
        self._last = (ts, value)
        self._history.append((ts, value))
        self._prune(ts)

        event = self._event
        if event is not None:
            if (value - event.extreme) * event.direction > 0:
                event.extreme = value
                event.extreme_ts = ts
            elif (
                not event.counted
                and (event.extreme - value) * event.direction >= self._start_threshold - _EPSILON
            ):
                # Uncounted candidate reversing: new excursion from its extreme.
                self._start(event.extreme_ts, event.extreme, -event.direction, ts, value)
        else:
            self._try_start(ts, value)

        event = self._event
        if event is not None and not event.counted and self._countable(event):
            event.counted = True
            self._last_flush = event.start
            return [EVENT_FLUSH]
        return []

    def _try_start(self, ts: datetime, value: float) -> None:
        oldest = ts - self._window
        if self._calm_since is not None:
            oldest = max(oldest, self._calm_since)
        calm = [(t, x) for t, x in self._history if t >= oldest and t < ts]
        if not calm:
            return
        # On ties, keep the most recent calm point.
        hi_ts, hi = max(calm, key=lambda s: (s[1], s[0]))
        lo_ts, lo = min(calm, key=lambda s: (s[1], -s[0].timestamp()))
        if hi - value >= self._start_threshold - _EPSILON:
            self._start(hi_ts, hi, DOWN, ts, value)
        elif value - lo >= self._start_threshold - _EPSILON:
            self._start(lo_ts, lo, UP, ts, value)

    def _start(
        self, calm_ts: datetime, calm: float, direction: int, ts: datetime, value: float
    ) -> None:
        before = [x for t, x in self._history if t < calm_ts]
        reference = min(before) if before else calm
        gap = calm - reference
        self._event = self._last_event = _Event(
            start=calm_ts,
            calm=calm,
            direction=direction,
            extreme=value,
            extreme_ts=ts,
            gap=gap,
            threshold=min(self._min_amplitude, self._gap_fraction * max(gap, 0.0)),
            blind=gap < self._min_gap - _EPSILON,
        )

    def _countable(self, event: _Event) -> bool:
        return (
            event.direction == DOWN
            and not event.blind
            and event.amplitude >= event.threshold - _EPSILON
            and (self._last_flush is None or event.start - self._last_flush >= self._debounce)
        )
