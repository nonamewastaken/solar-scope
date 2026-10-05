# SolarScope MVP 1 Test Dataset (Post Installation)

Synthetic data for the Tech Studio MVP 1 pipeline. It models one commercial rooftop in Buffalo, NY that was commissioned on 2025-06-15 and has been monitored by 12 SolarScope hubs since 2025-09-01. None of it comes from a real customer, so it is safe to share, commit, and break.

Treat it the way you would treat real field data. It is messy on purpose.

## Files

| File | What it is | Size |
|---|---|---|
| `readings.csv` | Hub readings every 15 minutes, 2025-09-01 to 2026-08-31 local time | about 421,000 rows |
| `site.json` | Array layout, hub to panel mapping, module ratings, temperature coefficients, sensor valid ranges | 1 file |
| `weather.csv` | Daily weather in NOAA GHCN Daily format (standard units) | 365 rows |
| `service_log.csv` | Every truck roll over the 12 months: why, what was found, what was fixed | 18 rows |

## Report windows

* 365 day report: 2025-09-01 to 2026-08-31
* 180 day report: 2026-03-05 to 2026-08-31

## The site in one paragraph

36 panels in 3 roof rows of 12. Each row is one string (R1 = S1, R2 = S2, R3 = S3). Every panel feeds its own DC optimizer, so each panel runs at its own maximum power point and its voltage and current are independent of its neighbors. Each hub serves 3 adjacent panels in the same row, so hubs H01 to H04 sit on row 1, H05 to H08 on row 2, and H09 to H12 on row 3. Row 3 sits against the parapet. Full details are in `site.json`.

## readings.csv

One row per hub per 15 minute interval. Panel data is wide: slots `p1`, `p2`, `p3` map to panel IDs through `site.json` (`hubs[].panels`).

| Column | Unit | Meaning |
|---|---|---|
| `timestamp_utc` | ISO 8601, UTC | Reading time. Convert to America/New_York for anything daily. |
| `hub_id` | | H01 to H12 |
| `irradiance_wm2` | W/m² | Plane of array irradiance from the hub reference cell (hub level) |
| `humidity_pct` | % | Relative humidity at the hub (hub level) |
| `pN_voltage_v` | V | Panel DC voltage for slot N |
| `pN_current_a` | A | Panel DC current for slot N |
| `pN_temp_c` | °C | Back of panel temperature for slot N |

Readings continue at night (near zero voltage, current, and irradiance).

**What to expect.** Rows arrive in received order, not strictly sorted. Expect exact duplicate rows, rows that share a timestamp and hub but disagree, missing values, gaps where a hub went offline, sensor sentinel values (see `site.json > sensors > sentinel_values`), and readings outside the valid ranges in `site.json`. The brief applies: flag these, never delete them.

## site.json

Key sections:

* `hubs`: which 3 panels each hub serves and in which slot order
* `panels`: row, column, string, hub, slot, serial for all 36 panels
* `module`: STC ratings (Pmax 400 W, Vmp 37.1 V, Imp 10.78 A, Voc 44.6 V, Isc 11.42 A) and temperature coefficients (Pmax −0.35 %/°C, Voc −0.27 %/°C, Isc +0.048 %/°C)
* `sensors.valid_ranges` and `sensors.sentinel_values`: use these for the validate step. They belong in your config file, not in code.

## weather.csv

GHCN Daily layout for station USW00014733 (Buffalo Niagara International). Values are synthetic. Dates are local calendar days.

| Column | Unit | Meaning |
|---|---|---|
| `AWND` | mph | Average daily wind speed |
| `PRCP` | in | Precipitation (water equivalent) |
| `SNOW` | in | Snowfall |
| `SNWD` | in | Snow depth on the ground |
| `TAVG`, `TMAX`, `TMIN` | °F | Average, maximum, and minimum temperature |
| `ACSH` | % | Average cloud cover, sunrise to sunset |
| `WT01`, `WT03`, `WT18` | flag | Fog, thunder, snow (blank means not observed) |

## service_log.csv

| Column | Meaning |
|---|---|
| `ticket_id` | Service request ID |
| `visit_date`, `arrival_time_local` | When the tech arrived |
| `trigger` | `scheduled`, `customer_call`, or `monitoring_alert` |
| `hub_ids`, `panel_ids` | Semicolon separated, or `ALL` |
| `reported_issue` | Why the truck rolled |
| `finding` | What the tech saw |
| `action_taken` | What was done |
| `fault_found` | Y or N |
| `root_cause`, `category` | Tech's call on the cause |
| `tech_hours`, `parts_cost_usd`, `parts_used` | Labor and parts |
| `truck_roll_cost_usd` | Flat cost per visit |

The log is what the techs wrote down. It is useful evidence, and it is not always right.

## Tips

* Local time matters. Weather is by local day, and the site crosses both DST changes.
* A panel is best judged against its hub mates and its row, under the same conditions.
* Keep every threshold in the config file. SolarScope will rerun your pipeline on a fresh dataset with no code changes.
