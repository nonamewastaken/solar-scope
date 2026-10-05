import shutil

import pandas as pd
from conftest import FIXTURES, RAW

from solarscope import load


def read_loaded_fixture(tz: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURES / "loaded" / "readings.csv", dtype={"hub_id": "str"})
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["timestamp_local"] = pd.to_datetime(df["timestamp_local"], utc=True).dt.tz_convert(tz)
    df["local_date"] = pd.to_datetime(df["local_date"])
    return df


def test_readings_match_loaded_fixture(cfg):
    got = load.load_inputs(RAW, cfg).readings
    pd.testing.assert_frame_equal(got, read_loaded_fixture(cfg.tz), check_dtype=False)
    assert list(got.columns) == load.READING_COLUMNS
    assert str(got["timestamp_utc"].dt.tz) == "UTC"
    assert str(got["timestamp_local"].dt.tz) == cfg.tz
    assert got["panel_id"].notna().all()


def test_fall_back_day_has_100_intervals(cfg):
    r = load.load_inputs(RAW, cfg).readings
    per_day = r[r.hub_id == "H01"].drop_duplicates("timestamp_utc").groupby("local_date").size()
    assert per_day.tolist() == [96, 100, 96]


def test_spring_forward_day_has_92_intervals(cfg, tmp_path):
    for f in ["site.json", "weather.csv", "service_log.csv"]:
        shutil.copy(RAW / f, tmp_path / f)
    stamps = pd.date_range("2026-03-08T05:00Z", "2026-03-09T03:45Z", freq="15min")
    pd.DataFrame({"timestamp_utc": stamps.strftime("%Y-%m-%dT%H:%M:%SZ"), "hub_id": "H01"}).reindex(
        columns=pd.read_csv(RAW / "readings.csv", nrows=0).columns
    ).to_csv(tmp_path / "readings.csv", index=False)
    r = load.load_inputs(tmp_path, cfg).readings
    assert r.drop_duplicates("timestamp_utc").groupby("local_date").size().tolist() == [92]


def test_weather_and_service_log(cfg):
    inputs = load.load_inputs(RAW, cfg)
    w = inputs.weather
    assert "STATION" not in w and w["date"].dtype.kind == "M"
    assert w["WT01"].tolist() == [False, True, False]
    s = inputs.service_log
    assert s["fault_found"].tolist() == [False, True]
    assert s.loc[0, "panel_list"] == [f"P0{i}" for i in range(1, 7)]  # ALL expanded
    assert s.loc[1, "panel_list"] == ["P05"] and s.loc[1, "hub_list"] == ["H02"]
    assert set(inputs.checksums) == set(load.INPUT_FILES)
    assert all(len(h) == 64 for h in inputs.checksums.values())
