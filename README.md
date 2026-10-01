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
uv run main.py
```

That single command runs the whole pipeline and writes the reports to the output folder.

---

## Outputs

### Site reports (PDF)

Two reports are generated, one covering the last **180 days** and one covering the last **365 days**. Each has 6 pages:

| Page | Contents |
| --- | --- |
| **1. Summary** | Total kWh lost, split into fault and weather, plus the top 3 findings |
| **2. Fault or Weather** | Every output drop, its label (fault or weather), and the kWh it cost |
| **3. Dispatch List** | Each panel that needs a truck, the likely cause, and the evidence |
| **4. Repeat Repairs** | Panels that keep getting fixed, with the root cause, using the service log |
| **5. Early Warnings** | Panels in slow decline and how fast they are dropping |
| **6. Data Quality and Method** | Usable data percent for every hub, excluded hubs, and the rules used |

### Results files

Five results files are written alongside the PDFs. **Every number in the reports comes from these files**, so any figure in a PDF can be traced back to its source.

### Scorecard

The scorecard checks the analysis against SolarScope's answer key:

- Faults caught
- False alarms
- Truck rolls avoided
- Days of early warning

---

## How it works

The pipeline runs in 6 steps, one Python module per step. Each step feeds the next.

```
 Raw hub data ──► Clean & validate ──► Fault vs weather ──► Dispatch
                                              │
                                              ├──► Repeat repairs (service log)
                                              ├──► Early warnings
                                              └──► Reports + scorecard
```

| Step | Job |
| --- | --- |
| 1. Load and clean | Read raw hub data, measure usable data percent, exclude hubs that fail the quality rules |
| 2. Classify drops | Compare each panel against its hub and the weather to label every drop as fault or weather |
| 3. Dispatch list | Rank panels that need a truck, with likely cause and evidence |
| 4. Repeat repairs | Match panels against the service log to find fixes that did not hold |
| 5. Early warnings | Detect slow decline and estimate the rate of loss |
| 6. Report | Build the results files, the PDFs, and the scorecard |

A flowsheet diagram of the pipeline is in `docs/` and matches the code.

---

## Project layout

```
solar-scope/
├── main.py            # Entry point: runs the full pipeline
├── pyproject.toml     # Project config and dependencies
├── uv.lock            # Locked dependency versions
├── .python-version    # Python 3.14.7
├── docs/              # Method notes and process flowsheet
└── tests/             # One test group per pipeline step
```

---

## Testing

There is a passing test group for each of the 6 steps. Expected outputs are checked against a hand calculation and must agree within **2%**.

```bash
uv run pytest
```

---

## Data quality

SolarScope does not assume the data is good. Page 6 of every report shows the usable data percent for each hub. A hub that falls below the quality threshold is excluded from the analysis, and the report says so and why. Nothing is silently dropped.

---

## Status

Built as the shared reference project for the Tech Studio. Work lands here after each weekly session.

## License

Add a license of your choice here.
