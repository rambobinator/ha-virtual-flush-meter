"""Base entity shared by all Virtual Flush Meter platforms."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import FlushCoordinator


class VirtualFlushEntity(Entity):
    """Entity updated by the coordinator, grouped under one device per entry."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: FlushCoordinator, entry: ConfigEntry, key: str) -> None:
        self.coordinator = coordinator
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_events))

    @callback
    def _handle_events(self, events: list[str]) -> None:
        self.async_write_ha_state()
