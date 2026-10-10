# readings.csv data profile

Status: **draft for team review** (SOL-12). Owner: Member 2 (Data Quality).
Source: `SolarScope_MVP1_TestData_Studio/readings.csv`.
Reproduce every number here with:

```bash
uv run scripts/profile_readings.py --input <input_folder>
```

Times are local (America/New_York) unless they end in `Z`. The answer key was not used.

## Summary

The data has the expected noise: 1,424 exact duplicates, about 1,000 blanks per hub,
193 sentinel hits, 282 out-of-range values, 220 short gaps and 3 communication outages.
`clean.py` handles all of these with the rules already in `docs/contracts.md`.

It also has 4 problems that need a decision or a config change:

1. **H02 clock offset, 2026-04-01 to 2026-04-15.** H02 logged local time as UTC for 14
   days. This also produces all 16 "conflicts" and one fake 4-hour outage, and a naive
   drift check flags it as drift. The contract has no rule for it yet.
2. **H09 irradiance drift from 2026-01-23.** The drift is slow (+4% a month). It only
   crosses the ±10% tolerance on 2026-04-07, so a tolerance-only rule misses 2.5
   months of inflated irradiance. The start has to come from a change-point fit.
3. **H09 humidity stuck near 100% from 2026-01-29.** The value dips to about 96% in
   the afternoons, so a rule that needs one exact value for 16 intervals in a row splits
   it into 152 pieces.
4. **Sentinel 327.6 is also a real irradiance reading.** All 24 irradiance values
   equal to 327.6 match their row. Sentinels need to be scoped to the measures they
   belong to.

## Dataset at a glance

| Item | Value |
| --- | --- |
| Records | 420,904 |
| Hubs | 12 (H01–H12), 4 per row, all in `site.json`, no unknown IDs |
| First / last timestamp | `2025-09-01T04:00Z` / `2026-09-01T03:45Z` (local 2025-09-01 00:00 to 2026-08-31 23:45) |
| Expected intervals per hub | 35,040. 2025-11-02 has 100, 2026-03-08 has 92 (DST) |
| Order in the file | Not sorted (received order) |
| Timestamps off the 15-minute grid | 0 |

## 1. Duplicates

| Hub | H01 | H02 | H03 | H04 | H05 | H06 | H07 | H08 | H09 | H10 | H11 | H12 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Exact duplicates | 127 | 120 | 106 | 109 | 127 | 99 | 120 | 110 | 140 | 126 | 116 | 124 |
| Conflicting keys | 0 | **16** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

- **Exact duplicates (1,424):** every one is a single re-sent copy that arrives 1–40 rows
  after the original (median 12). Keep the first one and flag the copy.
- **Conflicts (16 keys, 32 records):** all on H02, at `2026-04-01T00:00Z` to `03:45Z`,
  with 2 records per key and 9 of 11 values different. These are not two versions of
  one reading. They are two real readings 4 hours apart that got the same timestamp
  because of the H02 clock offset (section 6).

## 2. Missing values per column

11,542 records (2.7%) have a blank: 11,392 have 1, 149 have 2 and 1 has 3. Blanks are
spread evenly over columns and hubs, about 65–105 per column per hub.

| Hub | H01 | H02 | H03 | H04 | H05 | H06 | H07 | H08 | H09 | H10 | H11 | H12 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Blank values | 945 | 992 | 961 | 963 | 925 | 975 | 952 | 947 | **1,214** | 972 | 916 | 931 |
| of which `irradiance_wm2` | 84 | 96 | 100 | 85 | 106 | 80 | 93 | 90 | **355** | 79 | 79 | 92 |

The one exception is **H09 irradiance**. It has 5–9 blanks a month until December, then
the number climbs every month to 76 in August, while the other hubs stay at 2–15. This
matches the H09 drift in section 7.

## 3. Sentinel values

Sentinels from `site.json > sensors > sentinel_values`, counted per measure:

| Value | Meaning (site.json) | irradiance | voltage | current | temp |
| --- | --- | --- | --- | --- | --- |
| `6553.5` | ADC overflow on 16 bit channel | 13 | 42 | 0 | 0 |
| `655.35` | ADC overflow on current channel | 0 | 0 | 43 | 0 |
| `-40.0` | Thermistor open circuit | 0 | 0 | 0 | 37 |
| `327.6` | Thermistor short | **24** | 0 | 0 | 34 |

There are 0–9 per hub and measure, with no hub standing out. Humidity has none.

**`327.6` in irradiance is a real reading.** It is a valid irradiance value
(0–1500 W/m²). The 24 hits sit at 0.98–1.00 of the row median at the same moment,
so they are normal readings that happen to equal the thermistor-short code. Every other
sentinel hit is also outside its measure's valid range, so for those the
sentinel-over-out-of-range rule only changes the reason label.

## 4. Out-of-range values

Ranges come from `site.json > sensors > valid_ranges`, inclusive, with sentinels left out.
Each measure has only a few fixed glitch values:

| Measure | Valid | Below | Above | Values seen |
| --- | --- | --- | --- | --- |
| `irradiance_wm2` | [0, 1500] | 17 | 30 | -12.0, 1850.0, 2100.0 |
| `humidity_pct` | [0, 100] | 12 | 33 | -3.0, 104.3, 112.0 |
| `voltage_v` | [0, 50] | 34 | 45 | -1.2, 99.9 |
| `current_a` | [0, 13] | 29 | 48 | -0.84, 31.2 |
| `temp_c` | [-35, 95] | 0 | 34 | 150.0 |

That is 282 in total, 18–32 per hub, with no hub standing out. Only 28 of the 92
below-range records are at night, and no measure with a floor of 0 has a negative value
closer to 0 than -0.84. So these are glitches, not a night-time sensor offset. The
lower bound of 0 can stay, with no tolerance.

## 5. Missing 15-minute intervals and outages

| Hub | Missing intervals | Gaps | Longest | Missing % |
| --- | --- | --- | --- | --- |
| H01 | 47 | 17 | 4 | 0.13 |
| H02 | 58 | 19 | 16 | 0.17 |
| H03 | 31 | 15 | 4 | 0.09 |
| H04 | **264** | 19 | **220** | 0.75 |
| H05 | 43 | 20 | 4 | 0.12 |
| H06 | **128** | 23 | **68** | 0.37 |
| H07 | 54 | 17 | 4 | 0.15 |
| H08 | 51 | 21 | 4 | 0.15 |
| H09 | 54 | 24 | 4 | 0.15 |
| H10 | 47 | 21 | 4 | 0.13 |
| H11 | **210** | 16 | **178** | 0.60 |
| H12 | 29 | 12 | 4 | 0.08 |

- **220 short gaps** of 1–4 intervals (60, 55, 56 and 49 of each length) are spread
  over every hub. No gap starts on 3 or more hubs at the same time.
- **Long gaps** (≥ 8 intervals, end exclusive):

| Hub | Start | End | Intervals | What it is |
| --- | --- | --- | --- | --- |
| H04 | 2025-11-20 08:00 | 2025-11-22 15:00 | 220 (55 h) | Comm outage. SR-1004: hub breaker tripped |
| H06 | 2026-01-17 02:00 | 2026-01-17 19:00 | 68 (17 h) | Comm outage during the Jan 16–18 storm. No ticket |
| H11 | 2026-05-03 13:00 | 2026-05-05 09:30 | 178 (44.5 h) | Comm outage. SR-1014: cellular carrier outage |
| H02 | 2026-04-14 20:00 | 2026-04-15 00:00 | 16 (4 h) | **Not an outage.** Clock-offset artifact (section 6) |

No gap is between 5 and 15 intervals long, so `comm_outage_min_intervals: 8` separates
short gaps from outages cleanly.

## 6. Clock offsets

The check compares each hub's irradiance-weighted midday with the rest of its row,
day by day. Every hub is within 15 minutes of its row on every day except one stretch:

**H02, 2026-04-01 00:00 to 2026-04-15 00:00 (14 days): timestamps are 240 minutes early.**
For example, on 2026-04-05 H02's daylight runs from 03:45 to 14:45, while H01's runs
from 07:45 to 18:45. H02 logged local time (EDT, UTC−4) as if it were UTC. This one
fault causes 3 symptoms:

- When the offset starts, 4 hours of shifted readings land on timestamps that already
  have readings. These are the 16 "conflicts" in section 1.
- When it ends, 4 hours of timestamps are never written. This is the 16-interval
  "outage" in section 5.
- For 11 days H02 irradiance is 0.43 of its row, which a drift check flags as drift.

The data itself looks fine. Only the label is wrong.

## 7. Stuck and drifting sensors

| Hub | Sensor | Kind | Start | End | Evidence |
| --- | --- | --- | --- | --- | --- |
| H09 | irradiance | drift (reads high) | 2026-01-23 (change point) | end of data | Ratio to the other R3 hubs goes from 1.005 to 1.276 at about +4% a month |
| H09 | humidity | stuck near 100% | 2026-01-29 | end of data | About 40 points above its row every month from February. SR-1011 |

**H09 irradiance drift.** The H09 reading divided by the median of H10–H12 (daylight,
peers ≥ 200 W/m²), by month:

| Sep | Oct | Nov | Dec | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.004 | 1.004 | 1.005 | 1.006 | 1.011 | 1.042 | 1.079 | 1.118 | 1.156 | 1.196 | 1.236 | 1.276 |

- A flat-then-linear fit puts the change point at **2026-01-23**, a few days after the
  Jan 16–18 storm (37 in of snow on the ground on 01-18).
- With the current rule (±10% for 3 days) H09 is only flagged from **2026-04-07**. From
  Jan 23 to Apr 6, H09 irradiance is 1–10% too high, so panels P25–P27 would look up to
  10% weak. That would be a false decline or fault on a healthy panel.
- No service ticket mentions it. The growing blanks (section 2) are the only other sign.
- The healthy hubs sit at a fixed 0.98–1.02 of their row all year, so ±10% is wide.

**H09 humidity stuck.** It is not a single frozen value:

- From 2026-01-29 it reads 100% all night, then dips to about 96% from 11:00 to 18:00
  (at 14:00–15:00 it is near 100% only 70% of the time).
- The rule "16 identical values in a row" splits this into 152 runs. The longest is 572.
- The other hubs never stay within 1 point of 100% for more than 6 intervals, so a
  16-interval rule with a tolerance of 1 would not hit them by mistake.
- Compared with the median of its row, H09 is +36 to +44 points every month from
  February, while every healthy hub stays within ±3. This is the clearest signal.
- SR-1011 (2026-03-19) found condensation in the H09 sensor housing and left it reading
  100%, so it is never fixed in this data.

**Peer medians must use trusted hubs only.** H10 and H12 move against their row after
January only because H09 is in their peer group. H10 goes from 0.987 to 0.981 for
irradiance, and H10 and H12 move about 1 point for humidity.

No panel measure (voltage, current, temperature) and no other hub sensor has a stuck run.

## Cases `clean.py` and `quality.py` must handle

| # | Case | Stage | Reason or field | Config key |
| --- | --- | --- | --- | --- |
| 1 | Unsorted records | clean | sort by `timestamp_utc, hub_id`, keep `raw_row` | |
| 2 | Exact duplicates (1,424) | clean | `is_duplicate`, keep the first | `clean.duplicate_keys` |
| 3 | Conflicting records (16 keys, H02) | clean | `is_conflict`, reason `conflict` | `clean.conflict_keep` |
| 4 | Blank values (~11,700) | clean | `missing` | |
| 5 | Sentinels (169, plus 24 false hits) | clean | `sentinel`, scoped per measure (proposal 1) | `validation.sentinel_values` |
| 6 | Out-of-range values (282) | clean | `out_of_range` | `validation.valid_ranges` |
| 7 | Missing intervals (1,016 across 224 gaps) | clean | `is_gap`, `gaps` table, UTC grid | `clean.gap_min_intervals` |
| 8 | DST days (100 and 92 intervals) | clean | grid built from local midnights | |
| 9 | Comm outages (H04, H06, H11) | quality | `comm_outages` | `quality.comm_outage_min_intervals` |
| 10 | H02 clock offset, 240 min, 14 days | clean or quality | no field yet (proposal 2) | none yet |
| 11 | H09 humidity stuck near 100% | quality | `sensor_stuck` | `quality.stuck` |
| 12 | H09 irradiance drift, start from change point | quality | `sensor_drift`, `irradiance_source = row_median` | `quality.drift` |
| 13 | Peer medians from trusted hubs only | quality | | `quality.peer_group` |

## Proposed changes

These need agreement, mostly with Khang, because they touch `contracts.md` or `config.py`.

1. **Scope sentinels to measures.** Add, for example, `validation.sentinel_measures`
   (`6553.5: [irradiance_wm2, voltage_v]`, `655.35: [current_a]`,
   `-40.0: [temp_c]`, `327.6: [temp_c]`). Without it, 24 good irradiance readings
   are thrown away, and a fresh dataset could lose more.
2. **Decide how to handle a clock offset.** The contract mentions "timestamp offsets" in
   Stage 3, but `clean.py` runs first and already turns the H02 offset into conflicts and
   a gap. Option A (recommended): detect the offset and shift the timestamps back in
   `clean.py` before the duplicate and gap logic, keeping the original timestamp and
   the shift in new columns so nothing is lost. Option B: exclude H02 for those 14 days
   with a new reason such as `clock_offset`. Either way the contract needs a new field
   or reason.
3. **Start drift at the change point.** Keep `ratio_tolerance` as the trigger, then move
   the start back to the change point found from the data. Add the method to
   `quality.drift` (for example `start: change_point`). A tighter tolerance such as 0.05
   is also safe, because healthy hubs stay within ±2%.
4. **Detect stuck values with a tolerance or against the row.** Add
   `quality.stuck.tolerance: 1.0`, or a peer rule such as
   `quality.stuck.humidity_peer_diff_pp: 20` held for `drift.min_days`. Exact-value runs
   alone break the H09 period into pieces.
5. **Keep as is:** `valid_ranges`, `comm_outage_min_intervals: 8`,
   `stuck.min_intervals: 16`, `gap_min_intervals: 1`.

## Next

- Hand-write the cleaned and quality fixtures in `tests/fixtures/cleaned/` and
  `tests/fixtures/quality/`, including `data_quality.csv`, so Member 3 can build against them.
- Add fixture edge cases for cases 10–12, which the current fixture does not cover.
