# Expected output: formula, assumptions, peer method

Status: draft for review (SOL-13). Owner: Khang (EXP). If this file and
`docs/contracts.md` disagree, `contracts.md` wins. Every number below lives in
`config/thresholds.yaml` or `site.json`, never in code.

## 1. Physics baseline

```
P_exp_w    = P_stc * (G / 1000) * (1 + gamma * (T - T_ref))
energy_kwh = power_w * interval_min / 60 / 1000          (interval = 15 min)
```

| Symbol | Source | Value |
| --- | --- | --- |
| `P_stc` | `site.json > module > stc_rating_w` | 400 W |
| `gamma` | `site.json > module > temp_coefficients > pmax_pct_per_c` / 100 | -0.0035 per C |
| `T_ref` | `expected.reference_temp_c` | 25 C |
| `G` | `irradiance_used_wm2` from quality (hub value, or the row-median fallback) | W/m2 |
| `T` | `temp_c`, the back-of-panel reading | C |

Measured power is `power_w = voltage_v * current_a`.

**Assumption: `T` is back-of-panel.** Cell temperature runs a few C higher, so
the physics expected value is slightly optimistic in sun (about 0.35 % per C).
This is a constant bias, and the peer ratio is normalized against each panel's
own reference period, so it does not shift the peer result.

### Worked example

```
G = 800 W/m2, T = 45 C
P_exp  = 400 * 0.8 * (1 - 0.0035 * 20) = 297.6 W   -> 0.0744 kWh per interval
V = 33.0 V, I = 8.6 A -> P = 283.8 W               -> 0.07095 kWh
deficit = 0.0744 - 0.07095 = 0.00345 kWh (4.6 %)
```

### Rules

- **Daylight.** An interval with `G < expected.min_irradiance_wm2` (50) is not
  daylight (`is_daylight = false`) and is skipped.
- **Same intervals.** Daily `measured_kwh` and `expected_kwh` are summed over
  the same intervals: usable (`quality.is_usable`) and daylight. Otherwise a
  data gap looks like a loss.
- **Loss.** `loss_kwh = max(expected_kwh - measured_kwh, 0)`.
- **Usable.** `expected.py` calls `quality.is_usable(canonical)`. It does not
  re-implement it.

## 2. Peer baseline

- **Raw interval ratio** = panel power / median power of its usable hub mates
  (the panel itself excluded). With fewer than `expected.peer.min_peers` usable
  hub mates, use the usable panels in the same row at that timestamp.
- **Healthy peer** means usable and daylight. It must not depend on
  classification, which comes later. Using it would be circular.
- **Normalize.** `peer_ratio = raw ratio / reference ratio`. The reference ratio
  is the median daily raw ratio over the panel's first
  `expected.peer.reference_period_days` (30) days with usable data. If the data
  is shorter (the fixtures are), use all days.
- **Limit.** A whole hub or row that is down together has a peer ratio near 1.
  Physics catches that case. The peer ratio says *who* is low, physics says
  *how much*.
- Known weakness (decision 2 in `PHASE1_INSTRUCTIONS.txt`): a panel that is
  already faulty in its first 30 days gets a wrong reference ratio.

## 3. Hand calculation

`tests/fixtures/handcalc/handcalc.csv` holds 16 real rows from
`input/mvp1/readings.csv`. In Phase 2 (SOL-22), `test_expected.py` asserts that
`expected.py` is within `expected.hand_calc_tolerance_pct` (2 %) of
`expected_power_w` and `expected_kwh` in this file.

| Choice | Value |
| --- | --- |
| Hubs | H01 (R1), H06 (R2), H11 (R3), with panels rotated across `p1..p3` |
| Clear days (ACSH < 30) | 2025-09-19 and 2025-09-30, local date |
| Cloudy day (ACSH > 80) | 2025-09-23 (ACSH 93). The other cloudy days in Sep-Oct have `G < 200` all day |
| Irradiance | 200 to 1000 W/m2 |
| Excluded | duplicates, blanks, sentinels and out-of-range values, so each row is clean |
| Row 3 | Sep 2025 only, before the January drift |

Columns: `timestamp_utc, hub_id, panel_id, irradiance_wm2, temp_c, voltage_v,
current_a, power_w, energy_kwh, expected_power_w, expected_kwh, deficit_kwh`.
`power_w` and `expected_power_w` are rounded to 4 decimals, the kWh columns to
6.

Method note: the rows were picked from the readings with a throwaway script
that is not part of the project, and the arithmetic uses only the formula in
section 1. No `solarscope` code was used.
