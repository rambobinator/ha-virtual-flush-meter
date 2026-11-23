"""Constants for the Virtual Flush Meter integration."""

DOMAIN = "virtual_flush_meter"

# Configuration fields
CONF_SOURCE_SENSOR = "source_sensor"  # temperature probe immersed in the toilet bowl
CONF_DERIVATIVE_THRESHOLD = "derivative_threshold"  # degC/min, absolute value
CONF_MIN_AMPLITUDE = "min_amplitude"  # degC, cumulative change within the window
CONF_WINDOW = "window"  # minutes
CONF_DEBOUNCE = "debounce"  # minutes between two distinct flushes
CONF_FLUSH_VOLUME = "flush_volume"  # litres per flush
CONF_CALIBRATION = "calibration"  # multiplicative factor
CONF_COLD_WATER_WINDOW = "cold_water_window"  # hours, rolling minimum

DEFAULT_DERIVATIVE_THRESHOLD = 0.3
DEFAULT_MIN_AMPLITUDE = 1.0
DEFAULT_WINDOW = 30
DEFAULT_DEBOUNCE = 5
DEFAULT_FLUSH_VOLUME = 6.0
DEFAULT_CALIBRATION = 1.0
DEFAULT_COLD_WATER_WINDOW = 12

# A single isolated point further than this from its neighbours is an artefact.
OUTLIER_THRESHOLD = 2.0  # degC
