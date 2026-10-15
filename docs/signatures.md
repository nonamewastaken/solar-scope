# Signature catalog

Status: draft for review (SOL-14). Owner: Khang (CLS).
These are the rules `classify.py` starts from. Every number is a key in `config/thresholds.yaml`
under `classify:`. The answer key was not opened. The only sources are `input/mvp1` and
`scripts/catalog_signatures.py`.

Reproduce a plot (PNG in `output/signatures/`, not committed):

```bash
PYTHONPATH=. uv run python scripts/catalog_signatures.py --panels P22 --start 2026-07-14 --end 2026-07-20
```

Terms: **PR** is the performance ratio, `P / (400 * G/1000 * (1 + gamma*(T-25)))` with the hub
`G`. A normal day is 0.90 to 0.97. Values below are medians over intervals with `G >= 200 W/m2`
unless said otherwise. Times are local.

## Table

| Case | Dates | Scope | V | I | T | Hub G | Weather | Rule | Config keys |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **String outage** (fault) | 2025-11-04 late morning to 11-07 midday (SR-1003) | Row R2, string S2, P13-P24 | 43.4-44.2 V, near Voc (44.6) | 0.00 A, while R1 and R3 read 5.5 A | normal (21.4 vs 20.8 C) | normal (518 W/m2) | clear to partly cloudy, SNWD 0 | Every panel of one string: `I <= 0.2 A` and `V >= 0.9 * Voc` at `G >= 200` | `classify.string_outage.current_max_a` 0.2, `.voltage_min_frac_voc` 0.9, `.min_irradiance_wm2` 200 |
| **Wiring / connector** (fault) | P22: dropouts on 5 days in Dec, 4 in Feb, 14 in Apr, 22 in Jul, 28 in Aug (SR-1006, 1009, 1013) | One panel | normal between dropouts | drops to 0 for 1-4 intervals (median 2), 2-16 times a day, while hub mates make more than 1 A | normal | normal | any | `I < 0.1 A` for at most 4 intervals while hub mates `> 1 A`, at least 2 times a day | `classify.wiring.zero_current_max_a` 0.1, `.min_dropouts_per_day` 2, `.max_dropout_intervals` 4 (new), `.min_mate_current_a` 1.0 (new) |
| **Hotspot / bypass diode** (fault) | P29 from 2026-06-03, still active at the end of the data | One panel | 22.3 V against 34.3 V for hub mates (ratio 0.65, a step of 0.35) | normal (8.2 A against 8.0 A) | +4.3 to +5.3 C against hub mates | normal | any | Daily median `V / V_mates < 1 - 0.33 + 0.08` with `I` normal and `T` above mates | `classify.hotspot.voltage_step_frac` 0.33, `.voltage_step_tolerance` 0.08, `.temp_delta_c` 4.0 (was 5.0) |
| **Snow** (weather) | 2025-12-10..17, 12-20..31, 2026-01-14..30 (37 in at worst, SNWD 35), 02-04..03-15, 03-22..23 | All rows. R3 recovers last | 31.6-37.9 V, present | 0.04-2.5 A where 5 A is normal | pinned at 0.0-0.3 C on most covered days | often normal, so physics alone misses it | SNWD above 0 (8-35 in) | `SNWD > 0` is the gate. Then row median `PR < 0.7`, many panels at once, `V` present, `I` low. Recovery order R1, R2, then R3 (for example 2025-12-15 PR 0.84, 0.89, 0.64) | `classify.snow.snwd_min_in` 0.1, `.max_row_pr` 0.7 (new) |
| **Cloud** (weather) | 2025-10-08..09 (SR-1002, H05), 2026-06-12..16 (SR-1016) | Whole array | normal | low, in proportion to G | normal | low (140-250 W/m2) | ACSH 85-100, rain | `ACSH >= 70` and `PR >= 0.88`: measured matches expected at the lower irradiance | `classify.cloud.acsh_min_pct` 70, `.min_pr` 0.88 (new) |
| **Heat** (weather) | 2026-07-14..20 (SR-1017) | Whole array | 32.3-32.6 V against 34.5 V (-6 %), as the temperature coefficient predicts | normal | 50-54 C median in sun | normal | TMAX 93-96 F, ACSH below 25 | `T >= 50 C`, `V` at least 4 % below its cool-day level, temperature-corrected `PR >= 0.9` | `classify.heat.temp_min_c` 50, `.voltage_drop_frac` 0.04 (new), `.min_pr` 0.9 (new) |
| **Soiling** (weather) | Weeks before the 2026-05-14 cleaning (SR-1015), 2026-07-26 to 08-16 dry spell (SR-1018) | Whole array, R3 worst | normal | slow loss | normal | normal | dry (PRCP 0), ACSH under 70 | Slow row PR loss of 2-10 % over 7 or more days. Step up after rain of 0.25 in or more, or after a cleaning. 2026-08-16 weekly PR was 0.914 / 0.903 / 0.877 (R1, R2, R3) against 0.968 / 0.958 / 0.943 in June. It rose to 0.962 / 0.950 / 0.939 after SR-1018 | `classify.soiling.min_days` 7, `.reset_rain_in` 0.25, `.min_loss_frac` 0.02 (new), `.max_loss_frac` 0.10 (new) |
| **Sensor drift** (sensor_issue, DQ) | H09 irradiance from about 2026-01-23 | One hub | normal | normal | normal | H09 reads 1.026 (Feb) rising to 1.218 (Aug) of the rows 1-2 median. H10, H11 and H12 stay at 0.98-1.00 | any | DQ excludes the sensor (`quality.drift`). classify never calls it a fault on an excluded hub | `quality.drift.*` (owner DQ) |
| **Sensor stuck** (sensor_issue, DQ) | H09 humidity at about 100 % from 2026-01-29 (SR-1011, 2026-03-19) | One hub | normal | normal | normal | normal | any | DQ (`quality.stuck`) | `quality.stuck.*` (owner DQ) |
| **Comms outage** (data_issue, DQ) | H04 2025-11-20 12:45 to 11-22 20:00 (220 intervals), H11 2026-05-03 16:45 to 05-05 13:30 (178), H06 2026-01-17 to 01-18 (68) | One hub | no records | no records | no records | no records | storm days for H06 | No records for 8 or more intervals | `quality.comm_outage_min_intervals` 8 (owner DQ) |
| **Clock offset** (data_issue, DQ) | H02 2026-04-01 to 04-15 | One hub | shifted in time | shifted in time | shifted in time | shifted in time | any | DQ (`clean`) | owner DQ |
| **Unresolved** | P34: 27 low days across the year, for example 2026-04-20..22, 05-05, 05-07 | One panel | 0.90 of hub mates | 0.47 of hub mates | normal | normal | any | Peer ratio below `abnormal_peer_ratio` and no rule above matches (a voltage step of 0.10 is not a hotspot) | `classify.abnormal_peer_ratio` 0.85 |

## Candidates the service log does not name

Not confirmed. They come from scanning every panel against its hub mates.

| Panel | What the scan found | Matches |
| --- | --- | --- |
| P29 | Voltage ratio 0.65 from 2026-06-03 to the end, 84 days, T +4.8 C | Hotspot |
| P22 | Dropouts continue in Jul (22 days) and Aug (28 days), after the 2026-05-01 repair, so the fault is probably still active | Wiring |
| P07 | Power against the other hubs of R1 falls from a baseline of 1.028 (Sep-Nov) to 0.944 (Aug), about 1.2 % a month from February | Slow decline |
| P17 | Power against the other hubs of R2 falls from a baseline of 1.001 (Sep-Nov) to 0.961 (Mar) and 0.869 (Aug), about 2 % a month from March | Slow decline |
| P34 | Intermittent low days, all day, not morning only. V -10 %, I -53 % | Unresolved |

Hub mates of P29, P22, P07 and P17 read high against their own hub, because the faulty panel is in
the median. Use the faulty panel against its own row, not against the hub, when you check this.

## Where this differs from the plan

- **Row 3 drift is one hub, H09.** H10, H11 and H12 do not drift. The plan said H09-H12.
- **P34 is not morning only.** The affected days are low all day. The log says "morning".
- **The S2 outage starts late morning on 2025-11-04**, not at midnight.
- **The H04 outage ended on 2025-11-22**, two days before the SR-1004 visit.
- **P22 was repaired three times as a connector** (SR-1006, 1009, 1013). SR-1003 also lists P22, so
  `servicelog` counts repeats per panel and fault category.

## Open points

- The snow `max_row_pr` of 0.7 sits above the dead-snow days (PR 0.02-0.6) and below normal
  low-light cloudy days (0.83-0.90). Recovery days (0.70-0.85) are the grey zone. Tune in Phase 3
  from the service log, not from the answer key.
- Heat and cloud use the temperature-corrected PR, so both need `expected.py` v1 first.
