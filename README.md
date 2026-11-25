# Virtual Flush Meter

[🇫🇷 Version française](README.fr.md)

<img src="https://raw.githubusercontent.com/rambobinator/ha-virtual-flush-meter/main/docs/logo.jpg" alt="Virtual Flush Meter logo" width="160">

[Home Assistant](https://www.home-assistant.io/) integration that **counts toilet flushes** and estimates the **flushed water (in litres)** from a single temperature probe immersed in the toilet bowl (e.g. Sonoff SNZB-02D). The litres entity can be added to the **Water** section of the Energy dashboard as an individual water device.

> 🚧 Early version (0.1): detection thresholds still need to be validated on real data.

## Entities

| Entity | Description |
|---|---|
| Litres | Flushed water (L), cumulative. Add it in Energy → Water → Individual water devices. |
| Flushes | Number of flushes, cumulative (works with `utility_meter`). |
| Cold water | Lowest bowl temperature over the last hours, approximating the mains water temperature (rebuilt from history after a restart). |
| Flush | ON while a flush is in progress, for automations. |
| Last flush volume | *With a water meter.* Volume of the last flush, measured or estimated (`measured` attribute). |
| Half flushes / Full flushes | *With a water meter.* Number of half and full flushes, cumulative. |

## Principle

After a flush, the bowl fills with fresh mains water, colder than the water that sat in the bowl, then slowly warms back to room temperature. A flush is detected as a drop **towards the mains water temperature**:

- an event starts as soon as the temperature moves 0.3 °C away from its calm value within 30 min, whatever the speed;
- it is counted if the drop reaches **min(1.0 °C, 35 % of the available gap)**, where the available gap is the calm temperature minus the lowest temperature of the last 12 hours (≈ mains water);
- if the available gap is below 0.8 °C, the probe cannot tell a flush from noise: nothing is counted;
- warming back towards room temperature is never counted, since it goes the other way;
- at least 5 min between two flushes.

```
Litres = flushes × volume per flush × calibration
```

The **Flush** binary sensor exposes the figures of the last event (calm value, available gap, threshold, amplitude) to help tune the settings.

## Configuration

| Field | Default |
|---|---|
| Temperature probe in the toilet bowl | required |
| Start threshold (°C away from the calm value) | 0.3 |
| Amplitude to count a flush, upper bound (°C) | 1.0 |
| Share of the available gap required | 0.35 |
| Noise floor: minimum available gap (°C) | 0.8 |
| Detection window (min) | 30 |
| Minimum time between two flushes (min) | 5 |
| Volume per flush (L) | 6 |
| Calibration factor | 1 |
| Cold water rolling minimum window (h) | 12 |
| House water meter (optional, measures each flush) | — |
| Smallest plausible flush on the meter (L) | 2 |
| Largest plausible flush on the meter (L) | 9 |
| Half flush below (L) | 4.5 |

Every field except the probe can be changed later via **Configure** on the integration card.

## Optional: measure each flush with a water meter

If you have a house water meter in Home Assistant (wM-Bus via wmbusmeters, pulse counter, smart meter…), add it in the configuration or later via **Configure**. The probe still decides *that* the toilet was flushed; the meter tells *how much* water it took:

- the flush is matched with the meter draw within 5 min of it, preferring the one that started just before the probe moved (the tank refill starts at the flush);
- the volume is read once the refill is over, so the litres are added a few minutes after the flush;
- a draw outside 2–9 L means the flush was mixed with another use (shower, hand washing): the volume then falls back to the typical full flush, learned from recent measured flushes;
- below 4.5 L, the flush is counted as a half flush.

The meter cannot detect flushes on its own: a tap running for a minute looks exactly like a flush.

## Known limitations

- Missed flushes when the mains water and the bowl water are at nearly the same temperature (spring and autumn): below the noise floor, nothing is counted.
- Blind when the mains water is warmer than the bowl: only drops are counted.
- The probe only reports changes of 0.1 °C or more, so the fastest part of the change is not recorded precisely.
- Without a water meter, every flush counts as the configured volume: half and full flushes cannot be told apart.

## Installation

Via [HACS](https://hacs.xyz/) → Custom repositories → `https://github.com/rambobinator/ha-virtual-flush-meter` (category: Integration), then restart Home Assistant and add **Virtual Flush Meter** from Settings → Devices & services.

## License

MIT
