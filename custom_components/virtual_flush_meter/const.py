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
CONF_WATER_METER = "water_meter"  # optional house water meter (cumulative volume)
CONF_METER_MIN_VOLUME = "meter_min_volume"  # litres, smallest plausible flush draw
CONF_METER_MAX_VOLUME = "meter_max_volume"  # litres, largest plausible flush draw
CONF_HALF_FLUSH_VOLUME = "half_flush_volume"  # litres, below = half flush

DEFAULT_START_THRESHOLD = 0.3
DEFAULT_MIN_AMPLITUDE = 1.0
DEFAULT_GAP_FRACTION = 0.35
DEFAULT_MIN_GAP = 0.8
DEFAULT_WINDOW = 30
DEFAULT_DEBOUNCE = 5
DEFAULT_FLUSH_VOLUME = 6.0
DEFAULT_CALIBRATION = 1.0
DEFAULT_COLD_WATER_WINDOW = 12
DEFAULT_METER_MIN_VOLUME = 2.0
DEFAULT_METER_MAX_VOLUME = 9.0
DEFAULT_HALF_FLUSH_VOLUME = 4.5

# A single isolated point further than this from its neighbours is an artefact.
OUTLIER_THRESHOLD = 2.0  # degC

# Water meter timing (wM-Bus meters report about every 40 s while water flows).
METER_DRAW_GAP = 2  # minutes without increase that close a draw
METER_MATCH_WINDOW = 5  # minutes before/after a flush to look for its draw
METER_MAX_WAIT = 15  # minutes after a flush before giving up on an open draw
METER_CHECK_INTERVAL = 30  # seconds between checks while a flush awaits its volume
