"""Sensor platform: flushed litres, flush counts, last flush volume, cold water."""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EVENT_VOLUME
from .detector import EVENT_FLUSH
from .entity import VirtualFlushEntity
from .meter import FULL, HALF


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator = entry.runtime_data
    entities = [
        LitresSensor(coordinator, entry, "litres"),
        FlushCountSensor(coordinator, entry, "flushes"),
        ColdWaterSensor(coordinator, entry, "cold_water"),
    ]
    if coordinator.meter:
        entities += [
            LastFlushVolumeSensor(coordinator, entry, "last_flush_volume"),
            FlushKindCountSensor(coordinator, entry, "half_flushes", HALF),
            FlushKindCountSensor(coordinator, entry, "full_flushes", FULL),
        ]
    async_add_entities(entities)


class LitresSensor(VirtualFlushEntity, RestoreSensor):
    """Cumulative flushed water, usable in the Energy dashboard.

    Litres are added at each flush: the volume measured on the water meter if
    one is configured, otherwise volume per flush x calibration. Changing the
    settings later never rewrites (or decreases) the past total.
    """

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_suggested_display_precision = 1
    _attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = float(last.native_value)

    @callback
    def _handle_events(self, events: list[str]) -> None:
        if EVENT_VOLUME in events and self.coordinator.last_volume is not None:
            self._attr_native_value += self.coordinator.last_volume
            self.async_write_ha_state()


class FlushCountSensor(VirtualFlushEntity, RestoreSensor):
    """Cumulative number of flushes."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:toilet"
    _attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = int(float(last.native_value))

    @callback
    def _handle_events(self, events: list[str]) -> None:
        if EVENT_FLUSH in events:
            self._attr_native_value += 1
            self.async_write_ha_state()


class ColdWaterSensor(VirtualFlushEntity, SensorEntity):
    """Rolling minimum of the bowl temperature, approximating mains water."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        return self.coordinator.detector.cold_water

    @property
    def native_unit_of_measurement(self) -> str:
        return self.coordinator.unit or UnitOfTemperature.CELSIUS


class FlushKindCountSensor(FlushCountSensor):
    """Cumulative number of half or full flushes (water meter required)."""

    _attr_icon = "mdi:toilet"

    def __init__(self, coordinator, entry: ConfigEntry, key: str, kind: str) -> None:
        super().__init__(coordinator, entry, key)
        self._kind = kind

    @callback
    def _handle_events(self, events: list[str]) -> None:
        if EVENT_VOLUME in events and self.coordinator.last_kind == self._kind:
            self._attr_native_value += 1
            self.async_write_ha_state()


class LastFlushVolumeSensor(VirtualFlushEntity, RestoreSensor):
    """Volume of the last flush, measured on the water meter or estimated."""

    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:water"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = float(last.native_value)
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_extra_state_attributes = {
                k: last_state.attributes[k]
                for k in ("measured", "flush_type", "typical_full_flush")
                if k in last_state.attributes
            }

    @callback
    def _handle_events(self, events: list[str]) -> None:
        if EVENT_VOLUME not in events:
            return
        coordinator = self.coordinator
        self._attr_native_value = coordinator.last_volume
        self._attr_extra_state_attributes = {
            "measured": coordinator.last_measured,
            "flush_type": coordinator.last_kind,
            "typical_full_flush": round(coordinator.volumes.fallback, 2),
        }
        self.async_write_ha_state()
