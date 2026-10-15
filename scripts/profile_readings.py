"""SOL-12: profile the messiness in readings.csv, per hub. Read only.

Run from the project folder with:
    uv run scripts/profile_readings.py --input <input_folder>

Prints the counts behind docs/data_profile.md. Nothing is written to disk. The cleaning
here is rough on purpose: it only stops bad values from fooling the signal checks.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from solarscope import config  # noqa: E402

SLOTS = ("p1", "p2", "p3")
HUB_MEASURES = ["irradiance_wm2", "humidity_pct"]
PANEL_MEASURES = ["voltage_v", "current_a", "temp_c"]
KEY = ["timestamp_utc", "hub_id"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    args = p.parse_args()
    pd.set_option("display.width", 200, "display.max_columns", 50, "display.max_rows", 500)

    cfg = config.load_config(None, args.input / "site.json")
    hubs = pd.DataFrame(cfg.site["hubs"]).set_index("hub_id")
    raw = pd.read_csv(args.input / "readings.csv", dtype={"hub_id": "str"})
    raw["timestamp_utc"] = pd.to_datetime(raw["timestamp_utc"], utc=True)
    value_cols = [c for c in raw.columns if c not in KEY]
    is_sentinel = sentinel_mask(raw, value_cols, cfg)

    overview(raw, cfg, hubs)
    duplicates_and_conflicts(raw, value_cols)
    missing(raw, value_cols, cfg)
    sentinels(raw, value_cols, is_sentinel, cfg, hubs)
    out_of_range(raw, value_cols, is_sentinel, cfg)
    gaps(raw, cfg, hubs)
    signals = rough_clean(raw, value_cols, is_sentinel, cfg, hubs)
    clock_offsets(signals, cfg)
    stuck(signals, cfg)
    drift(signals, cfg)


def section(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def measure_of(col: str) -> str:
    return col.split("_", 1)[1] if col.startswith(SLOTS) else col


def by_measure(flags: pd.DataFrame, hub_id: pd.Series) -> pd.DataFrame:
    """Count flags per hub and measure, adding the 3 panel slots together."""
    return flags.T.groupby(by=[measure_of(c) for c in flags.columns]).sum().T.groupby(hub_id).sum()


def runs(mask: pd.Series) -> list[pd.Index]:
    """Index labels of each run of consecutive True values."""
    run_id = (mask != mask.shift()).cumsum()
    return [g.index for _, g in mask[mask].groupby(run_id[mask])]


def sentinel_mask(raw: pd.DataFrame, value_cols: list[str], cfg: config.Config) -> pd.DataFrame:
    v = cfg.thresholds["validation"]
    hit = pd.DataFrame(False, index=raw.index, columns=value_cols)
    for s in v["sentinel_values"]:
        hit |= (raw[value_cols] - float(s)).abs() <= v["sentinel_tolerance"]
    return hit


def overview(raw: pd.DataFrame, cfg: config.Config, hubs: pd.DataFrame) -> None:
    section("Overview")
    ts = raw["timestamp_utc"]
    print(f"records: {len(raw):,} | hubs: {raw['hub_id'].nunique()} (site.json: {len(hubs)})")
    print(f"UTC:   {ts.min()} -> {ts.max()}")
    print(f"local: {ts.min().tz_convert(cfg.tz)} -> {ts.max().tz_convert(cfg.tz)}")
    print(f"hub_ids not in site.json: {sorted(set(raw['hub_id']) - set(hubs.index))}")
    print(f"sorted by timestamp in the file: {ts.is_monotonic_increasing}")
    step = pd.Timedelta(minutes=cfg.interval_min)
    print(f"timestamps off the {cfg.interval_min}-minute grid: {(ts != ts.dt.floor(step)).sum()}")


def duplicates_and_conflicts(raw: pd.DataFrame, value_cols: list[str]) -> None:
    section("1. Exact duplicates and conflicting records")
    dup = raw.duplicated(keep="first")
    distinct = raw[~dup]
    conflict = distinct[distinct.duplicated(KEY, keep=False)]
    out = pd.DataFrame(
        {
            "records": raw.groupby("hub_id").size(),
            "exact_dup_records": raw[dup].groupby("hub_id").size(),
            "conflict_keys": conflict.groupby("hub_id")["timestamp_utc"].nunique(),
            "conflict_records": conflict.groupby("hub_id").size(),
        }
    )
    print(out.fillna(0).astype(int).to_string())
    n_keys = len(conflict[KEY].drop_duplicates())
    print(f"total: {dup.sum()} exact duplicates, {n_keys} conflicting keys")

    copies = raw[raw.duplicated(keep=False)].groupby(value_cols + KEY, dropna=False).size()
    print(f"copies per duplicated record: {copies.value_counts().to_dict()}")
    pos = raw.reset_index().merge(raw[dup].reset_index(), on=KEY + value_cols)
    lag = (pos["index_y"] - pos["index_x"]).loc[lambda s: s > 0]
    print(f"rows between a record and its duplicate: median {lag.median():.0f}, max {lag.max()}")

    if n_keys:
        print("\nconflicting keys (UTC):")
        for hub, g in conflict.groupby("hub_id"):
            t = g["timestamp_utc"]
            print(f"  {hub}: {t.min()} -> {t.max()}, {t.nunique()} keys")
        differ = conflict.groupby(KEY)[value_cols].nunique(dropna=False).gt(1)
        print(
            f"columns that disagree per key: {differ.sum(axis=1).mean():.1f} of {len(value_cols)}"
        )


def missing(raw: pd.DataFrame, value_cols: list[str], cfg: config.Config) -> None:
    section("2. Missing values per column (blank in the raw file)")
    out = raw[value_cols].isna().groupby(raw["hub_id"]).sum()
    out["total"] = out.sum(axis=1)
    print(out.to_string())
    blanks = raw[value_cols].isna().sum(axis=1)
    print(f"\nrecords with a blank: {(blanks > 0).sum()} | blanks per such record: "
          f"{blanks[blanks > 0].value_counts().to_dict()}")  # fmt: skip
    month = raw["timestamp_utc"].dt.tz_convert(cfg.tz).dt.strftime("%Y-%m")
    print("\nirradiance blanks per hub and month:")
    print(raw["irradiance_wm2"].isna().groupby([raw["hub_id"], month]).sum().unstack().to_string())


def sentinels(
    raw: pd.DataFrame,
    value_cols: list[str],
    is_sentinel: pd.DataFrame,
    cfg: config.Config,
    hubs: pd.DataFrame,
) -> None:
    section("3. Sentinel values")
    v = cfg.thresholds["validation"]
    rows = []
    for s, meaning in v["sentinel_values"].items():
        hit = (raw[value_cols] - float(s)).abs() <= v["sentinel_tolerance"]
        per_measure = by_measure(hit, raw["hub_id"]).sum()
        rows.append({"sentinel": s, "meaning": meaning, **per_measure.to_dict()})
    print(pd.DataFrame(rows).set_index("sentinel").to_string())
    print("\nper hub and measure:")
    print(by_measure(is_sentinel, raw["hub_id"]).to_string())

    print("\nsentinels that are also a valid reading for some measure:")
    row_of = raw["hub_id"].map(hubs["row"])
    for s in v["sentinel_values"]:
        for m, (lo, hi) in v["valid_ranges"].items():
            if not lo <= float(s) <= hi:
                continue
            cols = [c for c in value_cols if measure_of(c) == m]
            hits = ((raw[cols] - float(s)).abs() <= v["sentinel_tolerance"]).any(axis=1)
            line = f"  {s} is inside {m} [{lo}, {hi}]: {hits.sum()} records"
            if hits.any() and m in HUB_MEASURES:
                row_median = raw[m].groupby([row_of, raw["timestamp_utc"]]).transform("median")
                ratio = (raw.loc[hits, m] / row_median[hits]).describe()
                line += f", value / row median: min {ratio['min']:.2f}, median {ratio['50%']:.2f}"
            print(line)


def out_of_range(
    raw: pd.DataFrame, value_cols: list[str], is_sentinel: pd.DataFrame, cfg: config.Config
) -> None:
    section("4. Out-of-range values (sentinels excluded)")
    ranges = cfg.thresholds["validation"]["valid_ranges"]
    rows, oor = [], {}
    for c in value_cols:
        lo, hi = ranges[measure_of(c)]
        x = raw[c].mask(is_sentinel[c])
        low, high = x < lo, x > hi
        oor[c] = low | high
        rows.append(
            {
                "column": c,
                "valid": f"[{lo}, {hi}]",
                "below": int(low.sum()),
                "above": int(high.sum()),
                "values_below": _top(x[low]),
                "values_above": _top(x[high]),
            }
        )
    print(pd.DataFrame(rows).set_index("column").to_string())
    print("\nper hub and measure:")
    print(by_measure(pd.DataFrame(oor), raw["hub_id"]).to_string())
    hour = raw["timestamp_utc"].dt.tz_convert(cfg.tz).dt.hour
    below = pd.DataFrame(
        {c: raw[c].mask(is_sentinel[c]) < ranges[measure_of(c)][0] for c in value_cols}
    ).any(axis=1)
    night = below & ((hour < 6) | (hour >= 20))
    print(f"\nrecords with a below-range value: {below.sum()}, of which 20:00-06:00: {night.sum()}")
    zero_floor = [c for c in value_cols if ranges[measure_of(c)][0] == 0]
    x = raw[zero_floor]
    print(f"negative value closest to 0 (measures with a floor of 0): {x[x < 0].max().max()}")


def _top(s: pd.Series, n: int = 4) -> str:
    return ", ".join(f"{k}×{v}" for k, v in s.round(2).value_counts().head(n).items())


def gaps(raw: pd.DataFrame, cfg: config.Config, hubs: pd.DataFrame) -> None:
    section("5. Missing intervals and outages (UTC grid)")
    step = pd.Timedelta(minutes=cfg.interval_min)
    first = raw["timestamp_utc"].min().tz_convert(cfg.tz).normalize()
    last = (raw["timestamp_utc"].max().tz_convert(cfg.tz) + step).normalize()
    grid = pd.date_range(first, last, freq=step, inclusive="left").tz_convert("UTC")
    print(f"grid: {grid[0]} -> {grid[-1]}, {len(grid)} intervals per hub")
    per_day = pd.Series(grid.tz_convert(cfg.tz).date).value_counts()
    print(f"local days without 96 intervals: {per_day[per_day != 96].sort_index().to_dict()}")

    found = []
    for hub in hubs.index:
        present = raw.loc[raw["hub_id"] == hub, "timestamp_utc"]
        absent = pd.Series(~grid.isin(present), index=grid)
        for idx in runs(absent):
            found.append({"hub_id": hub, "start_utc": idx[0], "end_utc": idx[-1] + step,
                          "n_intervals": len(idx)})  # fmt: skip
    found = pd.DataFrame(found)
    min_outage = cfg.thresholds["quality"]["comm_outage_min_intervals"]
    summary = found.groupby("hub_id").agg(
        missing_intervals=("n_intervals", "sum"),
        gaps=("n_intervals", "size"),
        longest=("n_intervals", "max"),
        outages=("n_intervals", lambda n: int((n >= min_outage).sum())),
    )
    summary = summary.reindex(hubs.index, fill_value=0)
    summary["missing_pct"] = (100 * summary["missing_intervals"] / len(grid)).round(2)
    print(summary.to_string())
    print(f"\ngap lengths: {found['n_intervals'].value_counts().sort_index().to_dict()}")
    print(f"gaps that start at the same time on 3+ hubs: "
          f"{(found.groupby('start_utc')['hub_id'].nunique() >= 3).sum()}")  # fmt: skip

    long = found[found["n_intervals"] >= min_outage].copy()
    long["start_local"] = long["start_utc"].dt.tz_convert(cfg.tz)
    long["end_local"] = long["end_utc"].dt.tz_convert(cfg.tz)
    long["hours"] = long["n_intervals"] * cfg.interval_min / 60
    print(f"\ngaps of >= {min_outage} intervals (end exclusive):")
    print(
        long[["hub_id", "start_local", "end_local", "n_intervals", "hours"]].to_string(index=False)
    )


def rough_clean(
    raw: pd.DataFrame,
    value_cols: list[str],
    is_sentinel: pd.DataFrame,
    cfg: config.Config,
    hubs: pd.DataFrame,
) -> pd.DataFrame:
    """Hub-level signals with duplicates, conflicts, sentinels and out-of-range values removed."""
    ranges = cfg.thresholds["validation"]["valid_ranges"]
    d = raw.copy()
    for c in value_cols:
        lo, hi = ranges[measure_of(c)]
        d[c] = d[c].mask(is_sentinel[c] | ~d[c].between(lo, hi))
    d = d.drop_duplicates().drop_duplicates(KEY, keep=False)
    d["row"] = d["hub_id"].map(hubs["row"])
    d["local"] = d["timestamp_utc"].dt.tz_convert(cfg.tz)
    d["local_date"] = d["local"].dt.date
    for m in HUB_MEASURES:
        d[f"{m}_peer"] = leave_one_out_median(d, m)
    return d.sort_values(["hub_id", "timestamp_utc"]).reset_index(drop=True)


def leave_one_out_median(d: pd.DataFrame, measure: str) -> pd.Series:
    """Median of the other hubs in the same row at the same timestamp."""
    wide = d.pivot_table(index="timestamp_utc", columns="hub_id", values=measure)
    peer = {}
    for _, g in d.groupby("row"):
        members = sorted(g["hub_id"].unique())
        for hub in members:
            others = [h for h in members if h != hub and h in wide]
            peer[hub] = wide[others].median(axis=1)
    peer = pd.DataFrame(peer).stack().rename("peer")
    return d.join(peer, on=["timestamp_utc", "hub_id"])["peer"]


def clock_offsets(d: pd.DataFrame, cfg: config.Config) -> None:
    section("6. Clock offsets: irradiance-weighted midday, hub vs. the rest of its row")
    minute = d["timestamp_utc"].dt.hour * 60 + d["timestamp_utc"].dt.minute
    middays = {}
    for col in ["irradiance_wm2", "irradiance_wm2_peer"]:
        w = d[col].where(d[col] > 0)
        s = pd.DataFrame({"w": w, "wm": w * minute}).groupby([d["hub_id"], d["local_date"]]).sum()
        middays[col] = (s["wm"] / s["w"]).where(s["w"] > 2000)
    offset = (middays["irradiance_wm2"] - middays["irradiance_wm2_peer"]).dropna().round()
    big = offset[offset.abs() >= cfg.interval_min]
    print(f"hub-days with |offset| >= {cfg.interval_min} min: {len(big)}")
    for hub, o in big.groupby(level="hub_id"):
        days = pd.Series(pd.to_datetime(o.index.get_level_values("local_date")))
        streak = (days.diff().dt.days != 1).cumsum()
        for _, r in o.groupby(streak.to_numpy()):
            dates = r.index.get_level_values("local_date")
            print(f"  {hub}: {dates[0]} -> {dates[-1]} ({len(r)} days), "
                  f"offset median {r.median():+.0f} min")  # fmt: skip


def stuck(d: pd.DataFrame, cfg: config.Config) -> None:
    q = cfg.thresholds["quality"]["stuck"]
    section(f"7a. Stuck sensors: runs of >= {q['min_intervals']} intervals at one value")
    found = []
    cols = HUB_MEASURES + [c for c in d.columns if c.startswith(SLOTS)]
    for hub, g in d.groupby("hub_id"):
        for c in cols:
            x = g[c]
            same = x.eq(x.shift()) & x.abs().gt(0.05)
            for idx in runs(same):
                if len(idx) + 1 >= q["min_intervals"]:
                    found.append(
                        {"hub_id": hub, "column": c, "value": x[idx[0]], "n": len(idx) + 1}
                    )
    found = pd.DataFrame(found)
    if found.empty:
        print("none")
    else:
        agg = found.groupby(["hub_id", "column", "value"])["n"].agg(["size", "max", "sum"])
        print(
            agg.rename(columns={"size": "runs", "max": "longest", "sum": "intervals"}).to_string()
        )

    tol = 1.0
    print(f"\nhumidity within {tol} of a stuck value {q['humidity_stuck_values']}:")
    for v in q["humidity_stuck_values"]:
        for hub, g in d.groupby("hub_id"):
            near = g["humidity_pct"].sub(v).abs().le(tol)
            longest = max((len(i) for i in runs(near)), default=0)
            if longest >= q["min_intervals"]:
                daily = near.groupby(g["local_date"]).mean()
                start = daily[daily.ge(0.9)].index.min()
                share = daily[daily.index >= start].ge(0.9).mean()
                print(f"  {hub}: longest run {longest}; >=90% of the day near {v} from {start} "
                      f"on {share:.0%} of the days after")  # fmt: skip
            else:
                print(f"  {hub}: longest run {longest}")


def drift(d: pd.DataFrame, cfg: config.Config) -> None:
    q = cfg.thresholds["quality"]["drift"]
    section(f"7b. Drift: hub irradiance / median of the rest of its row (peer >= "
            f"{q['min_irradiance_wm2']} W/m²)")  # fmt: skip
    sun = d[d["irradiance_wm2_peer"] >= q["min_irradiance_wm2"]].copy()
    sun["ratio"] = sun["irradiance_wm2"] / sun["irradiance_wm2_peer"]
    sun["month"] = sun["local"].dt.strftime("%Y-%m")
    print(sun.pivot_table(index="hub_id", columns="month", values="ratio", aggfunc="median")
          .round(3).to_string())  # fmt: skip

    daily = sun.groupby(["hub_id", "local_date"])["ratio"].median()
    print(f"\nruns of >= {q['min_days']} daylight days outside 1 ± {q['ratio_tolerance']}, "
          "with the change point found by a flat-then-linear fit:")  # fmt: skip
    for hub, r in daily.groupby(level="hub_id"):
        r = r.droplevel("hub_id")
        off = pd.Series((r - 1).abs().gt(q["ratio_tolerance"]).to_numpy(), index=r.index)
        for idx in runs(off):
            if len(idx) < q["min_days"]:
                continue
            line = f"  {hub}: outside from {idx[0]} to {idx[-1]} ({len(idx)} days)"
            line += f", median ratio {r[idx].median():.3f}"
            history = r[r.index <= idx[-1]]
            if len(history) >= 30:
                line += f", change point {change_point(history)}"
            print(line)

    section("7c. Humidity: hub minus median of the rest of its row (percentage points)")
    d = d.assign(
        diff=d["humidity_pct"] - d["humidity_pct_peer"], month=d["local"].dt.strftime("%Y-%m")
    )
    print(d.pivot_table(index="hub_id", columns="month", values="diff", aggfunc="median")
          .round(1).to_string())  # fmt: skip


def change_point(ratio: pd.Series) -> object:
    """Day that best splits the series into flat-at-baseline, then a straight line."""
    y = ratio.to_numpy()
    x = np.arange(len(y))
    best, best_sse = None, np.inf
    for k in range(10, len(y) - 5):
        base = y[:k].mean()
        slope, icpt = np.polyfit(x[k:], y[k:] - base, 1)
        fit = np.concatenate([np.full(k, base), base + icpt + slope * x[k:]])
        sse = ((y - fit) ** 2).sum()
        if sse < best_sse:
            best, best_sse = ratio.index[k], sse
    return best


if __name__ == "__main__":
    main()
