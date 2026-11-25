"""Tests for the water meter logic (stdlib only, no Home Assistant needed)."""

from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import sys

_PATH = Path(__file__).parents[1] / "custom_components/virtual_flush_meter/meter.py"
_spec = importlib.util.spec_from_file_location("meter", _PATH)
meter = importlib.util.module_from_spec(_spec)
sys.modules["meter"] = meter
_spec.loader.exec_module(meter)

T0 = datetime(2026, 1, 1, 12, 0)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def tracker():
    return meter.WaterMeterTracker(
        match_window=timedelta(minutes=5),
        draw_gap=timedelta(minutes=2),
        max_wait=timedelta(minutes=15),
    )


def model(recent=()):
    return meter.FlushVolumeModel(
        min_volume=2, max_volume=9, half_threshold=4.5, default_volume=6, recent=recent
    )


def feed(t, readings):
    for m, litres in readings:
        t.add_reading(at(m), litres)


def test_one_digit_flapping_is_counted_once():
    t = tracker()
    feed(t, [(0, 1000.0), (1, 1000.333), (2, 1000.0), (3, 1000.333), (4, 1000.0), (5, 1000.333)])
    assert len(t.draws) == 1
    assert round(t.draws[0].volume, 3) == 0.333


def test_increments_close_together_form_one_draw():
    t = tracker()
    feed(t, [(0, 1000.0), (10, 1002.0), (10.7, 1004.0), (11.3, 1006.0), (20, 1010.0)])
    assert [round(d.volume, 1) for d in t.draws] == [6.0, 4.0]


def test_flush_matched_with_draw_started_just_before():
    t = tracker()
    feed(t, [(0, 1000.0), (9.5, 1003.0), (10.2, 1006.0)])
    assert t.match(at(10.7), at(12)) == meter.WAIT  # too early
    draw = t.match(at(10.7), at(16))
    assert round(draw.volume, 1) == 6.0


def test_wait_while_the_tank_refills():
    t = tracker()
    feed(t, [(0, 1000.0), (10, 1002.0), (11.5, 1003.0), (13, 1004.0)])
    assert t.match(at(10.5), at(14)) == meter.WAIT  # last increase 1 min ago
    draw = t.match(at(10.5), at(15.5))
    assert round(draw.volume, 1) == 4.0


def test_prefers_draw_before_the_probe_over_hand_washing_after():
    t = tracker()
    feed(t, [(0, 1000.0), (10, 1006.0), (13, 1009.0)])  # flush, then a tap 3 min later
    draw = t.match(at(10.5), at(20))
    assert round(draw.volume, 1) == 6.0


def test_no_draw_near_the_flush():
    t = tracker()
    feed(t, [(0, 1000.0), (30, 1006.0)])
    assert t.match(at(10), at(20)) is None


def test_a_draw_is_used_once():
    t = tracker()
    feed(t, [(0, 1000.0), (10, 1006.0)])
    assert t.match(at(10), at(20)) is not None
    assert t.match(at(11), at(20)) is None


def test_meter_reset_does_not_create_a_draw():
    t = tracker()
    feed(t, [(0, 712600.0), (1, 0.0), (2, 6.0)])
    assert [d.volume for d in t.draws] == [6.0]


def test_plausible_draw_is_measured():
    m = model()
    assert m.estimate(meter.Draw(at(0), at(1), 3.3)) == (3.3, True)
    assert m.kind(3.3) == meter.HALF


def test_contaminated_draw_falls_back_to_typical_full_flush():
    m = model(recent=[6.0, 7.0, 6.7, 3.3])
    volume, measured = m.estimate(meter.Draw(at(0), at(14), 59.0))  # flush during a shower
    assert (volume, measured) == (6.7, False)
    assert m.kind(volume) == meter.FULL


def test_fallback_without_history_is_the_configured_volume():
    assert model().estimate(None) == (6, False)
