"""Tests for the pure flush detector (stdlib only, no Home Assistant needed)."""

from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import sys

_PATH = Path(__file__).parents[1] / "custom_components/virtual_flush_meter/detector.py"
_spec = importlib.util.spec_from_file_location("detector", _PATH)
detector = importlib.util.module_from_spec(_spec)
sys.modules["detector"] = detector
_spec.loader.exec_module(detector)

T0 = datetime(2026, 1, 1, 12, 0)


def make(**overrides):
    params = {
        "derivative_threshold": 0.3,
        "min_amplitude": 1.0,
        "window": 30,
        "debounce": 5,
        "cold_water_window": 12,
        "outlier_threshold": 2.0,
    }
    params.update(overrides)
    return detector.FlushDetector(**params)


def feed(det, samples):
    """samples: list of (minutes since T0, value). Returns events per sample."""
    return [det.process(T0 + timedelta(minutes=m), v) for m, v in samples]


def flushes(events):
    return sum(e.count(detector.EVENT_FLUSH) for e in events)


def test_fast_drop_is_one_flush():
    det = make()
    events = feed(det, [(0, 19.0), (1, 18.5), (2, 18.0), (3, 17.5), (4, 17.2)])
    assert flushes(events) == 1
    assert det.in_flush


def test_fast_rise_is_one_flush():
    det = make()
    assert flushes(feed(det, [(0, 15.0), (1, 15.6), (2, 16.2)])) == 1


def test_slow_drift_is_not_a_flush():
    det = make()
    samples = [(m * 10, 19.0 - 0.1 * m) for m in range(30)]  # 0.01 degC/min
    assert flushes(feed(det, samples)) == 0


def test_small_fast_change_is_not_a_flush():
    det = make()
    assert flushes(feed(det, [(0, 19.0), (1, 18.6), (2, 18.4), (20, 18.5)])) == 0


def test_noise_flapping_does_not_block_real_flush():
    det = make()
    samples = [(0, 19.0), (0.1, 19.1), (0.2, 19.0), (0.3, 19.1), (1, 18.5), (2, 17.9)]
    assert flushes(feed(det, samples)) == 1


def test_event_ends_after_quiet_period():
    det = make()
    feed(det, [(0, 19.0), (1, 18.0)])
    assert det.in_flush
    assert det.expire(T0 + timedelta(minutes=5)) == []
    assert det.expire(T0 + timedelta(minutes=6)) == [detector.EVENT_END]
    assert not det.in_flush


def test_two_flushes_after_debounce():
    det = make()
    events = feed(det, [(0, 19.0), (1, 18.0), (20, 18.5), (21, 17.4)])
    assert flushes(events) == 2


def test_debounce_blocks_second_flush():
    det = make()
    # Second drop starts 3 min after the first one, within the 5 min debounce.
    events = feed(det, [(0, 19.0), (1, 18.0), (2, 19.0), (3, 18.0), (4, 17.0)])
    assert flushes(events) == 1


def test_isolated_spike_is_ignored():
    det = make()
    events = feed(det, [(0, 19.0), (1, 25.0), (2, 19.0)])
    assert flushes(events) == 0
    assert det.cold_water == 19.0


def test_large_jump_with_continuity_counts():
    det = make()
    events = feed(det, [(0, 19.0), (1, 15.0), (2, 15.1)])
    assert flushes(events) == 1


def test_cold_water_is_rolling_minimum():
    det = make(cold_water_window=1)
    feed(det, [(0, 12.0), (30, 18.0), (90, 18.5)])
    assert det.cold_water == 18.0
