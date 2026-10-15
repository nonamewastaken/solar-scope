"""The executable contract for the 5 result files (docs/contracts.md section 9)."""

import json
import re

import pandas as pd
import pytest
from conftest import FIXTURES

from solarscope import results

RESULTS = FIXTURES / "results"


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(RESULTS / f"{name}.csv")


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads((RESULTS / "summary.json").read_text())


@pytest.mark.parametrize("name", results.SCHEMAS)
def test_columns_match_schema(name):
    assert list(read(name).columns) == results.SCHEMAS[name]


def test_summary_keys(summary):
    assert set(results.SUMMARY_KEYS) <= set(summary)
    assert set(summary["windows"]) == set(read("data_quality")["window"])


def test_kwh_lost_matches_panel_daily(summary):
    daily = read("panel_daily")
    daily["date"] = pd.to_datetime(daily["date"])
    for w in summary["windows"].values():
        d = daily[daily["date"].between(w["start"], w["end"])]
        d = d[d["daily_label"] != "normal"]
        by_label = d.groupby("daily_label")["loss_kwh"].sum()
        for label, kwh in w["kwh_lost_by_label"].items():
            assert kwh == pytest.approx(by_label.get(label, 0.0))
        assert w["kwh_lost_total"] == pytest.approx(sum(w["kwh_lost_by_label"].values()))


def test_dispatch_points_at_active_faults():
    ev = read("events").set_index("event_id")
    for event_id in read("dispatch")["event_id"]:
        assert ev.loc[event_id, "label"] == "fault"
        assert ev.loc[event_id, "status"] == "active"


def test_id_formats():
    assert read("events")["event_id"].map(lambda v: bool(re.fullmatch(r"E\d{4}", v))).all()
    assert read("dispatch")["dispatch_id"].map(lambda v: bool(re.fullmatch(r"D\d{3}", v))).all()
