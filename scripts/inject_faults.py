"""Copy an input folder and plant known data faults in hubs that are healthy, for L3 tests.

    uv run scripts/inject_faults.py --input <input_folder> --output output/injected

Writes the 4 input files plus `injected_faults.json`, the list of what was planted and
what a good DQ stage should report. Row order is kept, so raw_row numbers match the
source file. This is our own synthetic truth; it never reads the answer key.
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "America/New_York"
SEED = 7


def local(s: str) -> pd.Timestamp:
    return pd.Timestamp(s).tz_localize(TZ).tz_convert("UTC")


def window(df: pd.DataFrame, hub: str, start: str, end: str | None) -> pd.Series:
    t = df["t"]
    hit = df["hub_id"].eq(hub) & t.ge(local(start))
    return hit & t.lt(local(end)) if end else hit


def plant(r: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, list, list]:
    faults, cases = [], []

    def fault(fid, kind, hub, sensor, start, end, note, **extra):
        faults.append({"id": fid, "kind": kind, "hub_id": hub, "sensor": sensor,
                       "start_local": start, "end_local": end, "note": note, **extra})  # fmt: skip

    # F1 clock: H07 labels 2 h late for 9 days (hole at the start, overlap at the end)
    hit = window(r, "H07", "2026-06-10", "2026-06-19")
    r.loc[hit, "t"] = r.loc[hit, "t"] + pd.Timedelta(hours=2)
    fault("F1", "clock_offset", "H07", None, "2026-06-10", "2026-06-19",
          "labels 120 min late", offset_min=120)  # fmt: skip

    # F2 slow drift: H05 irradiance +3 % a month from 2026-05-01
    hit = window(r, "H05", "2026-05-01", None)
    months = (r.loc[hit, "t"] - local("2026-05-01")).dt.total_seconds() / (30 * 86400)
    r.loc[hit, "irradiance_wm2"] = (r.loc[hit, "irradiance_wm2"] * (1 + 0.03 * months)).round(1)
    fault("F2", "drift", "H05", "irradiance_wm2", "2026-05-01", None, "+3 % a month")

    # F3 step drift that recovers: H03 irradiance x0.88
    hit = window(r, "H03", "2026-02-15", "2026-03-20")
    r.loc[hit, "irradiance_wm2"] = (r.loc[hit, "irradiance_wm2"] * 0.88).round(1)
    fault("F3", "drift", "H03", "irradiance_wm2", "2026-02-15", "2026-03-20", "x0.88 step")

    # F4 humidity frozen at exactly 100.0 for 3 weeks
    hit = window(r, "H01", "2026-06-01", "2026-06-22")
    r.loc[hit, "humidity_pct"] = 100.0
    fault("F4", "stuck", "H01", "humidity_pct", "2026-06-01", "2026-06-22", "exactly 100.0")

    # F5 humidity near 100 with afternoon dips and noise, like H09
    # values are drawn per timestamp, so duplicate records stay identical
    hit = window(r, "H06", "2026-02-01", None)
    t = pd.Series(r.loc[hit, "t"].unique())
    dip = t.dt.tz_convert(TZ).dt.hour.between(11, 17).to_numpy()
    vals = np.where(dip, rng.uniform(94.5, 98.0, len(t)), 100.0)
    noisy = rng.random(len(t)) < 0.08
    vals = np.where(noisy & ~dip, rng.uniform(99.0, 99.9, len(t)), vals)
    r.loc[hit, "humidity_pct"] = r.loc[hit, "t"].map(dict(zip(t, np.round(vals, 1), strict=True)))
    fault("F5", "stuck", "H06", "humidity_pct", "2026-02-01", None, "near 100 with dips")

    # F6 irradiance frozen at one value for 2 days
    hit = window(r, "H10", "2026-07-08", "2026-07-10")
    r.loc[hit, "irradiance_wm2"] = 512.3
    fault("F6", "stuck", "H10", "irradiance_wm2", "2026-07-08", "2026-07-10", "frozen 512.3")

    # S1 real sentinel in temp_c, S2 real irradiance equal to 655.35, S3 a bad 327.6
    # irradiance at night (impossible value whose meaning the config does not know)
    # single records (no duplicate) on hubs without a planted or known fault
    single = ~r.duplicated(["timestamp_utc", "hub_id"], keep=False)
    healthy = single & ~r["hub_id"].isin(["H01", "H03", "H05", "H06", "H07", "H09", "H10"])
    day = r["irradiance_wm2"].between(600, 700) & healthy
    for i in rng.choice(np.flatnonzero(day), 10, replace=False):
        slot = f"p{rng.integers(1, 4)}"
        r.loc[r.index[i], f"{slot}_temp_c"] = 327.6
        cases.append({"id": "S1", "raw_row": int(r.index[i]), "slot": slot,
                      "measure": "temp_c", "want": "sentinel"})  # fmt: skip
    used = {c["raw_row"] for c in cases}
    for i in rng.choice([i for i in np.flatnonzero(day) if i not in used], 10, replace=False):
        r.loc[r.index[i], "irradiance_wm2"] = 655.35
        cases.append({"id": "S2", "raw_row": int(r.index[i]), "slot": "p1",
                      "measure": "irradiance_wm2", "want": ""})  # fmt: skip
    night = r["irradiance_wm2"].eq(0) & healthy
    for i in rng.choice(np.flatnonzero(night), 10, replace=False):
        r.loc[r.index[i], "irradiance_wm2"] = 327.6
        cases.append({"id": "S3", "raw_row": int(r.index[i]), "slot": "p1",
                      "measure": "irradiance_wm2", "want": "sentinel"})  # fmt: skip
    return r, faults, cases


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for f in ["site.json", "weather.csv", "service_log.csv"]:
        shutil.copy(args.input / f, args.output / f)

    r = pd.read_csv(args.input / "readings.csv", dtype={"hub_id": "str"})
    cols = list(r.columns)
    r["t"] = pd.to_datetime(r["timestamp_utc"], utc=True)
    r, faults, cases = plant(r, np.random.default_rng(SEED))
    r["timestamp_utc"] = r["t"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    r[cols].to_csv(args.output / "readings.csv", index=False)

    truth = {
        "faults": faults,
        "value_cases": cases,
        # found while profiling the source data (docs/data_profile.md), not planted
        "known_real": [
            {"hub_id": "H09", "sensor": "irradiance_wm2", "kind": "drift"},
            {"hub_id": "H09", "sensor": "humidity_pct", "kind": "stuck"},
            {"hub_id": "H02", "sensor": None, "kind": "clock_offset"},
        ],
    }
    (args.output / "injected_faults.json").write_text(json.dumps(truth, indent=1))
    print(f"wrote {args.output} with {len(faults)} faults and {len(cases)} value cases")


if __name__ == "__main__":
    main()
