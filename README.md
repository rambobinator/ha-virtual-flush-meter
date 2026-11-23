# Virtual Flush Meter

[🇫🇷 Version française](README.fr.md)

<img src="https://raw.githubusercontent.com/rambobinator/ha-virtual-flush-meter/main/docs/logo.jpg" alt="Virtual Flush Meter logo" width="160">

[Home Assistant](https://www.home-assistant.io/) integration that **counts toilet flushes** and estimates the **flushed water (in litres)** from a single temperature probe immersed in the toilet bowl (e.g. Sonoff SNZB-02D). The litres entity can be added to the **Water** section of the Energy dashboard as an individual water device.

> 🚧 Work in progress: the configuration flow is available, flush detection is not implemented yet.

## Principle

After a flush, the bowl fills with fresh mains water whose temperature differs from the water that sat in the bowl. The probe sees a sharp change (up or down), which is detected as one flush:

- cumulative change ≥ 1.0 °C within 30 min,
- rate of change ≥ 0.3 °C/min,
- at least 5 min between two flushes.

```
Litres = flushes × volume per flush × calibration
```

As a bonus, the rolling minimum of the probe over several hours approximates the **cold mains water temperature**.

## Configuration

| Field | Default |
|---|---|
| Temperature probe in the toilet bowl | required |
| Minimum rate of change (°C/min) | 0.3 |
| Minimum temperature change (°C) | 1.0 |
| Detection window (min) | 30 |
| Minimum time between two flushes (min) | 5 |
| Volume per flush (L) | 6 |
| Calibration factor | 1 |
| Cold water rolling minimum window (h) | 12 |

Every field except the probe can be changed later via **Configure** on the integration card.

## Known limitations

- Missed flushes when the mains water and the bowl water are at nearly the same temperature (spring and autumn).
- The probe only reports changes of 0.1 °C or more, so the fastest part of the change is not recorded precisely.
- Telling 3 L and 6 L flushes apart is experimental.

## Installation

Via [HACS](https://hacs.xyz/) → Custom repositories → `https://github.com/rambobinator/ha-virtual-flush-meter` (category: Integration), then restart Home Assistant and add **Virtual Flush Meter** from Settings → Devices & services.

## License

MIT
