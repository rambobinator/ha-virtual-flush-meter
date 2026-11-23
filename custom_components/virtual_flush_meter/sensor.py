"""Sensor platform (to be implemented).

Planned entities:
- litres flushed: device_class water, state_class total_increasing, unit L,
  value = flushes x flush_volume x calibration, restored across restarts.
- cold mains water temperature: rolling minimum of the source over
  ``cold_water_window`` hours.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
