"""Synthetic input folders for stage tests that need more hubs or days than the fixture.

make_input() writes readings.csv + site.json (copied from the fixture, with a bigger
layout) + the fixture weather and service log. `edit` receives the wide readings
DataFrame with a `true_utc` column and may change it; readings are written in received
order (`true_utc`, then hub), so a clock fault looks like it does in a real file.
"""

import copy
import json
import math
import shutil
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from solarscope import config, load

RAW = Path(__file__).parent / "fixtures" / "raw"
SLOTS = ["p1", "p2", "p3"]


def site(rows: int, hubs_per_row: int) -> dict:
    s = copy.deepcopy(json.loads((RAW / "site.json").read_text()))
    hubs, panels, n = [], [], 0
    for r in range(1, rows + 1):
        for k in range(1, hubs_per_row + 1):
            hub = f"H{len(hubs) + 1:02d}"
            ids = [f"P{n + i + 1:02d}" for i in range(3)]
            n += 3
            hubs.append({"hub_id": hub, "row": f"R{r}", "string_id": f"S{r}",
                         "position_in_row": k, "panels": dict(zip(SLOTS, ids, strict=True)),
                         "panel_columns": ids})  # fmt: skip
            for slot, pid in zip(SLOTS, ids, strict=True):
                panels.append({"panel_id": pid, "row": f"R{r}", "column": len(panels) + 1,
                               "string_id": f"S{r}", "hub_id": hub, "hub_slot": slot,
                               "serial": f"SYN-{pid}"})  # fmt: skip
    s["hubs"], s["panels"] = hubs, panels
    s["module"]["count"] = len(panels)
    return s


def readings(site_: dict, start: str, days: int, seed: int = 0) -> pd.DataFrame:
    """Clear-sky days scaled by a per-day cloud factor shared by every hub, plus 1% noise."""
    rng = np.random.default_rng(seed)
    tz = site_["location"]["timezone"]
    t0 = pd.Timestamp(start).tz_localize(tz).tz_convert("UTC")
    t1 = (pd.Timestamp(start) + pd.Timedelta(days=days)).tz_localize(tz).tz_convert("UTC")
    stamps = pd.date_range(t0, t1, freq="15min", inclusive="left", unit="us")
    day = stamps.tz_convert(tz).normalize()
    cloud = pd.Series(rng.uniform(0.55, 1.0, days), index=day.unique())
    solar_h = stamps.hour + stamps.minute / 60 - 5
    clear = np.where(
        (solar_h > 7) & (solar_h < 17), 800 * np.sin(math.pi * (solar_h - 7) / 10), 0.0
    )
    g = clear * cloud.reindex(day).to_numpy()
    hum = 65 + 20 * np.cos(2 * math.pi * (solar_h - 4) / 24)
    parts = []
    for hub in site_["hubs"]:
        noise = 1 + rng.normal(0, 0.01, len(stamps))
        gi = np.round(g * noise, 1)
        rec = {"true_utc": stamps, "hub_id": hub["hub_id"], "irradiance_wm2": gi,
               "humidity_pct": np.round(hum + rng.normal(0, 0.5, len(stamps)), 1)}  # fmt: skip
        for i, slot in enumerate(SLOTS):
            temp = np.round(8 + gi / 40 + i * 0.1, 1)
            rec[f"{slot}_voltage_v"] = np.where(gi > 0, np.round(37.1 - 0.1 * (temp - 25), 2), 0)
            rec[f"{slot}_current_a"] = np.round(10.78 * gi / 1000, 3)
            rec[f"{slot}_temp_c"] = temp
        parts.append(pd.DataFrame(rec))
    return pd.concat(parts, ignore_index=True)


def write_input(folder: Path, site_: dict, wide: pd.DataFrame) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "site.json").write_text(json.dumps(site_, indent=1))
    for f in ["weather.csv", "service_log.csv"]:
        shutil.copy(RAW / f, folder / f)
    out = wide.sort_values(["true_utc", "hub_id"], kind="stable")
    if "timestamp_utc" not in out:
        out = out.assign(timestamp_utc=out["true_utc"])
    out = out.assign(timestamp_utc=out["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    cols = pd.read_csv(RAW / "readings.csv", nrows=0).columns
    out[list(cols)].to_csv(folder / "readings.csv", index=False)
    return folder


def make_input(
    folder: Path,
    start: str = "2026-03-01",
    days: int = 10,
    rows: int = 1,
    hubs_per_row: int = 4,
    edit: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
    seed: int = 0,
    overrides: list[str] | None = None,
):
    """Write a synthetic input folder and return (cfg, inputs). `overrides` are config
    overrides such as "dq.clock_offset=exclude"."""
    s = site(rows, hubs_per_row)
    wide = readings(s, start, days, seed)
    if edit is not None:
        wide = edit(wide)
    write_input(folder, s, wide)
    cfg = config.load_config(None, folder / "site.json", overrides)
    return cfg, load.load_inputs(folder, cfg)


def shift_clock(wide: pd.DataFrame, hub: str, start: str, end: str, offset_min: int, tz: str):
    """Label hub records whose true local time is in [start, end) `offset_min` off."""
    lo = pd.Timestamp(start).tz_localize(tz)
    hi = pd.Timestamp(end).tz_localize(tz)
    out = wide.copy()
    out["timestamp_utc"] = out["true_utc"]
    hit = out["hub_id"].eq(hub) & out["true_utc"].ge(lo) & out["true_utc"].lt(hi)
    out.loc[hit, "timestamp_utc"] = out.loc[hit, "true_utc"] + pd.Timedelta(minutes=offset_min)
    return out
