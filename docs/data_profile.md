# readings.csv data profile

Status: **draft, not yet run on the full dataset** (SOL-12).
Owner: Member 2 (Data Quality).

This write-up lists every kind of messiness in the real `readings.csv`, counted per hub.
Each finding names the stage that handles it (`clean.py` or `quality.py`) and the
threshold it needs in `config/thresholds.yaml`. It also seeds the fixture edge cases.

## Dataset at a glance

| Item | Value |
| --- | --- |
| Records | TBD |
| Hubs (from `site.json`) | TBD |
| First / last timestamp (UTC) | TBD |
| Expected intervals per hub | TBD |

## 1. Duplicates

| Hub | Exact duplicate rows | Same `timestamp_utc` + `hub_id`, values disagree |
| --- | --- | --- |
| TBD | | |

## 2. Missing values per column

| Hub | `irradiance_wm2` | `humidity_pct` | `p*_voltage_v` | `p*_current_a` | `p*_temp_c` |
| --- | --- | --- | --- | --- | --- |
| TBD | | | | | |

## 3. Sentinel values

Sentinels from `site.json > sensors > sentinel_values`:

| Value | Meaning |
| --- | --- |
| `6553.5` | ADC overflow on 16 bit channel |
| `655.35` | ADC overflow on current channel |
| `-40.0` | Thermistor open circuit |
| `327.6` | Thermistor short |

| Hub | Column | Sentinel | Count |
| --- | --- | --- | --- |
| TBD | | | |

## 4. Out-of-range values

Ranges from `site.json > sensors > valid_ranges`, inclusive.

| Hub | Column | Count | Min seen | Max seen |
| --- | --- | --- | --- | --- |
| TBD | | | | |

## 5. Missing 15-minute intervals and outages

| Hub | Missing intervals | Gaps | Gaps ≥ 8 intervals (comm outage) | Longest gap (start, end UTC) |
| --- | --- | --- | --- | --- |
| TBD | | | | |

## 6. Clock offsets

TBD: any hub whose timestamps are shifted from the 15-minute grid or from its row
neighbors (for example, sunrise in its irradiance curve arriving early or late).

## 7. Stuck and drifting sensors

| Hub | Sensor | Kind (stuck / drift) | Start (UTC) | End (UTC) | Evidence |
| --- | --- | --- | --- | --- | --- |
| TBD | | | | | |

## Cases `clean.py` and `quality.py` must handle

TBD: one line per case, with the reason code from `docs/contracts.md` and the config key.

## Proposed threshold changes

TBD: any value in the `validation`, `clean` or `quality` sections of
`config/thresholds.yaml` that the data says should change, and why.
