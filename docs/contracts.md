# SolarScope MVP 1: Stage Contracts

Status: **draft v1 (2026-10-04), waiting for owner review** (SOL-8).
Each owner reviews their stage's input and output. Agree, or comment on the Linear
issue. After review, a change to this file needs a PR that every affected owner approves.

Build against the fixtures in `tests/fixtures/` (see its README), not against a
teammate's unfinished code.

## 0. Conventions (apply everywhere)

| Topic | Rule |
| --- | --- |
| DataFrames | pandas 3. Default `RangeIndex`, no MultiIndex. Stages never change their input frames. They return new frames or copies. |
| Strings | pandas `str` dtype. |
| UTC timestamps | `datetime64[us, UTC]`, column names end in `_utc`. Gap and interval logic uses UTC. |
| Local timestamps | `datetime64[us, <site tz>]`, names end in `_local`. The time zone comes from `site.json > location > timezone`. |
| Local dates | `datetime64[us]`, naive, at midnight. Named `local_date`, `date`, or `*_date`. Joins with `weather.date`. |
| Interval | `site.json > sensors > reading_interval_min` (15 on this dataset). A timestamp marks the **start** of its interval. |
| Energy | kWh per interval = `power_w * interval_min / 60 / 1000`. |
| Measures | `MEASURES = irradiance_wm2, humidity_pct, voltage_v, current_a, temp_c`. Units: W/m², %, V, A, °C. The first 2 are hub-level. The last 3 are panel-level. |
| Missing | `NaN`, never `0` and never a sentinel. |
| Multi-valued cell | In memory: `list[str]`. In result files: joined with `;` (`P01;P02`). |
| Result-file times | ISO 8601 with offset: `2025-11-02T01:15:00-05:00`. Dates are `YYYY-MM-DD`. Floats keep full precision. Reports do the rounding. |
| Windows | `config.Window(name, days, start, end)`. `start` and `end` are inclusive `datetime.date`. Default windows are `365d` and `180d`. Code must loop over `windows` and never hard-code those names. |
| Config | `cfg.thresholds[<section>][<key>]` from `config/thresholds.yaml`. If a value is not in the config, it does not exist. Add it there, never in code. |

### Reason vocabulary (per value)

| Reason | Set by | Meaning |
| --- | --- | --- |
| `""` | | Usable |
| `missing` | clean | Blank in the raw file |
| `sentinel` | clean | Equals a `cfg.thresholds.validation.sentinel_values` key. Takes precedence over `out_of_range`. |
| `out_of_range` | clean | Outside `cfg.thresholds.validation.valid_ranges[measure]`, inclusive bounds |
| `conflict` | clean | Duplicate records for the same `(timestamp_utc, hub_id)` disagree on this value |
| `gap` | clean | No record for this interval |
| `sensor_drift` / `sensor_stuck` | quality | Hub sensor excluded for this period. Hub-level measures only. |

## 1. Pipeline wiring (`run.py`)

```python
cfg = config.load_config(config_path, input_dir / "site.json")
inputs = load.load_inputs(input_dir, cfg)  # Stage 1
windows = config.derive_windows(inputs.readings, cfg)
cleaned = clean.clean(inputs, cfg)  # Stage 2
qual = quality.assess(cleaned, inputs, windows, cfg)  # Stage 3
exp = expected.compute(qual, inputs, cfg)  # Stage 4
panel_daily, warnings = decline.detect(exp.panel_daily, inputs, qual, cfg)  # 4b
events, panel_daily = classify.classify(exp, panel_daily, warnings, qual, inputs, cfg)  # 5
dispatch_df = dispatch.build(events, windows, cfg)  # 5
svc = servicelog.analyze(inputs.service_log, events, windows, cfg)  # 6
summary_dict = summary.build(
    run_info, windows, qual.data_quality, panel_daily, events, dispatch_df, svc, cfg
)
results.write_all(tmp_dir, data_quality=..., panel_daily=..., events=..., dispatch=..., summary=...)
report.render(tmp_dir)  # reads the 5 files only, writes the 2 PDFs
# swap tmp_dir into the output folder only if every step succeeded
```

Only `run.py` writes files, and it writes them through `results.py`. Stage modules
return DataFrames and do not touch the disk. The exception is `report.py`, which
writes PDFs.

## 2. Stage 1: load (`load.py`, `config.py`, owner Khang)

**Input:** the input folder (`readings.csv`, `site.json`, `weather.csv`,
`service_log.csv`) and `Config`.

**Output:** `load.Inputs` with the fields below.

### `inputs.readings`: long format, one row per raw record per panel slot

| Column | Dtype | Notes |
| --- | --- | --- |
| `raw_row` | int64 | 0-based data-row index in `readings.csv`. Ties every value back to the raw file. |
| `timestamp_utc` | datetime64[us, UTC] | |
| `timestamp_local` | datetime64[us, tz] | DST aware |
| `local_date` | datetime64[us] | Local calendar day |
| `hub_id` | str | |
| `row` | str | From `site.json > panels` |
| `string_id` | str | |
| `panel_id` | str | From `site.json > hubs[].panels[slot]` |
| `slot` | str | `p1`, `p2`, `p3` |
| `irradiance_wm2` | float64 | Hub-level, repeated on each of the hub's panel rows |
| `humidity_pct` | float64 | Hub-level, repeated |
| `voltage_v` | float64 | |
| `current_a` | float64 | |
| `temp_c` | float64 | |

- Values are raw and unmodified. Duplicates, sentinels, and out-of-range values
  are all still there. Rows are sorted by `timestamp_utc, hub_id, raw_row, slot`.
- Each raw record produces exactly one row per slot. Hub-level counts must
  therefore count unique `raw_row`, not panel rows.

### Other fields

| Field | Type | Contents |
| --- | --- | --- |
| `inputs.panels` | DataFrame | `site.json > panels`: `panel_id, row, column (int64), string_id, hub_id, hub_slot, serial` |
| `inputs.weather` | DataFrame | `date` (local day, datetime64[us]), then the GHCN columns with their original names and units: `AWND` mph, `PRCP`/`SNOW`/`SNWD` in, `TAVG`/`TMAX`/`TMIN` °F, `ACSH` %. All are float64. `WT01, WT03, WT18` are bool, and a blank means False. `STATION` and `NAME` are dropped. |
| `inputs.service_log` | DataFrame | Original columns. `visit_date` is datetime64[us]. `fault_found` is bool. `tech_hours`, `parts_cost_usd` and `truck_roll_cost_usd` are float64. Adds `panel_list` (`list[str]`, with `ALL` expanded to every panel) and `hub_list` (`list[str]`). |
| `inputs.site` | dict | Parsed `site.json` |
| `inputs.checksums` | dict[str, str] | `{"readings.csv": "<sha256 hex>", ...}` for the 4 input files |

`config.derive_windows(readings, cfg) -> list[Window]`: `end_date` is the last complete
local day in the data, and each window is the `days` days ending on it. On the
supplied dataset this gives `365d` = 2025-09-01..2026-08-31 and `180d` =
2026-03-05..2026-08-31.

## 3. Stage 2: clean (`clean.py`, owner Member 2)

**Input:** `inputs`, `cfg`. **Output:** `clean.Cleaned`:

### `cleaned.flags`: every raw row, flagged (never dropped)

`inputs.readings` columns, plus:

| Column | Dtype | Notes |
| --- | --- | --- |
| `is_duplicate` | bool | Exact copy of an earlier record (same `timestamp_utc, hub_id`, every value equal) |
| `is_conflict` | bool | Shares `timestamp_utc, hub_id` with another record that has different values |
| `is_kept` | bool | The one record per `(timestamp_utc, hub_id)` that feeds `canonical` |
| `<measure>_flag` | str | One per measure, using the reason vocabulary. Blank means OK. |

### `cleaned.canonical`: the calculation dataset

One row per `(timestamp_utc, panel_id)` for **every** expected interval. The grid
runs from the first local midnight to the end of the last local day in the data,
for every panel in `site.json`. Gaps appear as rows.

| Column | Dtype | Notes |
| --- | --- | --- |
| `timestamp_utc`, `timestamp_local`, `local_date` | as in Stage 1 | |
| `hub_id`, `row`, `string_id`, `panel_id` | str | |
| `irradiance_wm2` ... `temp_c` | float64 | Usable value, or NaN |
| `<measure>_reason` | str | One per measure. Blank means usable. Otherwise the reason it is NaN. |
| `is_gap` | bool | No record for this hub and interval |
| `raw_row` | Int64 (nullable) | The source record, `<NA>` for gaps |

Sorted by `timestamp_utc, panel_id`.

### `cleaned.gaps`

`hub_id, start_utc, end_utc, n_intervals`. One row per run of consecutive missing
intervals. `end_utc` is exclusive.

## 4. Stage 3: quality (`quality.py`, owner Member 2)

**Input:** `cleaned`, `inputs`, `windows`, `cfg`. **Output:** `quality.Quality`:

| Field | Contents |
| --- | --- |
| `canonical` | `cleaned.canonical`, plus `irradiance_used_wm2` (float64), `irradiance_source` (str: `hub`, `row_median` or `none`), and `sensor_excluded` (bool). For an excluded hub sensor, the `<measure>_reason` columns are set to `sensor_drift` or `sensor_stuck`. |
| `sensor_periods` | `hub_id, sensor, kind (drift/stuck), start_utc, end_utc, evidence`. `end_utc` is exclusive, and NaT means "until the end of the data". |
| `comm_outages` | `hub_id, start_utc, end_utc, n_intervals`, for gaps of at least `quality.comm_outage_min_intervals` |
| `data_quality` | The `data_quality.csv` frame (section 9.1) |

`irradiance_used_wm2` is the hub's own value when it is trusted. Otherwise it is
the median of the trusted hubs in the same row at that interval. If neither exists,
it is NaN with source `none`.

## 5. Stage 4: expected (`expected.py`, owner Member 3)

**Input:** `qual`, `inputs`, `cfg`. **Output:** `expected.Expected`:

### `exp.intervals`: one row per `(timestamp_utc, panel_id)`, from `qual.canonical`

The `qual.canonical` columns, plus:

| Column | Dtype | Notes |
| --- | --- | --- |
| `power_w` | float64 | `voltage_v * current_a` |
| `energy_kwh` | float64 | |
| `expected_power_w` | float64 | Physics: `P_stc * G/1000 * (1 + gamma*(T-25))`, with `G = irradiance_used_wm2` |
| `expected_kwh` | float64 | |
| `peer_ratio` | float64 | Panel power divided by the median of healthy peers, normalized by the reference period. NaN when not computable. |
| `is_daylight` | bool | `irradiance_used_wm2 >= expected.min_irradiance_wm2` |
| `is_usable` | bool | V, I, T usable, and `irradiance_source != none` |

### `exp.panel_daily`

The base columns of `panel_daily.csv` (section 9.2). The decline columns are NaN or
False, and `daily_label` is `""`.

## 6. Stage 4b: decline (`decline.py`, owner Member 3)

**Input:** `exp.panel_daily`, `inputs`, `qual`, `cfg`.
**Output:** `(panel_daily, warnings)`.

- `panel_daily` has `rolling_peer_ratio`, `decline_slope_pct_per_month` and
  `decline_flag` filled in.
- `warnings` has one row per flagged panel: `panel_id, hub_id, row, first_flag_date,
  decline_rate_pct_per_month, current_deficit_pct, projected_10pct_date, evidence`.

## 7. Stage 5: classify and dispatch (`classify.py`, `dispatch.py`, owner Member 4)

`classify.classify(exp, panel_daily, warnings, qual, inputs, cfg) -> (events, panel_daily)`

- `events` is the `events.csv` frame (section 9.3). Each `warnings` row becomes one
  `early_warning` event.
- `panel_daily` gets `daily_label`: the label of the event that cost that panel the
  most kWh that day, or `normal` if there was no event.

`dispatch.build(events, windows, cfg) -> dispatch` gives the `dispatch.csv` frame
(section 9.4). It only includes faults that are still active at the window end and
pass the `dispatch` rules in the config.

### Labels and causes

| `label` | Allowed `cause` values |
| --- | --- |
| `weather` | `snow`, `soiling`, `cloud`, `heat` |
| `fault` | `string_outage`, `wiring`, `hotspot` |
| `sensor_issue` | `sensor_drift`, `sensor_stuck` |
| `data_issue` | `comms_outage`, `data_gap`, `invalid_data` |
| `early_warning` | `slow_decline` |
| `unresolved` | `unknown` |

`daily_label` uses these labels, plus `normal`.

## 8. Stage 6: service log, summary, report (owner Member 5)

`servicelog.analyze(service_log, events, windows, cfg) -> servicelog.ServiceLog`:

| Field | Contents |
| --- | --- |
| `visits` | One row per ticket. Has the `service_log` columns, plus `matched_event_ids` (`list[str]`), `explained_by` (the label of the best match, or `""`), and `avoidable` (bool). A visit is avoidable when it found no fault and the pipeline explains it with a non-fault event. |
| `repeat_repairs` | `panel_id, hub_id, n_repairs, ticket_ids (list), visit_dates (list), root_cause, permanent_fix`. Only panels where `fault_found` is Y more than once. |

`summary.build(...) -> dict` gives the `summary.json` content (section 9.5).

`report.render(results_dir) -> list[Path]` reads only the 5 result files. It writes
`report_<window>.pdf`, with 6 pages per window.

## 9. The 5 official result files

`results.py` holds the column lists (`results.SCHEMAS`). `results.write_all` refuses
a frame whose columns do not match exactly and in order. This section mirrors those
lists. **If the two disagree, `results.py` is correct.**

### 9.1 `data_quality.csv` (owner `quality.py`)

One row per hub per window.

| Column | Type | Notes |
| --- | --- | --- |
| `window` | str | `365d`, `180d`, ... |
| `window_start`, `window_end` | date | |
| `hub_id`, `row` | str | |
| `expected_intervals` | int | 15-minute intervals in the window. DST aware: 35040 for 365 days. |
| `received_records` | int | Raw records, including duplicates |
| `usable_pct` | float | 100 × usable panel-intervals ÷ (expected_intervals × panels on the hub). See `exp.intervals.is_usable`. |
| `n_duplicate` | int | Records with `is_duplicate` |
| `n_conflict` | int | Records with `is_conflict` |
| `n_missing`, `n_sentinel`, `n_out_of_range` | int | Flagged values. Hub-level measures count once per record. |
| `n_gap_intervals` | int | |
| `n_sensor_excluded_intervals` | int | |
| `excluded_periods` | str | `;`-joined `sensor:kind:start/end`, using local ISO times |
| `reasons` | str | Short human-readable summary |

### 9.2 `panel_daily.csv` (owner `expected.py`, plus decline columns from `decline.py` and `daily_label` from `classify.py`)

One row per panel per local day, for every day in the data. Windows filter by `date`.

| Column | Type | Notes |
| --- | --- | --- |
| `date` | date | Local day |
| `panel_id`, `hub_id`, `row`, `string_id` | str | |
| `n_intervals_used` | int | Usable daylight intervals |
| `measured_kwh`, `expected_kwh` | float | |
| `loss_kwh` | float | `max(expected_kwh - measured_kwh, 0)` |
| `peer_ratio` | float | Daily median of the interval `peer_ratio` |
| `irradiance_source` | str | `hub`, `row_median`, `mixed` or `none` |
| `rolling_peer_ratio` | float | decline.py |
| `decline_slope_pct_per_month` | float | decline.py |
| `decline_flag` | bool | decline.py |
| `daily_label` | str | classify.py |

### 9.3 `events.csv` (owner `classify.py`)

| Column | Type | Notes |
| --- | --- | --- |
| `event_id` | str | `E0001`, ... |
| `label`, `cause` | str | See section 7 |
| `scope` | str | `panel`, `hub`, `row` or `array` |
| `hub_ids`, `panel_ids` | str | `;`-joined |
| `start_local`, `end_local` | datetime | `end_local` is the end of the last abnormal interval (exclusive) |
| `duration_h` | float | |
| `kwh_lost` | float | Whole event |
| `status` | str | `active` (still going at the end of the data) or `resolved` |
| `evidence` | str | Short numeric reason, e.g. `V -33% vs hub mates, I normal, T +8C` |
| `first_flag_date` | date | Only for `early_warning`, otherwise blank |
| `decline_rate_pct_per_month` | float | Only for `early_warning` |
| `current_deficit_pct` | float | Only for `early_warning` |
| `projected_10pct_date` | date | Only for `early_warning` |

### 9.4 `dispatch.csv` (owner `dispatch.py`)

One row per panel per window. Panels on the same truck roll share a `dispatch_id`,
so a string outage is 1 dispatch with 12 rows.

| Column | Type | Notes |
| --- | --- | --- |
| `window` | str | |
| `dispatch_id` | str | `D001`, ..., numbered separately in each window |
| `priority` | str | `high`, `medium` or `low` |
| `panel_id`, `hub_id`, `row` | str | |
| `event_id` | str | |
| `cause` | str | |
| `evidence` | str | |
| `kwh_lost` | float | Event kWh lost |
| `first_seen_local` | datetime | Event start |
| `recommended_action` | str | |

### 9.5 `summary.json` (owner `summary.py`)

```json
{
  "schema_version": 1,
  "run_id": "20261004T214500Z-1a2b3c",
  "generated_at_utc": "2026-10-04T21:45:00Z",
  "site_id": "SS-TEST-001",
  "config_hash": "<sha256 hex>",
  "config": { "...effective thresholds, for report page 6": "..." },
  "input_checksums": { "readings.csv": "<sha256 hex>", "...": "..." },
  "files": { "data_quality": "data_quality.csv", "panel_daily": "panel_daily.csv",
             "events": "events.csv", "dispatch": "dispatch.csv" },
  "windows": {
    "365d": {
      "start": "2025-09-01", "end": "2026-08-31", "days": 365,
      "actual_kwh": 0.0, "expected_kwh": 0.0,
      "kwh_lost_total": 0.0,
      "kwh_lost_by_label": { "fault": 0.0, "weather": 0.0, "sensor_issue": 0.0,
                             "data_issue": 0.0, "early_warning": 0.0, "unresolved": 0.0 },
      "events_by_label": { "fault": 0, "weather": 0 },
      "n_dispatches": 0, "n_dispatch_panels": 0, "n_early_warnings": 0,
      "top_findings": [ { "rank": 1, "text": "...", "kwh_lost": 0.0, "event_id": "E0001" } ],
      "repeat_repairs": [ { "panel_id": "P22", "hub_id": "H08", "n_repairs": 3,
                            "ticket_ids": ["SR-1006"], "visit_dates": ["2025-12-18"],
                            "root_cause": "...", "permanent_fix": "..." } ],
      "truck_rolls_avoided": { "count": 0, "cost_usd": 0.0, "ticket_ids": [] },
      "service_visits": { "total": 0, "fault_found": 0, "no_fault": 0 }
    },
    "180d": { "...": "same keys" }
  }
}
```

- The kWh numbers in a window block are sums of `panel_daily` over the window's
  dates, grouped by `daily_label` (excluding `normal`).
- `kwh_lost_total` is the sum of `kwh_lost_by_label`.
- Counts come from `events`, `dispatch` and `servicelog`, filtered to the window by
  date overlap.
