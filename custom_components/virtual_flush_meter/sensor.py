"""Sensor platform: flushed litres, flush count and cold mains water temperature."""

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

from .detector import EVENT_FLUSH
from .entity import VirtualFlushEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            LitresSensor(coordinator, entry, "litres"),
            FlushCountSensor(coordinator, entry, "flushes"),
            ColdWaterSensor(coordinator, entry, "cold_water"),
        ]
    )


class LitresSensor(VirtualFlushEntity, RestoreSensor):
    """Cumulative flushed water, usable in the Energy dashboard.

    Litres are added at each flush with the current volume and calibration, so
    changing them later never rewrites (or decreases) the past total.
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
        if EVENT_FLUSH in events:
            self._attr_native_value += self.coordinator.litres_per_flush
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
