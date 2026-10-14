import pandas as pd
import pytest
import synth
from conftest import RAW

from solarscope import clean, load

TZ = "America/New_York"


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


@pytest.fixture
def inputs(cfg):
    return load.load_inputs(RAW, cfg)


@pytest.fixture
def cleaned(inputs, cfg):
    return clean.clean(inputs, cfg)


def canon(cleaned, stamp: str, panel: str) -> pd.Series:
    c = cleaned.canonical
    rows = c[(c.timestamp_utc == ts(stamp)) & (c.panel_id == panel)]
    assert len(rows) == 1
    return rows.iloc[0]


def records(cleaned, stamp: str, hub: str) -> pd.DataFrame:
    f = cleaned.flags
    return f[(f.timestamp_utc == ts(stamp)) & (f.hub_id == hub)].drop_duplicates("raw_row")


# every raw row survives ----------------------------------------------------------------


def test_flags_keep_every_raw_row_and_input_is_unchanged(inputs, cfg):
    before = inputs.readings.copy()
    out = clean.clean(inputs, cfg)
    pd.testing.assert_frame_equal(inputs.readings, before)
    assert len(out.flags) == len(inputs.readings) == 1746
    assert set(out.flags.raw_row) == set(inputs.readings.raw_row)


# C3 duplicates and conflicts -----------------------------------------------------------


def test_exact_duplicate(cleaned):
    r = records(cleaned, "2025-11-01T16:00Z", "H01")
    assert r.is_duplicate.tolist() == [False, True]
    assert r.is_kept.tolist() == [True, False]
    assert not r.is_conflict.any()
    assert canon(cleaned, "2025-11-01T16:00Z", "P01").irradiance_wm2_reason == ""


def test_conflicting_duplicate(cleaned):
    r = records(cleaned, "2025-11-01T17:00Z", "H02")
    assert r.is_conflict.all() and r.is_kept.sum() == 1 and not r.is_duplicate.any()
    p05 = canon(cleaned, "2025-11-01T17:00Z", "P05")
    assert p05.current_a_reason == "conflict" and pd.isna(p05.current_a)
    assert p05.voltage_v_reason == ""  # the records agree on everything else
    assert canon(cleaned, "2025-11-01T17:00Z", "P04").current_a_reason == ""


# C1 value flags -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stamp,panel,measure,reason",
    [
        ("2025-11-03T17:00Z", "P01", "temp_c", "sentinel"),  # -40.0, also out of range
        ("2025-11-03T18:00Z", "P06", "current_a", "sentinel"),  # 655.35
        ("2025-11-01T18:00Z", "P04", "humidity_pct", "out_of_range"),  # 104.5, hub-level
        ("2025-11-01T18:00Z", "P06", "humidity_pct", "out_of_range"),
        ("2025-11-03T18:00Z", "P02", "voltage_v", "out_of_range"),  # 52.3
        ("2025-11-01T19:00Z", "P03", "voltage_v", "missing"),
        ("2025-11-03T15:00Z", "P05", "irradiance_wm2", "missing"),
    ],
)
def test_value_flags(cleaned, stamp, panel, measure, reason):
    row = canon(cleaned, stamp, panel)
    assert row[f"{measure}_reason"] == reason
    assert pd.isna(row[measure])


def test_sentinels_are_scoped_to_their_measures(cfg):
    assert 327.6 not in clean.sentinels_for("irradiance_wm2", cfg)
    assert {327.6, -40.0} <= set(clean.sentinels_for("temp_c", cfg))
    assert 655.35 in clean.sentinels_for("current_a", cfg)
    assert 655.35 not in clean.sentinels_for("irradiance_wm2", cfg)
    assert 6553.5 in clean.sentinels_for("humidity_pct", cfg)  # unlisted = every measure


def test_real_irradiance_of_327_6_is_kept(inputs, cfg):
    r = inputs.readings.copy()
    r.loc[0, ["irradiance_wm2", "temp_c"]] = [327.6, 327.6]
    flags = clean.flag_values(r, cfg)
    assert flags.loc[0, "irradiance_wm2_flag"] == ""
    assert flags.loc[0, "temp_c_flag"] == "sentinel"


# C4 grid and C5 gaps --------------------------------------------------------------------


def test_canonical_grid_covers_every_panel_and_interval(cleaned):
    c = cleaned.canonical
    assert len(c) == 292 * 6
    assert c.groupby("panel_id").size().eq(292).all()
    per_day = c[c.panel_id == "P01"].groupby("local_date").size()
    assert per_day.tolist() == [96, 100, 96]  # DST fall-back day
    assert list(c.columns) == clean.CANONICAL_COLUMNS
    assert str(c.timestamp_utc.dt.tz) == "UTC" and str(c.raw_row.dtype) == "Int64"
    assert c.equals(c.sort_values(["timestamp_utc", "panel_id"]).reset_index(drop=True))


def test_gap_rows_and_gap_table(cleaned):
    c = cleaned.canonical
    gap = c[c.is_gap]
    assert set(gap.hub_id) == {"H02"} and len(gap) == 4 * 3
    assert gap.raw_row.isna().all() and gap.temp_c_reason.eq("gap").all()
    g = cleaned.gaps
    assert len(g) == 1
    assert g.iloc[0].to_dict() == {
        "hub_id": "H02",
        "start_utc": ts("2025-11-03T19:00Z"),
        "end_utc": ts("2025-11-03T20:00Z"),
        "n_intervals": 4,
    }


def test_no_clock_offset_on_the_fixture(cleaned):
    assert cleaned.clock_offsets.empty
    f = cleaned.flags
    assert f.clock_offset_min.eq(0).all() and f.timestamp_raw_utc.equals(f.timestamp_utc)


# C2 clock offsets (synthetic: 4 hubs in one row) ----------------------------------------


@pytest.mark.parametrize("offset", [-240, -180, 120])
def test_clock_offset_is_found_and_excluded(tmp_path, offset):
    def edit(w):
        return synth.shift_clock(w, "H02", "2026-03-04", "2026-03-07", offset, TZ)

    cfg, inputs = synth.make_input(tmp_path, days=10, edit=edit)
    out = clean.clean(inputs, cfg)

    off = out.clock_offsets
    assert len(off) == 1 and off.iloc[0].hub_id == "H02"
    assert off.iloc[0].offset_min == offset
    assert off.iloc[0].start_utc == ts("2026-03-04").tz_localize(TZ)
    assert off.iloc[0].end_utc == ts("2026-03-07").tz_localize(TZ)
    assert off.iloc[0].n_records == 3 * 96

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
    assert h02.irradiance_wm2.isna().all()
    assert h02.irradiance_wm2_reason.eq("clock_offset").all()


def test_healthy_hubs_have_no_clock_offset(tmp_path):
    cfg, inputs = synth.make_input(tmp_path, days=10)
    assert clean.clean(inputs, cfg).clock_offsets.empty


def test_a_frozen_sensor_is_not_a_clock_offset(tmp_path):
    def edit(w):
        t = w["true_utc"].dt.tz_convert(TZ)
        lo = pd.Timestamp("2026-03-04").tz_localize(TZ)
        hit = w["hub_id"].eq("H03") & t.ge(lo) & t.lt(lo + pd.Timedelta(days=3))
        w.loc[hit, "irradiance_wm2"] = 512.3  # flat line: its midday is noon
        return w

    cfg, inputs = synth.make_input(tmp_path, days=10, edit=edit)
    assert clean.clean(inputs, cfg).clock_offsets.empty
