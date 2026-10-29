# Fixture dataset

A small dataset built by hand: 2 hubs × 3 local days (2025-11-01 to 2025-11-03). It
includes the DST fall-back day, and it follows the real input schemas.
`make_fixtures.py` regenerates it. Do not edit the files by hand.

| Folder | Contents | Owner |
| --- | --- | --- |
| `raw/` | `readings.csv`, `site.json`, `weather.csv`, `service_log.csv` | Khang |
| `loaded/readings.csv` | Stage 1 output (`docs/contracts.md` §2), built independently of `load.py` | Khang |
| `handcalc/handcalc.csv` | 16 real rows worked by hand (SOL-13) | Khang |
| `results/` | One output folder: `data_quality.csv`, `panel_daily.csv`, `events.csv`, `dispatch.csv`, `summary.json`. Made by `make_result_fixtures.py`. `report.render` and `summary.py` are built against it, and `tests/test_result_fixtures.py` keeps it consistent. | Khang |

The result fixtures follow the contract and agree with each other. `data_quality.csv` is the
real `quality.py` output on the fixture readings (SOL-12); the other files are not derived
from them. They use 2 windows, 365d (2024-11-04 to 2025-11-03) and 180d
(2025-05-08 to 2025-11-03), which both hold all 3 days, so the two summary blocks match.
Story: E0001 cloud (11-02), E0002 P05 wiring (repaired, not dispatched), E0003 P02 hotspot
(active, dispatched), E0004 H02 data gap, E0005 P03 slow decline, E0006 P06 unresolved.
In `data_quality.csv`, `n_conflict` is 2 for H02 (both records of the key carry `is_conflict`),
`usable_pct` is tiny because the windows hold 3 days of data, and both hubs show a humidity
`stuck` period because the fixture humidity is a constant 70.0 / 72.0.

## Site

- Hubs: H01 (P01–P03) and H02 (P04–P06), both in row R1, string S1.
- The module, sensor ranges, and sentinels are copied from the real `site.json`.
- Sky: clear on 11-01 and 11-03, overcast on 11-02 (weather only).
- The readings have the same smooth clear-sky curve on all 3 days.

## Intervals

Local days have 96 + **100** + 96 intervals, because 01:00–01:45 local happens twice on
2025-11-02. A complete run is 292 intervals per hub.

The raw file has **582** records:

- 292 × 2 hubs
- plus 2 duplicate records
- minus 4 gap intervals

The loaded file has 582 × 3 = **1746** rows.

## Deliberate edge cases (UTC)

| Case | Where | Expected flag |
| --- | --- | --- |
| Exact duplicate | H01 `2025-11-01T16:00:00Z`, the whole record repeated at the end of the file | `is_duplicate` |
| Conflicting duplicate | H02 `2025-11-01T17:00:00Z`, second record has `p2_current_a = 2.0` (P05) | `is_conflict`, P05 `current_a` reason `conflict` |
| Sentinel | H01 `2025-11-03T17:00:00Z` `p1_temp_c = -40.0` (P01) | `sentinel` (not `out_of_range`) |
| Sentinel | H02 `2025-11-03T18:00:00Z` `p3_current_a = 655.35` (P06) | `sentinel` |
| Out of range | H02 `2025-11-01T18:00:00Z` `humidity_pct = 104.5` | `out_of_range` |
| Out of range | H01 `2025-11-03T18:00:00Z` `p2_voltage_v = 52.3` (P02) | `out_of_range` |
| Missing | H01 `2025-11-01T19:00:00Z` `p3_voltage_v` blank (P03) | `missing` |
| Missing | H02 `2025-11-03T15:00:00Z` `irradiance_wm2` blank | `missing` |
| Gap | H02 `2025-11-03T19:00Z`–`20:00Z` (4 intervals) | `is_gap`, 1 row in `gaps` |
| DST | 2025-11-02 has 100 local intervals | |
| Received order | Hub order alternates on each interval, and duplicates are at the end | Sort after load |

## Service log

- SR-9001 (`ALL`, no fault, weather) is a candidate for "truck roll avoided".
- SR-9002 (P05, wiring, fault found) is a real repair.
- SR-9003 (P05, wiring, 2025-10-20, fault found) is an earlier repair, so P05 is a repeat.
