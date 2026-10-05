"""Stage 1: read the 4 inputs, convert time, reshape panel slots to long format.

Quick version (SOL-11). Schema validation and clear failure messages come in SOL-18.
See docs/contracts.md §2 for the output contract.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from solarscope.config import Config

INPUT_FILES = ["readings.csv", "site.json", "weather.csv", "service_log.csv"]
PANEL_MEASURES = ["voltage_v", "current_a", "temp_c"]
HUB_MEASURES = ["irradiance_wm2", "humidity_pct"]
READING_COLUMNS = [
    "raw_row", "timestamp_utc", "timestamp_local", "local_date",
    "hub_id", "row", "string_id", "panel_id", "slot", *HUB_MEASURES, *PANEL_MEASURES,
]  # fmt: skip


@dataclass(frozen=True)
class Inputs:
    readings: pd.DataFrame
    panels: pd.DataFrame
    weather: pd.DataFrame
    service_log: pd.DataFrame
    site: dict
    checksums: dict[str, str]


def load_inputs(input_dir: Path | str, cfg: Config) -> Inputs:
    input_dir = Path(input_dir)
    panels = pd.DataFrame(cfg.site["panels"])
    return Inputs(
        readings=load_readings(input_dir / "readings.csv", cfg, panels),
        panels=panels,
        weather=load_weather(input_dir / "weather.csv"),
        service_log=load_service_log(input_dir / "service_log.csv", cfg.site),
        site=cfg.site,
        checksums={f: _sha256(input_dir / f) for f in INPUT_FILES},
    )


def load_readings(path: Path, cfg: Config, panels: pd.DataFrame) -> pd.DataFrame:
    wide = pd.read_csv(path, dtype={"hub_id": "str"})
    wide.insert(0, "raw_row", range(len(wide)))
    wide["timestamp_utc"] = pd.to_datetime(wide["timestamp_utc"], utc=True)

    slots = sorted({s for hub in cfg.site["hubs"] for s in hub["panels"]})
    parts = []
    for slot in slots:
        cols = {f"{slot}_{m}": m for m in PANEL_MEASURES}
        part = wide[["raw_row", "timestamp_utc", "hub_id", *HUB_MEASURES, *cols]]
        parts.append(part.rename(columns=cols).assign(slot=slot))
    long = pd.concat(parts, ignore_index=True)

    slot_map = panels.rename(columns={"hub_slot": "slot"})[
        ["hub_id", "slot", "panel_id", "row", "string_id"]
    ]
    long = long.merge(slot_map, on=["hub_id", "slot"], how="left")
    long["timestamp_local"] = long["timestamp_utc"].dt.tz_convert(cfg.tz)
    long["local_date"] = long["timestamp_local"].dt.tz_localize(None).dt.normalize()
    long = long.sort_values(["timestamp_utc", "hub_id", "raw_row", "slot"])
    return long[READING_COLUMNS].reset_index(drop=True)


def load_weather(path: Path) -> pd.DataFrame:
    w = pd.read_csv(path).drop(columns=["STATION", "NAME"], errors="ignore")
    w = w.rename(columns={"DATE": "date"})
    w["date"] = pd.to_datetime(w["date"])
    flags = [c for c in w.columns if c.startswith("WT")]
    w[flags] = w[flags].notna() & w[flags].ne(0)
    num = [c for c in w.columns if c != "date" and c not in flags]
    w[num] = w[num].astype("float64")
    return w


def load_service_log(path: Path, site: dict) -> pd.DataFrame:
    s = pd.read_csv(path, dtype="str", keep_default_na=False)
    s["visit_date"] = pd.to_datetime(s["visit_date"])
    s["fault_found"] = s["fault_found"].str.upper().eq("Y")
    for c in ["tech_hours", "parts_cost_usd", "truck_roll_cost_usd"]:
        s[c] = pd.to_numeric(s[c].replace("", "nan")).astype("float64")
    all_panels = [p["panel_id"] for p in site["panels"]]
    all_hubs = [h["hub_id"] for h in site["hubs"]]
    s["panel_list"] = s["panel_ids"].map(lambda v: _split(v, all_panels))
    s["hub_list"] = s["hub_ids"].map(lambda v: _split(v, all_hubs))
    return s


def _split(value: str, everything: list[str]) -> list[str]:
    if value.strip().upper() == "ALL":
        return list(everything)
    return [v.strip() for v in value.split(";") if v.strip()]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
