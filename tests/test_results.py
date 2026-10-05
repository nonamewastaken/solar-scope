import json

import pandas as pd
import pytest

from solarscope import results


def empty(name: str) -> pd.DataFrame:
    return pd.DataFrame(columns=results.SCHEMAS[name])


def test_write_csv_rejects_wrong_columns(tmp_path):
    bad = empty("dispatch").drop(columns="priority")
    with pytest.raises(ValueError, match="dispatch.csv columns"):
        results.write_csv(bad, "dispatch", tmp_path)
    assert not list(tmp_path.iterdir())


def test_write_csv_formats_times_dates_and_lists(tmp_path):
    df = empty("events").astype(object)
    df.loc[0] = None
    df["event_id"] = ["E0001"]
    df["panel_ids"] = [["P01", "P02"]]
    df["start_local"] = pd.to_datetime(["2025-11-02T06:15Z"]).tz_convert("America/New_York")
    df["first_flag_date"] = pd.to_datetime(["2025-11-02"])
    path = results.write_csv(df, "events", tmp_path)
    row = pd.read_csv(path, dtype=str).iloc[0]
    assert row["panel_ids"] == "P01;P02"
    assert row["start_local"] == "2025-11-02T01:15:00-05:00"  # 2nd 01:15 on fall-back day
    assert row["first_flag_date"] == "2025-11-02"
    assert [p.name for p in tmp_path.iterdir()] == ["events.csv"]  # no temp files left


def test_write_all_needs_every_file(tmp_path):
    summary = {k: None for k in results.SUMMARY_KEYS}
    frames = {n: empty(n) for n in results.SCHEMAS}
    frames.pop("dispatch")
    with pytest.raises(ValueError, match="need exactly"):
        results.write_all(tmp_path, summary=summary, **frames)
    with pytest.raises(ValueError, match="missing keys"):
        results.write_summary({"run_id": "x"}, tmp_path)

    frames["dispatch"] = empty("dispatch")
    paths = results.write_all(tmp_path, summary=summary, **frames)
    assert sorted(p.name for p in paths) == sorted(
        [f"{n}.csv" for n in results.SCHEMAS] + ["summary.json"]
    )
    assert json.loads((tmp_path / "summary.json").read_text())["run_id"] is None
