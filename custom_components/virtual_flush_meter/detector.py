"""Flush detection logic, independent from Home Assistant (stdlib only).

A flush is a temperature change of at least ``min_amplitude`` within ``window``
minutes, started by a step of at least ``derivative_threshold`` degC/min, in
either direction. Samples moving in the same direction extend the event; it
ends after ``debounce`` minutes without such a sample, or when ``window``
elapses. A new flush cannot start less than ``debounce`` minutes after the
start of the previous one. A single point more than ``outlier_threshold`` away
from the previous one is held until the next sample: dropped if the signal
comes back, accepted if it stays (continuity).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

EVENT_FLUSH = "flush"  # a new flush has been counted
EVENT_END = "end"  # the current counted flush event is over

_EPSILON = 1e-9


@dataclass
class _Event:
    start: datetime
    baseline: float
    direction: int
    extreme: float
    last_move: datetime
    counted: bool = False

    @property
    def amplitude(self) -> float:
        return abs(self.extreme - self.baseline)


class FlushDetector:
    """Turn a stream of (timestamp, temperature) samples into flush events."""

    def __init__(
        self,
        *,
        derivative_threshold: float,
        min_amplitude: float,
        window: float,
        debounce: float,
        cold_water_window: float,
        outlier_threshold: float,
    ) -> None:
        self._rate = derivative_threshold
        self._amplitude = min_amplitude
        self._window = timedelta(minutes=window)
        self._debounce = timedelta(minutes=debounce)
        # An event needs a non-zero quiet period to end, even with debounce = 0.
        self._quiet = timedelta(minutes=max(debounce, 1))
        self._cold_window = timedelta(hours=cold_water_window)
        self._outlier = outlier_threshold

        self._last: tuple[datetime, float] | None = None
        self._pending: tuple[datetime, float] | None = None
        self._event: _Event | None = None
        self._last_flush: datetime | None = None
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
        return min(self._event.last_move + self._quiet, self._event.start + self._window)

    def expire(self, now: datetime) -> list[str]:
        """End the current event if its deadline has passed."""
        deadline = self.deadline
        if deadline is None or now < deadline:
            return []
        counted = self._event.counted
        self._event = None
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

    def _accept(self, ts: datetime, value: float) -> list[str]:
        previous = self._last
        self._last = (ts, value)
        self._history.append((ts, value))
        cutoff = ts - self._cold_window
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        if previous is None:
            return []
        prev_ts, prev_value = previous
        delta = value - prev_value
        if abs(delta) < _EPSILON:
            return []

        direction = 1 if delta > 0 else -1
        minutes = max((ts - prev_ts).total_seconds() / 60, 1 / 60)
        fast = abs(delta) / minutes >= self._rate - _EPSILON

        event = self._event
        if event is not None:
            if direction == event.direction:
                event.last_move = ts
                if (value - event.extreme) * direction > 0:
                    event.extreme = value
            elif fast and not event.counted:
                # Fast reversal of an uncounted candidate: start over.
                self._event = None

        if self._event is None and fast and self._debounce_elapsed(prev_ts):
            self._event = _Event(
                start=prev_ts,
                baseline=prev_value,
                direction=direction,
                extreme=value,
                last_move=ts,
            )

        event = self._event
        if (
            event is not None
            and not event.counted
            and event.amplitude >= self._amplitude - _EPSILON
        ):
            event.counted = True
            self._last_flush = event.start
            return [EVENT_FLUSH]
        return []

    def _debounce_elapsed(self, ts: datetime) -> bool:
        return self._last_flush is None or ts - self._last_flush >= self._debounce
