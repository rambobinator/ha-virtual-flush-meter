"""Bridge between the source temperature sensor and the flush detector.

Event driven, no polling: listens to state changes of the source sensor, feeds
the detector, and schedules a timer so an event can end without a new sample.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)

from .const import (
    CONF_CALIBRATION,
    CONF_COLD_WATER_WINDOW,
    CONF_DEBOUNCE,
    CONF_DERIVATIVE_THRESHOLD,
    CONF_FLUSH_VOLUME,
    CONF_MIN_AMPLITUDE,
    CONF_SOURCE_SENSOR,
    CONF_WINDOW,
    DEFAULT_CALIBRATION,
    DEFAULT_COLD_WATER_WINDOW,
    DEFAULT_DEBOUNCE,
    DEFAULT_DERIVATIVE_THRESHOLD,
    DEFAULT_FLUSH_VOLUME,
    DEFAULT_MIN_AMPLITUDE,
    DEFAULT_WINDOW,
    OUTLIER_THRESHOLD,
)
from .detector import FlushDetector

EVENT_UPDATE = "update"

Listener = Callable[[list[str]], None]


class FlushCoordinator:
    """Own the detector for one config entry and notify entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        config = {**entry.data, **entry.options}
        self.hass = hass
        self.source = config[CONF_SOURCE_SENSOR]
        self.litres_per_flush = config.get(CONF_FLUSH_VOLUME, DEFAULT_FLUSH_VOLUME) * config.get(
            CONF_CALIBRATION, DEFAULT_CALIBRATION
        )
        self.detector = FlushDetector(
            derivative_threshold=config.get(
                CONF_DERIVATIVE_THRESHOLD, DEFAULT_DERIVATIVE_THRESHOLD
            ),
            min_amplitude=config.get(CONF_MIN_AMPLITUDE, DEFAULT_MIN_AMPLITUDE),
            window=config.get(CONF_WINDOW, DEFAULT_WINDOW),
            debounce=config.get(CONF_DEBOUNCE, DEFAULT_DEBOUNCE),
            cold_water_window=config.get(CONF_COLD_WATER_WINDOW, DEFAULT_COLD_WATER_WINDOW),
            outlier_threshold=OUTLIER_THRESHOLD,
        )
        self.unit: str | None = None
        self._listeners: list[Listener] = []
        self._unsub_state: CALLBACK_TYPE | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None

    @callback
    def async_add_listener(self, listener: Listener) -> CALLBACK_TYPE:
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    @callback
    def async_start(self) -> None:
        self._handle_state(self.hass.states.get(self.source))
        self._unsub_state = async_track_state_change_event(
            self.hass, [self.source], self._on_state_change
        )

    @callback
    def async_stop(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        self._cancel_timer()

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        if old_state is not None and new_state is not None and old_state.state == new_state.state:
            return  # attribute-only change
        self._handle_state(new_state)

    @callback
    def _handle_state(self, state: State | None) -> None:
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            value = float(state.state)
        except ValueError:
            return
        self.unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or self.unit
        events = self.detector.process(state.last_updated, value)
        self._schedule_timer()
        self._notify([*events, EVENT_UPDATE])

    @callback
    def _on_timer(self, now: datetime) -> None:
        self._unsub_timer = None
        events = self.detector.expire(now)
        self._schedule_timer()
        if events:
            self._notify(events)

    @callback
    def _schedule_timer(self) -> None:
        self._cancel_timer()
        deadline = self.detector.deadline
        if deadline is not None:
            self._unsub_timer = async_track_point_in_utc_time(self.hass, self._on_timer, deadline)

    @callback
    def _cancel_timer(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _notify(self, events: list[str]) -> None:
        for listener in list(self._listeners):
            listener(events)
