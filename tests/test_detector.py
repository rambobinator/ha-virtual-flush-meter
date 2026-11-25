"""Tests for the pure flush detector (stdlib only, no Home Assistant needed)."""

from datetime import datetime, timedelta
import importlib.util
import math
from pathlib import Path
import random
import sys

_PATH = Path(__file__).parents[1] / "custom_components/virtual_flush_meter/detector.py"
_spec = importlib.util.spec_from_file_location("detector", _PATH)
detector = importlib.util.module_from_spec(_spec)
sys.modules["detector"] = detector
_spec.loader.exec_module(detector)

T0 = datetime(2026, 1, 1, 12, 0)
MAINS = 12.0


def make(mains=MAINS, **overrides):
    """Detector whose history already knows the mains temperature (if given)."""
    params = {
        "start_threshold": 0.3,
        "min_amplitude": 1.0,
        "gap_fraction": 0.5,
        "min_gap": 0.8,
        "window": 30,
        "debounce": 5,
        "cold_water_window": 12,
        "outlier_threshold": 2.0,
    }
    params.update(overrides)
    det = detector.FlushDetector(**params)
    if mains is not None:
        det.seed_history([(T0 - timedelta(hours=6), mains)])
    return det


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def feed(det, samples):
    """samples: (minutes since T0, value). Returns the number of flushes counted."""
    count = 0
    for m, v in samples:
        count += det.process(at(m), v).count(detector.EVENT_FLUSH)
    return count


def probe(signal, start, end, step=0.25, jitter=0.0, seed=0):
    """Simulate a 0.1 degC probe that only reports when its reading changes.

    ``signal`` maps minutes to the true temperature; ``jitter`` adds +/- one
    quantum of noise with that probability.
    """
    rng = random.Random(seed)
    samples, last = [], None
    m = start
    while m <= end:
        reading = round(signal(m), 1)
        if jitter and rng.random() < jitter:
            reading = round(reading + rng.choice((-0.1, 0.1)), 1)
        if reading != last:
            samples.append((m, reading))
            last = reading
        m += step
    return samples


# --- Counting -----------------------------------------------------------------


def test_fast_drop_is_one_flush():
    det = make()
    assert feed(det, [(0, 18.5), (1, 18.0), (2, 17.0), (3, 16.0), (4, 15.5)]) == 1
    assert det.in_flush


def test_fine_steps_without_rate_gate_count():
    """0.1 degC every 30 s is only 0.2 degC/min per step: v1 missed it."""
    det = make()
    samples = [(0, 18.5)] + [(0.5 * i, round(18.5 - 0.1 * i, 1)) for i in range(1, 16)]
    assert feed(det, samples) == 1


def test_slow_reporting_probe_counts():
    """One report every 4 min (0.125 degC/min per step): v1 missed it."""
    det = make()
    assert feed(det, [(0, 18.5), (4, 18.0), (8, 17.5), (12, 17.0), (16, 16.6)]) == 1


def test_upward_excursion_is_never_counted():
    det = make()
    assert feed(det, [(0, 15.0), (1, 16.0), (2, 17.5), (3, 18.5)]) == 0


def test_small_drop_is_not_a_flush():
    det = make()
    assert feed(det, [(0, 18.5), (1, 18.2), (2, 18.0), (20, 18.1)]) == 0


# --- Adaptive threshold and noise floor -----------------------------------------


def test_adaptive_threshold_uses_available_gap():
    # Gap = 18.5 - 17.3 = 1.2 degC, threshold = min(1.0, 0.5 x 1.2) = 0.6.
    det = make(mains=17.3)
    assert feed(det, [(0, 18.5), (1, 18.2), (2, 18.0)]) == 0
    assert det.diagnostics["amplitude_threshold"] == 0.6
    assert feed(det, [(3, 17.9)]) == 1


def test_small_gap_is_blind():
    # Gap = 18.5 - 17.8 = 0.7 degC < 0.8: count nothing, even a clear drop.
    det = make(mains=17.8)
    assert feed(det, [(0, 18.5), (1, 18.0), (2, 17.5), (3, 17.0)]) == 0
    assert det.diagnostics["blind"] is True


def test_no_reference_is_blind():
    det = make(mains=None)
    assert feed(det, [(0, 18.5), (1, 17.5), (2, 16.5)]) == 0


# --- Grouping, debounce, end ----------------------------------------------------


def test_event_ends_after_quiet_period_and_is_not_recounted():
    det = make()
    feed(det, [(0, 18.5), (1, 17.0), (2, 16.0)])
    assert det.in_flush
    assert det.expire(at(6)) == []
    assert det.expire(at(7)) == [detector.EVENT_END]
    assert not det.in_flush
    # The pre-flush 18.5 is still in the window but must not act as calm value.
    assert feed(det, [(8, 16.1), (9, 16.0), (10, 15.9)]) == 0


def test_debounce_blocks_second_flush():
    det = make()
    samples = [(0, 18.5), (1, 17.0), (2, 18.5), (3, 17.0), (4, 16.5)]
    assert feed(det, samples) == 1


def test_flush_during_recovery_counts():
    """Second flush while the bowl is still warming back after the first."""
    det = make()
    count = feed(det, [(0, 18.5), (1, 16.0), (2, 14.0), (3, 13.5)])
    det.expire(at(10))
    recovery = probe(lambda m: 13.5 + 2.5 * (1 - math.exp(-(m - 10) / 60)), 10, 40)
    count += feed(det, recovery)
    count += feed(det, [(41, 15.0), (42, 14.0), (43, 13.6)])
    assert count == 2


# --- Ambient drift regression (no flush at night) --------------------------------


def test_night_warming_drift_is_never_counted():
    """Bowl warming back from mains to ambient for 10 h after an evening flush.

    The start of the curve reaches 0.4 degC in 15 min (as seen on 21:38-21:53),
    above the 0.3 degC start threshold. Probe noise flips one quantum 10% of the
    time.
    """
    ambient = 19.5

    def bowl(m):
        return ambient - (ambient - 13.0) * math.exp(-m / 200)

    rise_15_min = bowl(15) - bowl(0)
    assert rise_15_min >= 0.4
    det = make(mains=13.0)
    det.process(at(-1), 13.0)
    assert feed(det, probe(bowl, 0, 600, jitter=0.1, seed=42)) == 0


def test_night_cooling_drift_is_never_counted():
    """Heating off at night: the bowl cools 1.5 degC over 6 h, with noise."""
    det = make(mains=12.0)
    signal = probe(lambda m: 19.0 - 1.5 * m / 360, 0, 360, jitter=0.1, seed=7)
    assert feed(det, signal) == 0


def test_noisy_stable_night_is_never_counted():
    det = make(mains=12.0)
    assert feed(det, probe(lambda m: 18.6, 0, 600, jitter=0.3, seed=3)) == 0


# --- Outliers and cold water ------------------------------------------------------


def test_isolated_spike_is_ignored():
    det = make()
    assert feed(det, [(0, 18.5), (1, 12.0), (2, 18.5)]) == 0
    assert det.cold_water == MAINS


def test_large_jump_with_continuity_counts():
    det = make()
    assert feed(det, [(0, 18.5), (1, 15.0), (2, 14.9)]) == 1


def test_cold_water_is_rolling_minimum():
    det = make(mains=None, cold_water_window=1)
    feed(det, [(0, 12.0), (30, 18.0), (90, 18.5)])
    assert det.cold_water == 18.0


def test_seeded_history_does_not_count():
    det = make(mains=None)
    det.seed_history([(at(-30), 18.5), (at(-20), 15.0), (at(-10), 14.0)])
    assert det.cold_water == 14.0
    assert feed(det, [(0, 14.1)]) == 0


def test_restart_during_or_after_flush_does_not_recount():
    """After a restart/reload, the live state may already be low: no new flush."""
    det = make(mains=None)
    det.seed_history([(at(-60), 12.0), (at(-5), 18.5), (at(-2), 17.0)])
    assert feed(det, [(0, 15.0), (1, 14.5)]) == 0


def test_value_held_longer_than_window_is_calm():
    """Sparse probe: same reading for 70 min (no state change in HA), then two
    0.5 degC steps 2 min apart, as observed on a real SNZB-02LD."""
    det = make(mains=14.7)
    assert feed(det, [(0, 15.5), (70, 15.0), (72, 14.5)]) == 1
    assert det.diagnostics["calm_value"] == 15.5


def test_old_calm_value_does_not_expire_the_event():
    """Calm value hours old: the event window runs from the first step, not from it."""
    det = make(mains=14.7)
    assert feed(det, [(0, 16.6), (220, 15.9), (222, 15.4)]) == 1
