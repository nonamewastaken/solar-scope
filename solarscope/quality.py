"""Stage 3: hub sensor quality, sensor exclusion, irradiance fallback, data_quality.csv.

See docs/contracts.md §4. Steps:

Q1 hub_sensors        one value per hub and interval for each hub-level sensor
Q2 find_stuck         identical-value runs (any hub sensor), and humidity far from its row
Q3 find_drift         irradiance ratio to the trusted hubs in the row, against the hub's
                      own normal ratio; the start is moved back to the change point
                      (Q2 and Q3 repeat with the hubs found so far left out of the peer
                      medians, so one bad sensor cannot make its neighbours look bad)
Q4 apply_exclusions   reason sensor_drift / sensor_stuck, sensor_excluded
Q5 add_irradiance_used  the hub's own value when trusted, else the trusted row median
Q6 comm_outages       gaps of at least quality.comm_outage_min_intervals
Q7 data_quality       one row per hub per window (data_quality.csv)
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from solarscope import results
from solarscope.clean import Cleaned
from solarscope.config import Config, Window
from solarscope.load import HUB_MEASURES, PANEL_MEASURES, Inputs

KEY = ["timestamp_utc", "hub_id"]
PERIOD_COLUMNS = ["hub_id", "sensor", "kind", "start_utc", "end_utc", "evidence"]
REASON = {"drift": "sensor_drift", "stuck": "sensor_stuck"}
DAY = pd.Timedelta(days=1)


@dataclass(frozen=True)
class Quality:
    canonical: pd.DataFrame
    sensor_periods: pd.DataFrame
    comm_outages: pd.DataFrame
    data_quality: pd.DataFrame


def assess(cleaned: Cleaned, inputs: Inputs, windows: list[Window], cfg: Config) -> Quality:
    rows = inputs.panels.drop_duplicates("hub_id").set_index("hub_id")["row"]
    hub = hub_sensors(cleaned.canonical)
    periods = find_sensor_periods(hub, rows, cfg)
    canonical = apply_exclusions(cleaned.canonical, periods)
    canonical = add_irradiance_used(canonical, cfg)
    outages = comm_outages(cleaned.gaps, cfg)
    dq = data_quality(cleaned, canonical, periods, outages, windows, inputs, cfg)
    return Quality(canonical, periods, outages, dq)


# Q1 -------------------------------------------------------------------------------------


def hub_sensors(canonical: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{sensor: wide frame, index timestamp_utc, one column per hub}. NaN = not usable."""
    hub = canonical.drop_duplicates(KEY)
    return {m: hub.pivot(index="timestamp_utc", columns="hub_id", values=m) for m in HUB_MEASURES}


def find_sensor_periods(hub: dict, rows: pd.Series, cfg: Config) -> pd.DataFrame:
    """Q2 + Q3, repeated with confirmed bad sensors left out of the peer medians.

    A rule that compares a hub with its row can blame the neighbours of a bad hub too
    (with 3 hubs in a row, one hub 40% high pulls the median of the other two up 20%).
    So each pass confirms only the worst peer-based finding per row and sensor, masks
    it, and runs again. Identical-value runs do not depend on peers and are always masked.
    """
    q = cfg.thresholds["quality"]
    confirmed: set[tuple[str, str]] = set()
    found = empty_periods()
    for _ in range(q["max_passes"]):
        keys = list(zip(found["hub_id"], found["sensor"], strict=True))
        sure = found["severity"].isna() | pd.Series([k in confirmed for k in keys], dtype=bool)
        trusted = {m: mask_periods(hub[m], found[sure.to_numpy()], m) for m in hub}
        found = pd.concat(
            [
                find_stuck(hub, trusted, rows, cfg),
                find_drift(hub["irradiance_wm2"], trusted["irradiance_wm2"], rows, cfg),
            ],
            ignore_index=True,
        )
        keys = list(zip(found["hub_id"], found["sensor"], strict=True))
        fresh = np.array([k not in confirmed for k in keys], dtype=bool)
        new = found[found["severity"].notna().to_numpy() & fresh]
        if new.empty:
            break
        worst = new.assign(row=new["hub_id"].map(rows)).sort_values("severity")
        worst = worst.groupby(["row", "sensor"]).tail(1)
        confirmed |= set(zip(worst["hub_id"], worst["sensor"], strict=True))
    gap = pd.Timedelta(hours=q["merge_gap_h"])
    return merge_periods(found[PERIOD_COLUMNS], gap)


def empty_periods() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "hub_id": pd.Series(dtype="str"),
            "sensor": pd.Series(dtype="str"),
            "kind": pd.Series(dtype="str"),
            "start_utc": pd.Series(dtype="datetime64[us, UTC]"),
            "end_utc": pd.Series(dtype="datetime64[us, UTC]"),
            "evidence": pd.Series(dtype="str"),
            "severity": pd.Series(dtype="float64"),  # peer-based findings only
        }
    )


def mask_periods(wide: pd.DataFrame, periods: pd.DataFrame, sensor: str) -> pd.DataFrame:
    """`wide` with every value inside a period of this sensor set to NaN."""
    out = wide.copy()
    for p in periods[periods["sensor"] == sensor].itertuples():
        out.loc[in_period(out.index, p), p.hub_id] = np.nan
    return out


def in_period(index: pd.DatetimeIndex, p) -> np.ndarray:
    hit = index >= p.start_utc
    if pd.notna(p.end_utc):
        hit &= index < p.end_utc
    return hit


def peer_median(trusted: pd.DataFrame, rows: pd.Series, hub: str, min_peers: int) -> pd.Series:
    """Median of the other trusted hubs in the hub's row, NaN with fewer than min_peers."""
    peers = [h for h in trusted.columns if h != hub and rows.get(h) == rows[hub]]
    p = trusted[peers]
    return p.median(axis=1).where(p.notna().sum(axis=1) >= min_peers)


def local_day(index: pd.DatetimeIndex, cfg: Config) -> pd.DatetimeIndex:
    return index.tz_convert(cfg.tz).tz_localize(None).normalize()


def day_start_utc(day: pd.Timestamp, cfg: Config) -> pd.Timestamp:
    return pd.Timestamp(day).tz_localize(cfg.tz).tz_convert("UTC").as_unit("us")


def day_runs(flag: pd.Series, min_days: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """(first, last) day of each run of True days. Days with NaN (no estimate) inside a
    run do not break it and do not count toward min_days."""
    known = flag.dropna().astype(bool)
    runs, start, last, n = [], None, None, 0
    for day, hit in known.items():
        if hit:
            start = day if start is None else start
            last, n = day, n + 1
        elif start is not None:
            runs.append((start, last, n))
            start, n = None, 0
    if start is not None:
        runs.append((start, last, n))
    return [(s, e) for s, e, k in runs if k >= min_days]


# Q2 -------------------------------------------------------------------------------------


def find_stuck(hub: dict, trusted: dict, rows: pd.Series, cfg: Config) -> pd.DataFrame:
    return pd.concat(
        [*(identical_runs(hub[m], m, cfg) for m in hub), humidity_vs_row(hub, trusted, rows, cfg)],
        ignore_index=True,
    )


def identical_runs(wide: pd.DataFrame, sensor: str, cfg: Config) -> pd.DataFrame:
    """The same value `stuck.min_intervals` or more intervals in a row."""
    s = cfg.thresholds["quality"]["stuck"]
    step = pd.Timedelta(minutes=cfg.interval_min)
    out = []
    for hub in wide.columns:
        x = wide[hub]
        run = (x.ne(x.shift()) | x.isna()).cumsum()
        g = pd.DataFrame({"x": x, "run": run}).dropna().groupby("run")
        size = g["x"].size()
        value = g["x"].first()
        keep = size.index[(size >= s["min_intervals"]) & ~value.isin(s["skip_values"])]
        for r in keep:
            idx = x.index[run == r]
            out.append(
                {
                    "hub_id": hub,
                    "sensor": sensor,
                    "kind": "stuck",
                    "start_utc": idx[0],
                    "end_utc": idx[-1] + step,
                    "evidence": f"{sensor} = {value[r]:g} for {size[r]} intervals",
                }
            )
    return pd.DataFrame(out, columns=[*PERIOD_COLUMNS, "severity"]) if out else empty_periods()


def humidity_vs_row(hub: dict, trusted: dict, rows: pd.Series, cfg: Config) -> pd.DataFrame:
    """Daily median humidity more than `humidity_peer_diff_pp` from the row median for
    `stuck.min_days` days or more (H09 sits near 100% while its row reads 50-70%)."""
    q = cfg.thresholds["quality"]
    s = q["stuck"]
    raw, tr = hub["humidity_pct"], trusted["humidity_pct"]
    last_day = local_day(raw.index, cfg).max()
    out = []
    for h in raw.columns:
        diff = raw[h] - peer_median(tr, rows, h, q["min_peer_hubs"])
        daily = diff.groupby(local_day(diff.index, cfg)).median()
        hit = daily.abs().gt(s["humidity_peer_diff_pp"]).where(daily.notna())
        for first, last in day_runs(hit, s["min_days"]):
            d = daily.loc[first:last]
            out.append(
                {
                    "hub_id": h,
                    "sensor": "humidity_pct",
                    "kind": "stuck",
                    "start_utc": day_start_utc(first, cfg),
                    "end_utc": _end(last, last_day, cfg),
                    "evidence": f"humidity {d.median():+.0f} pp vs row median "
                    f"(daily median) for {d.notna().sum()} days",
                    "severity": abs(d.median()) / s["humidity_peer_diff_pp"],
                }
            )
    return pd.DataFrame(out, columns=[*PERIOD_COLUMNS, "severity"]) if out else empty_periods()


def _end(last: pd.Timestamp, last_day: pd.Timestamp, cfg: Config):
    """Exclusive end of a run of days, or NaT when it reaches the end of the data."""
    if last >= last_day:
        return pd.NaT
    return day_start_utc(last + DAY, cfg)


# Q3 -------------------------------------------------------------------------------------


def daily_ratio(raw: pd.DataFrame, trusted: pd.DataFrame, rows: pd.Series, hub: str, cfg):
    """Daily median of hub irradiance / trusted row median, daylight only."""
    q = cfg.thresholds["quality"]
    d = q["drift"]
    peer = peer_median(trusted, rows, hub, q["min_peer_hubs"])
    lit = peer >= d["min_irradiance_wm2"]
    ratio = (raw[hub] / peer)[lit & raw[hub].notna()]
    g = ratio.groupby(local_day(ratio.index, cfg))
    return g.median().where(g.size() >= d["min_intervals_per_day"]).dropna()


def find_drift(raw: pd.DataFrame, trusted: pd.DataFrame, rows: pd.Series, cfg) -> pd.DataFrame:
    """Irradiance drift: the hub's ratio to its row, divided by the hub's own normal ratio
    (its first `baseline_days` days), stays outside 1 ± ratio_tolerance on a
    `rolling_days` rolling median for `min_days` days."""
    d = cfg.thresholds["quality"]["drift"]
    out = []
    for h in raw.columns:
        ratio = daily_ratio(raw, trusted, rows, h, cfg)
        if len(ratio) < d["baseline_days"]:
            continue
        base = ratio.iloc[: d["baseline_days"]].median()
        dev = ratio / base - 1
        rolling = dev.rolling(f"{d['rolling_days']}D", min_periods=d["min_days"]).median()
        hit = rolling.abs().gt(d["ratio_tolerance"]).where(rolling.notna())
        prev_end = dev.index[0]
        for trig, last in day_runs(hit, d["min_days"]):
            start = trig
            if d["start"] == "change_point":
                cp = change_point(dev.loc[prev_end:last], d["min_segment_days"])
                start = min(cp, trig) if cp is not None else trig
            over = dev.loc[start:last].abs().gt(d["ratio_tolerance"])
            end_day = over.index[over][-1] if over.any() else last
            ongoing = last >= ratio.index[-1]
            peak = dev.loc[start:last]
            peak = peak.loc[peak.abs().idxmax()]
            out.append(
                {
                    "hub_id": h,
                    "sensor": "irradiance_wm2",
                    "kind": "drift",
                    "start_utc": day_start_utc(start, cfg),
                    "end_utc": pd.NaT if ongoing else day_start_utc(end_day + DAY, cfg),
                    "evidence": f"ratio to row {base * (1 + peak):.3f} vs own normal "
                    f"{base:.3f} ({peak:+.0%}); over ±{d['ratio_tolerance']:.0%} from "
                    f"{trig.date()}, change point {start.date()}",
                    "severity": abs(peak) / d["ratio_tolerance"],
                }
            )
            prev_end = last
    return pd.DataFrame(out, columns=[*PERIOD_COLUMNS, "severity"]) if out else empty_periods()


def change_point(y: pd.Series, min_seg: int) -> pd.Timestamp | None:
    """Day where a flat line turns into a free line (step and/or slope), by least squares.

    Fits y = a before the change and y = b + c*t from it on, for every split with at
    least min_seg days on each side, and returns the split with the smallest error.
    """
    y = y.dropna()
    n = len(y)
    if n < 2 * min_seg:
        return None
    t = (y.index - y.index[0]).days.to_numpy(dtype=float)
    v = y.to_numpy(dtype=float)
    best, best_k = math.inf, None
    for k in range(min_seg, n - min_seg + 1):
        left = v[:k]
        sse = ((left - left.mean()) ** 2).sum()
        tr, vr = t[k:], v[k:]
        slope, icpt = np.polyfit(tr, vr, 1)
        sse += ((vr - (icpt + slope * tr)) ** 2).sum()
        if sse < best:
            best, best_k = sse, k
    return y.index[best_k]


def merge_periods(p: pd.DataFrame, gap: pd.Timedelta) -> pd.DataFrame:
    """Merge periods of the same hub, sensor and kind that overlap or are less than `gap`
    apart (a stuck sensor that briefly reads something else is still the same fault).
    The evidence of the longest one is kept."""
    if p.empty:
        return empty_periods()[PERIOD_COLUMNS]
    far = pd.Timestamp.max.tz_localize("UTC").as_unit("us")
    p = p.assign(fill_end=p["end_utc"].fillna(far))
    p = p.sort_values(["hub_id", "sensor", "kind", "start_utc"])
    out = []
    for (hub, sensor, kind), g in p.groupby(["hub_id", "sensor", "kind"], sort=True):
        cur = None
        for r in g.itertuples():
            if cur is not None and r.start_utc <= cur["end"] + gap:
                longer = (r.fill_end - r.start_utc) > (cur["end"] - cur["start_utc"])
                ev = r.evidence if longer else cur["ev"]
                cur.update(end=max(cur["end"], r.fill_end), ev=ev, n=cur["n"] + 1)
            else:
                if cur is not None:
                    out.append(cur)
                cur = {"hub_id": hub, "sensor": sensor, "kind": kind, "start_utc": r.start_utc,
                       "end": r.fill_end, "ev": r.evidence, "n": 1}  # fmt: skip
        out.append(cur)
    rows = []
    for c in out:
        ev = c["ev"] + (f" (merged with {c['n'] - 1} shorter periods)" if c["n"] > 1 else "")
        end = pd.NaT if c["end"] == far else c["end"]
        rows.append([c["hub_id"], c["sensor"], c["kind"], c["start_utc"], end, ev])
    df = pd.DataFrame(rows, columns=PERIOD_COLUMNS)
    for col in ["start_utc", "end_utc"]:
        df[col] = pd.to_datetime(df[col], utc=True).dt.as_unit("us")
    return df


# Q4 + Q5 --------------------------------------------------------------------------------


def apply_exclusions(canonical: pd.DataFrame, periods: pd.DataFrame) -> pd.DataFrame:
    """Values inside a sensor period become NaN with reason sensor_drift / sensor_stuck
    (a value already flagged keeps its first reason). `sensor_excluded` marks intervals
    where the hub's irradiance sensor is excluded, the one that feeds expected output."""
    out = canonical.copy()
    out["sensor_excluded"] = False
    ts = pd.DatetimeIndex(out["timestamp_utc"])
    for p in periods.itertuples():
        hit = out["hub_id"].eq(p.hub_id).to_numpy() & in_period(ts, p)
        ok = hit & out[f"{p.sensor}_reason"].eq("").to_numpy()
        out.loc[ok, f"{p.sensor}_reason"] = REASON[p.kind]
        out.loc[ok, p.sensor] = np.nan
        if p.sensor == "irradiance_wm2":
            out.loc[hit, "sensor_excluded"] = True
    return out


def add_irradiance_used(canonical: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """irradiance_used_wm2: the hub's own value when it is usable, else the median of the
    usable hubs in the same row at that interval, else NaN (source none)."""
    q = cfg.thresholds["quality"]
    out = canonical.copy()
    hub = out.drop_duplicates(KEY)[[*KEY, "row", "irradiance_wm2"]]
    g = hub.groupby(["timestamp_utc", "row"])["irradiance_wm2"]
    row_med = g.transform("median").where(g.transform("count") >= q["fallback_min_hubs"])
    sub = hub.assign(row_median=row_med)[[*KEY, "row_median"]]
    out = out.merge(sub, on=KEY, how="left")
    own = out["irradiance_wm2"].notna()
    out["irradiance_used_wm2"] = out["irradiance_wm2"].where(own, out["row_median"])
    source = np.where(own, "hub", np.where(out["row_median"].notna(), "row_median", "none"))
    out["irradiance_source"] = pd.Series(source, index=out.index, dtype="str")
    return out.drop(columns="row_median")


def is_usable(canonical: pd.DataFrame) -> pd.Series:
    """Panel V, I and T usable, and some irradiance to compare with (contract §5)."""
    ok = canonical["irradiance_source"].ne("none")
    for m in PANEL_MEASURES:
        ok &= canonical[f"{m}_reason"].eq("")
    return ok


# Q6 -------------------------------------------------------------------------------------


def comm_outages(gaps: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    n = cfg.thresholds["quality"]["comm_outage_min_intervals"]
    return gaps[gaps["n_intervals"] >= n].reset_index(drop=True)


# Q7 -------------------------------------------------------------------------------------


def data_quality(
    cleaned: Cleaned,
    canonical: pd.DataFrame,
    periods: pd.DataFrame,
    outages: pd.DataFrame,
    windows: list[Window],
    inputs: Inputs,
    cfg: Config,
) -> pd.DataFrame:
    """One row per hub per window. Counts use corrected local dates."""
    hubs = inputs.panels.groupby("hub_id", sort=True).agg(
        row=("row", "first"), n=("panel_id", "size")
    )
    flags = cleaned.flags
    first_slot = flags["slot"].eq(flags["slot"].min())
    rec = flags[first_slot]  # one row per raw record
    distinct = flags[~flags["is_duplicate"]]
    usable = canonical.assign(ok=is_usable(canonical))
    hub_can = canonical.drop_duplicates(KEY)
    step = pd.Timedelta(minutes=cfg.interval_min)

    out = []
    for w in windows:
        lo, hi = pd.Timestamp(w.start), pd.Timestamp(w.end)
        lo_utc = day_start_utc(lo, cfg)
        hi_utc = day_start_utc(hi + DAY, cfg)
        expected = int((hi_utc - lo_utc) / step)

        r, dd, u, hc = (
            df[df["local_date"].between(lo, hi)] for df in (rec, distinct, usable, hub_can)
        )
        for hub, info in hubs.iterrows():
            hr, hd = r[r.hub_id == hub], dd[dd.hub_id == hub]
            hdh = hd[hd["slot"].eq(flags["slot"].min())]  # hub-level: once per record
            counts = {}
            for reason in ["missing", "sentinel", "out_of_range"]:
                n = sum(hdh[f"{m}_flag"].eq(reason).sum() for m in HUB_MEASURES)
                n += sum(hd[f"{m}_flag"].eq(reason).sum() for m in PANEL_MEASURES)
                counts[reason] = int(n)
            h_can = hc[hc.hub_id == hub]
            hp = periods[periods.hub_id == hub]
            covered = np.zeros(len(h_can), dtype=bool)
            stamps = pd.DatetimeIndex(h_can["timestamp_utc"])
            for p in hp.itertuples():
                covered |= in_period(stamps, p)
            row = {
                "window": w.name,
                "window_start": lo,
                "window_end": hi,
                "hub_id": hub,
                "row": info["row"],
                "expected_intervals": expected,
                "received_records": len(hr),
                "usable_pct": 100 * u.loc[u.hub_id == hub, "ok"].sum() / (expected * info["n"]),
                "n_duplicate": int(hr["is_duplicate"].sum()),
                "n_conflict": int(hr["is_conflict"].sum()),
                "n_missing": counts["missing"],
                "n_sentinel": counts["sentinel"],
                "n_out_of_range": counts["out_of_range"],
                "n_gap_intervals": int(h_can["is_gap"].sum()),
                "n_sensor_excluded_intervals": int(covered.sum()),
                "excluded_periods": excluded_text(hp, lo_utc, hi_utc, cfg),
            }
            row["reasons"] = reasons_text(
                row, hp, outages, cleaned.clock_offsets, lo_utc, hi_utc, cfg
            )
            out.append(row)
    df = pd.DataFrame(out, columns=results.SCHEMAS["data_quality"])
    return df.astype({"window_start": "datetime64[us]", "window_end": "datetime64[us]"})


def _clip(p, lo_utc, hi_utc):
    end = hi_utc if pd.isna(p.end_utc) else min(p.end_utc, hi_utc)
    return max(p.start_utc, lo_utc), end


def excluded_text(hp: pd.DataFrame, lo_utc, hi_utc, cfg: Config) -> str:
    parts = []
    for p in hp.sort_values("start_utc").itertuples():
        s, e = _clip(p, lo_utc, hi_utc)
        if s < e:
            iso = [t.tz_convert(cfg.tz).isoformat() for t in (s, e)]
            parts.append(f"{p.sensor}:{p.kind}:{iso[0]}/{iso[1]}")
    return ";".join(parts)


def reasons_text(row, hp, outages, offsets, lo_utc, hi_utc, cfg) -> str:
    """Short human-readable summary of what affected this hub in this window."""
    words = {"irradiance_wm2": "irradiance", "humidity_pct": "humidity"}
    hub = row["hub_id"]
    parts = []
    for p in hp.sort_values("start_utc").itertuples():
        s, e = _clip(p, lo_utc, hi_utc)
        if s < e:
            until = "" if pd.isna(p.end_utc) else f" to {p.end_utc.date()}"
            parts.append(f"{words[p.sensor]} {p.kind} from {p.start_utc.date()}{until}")
    for o in offsets[offsets.hub_id == hub].itertuples():
        if o.start_utc < hi_utc and o.end_utc > lo_utc:
            parts.append(
                f"clock {o.offset_min:+d} min fixed {o.start_utc.date()} to {o.end_utc.date()}"
            )
    ho = outages[
        (outages.hub_id == hub) & (outages.start_utc < hi_utc) & (outages.end_utc > lo_utc)
    ]
    if len(ho):
        hours = ho["n_intervals"].sum() * cfg.interval_min / 60
        parts.append(f"{len(ho)} comm outage{'s' if len(ho) > 1 else ''} ({hours:g} h)")
    for col, name in [("n_conflict", "conflicting records"), ("n_sentinel", "sentinel values")]:
        if row[col]:
            parts.append(f"{row[col]} {name}")
    return "; ".join(parts) if parts else "no sensor or timing issues"
