"""Bridge between the source sensors and the detection logic.

Event driven: listens to state changes of the temperature probe (and of the
optional water meter), feeds the detector, and schedules timers so an event
can end, or a flush volume can be read, without a new sample.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from functools import partial
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfVolume,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util
from homeassistant.util.unit_conversion import VolumeConverter

from .const import (
    CONF_CALIBRATION,
    CONF_COLD_WATER_WINDOW,
    CONF_DEBOUNCE,
    CONF_FLUSH_VOLUME,
    CONF_GAP_FRACTION,
    CONF_HALF_FLUSH_VOLUME,
    CONF_METER_MAX_VOLUME,
    CONF_METER_MIN_VOLUME,
    CONF_MIN_AMPLITUDE,
    CONF_MIN_GAP,
    CONF_SOURCE_SENSOR,
    CONF_START_THRESHOLD,
    CONF_WATER_METER,
    CONF_WINDOW,
    DEFAULT_CALIBRATION,
    DEFAULT_COLD_WATER_WINDOW,
    DEFAULT_DEBOUNCE,
    DEFAULT_FLUSH_VOLUME,
    DEFAULT_GAP_FRACTION,
    DEFAULT_HALF_FLUSH_VOLUME,
    DEFAULT_METER_MAX_VOLUME,
    DEFAULT_METER_MIN_VOLUME,
    DEFAULT_MIN_AMPLITUDE,
    DEFAULT_MIN_GAP,
    DEFAULT_START_THRESHOLD,
    DEFAULT_WINDOW,
    DOMAIN,
    METER_CHECK_INTERVAL,
    METER_DRAW_GAP,
    METER_MATCH_WINDOW,
    METER_MAX_WAIT,
    OUTLIER_THRESHOLD,
)
from .detector import EVENT_FLUSH, FlushDetector
from .meter import WAIT, FlushVolumeModel, WaterMeterTracker

_LOGGER = logging.getLogger(__name__)

EVENT_UPDATE = "update"
EVENT_VOLUME = "volume"  # the volume of a flush is known (last_volume)

STORAGE_VERSION = 1

Listener = Callable[[list[str]], None]


def storage_key(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}"


class FlushCoordinator:
    """Own the detection logic for one config entry and notify entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        config = {**entry.data, **entry.options}
        self.hass = hass
        self.source = config[CONF_SOURCE_SENSOR]
        self.meter = config.get(CONF_WATER_METER) or None
        self.litres_per_flush = config.get(CONF_FLUSH_VOLUME, DEFAULT_FLUSH_VOLUME) * config.get(
            CONF_CALIBRATION, DEFAULT_CALIBRATION
        )
        self.detector = FlushDetector(
            start_threshold=config.get(CONF_START_THRESHOLD, DEFAULT_START_THRESHOLD),
            min_amplitude=config.get(CONF_MIN_AMPLITUDE, DEFAULT_MIN_AMPLITUDE),
            gap_fraction=config.get(CONF_GAP_FRACTION, DEFAULT_GAP_FRACTION),
            min_gap=config.get(CONF_MIN_GAP, DEFAULT_MIN_GAP),
            window=config.get(CONF_WINDOW, DEFAULT_WINDOW),
            debounce=config.get(CONF_DEBOUNCE, DEFAULT_DEBOUNCE),
            cold_water_window=config.get(CONF_COLD_WATER_WINDOW, DEFAULT_COLD_WATER_WINDOW),
            outlier_threshold=OUTLIER_THRESHOLD,
        )
        self.cold_water_window = timedelta(
            hours=config.get(CONF_COLD_WATER_WINDOW, DEFAULT_COLD_WATER_WINDOW)
        )
        self.unit: str | None = None

        # Volume of the last flush, measured on the water meter or estimated.
        self.last_volume: float | None = None
        self.last_measured: bool | None = None
        self.last_kind: str | None = None
        self.tracker: WaterMeterTracker | None = None
        self.volumes: FlushVolumeModel | None = None
        if self.meter:
            self.tracker = WaterMeterTracker(
                match_window=timedelta(minutes=METER_MATCH_WINDOW),
                draw_gap=timedelta(minutes=METER_DRAW_GAP),
                max_wait=timedelta(minutes=METER_MAX_WAIT),
            )
        self._volume_params = {
            "min_volume": config.get(CONF_METER_MIN_VOLUME, DEFAULT_METER_MIN_VOLUME),
            "max_volume": config.get(CONF_METER_MAX_VOLUME, DEFAULT_METER_MAX_VOLUME),
            "half_threshold": config.get(CONF_HALF_FLUSH_VOLUME, DEFAULT_HALF_FLUSH_VOLUME),
            "default_volume": self.litres_per_flush,
        }
        self._store: Store = Store(hass, STORAGE_VERSION, storage_key(entry.entry_id))
        self._pending: list[datetime] = []  # flushes waiting for their meter draw

        self._listeners: list[Listener] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_meter_check: CALLBACK_TYPE | None = None
        self._meter_unit_warned = False

    @callback
    def async_add_listener(self, listener: Listener) -> CALLBACK_TYPE:
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    async def async_start(self) -> None:
        await self._async_seed_from_recorder()
        if self.meter:
            stored = await self._store.async_load() or {}
            self.volumes = FlushVolumeModel(
                **self._volume_params, recent=stored.get("recent_volumes", [])
            )
            self._handle_meter_state(self.hass.states.get(self.meter))
            self._unsubs.append(
                async_track_state_change_event(self.hass, [self.meter], self._on_meter_change)
            )
        self._handle_state(self.hass.states.get(self.source))
        self._unsubs.append(
            async_track_state_change_event(self.hass, [self.source], self._on_state_change)
        )

    async def _async_seed_from_recorder(self) -> None:
        """Rebuild the cold water history so a restart does not blind detection."""
        if "recorder" not in self.hass.config.components:
            return
        from homeassistant.components.recorder import get_instance, history

        start = dt_util.utcnow() - self.cold_water_window
        try:
            states = await get_instance(self.hass).async_add_executor_job(
                partial(
                    history.state_changes_during_period,
                    self.hass,
                    start,
                    entity_id=self.source,
                    no_attributes=True,
                    include_start_time_state=False,
                )
            )
        except Exception:  # noqa: BLE001 - history is a best-effort bonus
            _LOGGER.warning("Could not read the history of %s", self.source, exc_info=True)
            return
        samples = []
        for state in states.get(self.source, []):
            try:
                samples.append((state.last_updated, float(state.state)))
            except ValueError:
                continue
        self.detector.seed_history(samples)

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._cancel_timer()
        if self._unsub_meter_check:
            self._unsub_meter_check()
            self._unsub_meter_check = None

    # --- Temperature probe -------------------------------------------------------

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        if old_state is not None and new_state is not None and old_state.state == new_state.state:
            return  # attribute-only change
        self._handle_state(new_state)

    @callback
    def _handle_state(self, state: State | None) -> None:
        value = _numeric(state)
        if value is None:
            return
        self.unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or self.unit
        events = self.detector.process(state.last_updated, value)
        self._schedule_timer()
        if EVENT_FLUSH in events:
            events += self._on_flush(state.last_updated)
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

    # --- Flush volume ---------------------------------------------------------------

    @callback
    def _on_flush(self, flush_ts: datetime) -> list[str]:
        if self.tracker is None:
            self._set_volume(self.litres_per_flush, measured=False)
            return [EVENT_VOLUME]
        self._pending.append(flush_ts)
        self._schedule_meter_check()
        return []

    @callback
    def _on_meter_change(self, event: Event[EventStateChangedData]) -> None:
        self._handle_meter_state(event.data["new_state"])

    @callback
    def _handle_meter_state(self, state: State | None) -> None:
        value = _numeric(state)
        if value is None:
            return
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        try:
            litres = VolumeConverter.convert(value, unit, UnitOfVolume.LITERS)
        except HomeAssistantError:
            if not self._meter_unit_warned:
                _LOGGER.warning("Unsupported unit %s for water meter %s", unit, self.meter)
                self._meter_unit_warned = True
            return
        self.tracker.add_reading(state.last_updated, litres)

    @callback
    def _schedule_meter_check(self) -> None:
        if self._unsub_meter_check is None and self._pending:
            self._unsub_meter_check = async_call_later(
                self.hass, METER_CHECK_INTERVAL, self._on_meter_check
            )

    @callback
    def _on_meter_check(self, now: datetime) -> None:
        self._unsub_meter_check = None
        resolved = False
        for flush_ts in list(self._pending):
            draw = self.tracker.match(flush_ts, now)
            if draw == WAIT:
                continue
            self._pending.remove(flush_ts)
            volume, measured = self.volumes.estimate(draw)
            self._set_volume(volume, measured)
            resolved = True
            self._notify([EVENT_VOLUME])
        if resolved:
            self._store.async_delay_save(lambda: {"recent_volumes": self.volumes.recent}, delay=10)
        self._schedule_meter_check()

    @callback
    def _set_volume(self, volume: float, measured: bool) -> None:
        self.last_volume = volume
        self.last_measured = measured
        self.last_kind = self.volumes.kind(volume) if self.volumes else None

    @callback
    def _notify(self, events: list[str]) -> None:
        for listener in list(self._listeners):
            listener(events)


def _numeric(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None
