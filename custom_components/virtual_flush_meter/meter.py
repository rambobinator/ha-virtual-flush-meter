"""Water meter draws and flush volume estimation (stdlib only, unit-testable).

The temperature probe says *that* the toilet was flushed; an optional house
water meter says *how much* water it took.

- Draws: consecutive increases of the meter, closer than ``draw_gap`` to each
  other, form one draw. The meter level only moves up: a one-digit flap back
  and forth (seen on wM-Bus meters) is counted once, never twice.
- Matching: a flush is matched with the draw closest to it within
  ``match_window`` before or after it, preferring the one that started before
  the probe moved (the tank refill starts at the flush, the bowl temperature
  follows). The volume is only read once the draw is over.
- Plausibility: a draw outside [min_volume, max_volume] is a flush mixed with
  another use (shower, hand washing): the volume falls back to the median of
  recently measured full flushes, or to the configured volume.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

WAIT = "wait"
HALF = "half"
FULL = "full"

# A drop larger than this means the meter was replaced or reset, not a flap.
_RESET_DROP = 10.0  # litres
# Draws older than this can no longer be matched with a flush.
_KEEP = timedelta(hours=1)


@dataclass
class Draw:
    start: datetime
    end: datetime
    volume: float
    used: bool = False


class WaterMeterTracker:
    """Turn cumulative meter readings (litres) into draws."""

    def __init__(
        self,
        *,
        match_window: timedelta,
        draw_gap: timedelta,
        max_wait: timedelta,
    ) -> None:
        self._window = match_window
        self._gap = draw_gap
        self._max_wait = max_wait
        self._level: float | None = None
        self._draws: deque[Draw] = deque()

    @property
    def draws(self) -> list[Draw]:
        return list(self._draws)

    def add_reading(self, ts: datetime, litres: float) -> None:
        if self._level is None or litres < self._level - _RESET_DROP:
            self._level = litres
            return
        delta = litres - self._level
        if delta <= 0:
            return
        self._level = litres
        last = self._draws[-1] if self._draws else None
        if last is not None and ts - last.end <= self._gap:
            last.end = ts
            last.volume += delta
        else:
            self._draws.append(Draw(start=ts, end=ts, volume=delta))
        while self._draws and self._draws[0].end < ts - _KEEP:
            self._draws.popleft()

    def match(self, flush_ts: datetime, now: datetime) -> Draw | str | None:
        """Return the draw of a flush, ``WAIT`` if it is too early, or None."""
        if now < flush_ts + self._window:
            return WAIT
        low, high = flush_ts - self._window, flush_ts + self._window
        candidates = [d for d in self._draws if not d.used and d.end >= low and d.start <= high]
        if not candidates:
            return None
        before = [d for d in candidates if d.start <= flush_ts]
        draw = before[-1] if before else candidates[0]
        if now - draw.end < self._gap and now < flush_ts + self._max_wait:
            return WAIT  # still flowing: the tank is refilling
        draw.used = True
        return draw


class FlushVolumeModel:
    """Decide the volume of a flush from its draw, and learn typical volumes."""

    def __init__(
        self,
        *,
        min_volume: float,
        max_volume: float,
        half_threshold: float,
        default_volume: float,
        recent: Iterable[float] = (),
        history: int = 10,
    ) -> None:
        self._min = min_volume
        self._max = max_volume
        self._half = half_threshold
        self._default = default_volume
        self._recent: deque[float] = deque(recent, maxlen=history)

    @property
    def recent(self) -> list[float]:
        """Recently measured volumes, to persist across restarts."""
        return list(self._recent)

    @property
    def fallback(self) -> float:
        """Typical full flush: median of recent measured full flushes."""
        full = [v for v in self._recent if v >= self._half]
        return median(full) if full else self._default

    def estimate(self, draw: Draw | None) -> tuple[float, bool]:
        """Return (litres, measured)."""
        if draw is not None and self._min <= draw.volume <= self._max:
            volume = round(draw.volume, 2)
            self._recent.append(volume)
            return volume, True
        return self.fallback, False

    def kind(self, volume: float) -> str:
        return HALF if volume < self._half else FULL
