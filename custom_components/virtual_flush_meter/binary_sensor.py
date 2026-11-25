"""Binary sensor platform: ON while a detected flush is in progress."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import VirtualFlushEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from a config entry."""
    async_add_entities([FlushBinarySensor(entry.runtime_data, entry, "flush")])


class FlushBinarySensor(VirtualFlushEntity, BinarySensorEntity):
    """Flush in progress, for automations."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def is_on(self) -> bool:
        return self.coordinator.detector.in_flush

    @property
    def extra_state_attributes(self) -> dict:
        """Figures of the last event, to tune the thresholds."""
        return self.coordinator.detector.diagnostics
