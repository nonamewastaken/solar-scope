# SolarScope

**Is it the weather, or is it the equipment?**

SolarScope reads raw performance data from 8 solar hubs, works out whether each drop in energy output was caused by **weather** or by a **technical fault**, and exports a PDF report that tells the operations team what to do about it.

One command goes from raw data to a finished report.

---

## What it does

Solar panels lose output for two very different reasons:

| Cause | What it looks like | What to do |
| --- | --- | --- |
| **Weather** | Output falls across a whole hub at once, in line with cloud, rain or low sun | Nothing. Wait it out. |
| **Technical fault** | One panel underperforms its neighbours under the same conditions | Send a truck. |

Sending a truck for a weather dip wastes money. Ignoring a real fault wastes energy. SolarScope separates the two so crews are only dispatched when they are needed.

For every hub, it:

1. Measures total energy lost (kWh) and what that loss cost.
2. Splits the loss into **fault** and **weather**.
3. Lists which panels need a truck, the likely cause, and the evidence.
4. Flags panels that keep getting fixed and never stay fixed.
5. Catches panels in slow decline before they fail.
6. Reports how much of the data was actually usable.

---

## Quick start

You need [uv](https://docs.astral.sh/uv/) installed. The project is pinned to Python 3.14.7.

```bash
git clone https://github.com/nonamewastaken/solar-scope.git
cd solar-scope
uv sync
uv run pytest
uv run run.py --input input/mvp1 --output output
```

The input folder holds `readings.csv`, `site.json`, `weather.csv` and `service_log.csv`. Thresholds live in `config/thresholds.yaml` (`--config` to use another). When the pipeline is complete (Phase 2), that one command writes the result files and both PDFs to the output folder. Today it runs stages 1-3 and prints usable data per hub. Without uv: `pip install -r requirements.txt`.

---

## Outputs

### Site reports (PDF)

Two reports are generated, one covering the last **180 days** and one covering the last **365 days**. Each has 6 pages:

| Page | Contents |
| --- | --- |
| **1. Summary** | Total kWh lost, split into fault and weather, plus the top 3 findings |
| **2. Fault or Weather** | kWh lost by label and cause, and the top events (full list in `events.csv`) |
| **3. Dispatch List** | Each panel that needs a truck, the likely cause, and the evidence |
| **4. Repeat Repairs** | Panels that keep getting fixed, with the root cause, using the service log |
| **5. Early Warnings** | Panels in slow decline and how fast they are dropping |
| **6. Data Quality and Method** | Usable data percent for every hub, excluded hubs, and the rules used |

### Results files

`data_quality.csv`, `panel_daily.csv`, `events.csv`, `dispatch.csv` and `summary.json` are written alongside the PDFs. **Every number in the reports comes from these files.**

### Scorecard

`scripts/score.py` (Phase 2) checks the results against the answer key, once, after thresholds are frozen: faults caught, false alarms, truck rolls avoided, days of early warning.

---

## How it works

Six stages, one module each, chained by `run.py`. Stage inputs and outputs are fixed in [`docs/contracts.md`](docs/contracts.md).

| # | Stage | Module | Job |
| --- | --- | --- | --- |
| 1 | Load | `load.py`, `config.py` | Read the 4 input files, convert time zones, reshape to one row per panel |
| 2 | Clean | `clean.py` | Flag duplicates, conflicts, sentinels, out-of-range values, gaps and clock offsets |
| 3 | Quality | `quality.py` | Find drifting or stuck hub sensors, pick the irradiance to trust, score usable data per hub |
| 4 | Expected | `expected.py`, `decline.py` | Expected output (physics + peer panels), kWh lost, slow decline |
| 5 | Classify | `classify.py`, `dispatch.py` | Group losses into events, label fault / weather / sensor / data, build the dispatch list |
| 6 | Report | `servicelog.py`, `summary.py`, `report.py` | Repeat repairs and avoidable truck rolls, `summary.json`, the 2 PDFs |

Every tunable number is in `config/thresholds.yaml`. Data-quality choices are switchable per run (`--set dq.clock_offset=exclude`, see [`docs/dq_options.md`](docs/dq_options.md)).

---

## Project layout

```
solar-scope/
├── run.py                    # Entry point (stages 1-3 wired so far)
├── solarscope/
│   ├── config.py             # thresholds.yaml + site.json, config hash, report windows
│   ├── load.py               # Stage 1
│   ├── clean.py              # Stage 2
│   ├── quality.py            # Stage 3
│   ├── servicelog.py         # Stage 6: repeat repairs, visit tagging
│   ├── report.py             # Stage 6: 6-page PDF per window from the result files
│   └── results.py            # Result-file schemas, atomic writes
├── config/thresholds.yaml    # Every tunable number, one section per stage
├── scripts/                  # Analysis tools, not part of the pipeline
│   ├── profile_readings.py   #   data profile behind docs/data_profile.md
│   ├── catalog_signatures.py #   fault/weather plots behind docs/signatures.md
│   ├── inject_faults.py      #   plant synthetic faults in a copy of the data
│   ├── dq_eval.py            #   score data-quality rules on planted faults
│   └── dq_compare.py         #   compare the dq.* approaches
├── docs/
│   ├── contracts.md          # Stage inputs/outputs and the 5 result files (agreed v1)
│   ├── SYSTEM_OVERVIEW.txt   # Full design, module map, team plan
│   ├── expected_method.md    # Expected-output formula and hand calculation
│   ├── signatures.md         # Fault and weather signatures = classify rules
│   ├── data_profile.md       # What is messy in readings.csv
│   ├── dq_options.md         # Data-quality approaches and evidence
│   └── SolarScope_Tech_Studio_Brief_MVP1.pdf
├── tests/
│   ├── test_*.py             # One file per module
│   └── fixtures/             # 2-hub x 3-day dataset, hand calc, sample result folder (see its README)
├── input/                    # Datasets, e.g. input/mvp1 (not committed)
└── output/                   # Run results (not committed)
```

The answer key is never committed (the repo is public). It stays outside version control and is read only by the scorecard.

---

## Testing

```bash
uv run ruff format . && uv run ruff check . && uv run pytest
```

CI runs the same three commands on every push and pull request. Expected output is checked against a hand calculation (`tests/fixtures/handcalc/`) within **2%**.

---

## Status

| Phase | Scope | State |
| --- | --- | --- |
| 1 · Setup | Repo, CI, contracts, fixtures, config, load, clean, quality, method docs, servicelog, report layout | Done |
| 2 · Build | `expected.py`, `classify.py`, `dispatch.py`, `summary.py`, full `run.py`, load validation, scorecard | Next |
| 3 · Integrate & tune | Decline, threshold review, full-dataset run, flowsheet, single scoring run | Planned |

Data quality: dtri. Everything else: Khang.

## License

Add a license of your choice here.
