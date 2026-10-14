import datetime as dt

import numpy as np
import pandas as pd
import pytest
import synth
from conftest import RAW

from solarscope import clean, config, load, quality, results

TZ = "America/New_York"


def run(cfg, inputs, windows=None):
    windows = windows or config.derive_windows(inputs.readings, cfg)
    return quality.assess(clean.clean(inputs, cfg), inputs, windows, cfg)


def day(s: str) -> pd.Timestamp:
    return pd.Timestamp(s).tz_localize(TZ).tz_convert("UTC")


def scale(hub: str, start: str, end: str | None, factor):
    """Multiply a hub's irradiance by `factor(days since start)` from start to end."""

    def edit(w):
        t = w["true_utc"].dt.tz_convert(TZ)
        hit = w["hub_id"].eq(hub) & t.ge(pd.Timestamp(start).tz_localize(TZ))
        if end:
            hit &= t.lt(pd.Timestamp(end).tz_localize(TZ))
        days = (t[hit] - pd.Timestamp(start).tz_localize(TZ)).dt.total_seconds() / 86400
        w.loc[hit, "irradiance_wm2"] = (w.loc[hit, "irradiance_wm2"] * factor(days)).round(1)
        return w

    return edit


# fixture --------------------------------------------------------------------------------


@pytest.fixture
def fixture_quality(cfg):
    return run(cfg, load.load_inputs(RAW, cfg))


def test_data_quality_matches_the_contract(fixture_quality):
    dq = fixture_quality.data_quality
    assert list(dq.columns) == results.SCHEMAS["data_quality"]
    assert len(dq) == 2 * 2  # 2 hubs x 2 windows
    h = dq[dq.window == "365d"].set_index("hub_id")
    assert h.loc["H01", "expected_intervals"] == 35040
    assert h.loc["H01", "received_records"] == 293 and h.loc["H01", "n_duplicate"] == 1
    assert h.loc["H02", "n_conflict"] == 2 and h.loc["H02", "n_gap_intervals"] == 4
    assert h.loc["H01", "n_sentinel"] == 1 and h.loc["H02", "n_sentinel"] == 1
    assert h.loc["H02", "n_out_of_range"] == 1  # humidity 104.5 counts once per record
    assert h.loc["H01", "n_missing"] == 1 and h.loc["H02", "n_missing"] == 1
    assert "comm outage" not in h.loc["H02", "reasons"]  # 4 intervals < 8


def test_fixture_peer_rules_need_more_hubs(fixture_quality):
    # 2 hubs = 1 peer each, below min_peer_hubs, so no drift or humidity-vs-row finding.
    # The fixture humidity is a constant 70.0 / 72.0, so the identical-value rule does
    # fire (that is what a frozen sensor looks like); night irradiance zeros do not.
    p = fixture_quality.sensor_periods
    assert set(zip(p.sensor, p.kind, strict=True)) == {("humidity_pct", "stuck")}
    assert not fixture_quality.canonical.sensor_excluded.any()


def test_missing_irradiance_falls_back_to_the_row(fixture_quality):
    c = fixture_quality.canonical
    at = c[c.timestamp_utc == pd.Timestamp("2025-11-03T15:00Z")].set_index("panel_id")
    assert at.loc["P05", "irradiance_source"] == "row_median"
    assert at.loc["P05", "irradiance_used_wm2"] == at.loc["P01", "irradiance_wm2"]
    assert at.loc["P01", "irradiance_source"] == "hub"
    gap = c[c.is_gap]
    assert (gap.irradiance_source == "row_median").all()  # H01 still reports


# synthetic: healthy -----------------------------------------------------------------------


def test_healthy_hubs_are_not_excluded(tmp_path):
    cfg, inputs = synth.make_input(tmp_path, days=60, rows=2)
    q = run(cfg, inputs)
    assert q.sensor_periods.empty
    assert q.canonical.irradiance_source.eq("hub").all()
    assert q.data_quality.n_sensor_excluded_intervals.eq(0).all()


# synthetic: drift -------------------------------------------------------------------------


def test_slow_drift_is_found_once_it_passes_10_pct(tmp_path):
    edit = scale("H03", "2026-04-10", None, lambda d: 1 + 0.04 * d / 30)  # +4 % a month
    cfg, inputs = synth.make_input(tmp_path, days=120, edit=edit)
    q = run(cfg, inputs)
    p = q.sensor_periods
    assert len(p) == 1 and p.iloc[0].hub_id == "H03" and p.iloc[0].kind == "drift"
    # option 2B starts when the rule fires: +4 %/month passes 10 % after ~75 days
    assert day("2026-06-20") <= p.iloc[0].start_utc <= day("2026-07-05")
    assert pd.isna(p.iloc[0].end_utc)

    c = q.canonical
    late = c[(c.hub_id == "H03") & (c.timestamp_utc >= day("2026-07-05"))]
    assert late.sensor_excluded.all() and late.irradiance_wm2_reason.eq("sensor_drift").all()
    assert late.irradiance_source.eq("row_median").all()
    others = c[c.hub_id != "H03"]
    assert not others.sensor_excluded.any() and others.irradiance_source.eq("hub").all()


def test_step_drift_that_recovers_has_an_end(tmp_path):
    edit = scale("H02", "2026-04-20", "2026-05-10", lambda d: 0.85)
    cfg, inputs = synth.make_input(tmp_path, days=90, edit=edit)
    p = run(cfg, inputs).sensor_periods
    assert len(p) == 1 and p.iloc[0].hub_id == "H02"
    # the rolling median needs a few days to cross the line, both ways
    assert abs(p.iloc[0].start_utc - day("2026-04-20")) <= pd.Timedelta(days=4)
    assert abs(p.iloc[0].end_utc - day("2026-05-10")) <= pd.Timedelta(days=4)


def test_a_bad_peer_does_not_make_its_neighbours_look_bad(tmp_path):
    # 3 hubs in the row: H01 reads 40 % high, which drags the H02/H03 peer median up
    edit = scale("H01", "2026-04-15", None, lambda d: 1.4)
    cfg, inputs = synth.make_input(tmp_path, days=90, hubs_per_row=3, edit=edit)
    p = run(cfg, inputs).sensor_periods
    assert p.hub_id.tolist() == ["H01"]


# synthetic: stuck -------------------------------------------------------------------------


def test_humidity_stuck_near_100_is_one_period(tmp_path):
    def edit(w):
        t = w["true_utc"].dt.tz_convert(TZ)
        hit = w["hub_id"].eq("H04") & t.ge(pd.Timestamp("2026-04-01").tz_localize(TZ))
        dip = t.dt.hour.between(12, 17)  # afternoon dips break exact-value runs
        w.loc[hit, "humidity_pct"] = np.where(dip[hit], 96.0, 100.0)
        return w

    cfg, inputs = synth.make_input(tmp_path, days=60, edit=edit)
    p = run(cfg, inputs).sensor_periods
    assert len(p) == 1
    r = p.iloc[0]
    assert (r.hub_id, r.sensor, r.kind) == ("H04", "humidity_pct", "stuck")
    assert abs(r.start_utc - day("2026-04-01")) <= pd.Timedelta(days=1)
    assert pd.isna(r.end_utc)


def test_frozen_irradiance_is_stuck_but_night_zeros_are_not(tmp_path):
    def edit(w):
        t = w["true_utc"]
        lo = pd.Timestamp("2026-03-20T14:00Z")
        hit = w["hub_id"].eq("H01") & t.ge(lo) & t.lt(lo + pd.Timedelta(hours=5))
        w.loc[hit, "irradiance_wm2"] = 512.3
        return w

    cfg, inputs = synth.make_input(tmp_path, days=40, edit=edit)
    p = run(cfg, inputs).sensor_periods
    assert len(p) == 1
    r = p.iloc[0]
    assert (r.hub_id, r.sensor, r.kind) == ("H01", "irradiance_wm2", "stuck")
    assert r.end_utc - r.start_utc == pd.Timedelta(hours=5)


# per window -------------------------------------------------------------------------------


def test_window_numbers_differ_by_window(tmp_path):
    edit = scale("H03", "2026-04-10", None, lambda d: 1.3)
    cfg, inputs = synth.make_input(tmp_path, days=60, edit=edit)
    windows = [
        config.Window("all", 60, dt.date(2026, 3, 1), dt.date(2026, 4, 29)),
        config.Window("early", 20, dt.date(2026, 3, 1), dt.date(2026, 3, 20)),
    ]
    dq = run(cfg, inputs, windows).data_quality.set_index(["window", "hub_id"])
    assert dq.loc[("all", "H01"), "expected_intervals"] == 60 * 96 - 4  # DST spring-forward
    assert dq.loc[("early", "H01"), "expected_intervals"] == 20 * 96 - 4
    assert dq.loc[("all", "H03"), "n_sensor_excluded_intervals"] > 0
    assert dq.loc[("early", "H03"), "n_sensor_excluded_intervals"] == 0
    assert dq.loc[("early", "H03"), "excluded_periods"] == ""
    assert "irradiance_wm2:drift:" in dq.loc[("all", "H03"), "excluded_periods"]
    assert dq.loc[("all", "H03"), "usable_pct"] == pytest.approx(100.0)  # fallback keeps it usable
