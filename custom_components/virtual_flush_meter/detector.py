"""Flush detection logic, independent from Home Assistant (stdlib only).

Detection v2: sliding-window amplitude, no per-step rate gate (a rate between
two samples depends on how often the probe reports, which made v1 miss
flushes).

- Start: an event starts as soon as the value moves at least
  ``start_threshold`` away from a calm value seen within the last ``window``
  minutes, in either direction. The value held at the start of the window
  (last sample before it) counts too: Home Assistant fires no state change
  while the probe keeps reporting the same value, so a reading hours old can
  still be the current one. Samples older than the end of the previous event,
  or coming from the recorder history, never serve as calm value.
- Available gap: calm value minus the cold mains reference (rolling minimum
  of the samples before the event, over ``cold_water_window`` hours).
- Count, asymmetric:
  - Fast step, either direction: a single step of at least ``fast_step``
    between two readings is a flush, even when the gap is small. A probe that
    reports at once on a large change (0.5 degC for the Sonoff SNZB-02, every
    15 min otherwise) shows a fast change as one big step, while ambient drift
    arrives in small periodic steps (up to 0.4 degC per 15 min observed) and
    noise in 0.1 degC steps. A speed cannot be used instead: Home Assistant sees
    no change while the probe repeats the same value, so a jump held for 90 min
    looks slower than the evening drift.
  - Upwards, only a fast step counts: water standing in the house pipes warms
    up during the day, so an afternoon flush can bring water warmer than the
    bowl, but the bowl also drifts up towards ambient, slowly.
  - Downwards, a drop also counts at any speed if it reaches
    ``min(min_amplitude, gap_fraction x gap)``. Noise floor: if the gap is
    below ``min_gap``, the event is "blind" for this rule: missing a flush
    beats counting noise.
- End: ``window`` minutes after the start; a counted event also ends after
  ``debounce`` minutes without a new extreme. An uncounted candidate stays open
  for the whole window, as a sparse probe may report the rest of the change up
  to 15 min later. A new flush cannot be counted less than ``debounce`` minutes after
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
    start: datetime  # first sample away from the calm value
    calm: float
    calm_ts: datetime
    direction: int
    extreme: float
    extreme_ts: datetime
    gap: float
    threshold: float
    blind: bool
    max_step: float  # largest single step in the event direction
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
        fast_step: float,
        window: float,
        debounce: float,
        cold_water_window: float,
        outlier_threshold: float,
    ) -> None:
        self._start_threshold = start_threshold
        self._min_amplitude = min_amplitude
        self._gap_fraction = gap_fraction
        self._min_gap = min_gap
        self._fast_step = fast_step
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
        event = self._event
        if event is None:
            return None
        end = event.start + self._window
        return min(event.extreme_ts + self._quiet, end) if event.counted else end

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
            "largest_step": round(event.max_step, 2),
            "counted": event.counted,
        }

    def seed_history(self, samples: list[tuple[datetime, float]]) -> None:
        """Pre-fill the cold water history (e.g. from the recorder at startup).

        Seeded samples only feed the mains reference: they never count as a
        flush nor serve as calm value. A fast step among them is taken as a flush
        already counted, so a restart in the middle of a flush does not count it
        twice.
        """
        previous = None
        for ts, value in sorted(samples):
            self._history.append((ts, value))
            if previous is not None and abs(value - previous) >= self._fast_step - _EPSILON:
                # Probably a flush already counted before the restart: debounce it.
                self._last_flush = max(self._last_flush or ts, ts)
            previous = value
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
        step = value - self._last[1] if self._last is not None else 0.0
        self._last = (ts, value)
        self._history.append((ts, value))
        self._prune(ts)

        event = self._event
        if event is not None:
            event.max_step = max(event.max_step, step * event.direction)
            if (value - event.extreme) * event.direction > 0:
                event.extreme = value
                event.extreme_ts = ts
            elif (
                not event.counted
                and (event.extreme - value) * event.direction >= self._start_threshold - _EPSILON
            ):
                # Uncounted candidate reversing: new excursion from its extreme.
                self._start(event.extreme_ts, event.extreme, -event.direction, ts, value, step)
        else:
            self._try_start(ts, value, step)

        event = self._event
        if event is not None and not event.counted and self._countable(event):
            event.counted = True
            self._last_flush = event.start
            return [EVENT_FLUSH]
        return []

    def _try_start(self, ts: datetime, value: float, step: float) -> None:
        oldest = ts - self._window
        calm: list[tuple[datetime, float]] = []
        held: tuple[datetime, float] | None = None
        # Walk back from the newest sample: only the window and one more sample matter.
        for t, x in reversed(self._history):
            if t >= ts:
                continue
            if self._calm_since is not None and t < self._calm_since:
                break
            if t < oldest:
                held = (t, x)  # value still current at the start of the window
                break
            calm.append((t, x))
        if held is not None:
            calm.append(held)
        if not calm:
            return
        # On ties, keep the most recent calm point.
        hi_ts, hi = max(calm, key=lambda s: (s[1], s[0]))
        lo_ts, lo = min(calm, key=lambda s: (s[1], -s[0].timestamp()))
        if hi - value >= self._start_threshold - _EPSILON:
            self._start(hi_ts, hi, DOWN, ts, value, step)
        elif value - lo >= self._start_threshold - _EPSILON:
            self._start(lo_ts, lo, UP, ts, value, step)

    def _start(
        self,
        calm_ts: datetime,
        calm: float,
        direction: int,
        ts: datetime,
        value: float,
        step: float,
    ) -> None:
        before = [x for t, x in self._history if t < calm_ts]
        reference = min(before) if before else calm
        gap = calm - reference
        if direction == DOWN:
            threshold = min(self._min_amplitude, self._gap_fraction * max(gap, 0.0))
            blind = gap < self._min_gap - _EPSILON
        else:
            threshold = self._fast_step
            blind = False
        self._event = self._last_event = _Event(
            start=ts,
            calm=calm,
            calm_ts=calm_ts,
            direction=direction,
            extreme=value,
            extreme_ts=ts,
            gap=gap,
            threshold=threshold,
            blind=blind,
            max_step=max(step * direction, 0.0),
        )

    def _countable(self, event: _Event) -> bool:
        if self._last_flush is not None and event.start - self._last_flush < self._debounce:
            return False
        if event.max_step >= self._fast_step - _EPSILON:
            return True
        return (
            event.direction == DOWN
            and not event.blind
            and event.amplitude >= event.threshold - _EPSILON
        )
