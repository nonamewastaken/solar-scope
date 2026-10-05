"""Load thresholds + site.json, hash the effective config, derive report windows."""

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "thresholds.yaml"


@dataclass(frozen=True)
class Config:
    thresholds: dict  # effective thresholds (site.json values merged in)
    site: dict
    hash: str  # sha256 of the effective thresholds

    @property
    def tz(self) -> str:
        return self.site["location"]["timezone"]

    @property
    def interval_min(self) -> int:
        return int(self.site["sensors"]["reading_interval_min"])


@dataclass(frozen=True)
class Window:
    name: str
    days: int
    start: dt.date  # inclusive, local
    end: dt.date  # inclusive, local


def load_config(config_path: Path | str | None, site_path: Path | str) -> Config:
    thresholds = yaml.safe_load(Path(config_path or DEFAULT_CONFIG).read_text())
    site = json.loads(Path(site_path).read_text())
    # site.json wins over the config for valid ranges and sentinels
    validation = thresholds.setdefault("validation", {})
    sensors = site.get("sensors", {})
    validation["valid_ranges"] = {
        **validation.get("valid_ranges", {}),
        **sensors.get("valid_ranges", {}),
    }
    validation["sentinel_values"] = {
        **(validation.get("sentinel_values") or {}),
        **sensors.get("sentinel_values", {}),
    }
    canonical = json.dumps(thresholds, sort_keys=True, default=str).encode()
    return Config(thresholds, site, hashlib.sha256(canonical).hexdigest())


def derive_windows(readings: pd.DataFrame, cfg: Config) -> list[Window]:
    """end_date = last complete local day in the data; each window = N days ending on it."""
    rw = cfg.thresholds["report_windows"]
    if rw.get("end_date"):
        end = pd.Timestamp(rw["end_date"]).date()
    else:
        last = readings["timestamp_utc"].max().tz_convert(cfg.tz)
        # complete when the last interval reaches local midnight, else the day before
        end = (last + pd.Timedelta(minutes=cfg.interval_min)).date() - dt.timedelta(days=1)
    windows = []
    for w in rw["windows"]:
        if w.get("start_date"):
            start = pd.Timestamp(w["start_date"]).date()
            days = (end - start).days + 1
        else:
            days = int(w["days"])
            start = end - dt.timedelta(days=days - 1)
        windows.append(Window(w["name"], days, start, end))
    return windows
