import datetime as dt
from pathlib import Path

import pandas as pd
import pytest
import yaml
from conftest import RAW

from solarscope import config, load

REAL = Path(__file__).parent.parent / "input" / "mvp1"


def stamps(*utc: str) -> pd.DataFrame:
    return pd.DataFrame({"timestamp_utc": pd.to_datetime(list(utc), utc=True)})


def test_windows_end_on_last_complete_local_day(cfg):
    # 2025-11-04T04:45Z = 23:45 EST on 11-03, the last interval of that day
    w = config.derive_windows(stamps("2025-11-01T04:00Z", "2025-11-04T04:45Z"), cfg)
    assert [(x.name, x.days, x.end) for x in w] == [
        ("365d", 365, dt.date(2025, 11, 3)),
        ("180d", 180, dt.date(2025, 11, 3)),
    ]
    assert w[0].start == dt.date(2024, 11, 4) and w[1].start == dt.date(2025, 5, 8)


def test_incomplete_last_day_is_dropped(cfg):
    w = config.derive_windows(stamps("2025-11-03T17:00Z"), cfg)  # noon local
    assert w[0].end == dt.date(2025, 11, 2)


def test_window_overrides(tmp_path):
    t = yaml.safe_load(config.DEFAULT_CONFIG.read_text())
    t["report_windows"] = {
        "end_date": "2025-11-02",
        "windows": [{"name": "custom", "start_date": "2025-11-01"}],
    }
    path = tmp_path / "t.yaml"
    path.write_text(yaml.safe_dump(t))
    cfg = config.load_config(path, RAW / "site.json")
    (w,) = config.derive_windows(stamps("2025-11-04T04:45Z"), cfg)
    assert (w.start, w.end, w.days) == (dt.date(2025, 11, 1), dt.date(2025, 11, 2), 2)


def test_site_json_wins_and_hash_tracks_config(cfg, tmp_path):
    v = cfg.thresholds["validation"]
    assert v["valid_ranges"]["current_a"] == [0, 13]
    assert "655.35" in v["sentinel_values"]

    t = yaml.safe_load(config.DEFAULT_CONFIG.read_text())
    t["validation"]["valid_ranges"]["current_a"] = [0, 99]  # site.json overrides this
    path = tmp_path / "t.yaml"
    path.write_text(yaml.safe_dump(t))
    other = config.load_config(path, RAW / "site.json")
    assert other.thresholds["validation"]["valid_ranges"]["current_a"] == [0, 13]
    assert other.hash == cfg.hash  # same effective config

    t["expected"]["min_irradiance_wm2"] = 51
    path.write_text(yaml.safe_dump(t))
    assert config.load_config(path, RAW / "site.json").hash != cfg.hash


@pytest.mark.skipif(not (REAL / "readings.csv").exists(), reason="real dataset not present")
def test_real_dataset_windows_match_brief():
    cfg = config.load_config(None, REAL / "site.json")
    w = {x.name: x for x in config.derive_windows(load.load_inputs(REAL, cfg).readings, cfg)}
    assert (w["365d"].start, w["365d"].end) == (dt.date(2025, 9, 1), dt.date(2026, 8, 31))
    assert (w["180d"].start, w["180d"].end) == (dt.date(2026, 3, 5), dt.date(2026, 8, 31))
