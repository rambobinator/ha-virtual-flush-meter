"""Config flow for the Virtual Flush Meter integration."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
)
import voluptuous as vol

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
    DOMAIN,
)

# (key, default, min, max, step, unit)
_NUMBER_FIELDS = (
    (CONF_DERIVATIVE_THRESHOLD, DEFAULT_DERIVATIVE_THRESHOLD, 0.05, 5, 0.05, "°C/min"),
    (CONF_MIN_AMPLITUDE, DEFAULT_MIN_AMPLITUDE, 0.2, 10, 0.1, "°C"),
    (CONF_WINDOW, DEFAULT_WINDOW, 5, 120, 1, "min"),
    (CONF_DEBOUNCE, DEFAULT_DEBOUNCE, 0, 60, 1, "min"),
    (CONF_FLUSH_VOLUME, DEFAULT_FLUSH_VOLUME, 1, 15, 0.5, "L"),
    (CONF_CALIBRATION, DEFAULT_CALIBRATION, 0.1, 10, 0.05, None),
    (CONF_COLD_WATER_WINDOW, DEFAULT_COLD_WATER_WINDOW, 1, 48, 1, "h"),
)


def _build_schema(user_input: dict, include_source: bool = True) -> vol.Schema:
    """Build the configuration schema.

    The source sensor is only asked at creation: changing it afterwards would
    make the running litres total meaningless.
    """
    schema_dict = {}

    if include_source:
        existing = user_input.get(CONF_SOURCE_SENSOR)
        key = (
            vol.Required(CONF_SOURCE_SENSOR, description={"suggested_value": existing})
            if existing
            else vol.Required(CONF_SOURCE_SENSOR)
        )
        schema_dict[key] = EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="temperature", multiple=False)
        )

    for key, default, vmin, vmax, step, unit in _NUMBER_FIELDS:
        # NumberSelector rejects unit_of_measurement=None: omit the key instead.
        config = NumberSelectorConfig(min=vmin, max=vmax, step=step, mode="box")
        if unit:
            config["unit_of_measurement"] = unit
        schema_dict[vol.Required(key, default=user_input.get(key, default))] = NumberSelector(
            config
        )

    return vol.Schema(schema_dict)


class VirtualFlushMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Virtual Flush Meter config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_SOURCE_SENSOR])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Chasses d'eau", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_build_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VirtualFlushMeterOptionsFlow()


class VirtualFlushMeterOptionsFlow(config_entries.OptionsFlow):
    """Allow editing every parameter except the source sensor."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            user_input[CONF_SOURCE_SENSOR] = self.config_entry.data[CONF_SOURCE_SENSOR]
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_build_schema(current, include_source=False)
        )
