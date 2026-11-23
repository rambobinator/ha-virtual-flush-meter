"""Flush detection engine (to be implemented).

Planned design: event driven, no polling. The detector subscribes to state
changes of the source temperature sensor with ``async_track_state_change_event``
and keeps a short history of (timestamp, temperature) samples.

A flush is detected when, within ``window`` minutes, the cumulative change
reaches ``min_amplitude`` with ``|dT/dt| >= derivative_threshold``, in either
direction. Close points are grouped into one event, and a new flush cannot
start less than ``debounce`` minutes after the previous one. A single
isolated point more than ``OUTLIER_THRESHOLD`` away from its neighbours,
with no continuity, is ignored.

The sensor and binary_sensor platforms will listen to this detector.
"""

from __future__ import annotations
