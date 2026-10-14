"""Run Stage 2-3 on one input folder and report metrics for comparing DQ branches.

    uv run scripts/dq_eval.py --input <folder> [--truth <injected_faults.json>] [--out m.json]

L2 metrics (any input): reasons, clock offsets, sensor periods, gaps, usable %, and two
proxies until expected.py exists (physics loss with irradiance_used_wm2, and daylight
panel-intervals below 0.85 of the row's median panel power).
L3 metrics (with --truth from scripts/inject_faults.py): planted faults found, start
and end error, false alarms, sentinel cases right. Never reads the answer key.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from solarscope import clean, config, load, quality  # noqa: E402

ABNORMAL = 0.85  # classify.abnormal_peer_ratio, used here only as a yardstick


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def local_date(t, tz: str) -> str | None:
    return None if pd.isna(t) else t.tz_convert(tz).date().isoformat()


def proxies(qual, inputs, windows, cfg) -> dict:
    c = qual.canonical
    mod = inputs.site["module"]
    gamma = mod["temp_coefficients"]["pmax_pct_per_c"] / 100
    lit_min = cfg.thresholds["expected"]["min_irradiance_wm2"]
    ok = quality.is_usable(c) & c["irradiance_used_wm2"].ge(lit_min)
    d = c.loc[ok].copy()
    d["power"] = d["voltage_v"] * d["current_a"]
    d["expected"] = (
        mod["stc_rating_w"] * d["irradiance_used_wm2"] / 1000 * (1 + gamma * (d["temp_c"] - 25))
    )
    kwh = cfg.interval_min / 60 / 1000
    daily = d.groupby(["local_date", "hub_id", "panel_id"])[["power", "expected"]].sum() * kwh
    daily["loss"] = (daily["expected"] - daily["power"]).clip(lower=0)
    daily = daily.reset_index()

    lit = d[d["irradiance_used_wm2"] >= 200]
    row_med = lit.groupby(["timestamp_utc", "row"])["power"].transform("median")
    lit = lit.assign(abnormal=(lit["power"] / row_med) < ABNORMAL)
    month = lit["timestamp_local"].dt.strftime("%Y-%m")

    out = {"abnormal_by_hub_month": {}}
    for h, g in lit.groupby("hub_id"):
        out["abnormal_by_hub_month"][h] = g.groupby(month[g.index])["abnormal"].sum().to_dict()
    for w in windows:
        lo, hi = pd.Timestamp(w.start), pd.Timestamp(w.end)
        dw = daily[daily["local_date"].between(lo, hi)]
        lw = lit[lit["local_date"].between(lo, hi)]
        out[w.name] = {
            "loss_kwh": round(float(dw["loss"].sum()), 1),
            "loss_kwh_by_hub": dw.groupby("hub_id")["loss"].sum().round(1).to_dict(),
            "abnormal_by_hub": lw.groupby("hub_id")["abnormal"].sum().astype(int).to_dict(),
        }
    return out


def l2(cleaned, qual, inputs, windows, cfg) -> dict:
    tz = cfg.tz
    c, f = qual.canonical, cleaned.flags
    rec = f.drop_duplicates("raw_row")
    dq = qual.data_quality
    return {
        "reasons": {m: c[f"{m}_reason"].value_counts().to_dict() for m in [*clean.MEASURES]},
        "n_duplicate_records": int(rec["is_duplicate"].sum()),
        "n_conflict_records": int(rec["is_conflict"].sum()),
        "n_gaps": len(cleaned.gaps),
        "n_gap_intervals": int(cleaned.gaps["n_intervals"].sum()),
        "n_comm_outages": len(qual.comm_outages),
        "clock_offsets": [
            {
                "hub_id": o.hub_id,
                "start": local_date(o.start_utc, tz),
                "end": local_date(o.end_utc, tz),
                "offset_min": int(o.offset_min),
                "n_records": int(o.n_records),
            }  # fmt: skip
            for o in cleaned.clock_offsets.itertuples()
        ],
        "sensor_periods": [
            {
                "hub_id": p.hub_id,
                "sensor": p.sensor,
                "kind": p.kind,
                "start": local_date(p.start_utc, tz),
                "end": local_date(p.end_utc, tz),
                "evidence": p.evidence,
            }  # fmt: skip
            for p in qual.sensor_periods.itertuples()
        ],
        "irradiance_source": c["irradiance_source"].value_counts().to_dict(),
        "usable_pct": {
            w: {
                "mean": round(float(g["usable_pct"].mean()), 2),
                "min": round(float(g["usable_pct"].min()), 2),
            }  # fmt: skip
            for w, g in dq.groupby("window")
        },
        "proxies": proxies(qual, inputs, windows, cfg),
    }


def l3(truth: dict, cleaned, qual, cfg) -> dict:
    tz = cfg.tz
    periods = qual.sensor_periods
    offsets = cleaned.clock_offsets
    results, matched_p, matched_o = [], set(), set()

    def day(s):
        return None if s is None else pd.Timestamp(s).tz_localize(tz).tz_convert("UTC")

    for fault in truth["faults"]:
        start, end = day(fault["start_local"]), day(fault["end_local"])
        r = {"id": fault["id"], "kind": fault["kind"], "hub_id": fault["hub_id"],
             "sensor": fault["sensor"], "found": False}  # fmt: skip
        if fault["kind"] == "clock_offset":
            hit = offsets[(offsets.hub_id == fault["hub_id"])]
            hit = hit[hit.offset_min == fault["offset_min"]]
            idx = list(hit.index)
            matched_o |= set(idx)
        else:
            hit = periods[(periods.hub_id == fault["hub_id"]) & (periods.sensor == fault["sensor"])]
            far = pd.Timestamp.max.tz_localize("UTC")
            overlap = hit.start_utc.lt(end or far) & hit.end_utc.fillna(far).gt(start)
            hit = hit[overlap]
            matched_p |= set(hit.index)
        if len(hit):
            first = hit.sort_values("start_utc").iloc[0]
            last_end = hit["end_utc"].max() if hit["end_utc"].notna().all() else pd.NaT
            err = (first.start_utc - start).total_seconds() / 86400
            r.update(found=True, found_kind=first.get("kind", "clock_offset"))
            r["start_err_days"] = round(err, 2)
            if end is None and pd.isna(last_end):
                r["end_err_days"] = 0.0
            elif end is None or pd.isna(last_end):
                r["end_err_days"] = None
                r["end_note"] = "still open" if pd.isna(last_end) else "closed early"
            else:
                r["end_err_days"] = round((last_end - end).total_seconds() / 86400, 2)
        results.append(r)

    known = {(k["hub_id"], k["sensor"], k["kind"]) for k in truth["known_real"]}
    false_alarms = []
    for i, p in periods.iterrows():
        if i not in matched_p and (p.hub_id, p.sensor, p.kind) not in known:
            false_alarms.append(f"{p.hub_id} {p.sensor} {p.kind} {local_date(p.start_utc, tz)}")
    for i, o in offsets.iterrows():
        if i not in matched_o and (o.hub_id, None, "clock_offset") not in known:
            false_alarms.append(f"{o.hub_id} clock {o.offset_min:+d} {local_date(o.start_utc, tz)}")

    f = cleaned.flags.set_index(["raw_row", "slot"])
    cases = []
    for case in truth["value_cases"]:
        got = f.loc[(case["raw_row"], case["slot"]), f"{case['measure']}_flag"]
        cases.append({**case, "got": got, "ok": got == case["want"]})
    by_id = pd.DataFrame(cases).groupby("id")["ok"].agg(["sum", "size"])
    return {
        "faults": results,
        "n_found": sum(r["found"] for r in results),
        "n_faults": len(results),
        "false_alarms": false_alarms,
        "value_cases": {k: f"{int(v['sum'])}/{int(v['size'])}" for k, v in by_id.iterrows()},
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--truth", type=Path)
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    cfg = config.load_config(None, args.input / "site.json")
    inputs = load.load_inputs(args.input, cfg)
    windows = config.derive_windows(inputs.readings, cfg)
    t0 = time.time()
    cleaned = clean.clean(inputs, cfg)
    qual = quality.assess(cleaned, inputs, windows, cfg)
    seconds = round(time.time() - t0, 1)

    report = {
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "input": args.input.name,
        "config_hash": cfg.hash[:12],
        "seconds": seconds,
        "l2": l2(cleaned, qual, inputs, windows, cfg),
    }
    if args.truth:
        report["l3"] = l3(json.loads(args.truth.read_text()), cleaned, qual, cfg)
    text = json.dumps(report, indent=1, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
