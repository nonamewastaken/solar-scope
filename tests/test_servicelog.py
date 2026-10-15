import pandas as pd
from conftest import FIXTURES, RAW

from solarscope import config, load, servicelog

RESULTS = FIXTURES / "results"


def analyze(cfg, service_log=None):
    inputs = load.load_inputs(RAW, cfg)
    events = pd.read_csv(RESULTS / "events.csv")
    windows = config.derive_windows(inputs.readings, cfg)
    sl = inputs.service_log if service_log is None else service_log
    return servicelog.analyze(sl, events, windows, cfg)


def test_p05_is_a_repeat_repair(cfg):
    r = analyze(cfg).repeat_repairs
    assert r["panel_id"].tolist() == ["P05"]
    row = r.iloc[0]
    assert row["hub_id"] == "H02" and row["n_repairs"] == 2
    assert row["ticket_ids"] == ["SR-9003", "SR-9002"]  # sorted by date
    assert row["visit_dates"] == ["2025-10-20", "2025-11-03"]
    assert row["permanent_fix"] == cfg.thresholds["servicelog"]["permanent_fix"]["wiring"]


def test_visits_are_tagged(cfg):
    v = analyze(cfg).visits.set_index("ticket_id")
    assert "E0001" in v.loc["SR-9001", "matched_event_ids"]  # overcast event, all panels
    assert v.loc["SR-9001", "explained_by"] == "weather"
    assert bool(v.loc["SR-9001", "avoidable"])
    assert "E0002" in v.loc["SR-9002", "matched_event_ids"]
    assert not v.loc["SR-9002", "avoidable"]  # a fault was found


def test_scheduled_visit_is_never_avoidable(cfg):
    sl = load.load_inputs(RAW, cfg).service_log.copy()
    sl.loc[sl["ticket_id"] == "SR-9001", "trigger"] = "scheduled"
    v = analyze(cfg, sl).visits.set_index("ticket_id")
    assert v.loc["SR-9001", "explained_by"] == "weather"
    assert not v.loc["SR-9001", "avoidable"]
