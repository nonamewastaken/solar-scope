"""One test per data-quality approach (dq.* in config/thresholds.yaml, docs/dq_options.md).

The default approach of each decision is tested in test_clean.py and test_quality.py. Each
alternative here has the behaviour that sets it apart.
"""

import numpy as np
import pandas as pd
import pytest
import synth
from conftest import RAW
from test_quality import day, run, scale

from solarscope import clean, config, load

TZ = "America/New_York"


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


def readings_cfg(*overrides):
    cfg = config.load_config(None, RAW / "site.json", list(overrides))
    return cfg, load.load_inputs(RAW, cfg).readings


# config ---------------------------------------------------------------------------------


def test_an_unknown_approach_is_refused():
    with pytest.raises(ValueError, match=r"dq\.drift is 'nope'; choose one of"):
        config.load_config(None, RAW / "site.json", ["dq.drift=nope"])


def test_the_choice_is_part_of_the_config_hash():
    a = config.load_config(None, RAW / "site.json")
    b = config.load_config(None, RAW / "site.json", ["dq.clock_offset=exclude"])
    assert (
        a.thresholds["dq"]["clock_offset"] == "shift"
        and b.thresholds["dq"]["clock_offset"] == "exclude"
    )
    assert a.hash != b.hash


def test_every_approach_runs_together_on_the_fixture():
    every = [f"dq.{k}={v[1]}" for k, v in config.DQ_OPTIONS.items()]
    cfg = config.load_config(None, RAW / "site.json", every)
    inputs = load.load_inputs(RAW, cfg)
    q = run(cfg, inputs)
    assert list(q.data_quality["hub_id"].unique()) == ["H01", "H02"]


# 1B clock_offset = exclude --------------------------------------------------------------


@pytest.mark.parametrize("offset", [-240, -180, 120])
def test_clock_offset_records_can_be_excluded_instead_of_moved(tmp_path, offset):
    def edit(w):
        return synth.shift_clock(w, "H02", "2026-03-04", "2026-03-07", offset, TZ)

    cfg, inputs = synth.make_input(
        tmp_path, days=10, edit=edit, overrides=["dq.clock_offset=exclude"]
    )
    out = clean.clean(inputs, cfg)
    assert len(out.clock_offsets) == 1 and out.clock_offsets.iloc[0].offset_min == offset

    f = out.flags
    assert not f.is_conflict.any() and not f.is_duplicate.any()
    assert f.timestamp_raw_utc.equals(f.timestamp_utc)  # nothing is moved
    bad = f[f.clock_offset_min != 0]
    assert len(bad) == 3 * 96 * 3
    for m in clean.MEASURES:
        assert bad[f"{m}_flag"].eq("clock_offset").all()

    # the hole the jump left stays a gap, and every kept H02 value in the period is NaN
    assert out.gaps.n_intervals.sum() == abs(offset) // 15
    c = out.canonical
    h02 = c[(c.hub_id == "H02") & c.raw_row.isin(bad.raw_row)]
    assert h02.irradiance_wm2.isna().all() and h02.irradiance_wm2_reason.eq("clock_offset").all()


# 2B drift = contract --------------------------------------------------------------------


def test_contract_drift_is_found_only_once_it_passes_10_pct(tmp_path):
    edit = scale("H03", "2026-04-10", None, lambda d: 1 + 0.04 * d / 30)  # +4 % a month
    cfg, inputs = synth.make_input(tmp_path, days=120, edit=edit, overrides=["dq.drift=contract"])
    p = run(cfg, inputs).sensor_periods
    assert len(p) == 1 and p.iloc[0].hub_id == "H03" and p.iloc[0].kind == "drift"
    # +4 %/month passes 10 % after about 75 days; the default dates it from 2026-04-10
    assert day("2026-06-20") <= p.iloc[0].start_utc <= day("2026-07-05")
    assert pd.isna(p.iloc[0].end_utc)


# 2C fallback = rescale ------------------------------------------------------------------


def test_a_drifting_sensor_can_be_rescaled_instead_of_replaced(tmp_path):
    edit = scale("H03", "2026-04-10", None, lambda d: 1 + 0.04 * d / 30)
    cfg, inputs = synth.make_input(tmp_path, days=120, edit=edit, overrides=["dq.fallback=rescale"])
    c = run(cfg, inputs).canonical
    late = c[(c.hub_id == "H03") & (c.timestamp_utc >= day("2026-06-01"))]
    assert late.sensor_excluded.all() and late.irradiance_wm2_reason.eq("sensor_drift").all()
    assert late.irradiance_source.eq("hub_corrected").all()
    # the corrected H03 values sit on the row again (daylight)
    hub = c.drop_duplicates(["timestamp_utc", "hub_id"])
    wide = hub.pivot(index="timestamp_utc", columns="hub_id", values="irradiance_used_wm2")
    lit = wide[wide["H01"] > 200].loc[day("2026-06-01") :]
    peers = lit[["H01", "H02", "H04"]].median(axis=1)
    assert (lit["H03"] / peers).median() == pytest.approx(1.0, abs=0.02)


# 3B humidity = self_check ---------------------------------------------------------------


def test_stuck_humidity_can_be_found_from_the_hub_alone(tmp_path):
    def edit(w):
        t = w["true_utc"].dt.tz_convert(TZ)
        hit = w["hub_id"].eq("H04") & t.ge(pd.Timestamp("2026-04-01").tz_localize(TZ))
        dip = t.dt.hour.between(12, 17)  # afternoon dips break exact-value runs
        w.loc[hit, "humidity_pct"] = np.where(dip[hit], 96.0, 100.0)
        return w

    cfg, inputs = synth.make_input(
        tmp_path, days=60, edit=edit, overrides=["dq.humidity=self_check"]
    )
    p = run(cfg, inputs).sensor_periods
    assert len(p) == 1
    r = p.iloc[0]
    assert (r.hub_id, r.sensor, r.kind) == ("H04", "humidity_pct", "stuck")
    assert abs(r.start_utc - day("2026-04-01")) <= pd.Timedelta(days=2)
    assert pd.isna(r.end_utc)


# 4B sentinel = context ------------------------------------------------------------------


def test_a_sentinel_outside_the_range_is_always_a_sentinel():
    cfg, r = readings_cfg("dq.sentinel=context")
    i = r.index[r.timestamp_utc.eq(ts("2025-11-01T17:00Z")) & r.hub_id.eq("H01")][0]
    r.loc[i, "temp_c"] = 327.6  # thermistor short, above 95 C
    assert clean.flag_values(r, cfg).loc[i, "temp_c_flag"] == "sentinel"


def test_an_in_range_sentinel_is_kept_when_it_agrees_with_the_row():
    cfg, r = readings_cfg("dq.sentinel=context")
    t = r[(r.hub_id == "H02") & r.irradiance_wm2.between(300, 360)].timestamp_utc.iloc[0]
    hit = r.index[r.timestamp_utc.eq(t) & r.hub_id.eq("H01")]
    r.loc[hit, "irradiance_wm2"] = 327.6  # H02 reads about 330 here
    assert clean.flag_values(r, cfg).loc[hit, "irradiance_wm2_flag"].eq("").all()


def test_an_in_range_sentinel_far_from_the_row_is_a_sentinel():
    cfg, r = readings_cfg("dq.sentinel=context")
    night = r.index[r.timestamp_utc.eq(ts("2025-11-01T04:00Z")) & r.hub_id.eq("H01")]
    r.loc[night, "irradiance_wm2"] = 327.6  # H02 reads 0 at night
    assert clean.flag_values(r, cfg).loc[night, "irradiance_wm2_flag"].eq("sentinel").all()


def test_a_panel_sentinel_inside_the_range_is_checked_against_hub_mates():
    cfg, r = readings_cfg("dq.sentinel=context")
    cfg.thresholds["validation"]["sentinel_values"]["36.0"] = "made-up in-range voltage"
    rec = r[r.irradiance_wm2.gt(300)].raw_row.iloc[0]
    rows = r.index[r.raw_row.eq(rec)]
    r.loc[rows[0], "voltage_v"] = 36.0  # mates read about 35-37 V: real
    r.loc[rows[1], "current_a"] = 655.35  # out of range: sentinel
    f = clean.flag_values(r, cfg)
    assert f.loc[rows[0], "voltage_v_flag"] == ""
    r.loc[rows[1:], "voltage_v"] = 0.5  # mates read 0.5 V: 36.0 is far off
    assert clean.flag_values(r, cfg).loc[rows[0], "voltage_v_flag"] == "sentinel"
    assert f.loc[rows[1], "current_a_flag"] == "sentinel"
