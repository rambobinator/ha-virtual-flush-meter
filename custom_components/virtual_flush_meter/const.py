"""Constants for the Virtual Flush Meter integration."""

DOMAIN = "virtual_flush_meter"

# Configuration fields
CONF_SOURCE_SENSOR = "source_sensor"  # temperature probe immersed in the toilet bowl
CONF_START_THRESHOLD = "start_threshold"  # degC away from the calm value to open an event
CONF_MIN_AMPLITUDE = "min_amplitude"  # degC, amplitude cap to count a flush
CONF_GAP_FRACTION = "gap_fraction"  # share of the available gap required to count
CONF_MIN_GAP = "min_gap"  # degC, below this gap the probe is blind: count nothing
CONF_WINDOW = "window"  # minutes
CONF_DEBOUNCE = "debounce"  # minutes between two distinct flushes
CONF_FLUSH_VOLUME = "flush_volume"  # litres per flush
CONF_CALIBRATION = "calibration"  # multiplicative factor
CONF_COLD_WATER_WINDOW = "cold_water_window"  # hours, rolling minimum

DEFAULT_START_THRESHOLD = 0.3
DEFAULT_MIN_AMPLITUDE = 1.0
DEFAULT_GAP_FRACTION = 0.35
DEFAULT_MIN_GAP = 0.8
DEFAULT_WINDOW = 30
DEFAULT_DEBOUNCE = 5
DEFAULT_FLUSH_VOLUME = 6.0
DEFAULT_CALIBRATION = 1.0
DEFAULT_COLD_WATER_WINDOW = 12

# A single isolated point further than this from its neighbours is an artefact.
OUTLIER_THRESHOLD = 2.0  # degC
