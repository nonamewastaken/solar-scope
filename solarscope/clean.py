"""Stage 2: flag every raw value, fix clock offsets, build the canonical 15-minute grid.

See docs/contracts.md §3. Flag, never delete: every raw row survives in `flags`.
Steps, in order (each one needs the one before it):

C1 flag_values        missing, then sentinel, then out_of_range, per measure
C2 fix_clock_offsets  find hubs whose clock ran a whole number of hours off and move
                      their records back to the true time (before C3, because an
                      offset is what creates fake conflicts and gaps)
C3 flag_duplicates    exact duplicates, conflicting duplicates, the record kept per key
C4 build_canonical    one row per (timestamp_utc, panel_id) on the full grid
C5 find_gaps          runs of intervals with no record, per hub
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from solarscope.config import Config
from solarscope.load import HUB_MEASURES, PANEL_MEASURES, Inputs

MEASURES = [*HUB_MEASURES, *PANEL_MEASURES]
KEY = ["timestamp_utc", "hub_id"]
OFFSET_COLUMNS = ["hub_id", "start_utc", "end_utc", "offset_min", "n_records", "evidence"]
GAP_COLUMNS = ["hub_id", "start_utc", "end_utc", "n_intervals"]


@dataclass(frozen=True)
class Cleaned:
    flags: pd.DataFrame  # every raw row, flagged
    canonical: pd.DataFrame  # the calculation dataset
    gaps: pd.DataFrame
    clock_offsets: pd.DataFrame  # one row per corrected clock-offset period


def clean(inputs: Inputs, cfg: Config) -> Cleaned:
    flags = flag_values(inputs.readings, cfg)
    flags, offsets = fix_clock_offsets(flags, cfg)
    flags = flag_duplicates(flags)
    canonical = build_canonical(flags, inputs.panels, cfg)
    gaps = find_gaps(canonical, cfg)
    return Cleaned(flags, canonical, gaps, offsets)


# C1 -------------------------------------------------------------------------------------


def sentinels_for(measure: str, cfg: Config) -> list[float]:
    """Sentinel values that apply to this measure.

    `validation.sentinel_measures` scopes a sentinel to the measures it belongs to (327.6
    is a thermistor short, so only temp_c). A sentinel it does not list applies to every
    measure.
    """
    v = cfg.thresholds["validation"]
    scope = {float(k): ms for k, ms in (v.get("sentinel_measures") or {}).items()}
    values = [float(k) for k in v["sentinel_values"]]
    return [s for s in values if s not in scope or measure in scope[s]]


def flag_values(readings: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add `<measure>_flag`: missing, sentinel, or out_of_range (first match wins)."""
    v = cfg.thresholds["validation"]
    out = readings.copy()
    for m in MEASURES:
        x = out[m]
        sentinel = np.zeros(len(out), dtype=bool)
        for s in sentinels_for(m, cfg):
            sentinel |= (x - s).abs().le(v["sentinel_tolerance"]).to_numpy()
        lo, hi = v["valid_ranges"][m]
        flag = np.select(
            [x.isna().to_numpy(), sentinel, ((x < lo) | (x > hi)).to_numpy()],
            ["missing", "sentinel", "out_of_range"],
            default="",
        )
        out[f"{m}_flag"] = pd.Series(flag, index=out.index, dtype="str")
    return out


# C2 -------------------------------------------------------------------------------------


def fix_clock_offsets(flags: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Find clock-offset periods and move those records back to the true time.

    Adds `timestamp_raw_utc` (the label as written) and `clock_offset_min` (label minus
    true time, 0 when the clock was right), then fixes timestamp_utc/_local/local_date.
    """
    out = flags.copy()
    out["timestamp_raw_utc"] = out["timestamp_utc"]
    out["clock_offset_min"] = np.int64(0)
    periods = find_clock_offsets(out, cfg)
    for p in periods:
        hit = out["raw_row"].isin(p["raw_rows"])
        out.loc[hit, "clock_offset_min"] = p["offset_min"]
    shift = pd.to_timedelta(out["clock_offset_min"], unit="min")
    out["timestamp_utc"] = (out["timestamp_raw_utc"] - shift).dt.as_unit("us")
    out["timestamp_local"] = out["timestamp_utc"].dt.tz_convert(cfg.tz)
    out["local_date"] = out["timestamp_local"].dt.tz_localize(None).dt.normalize()
    out = out.sort_values(["timestamp_utc", "hub_id", "raw_row", "slot"]).reset_index(drop=True)
    table = pd.DataFrame(
        [{c: p[c] for c in OFFSET_COLUMNS} for p in periods], columns=OFFSET_COLUMNS
    )
    return out, table.astype({"offset_min": "int64", "n_records": "int64"})


def hub_records(flags: pd.DataFrame) -> pd.DataFrame:
    """One row per raw record (the p1 slot row carries the hub-level values)."""
    first_slot = flags["slot"].eq(flags["slot"].min())
    return flags.loc[first_slot, ["raw_row", "timestamp_utc", "hub_id", "row", *HUB_MEASURES]]


def find_clock_offsets(flags: pd.DataFrame, cfg: Config) -> list[dict]:
    """Day-level detection, then edge refinement. Returns one dict per period.

    A hub's day is offset when its irradiance-weighted midday differs from the median of
    the other hubs in its row by a whole number of `step_min`. At least `min_days` such
    days in a row, all with the same offset, make a period. The period edges are then
    moved to where the clock actually jumped, using the overlap (keys written twice) and
    the hole (keys never written) that a jump leaves behind.
    """
    c = cfg.thresholds["clean"]["clock_offset"]
    q = cfg.thresholds["quality"]
    rec = hub_records(flags)
    usable = flags.loc[rec.index, "irradiance_wm2_flag"].eq("")
    irr = rec.assign(irr=rec["irradiance_wm2"].where(usable))
    first = irr.drop_duplicates(KEY)  # one value per key is enough to find the shape of a day
    wide = first.pivot(index="timestamp_utc", columns="hub_id", values="irr")
    rows = first.drop_duplicates("hub_id").set_index("hub_id")["row"]

    periods = []
    for hub in wide.columns:
        peers = [h for h in rows.index if rows[h] == rows[hub] and h != hub]
        if len(peers) < q["min_peer_hubs"]:
            continue
        peer = wide[peers].median(axis=1)
        daily = _daily_offsets(wide[hub], peer, cfg)
        for start_day, end_day, offset in _offset_runs(daily, c["min_days"]):
            periods.append(_refine(flags, rec, hub, start_day, end_day, offset, daily, cfg))
    return periods


def _daily_offsets(hub: pd.Series, peer: pd.Series, cfg: Config) -> pd.Series:
    """Per local label day: hub midday minus peer midday, rounded to `step_min`, or NaN."""
    c = cfg.thresholds["clean"]["clock_offset"]
    both = hub.notna() & peer.notna()
    t = pd.Series(hub.index.as_unit("s").asi8 / 60.0, index=hub.index)  # minutes
    df = pd.DataFrame({"h": hub[both], "p": peer[both], "t": t[both]})
    df["day"] = df.index.tz_convert(cfg.tz).tz_localize(None).normalize()
    lit = c["min_irradiance_wm2"]
    g = df.assign(
        ht=df.h * df.t,
        pt=df.p * df.t,
        hn=df.h.ge(lit),
        pn=df.p.ge(lit),
    ).groupby("day")
    s = g[["h", "p", "ht", "pt", "hn", "pn"]].sum()
    enough = (s.hn >= c["min_daylight_intervals"]) & (s.pn >= c["min_daylight_intervals"])
    raw = (s.ht / s.h - s.pt / s.p).where(enough)
    step = c["step_min"]
    rounded = (raw / step).round() * step
    return rounded.where((raw - rounded).abs() <= c["tolerance_min"])


def _offset_runs(daily: pd.Series, min_days: int) -> list[tuple]:
    """Runs of days with the same non-zero offset. Days without an estimate (overcast,
    no data) inside a run do not break it."""
    known = daily.dropna()
    runs, start, prev_day, prev = [], None, None, 0.0
    for day, off in known.items():
        if off != prev:
            if prev != 0 and start is not None:
                runs.append((start, prev_day, prev))
            start = day
        prev_day, prev = day, off
    if prev != 0 and start is not None:
        runs.append((start, prev_day, prev))
    out = []
    for s, e, off in runs:
        n_days = int(known.loc[s:e].ne(0).sum())
        if n_days >= min_days:
            out.append((s, e, int(off)))
    return out


def _refine(flags, rec, hub, start_day, end_day, offset, daily, cfg) -> dict:
    """Pick the exact records of one offset period.

    Core: every record labelled inside the offset days. Then the edges:
    - offset < 0 (labels early): the jump back writes an overlap of |offset| before the
      first shifted label (the later-received record of each overlapping key is the
      shifted one), and the jump forward at the end leaves a hole of |offset|.
    - offset > 0 (labels late): the hole is at the start and the overlap at the end (the
      earlier-received record is the shifted one).
    """
    tz, step = cfg.tz, pd.Timedelta(minutes=cfg.interval_min)
    span = pd.Timedelta(minutes=abs(offset))
    lo = pd.Timestamp(start_day).tz_localize(tz).tz_convert("UTC")
    hi = (pd.Timestamp(end_day) + pd.Timedelta(days=1)).tz_localize(tz).tz_convert("UTC")
    h = rec[rec["hub_id"] == hub].sort_values("raw_row")
    sig = _record_signature(flags, h["raw_row"])
    h = h.assign(sig=sig.to_numpy())
    distinct = h.drop_duplicates([*KEY, "sig"])
    multi = distinct.groupby("timestamp_utc").size()
    overlap_keys = multi[multi > 1].index
    present = pd.DatetimeIndex(h["timestamp_utc"].unique())

    def hole_after(t):  # first label at or after t that was never written
        return _first_missing(present, t, step, forward=True)

    def hole_before(t):
        return _first_missing(present, t - step, step, forward=False)

    if offset < 0:
        ov = overlap_keys[(overlap_keys >= lo - span - step) & (overlap_keys < lo + span)]
        start = ov.min() if len(ov) else lo
        end = hole_after(hi - span) if hole_after(hi - span) is not None else hi
        end = min(max(end, hi - span), hi + span)
        core = h[(h["timestamp_utc"] >= start) & (h["timestamp_utc"] < end)]
        # inside the overlap, the later-received copy of each key is the shifted one
        in_ov = core["timestamp_utc"].isin(ov)
        later = core[in_ov].drop_duplicates("timestamp_utc", keep="last")
        rows = pd.concat([core[~in_ov], later])
    else:
        hole = hole_before(lo + span)
        start = max(min(hole + step, lo + span), lo - span) if hole is not None else lo
        ov = overlap_keys[(overlap_keys >= hi - span) & (overlap_keys < hi + span + step)]
        end = ov.max() + step if len(ov) else hi
        core = h[(h["timestamp_utc"] >= start) & (h["timestamp_utc"] < end)]
        in_ov = core["timestamp_utc"].isin(ov)
        earlier = core[in_ov].drop_duplicates("timestamp_utc", keep="first")
        rows = pd.concat([core[~in_ov], earlier])

    # an exact duplicate of a shifted record is shifted too
    dup = h.merge(rows[["timestamp_utc", "sig"]], on=["timestamp_utc", "sig"])
    raw_rows = set(rows["raw_row"]) | set(dup["raw_row"])
    shift = pd.Timedelta(minutes=offset)
    true = (h.loc[h["raw_row"].isin(raw_rows), "timestamp_utc"] - shift).sort_values()
    n_days = int(daily.loc[start_day:end_day].eq(offset).sum())
    return {
        "hub_id": hub,
        "start_utc": true.iloc[0],
        "end_utc": true.iloc[-1] + step,
        "offset_min": offset,
        "n_records": len(raw_rows),
        "evidence": f"irradiance midday {offset:+d} min vs row on {n_days} days",
        "raw_rows": raw_rows,
    }


def _first_missing(present: pd.DatetimeIndex, t, step, forward: bool, limit: int = 192):
    for _ in range(limit):
        if t not in present:
            return t
        t = t + step if forward else t - step
    return None


def _record_signature(flags: pd.DataFrame, raw_rows: pd.Series) -> pd.Series:
    """A hash of every value in each raw record (all slots). Equal hash = identical record."""
    sub = flags[flags["raw_row"].isin(raw_rows)]
    wide = sub.pivot(index="raw_row", columns="slot", values=MEASURES)
    wide.columns = [f"{s}_{m}" for m, s in wide.columns]
    sig = pd.util.hash_pandas_object(wide, index=False)
    return sig.reindex(raw_rows.to_numpy())


# C3 -------------------------------------------------------------------------------------


def flag_duplicates(flags: pd.DataFrame) -> pd.DataFrame:
    """Add is_duplicate, is_conflict, is_kept, and the `conflict` reason.

    Duplicate: identical to an earlier-received record with the same key.
    Conflict: the key has records with different values. Each measure the records
    disagree on gets reason `conflict` on all of them (unless already flagged), so its
    canonical value is NaN (`clean.conflict_keep: none`).
    Kept: the earliest-received record per key.
    """
    out = flags.copy()
    rec = hub_records(out).sort_values("raw_row")
    rec = rec.assign(sig=_record_signature(out, rec["raw_row"]).to_numpy())
    rec["is_duplicate"] = rec.duplicated([*KEY, "sig"], keep="first")
    rec["is_conflict"] = rec.groupby(KEY)["sig"].transform("nunique").gt(1)
    rec["is_kept"] = ~rec.duplicated(KEY, keep="first")
    per_raw = rec.set_index("raw_row")[["is_duplicate", "is_conflict", "is_kept"]]
    for col in per_raw.columns:
        out[col] = out["raw_row"].map(per_raw[col]).astype(bool)

    conflict_rows = out[out["is_conflict"]]
    if len(conflict_rows):
        for m in MEASURES:
            by = [*KEY] if m in HUB_MEASURES else [*KEY, "slot"]
            n = conflict_rows.groupby(by)[m].transform(lambda s: s.nunique(dropna=False))
            hit = n.index[n.gt(1)]
            ok = out.loc[hit, f"{m}_flag"].eq("")
            out.loc[ok.index[ok], f"{m}_flag"] = "conflict"
    return out


# C4 -------------------------------------------------------------------------------------

CANONICAL_COLUMNS = [
    "timestamp_utc", "timestamp_local", "local_date", "hub_id", "row", "string_id",
    "panel_id", *MEASURES, *[f"{m}_reason" for m in MEASURES], "is_gap", "raw_row",
]  # fmt: skip


def build_canonical(flags: pd.DataFrame, panels: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Full grid: every interval from the first local midnight to the end of the last
    local day, for every panel in site.json. Gaps are rows with reason `gap`."""
    grid = full_grid(flags["timestamp_utc"], cfg)
    p = panels[["panel_id", "hub_id", "row", "string_id"]]
    base = pd.DataFrame({"timestamp_utc": grid.repeat(len(p))})
    for col in p.columns:
        base[col] = np.tile(p[col].to_numpy(), len(grid))

    kept = flags[flags["is_kept"]]
    vals = kept[["timestamp_utc", "panel_id", "raw_row"]].copy()
    for m in MEASURES:
        ok = kept[f"{m}_flag"].eq("")
        vals[m] = kept[m].where(ok)
        vals[f"{m}_reason"] = kept[f"{m}_flag"]
    out = base.merge(vals, on=["timestamp_utc", "panel_id"], how="left")
    out["is_gap"] = out["raw_row"].isna()
    for m in MEASURES:
        out[f"{m}_reason"] = out[f"{m}_reason"].fillna("gap").astype("str")
    out["raw_row"] = out["raw_row"].astype("Int64")
    out["timestamp_local"] = out["timestamp_utc"].dt.tz_convert(cfg.tz)
    out["local_date"] = out["timestamp_local"].dt.tz_localize(None).dt.normalize()
    out = out.sort_values(["timestamp_utc", "panel_id"]).reset_index(drop=True)
    return out[CANONICAL_COLUMNS]


def full_grid(timestamps: pd.Series, cfg: Config) -> pd.DatetimeIndex:
    local = timestamps.dt.tz_convert(cfg.tz).dt.tz_localize(None).dt.normalize()
    first = local.min().tz_localize(cfg.tz)
    end = (local.max() + pd.Timedelta(days=1)).tz_localize(cfg.tz)
    return pd.date_range(
        first.tz_convert("UTC"),
        end.tz_convert("UTC"),
        freq=f"{cfg.interval_min}min",
        inclusive="left",
        unit="us",
    )


# C5 -------------------------------------------------------------------------------------


def find_gaps(canonical: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """One row per run of consecutive intervals with no record (`end_utc` exclusive)."""
    step = pd.Timedelta(minutes=cfg.interval_min)
    hub = canonical.drop_duplicates(KEY)[[*KEY, "is_gap"]].sort_values(["hub_id", "timestamp_utc"])
    hub = hub.assign(run=(hub["is_gap"] != hub.groupby("hub_id")["is_gap"].shift()).cumsum())
    g = hub[hub["is_gap"]].groupby(["hub_id", "run"])["timestamp_utc"]
    gaps = g.agg(start_utc="min", end_utc="max", n_intervals="size").reset_index(level=0)
    gaps["end_utc"] = gaps["end_utc"] + step
    gaps = gaps[gaps["n_intervals"] >= cfg.thresholds["clean"]["gap_min_intervals"]]
    gaps = gaps.sort_values(["hub_id", "start_utc"]).reset_index(drop=True)
    return gaps[GAP_COLUMNS].astype({"n_intervals": "int64"})
