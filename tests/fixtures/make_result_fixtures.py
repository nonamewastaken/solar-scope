"""Write tests/fixtures/results/: one folder that looks like a real run's output.

Run from the repo root after make_fixtures.py:
    PYTHONPATH=. uv run python tests/fixtures/make_result_fixtures.py

These are FORMAT and CONSISTENCY fixtures. They follow docs/contracts.md section 9 column for
column and agree with each other (see tests/test_result_fixtures.py), but they are not derived
from the fixture readings. Do not edit the output by hand.
"""

from pathlib import Path

import pandas as pd

from solarscope import config, load, results

FIX = Path(__file__).parent
RAW = FIX / "raw"
OUT = FIX / "results"
DAYS = ["2025-11-01", "2025-11-02", "2025-11-03"]
EXPECTED_KWH = dict(
    zip(DAYS, [1.20, 0.40, 1.15], strict=True)
)  # per panel and day: clear, overcast, clear
LABELS = ["fault", "weather", "sensor_issue", "data_issue", "early_warning", "unresolved"]

# (panel, date) -> (loss_kwh, daily_label). Anything missing is a normal day with no loss.
LOSS = {
    ("P05", DAYS[0]): (0.18, "fault"),
    ("P06", DAYS[0]): (0.05, "unresolved"),
    **{(p, DAYS[1]): (0.08, "weather") for p in ["P01", "P02", "P03", "P04", "P06"]},
    ("P05", DAYS[1]): (0.10, "weather"),  # wiring fault also costs P05 here, weather costs more
    ("P02", DAYS[2]): (0.35, "fault"),
    ("P03", DAYS[2]): (0.05, "early_warning"),
    ("P04", DAYS[2]): (0.02, "data_issue"),
    ("P05", DAYS[2]): (0.06, "fault"),
    ("P06", DAYS[2]): (0.02, "data_issue"),
}  # fmt: skip


def panel_daily(panels: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for d in DAYS:
        for p in panels.itertuples():
            loss, label = LOSS.get((p.panel_id, d), (0.0, "normal"))
            exp = EXPECTED_KWH[d]
            decline = p.panel_id == "P03" and d != DAYS[0]
            rows.append({
                "date": d, "panel_id": p.panel_id, "hub_id": p.hub_id, "row": p.row,
                "string_id": p.string_id, "n_intervals_used": 44 if d != DAYS[1] else 40,
                "measured_kwh": round(exp - loss, 3), "expected_kwh": exp, "loss_kwh": loss,
                "peer_ratio": round(1 - loss / exp, 3), "irradiance_source": "hub",
                "rolling_peer_ratio": 0.98 if decline else float("nan"),
                "decline_slope_pct_per_month": -1.5 if decline else float("nan"),
                "decline_flag": decline, "daily_label": label,
            })  # fmt: skip
    return pd.DataFrame(rows, columns=results.SCHEMAS["panel_daily"])


def events() -> pd.DataFrame:
    blank = {"first_flag_date": "", "decline_rate_pct_per_month": float("nan"),
             "current_deficit_pct": float("nan"), "projected_10pct_date": ""}  # fmt: skip
    rows = [
        ("E0001", "weather", "cloud", "array", "H01;H02", "P01;P02;P03;P04;P05;P06",
         "2025-11-02T00:00:00-04:00", "2025-11-03T00:00:00-05:00", 25.0, 0.50, "resolved",
         "Overcast (ACSH 95), irradiance low at both hubs, all panels low together", blank),
        ("E0002", "fault", "wiring", "panel", "H02", "P05",
         "2025-11-01T10:00:00-04:00", "2025-11-03T10:00:00-05:00", 49.0, 0.24, "resolved",
         "I drops to 0 for 15-60 min, 4-9 times a day, V normal, hub mates normal", blank),
        ("E0003", "fault", "hotspot", "panel", "H01", "P02",
         "2025-11-03T09:00:00-05:00", "2025-11-04T00:00:00-05:00", 15.0, 0.35, "active",
         "V -33% vs hub mates, I normal, T +8C", blank),
        ("E0004", "data_issue", "data_gap", "hub", "H02", "P04;P05;P06",
         "2025-11-03T14:00:00-05:00", "2025-11-03T15:00:00-05:00", 1.0, 0.04, "resolved",
         "No records for 4 intervals (19:00-20:00Z)", blank),
        ("E0005", "early_warning", "slow_decline", "panel", "H01", "P03",
         "2025-11-02T00:00:00-04:00", "2025-11-04T00:00:00-05:00", 49.0, 0.05, "active",
         "Peer ratio falling 1.5%/month, 4.0% behind hub mates",
         {"first_flag_date": "2025-11-02", "decline_rate_pct_per_month": -1.5,
          "current_deficit_pct": 4.0, "projected_10pct_date": "2026-03-01"}),
        ("E0006", "unresolved", "unknown", "panel", "H02", "P06",
         "2025-11-01T11:00:00-04:00", "2025-11-01T13:00:00-04:00", 2.0, 0.05, "resolved",
         "P06 2 h dip, V and I both about 15% low, no matching signature", blank),
    ]  # fmt: skip
    cols = results.SCHEMAS["events"][:12]
    return pd.DataFrame([dict(zip(cols, r[:12], strict=True)) | r[12] for r in rows],
                        columns=results.SCHEMAS["events"])  # fmt: skip


def dispatch(windows) -> pd.DataFrame:
    return pd.DataFrame([{
        "window": w.name, "dispatch_id": "D001", "priority": "high", "panel_id": "P02",
        "hub_id": "H01", "row": "R1", "event_id": "E0003", "cause": "hotspot",
        "evidence": "V -33% vs hub mates, I normal, T +8C", "kwh_lost": 0.35,
        "first_seen_local": "2025-11-03T09:00:00-05:00",
        "recommended_action": "Inspect module for a failed bypass diode; replace under warranty",
    } for w in windows], columns=results.SCHEMAS["dispatch"])  # fmt: skip


def data_quality(windows) -> pd.DataFrame:
    # Placeholder until dtri's tests/fixtures/quality/data_quality.csv lands.
    # Per-hub counts are the edge-case table in tests/fixtures/README.md.
    hubs = {
        "H01": dict(row="R1", received=293, usable=873, n_duplicate=1, n_conflict=0,
                    n_missing=1, n_sentinel=1, n_out_of_range=1, n_gap=0,
                    reasons="1 duplicate, 1 sentinel, 1 out of range, 1 missing"),
        "H02": dict(row="R1", received=289, usable=862, n_duplicate=0, n_conflict=2,
                    n_missing=1, n_sentinel=1, n_out_of_range=1, n_gap=4,
                    reasons="1 conflict (2 records), 1 sentinel, 1 out of range, 1 missing, "
                            "4 gap intervals"),
    }  # fmt: skip
    rows = []
    for w in windows:
        # 96 per day; the fall-back day (2025-11-02) adds 4 and the spring-forward day
        # (2025-03-09) removes 4, so the 365d window nets 35040 and 180d is 17284.
        n = w.days * 96 + 4 - (4 if str(w.start) <= "2025-03-09" else 0)
        for h, c in hubs.items():
            rows.append({
                "window": w.name, "window_start": str(w.start), "window_end": str(w.end),
                "hub_id": h, "row": c["row"], "expected_intervals": n,
                "received_records": c["received"],
                "usable_pct": round(100 * c["usable"] / (n * 3), 2),
                "n_duplicate": c["n_duplicate"], "n_conflict": c["n_conflict"],
                "n_missing": c["n_missing"], "n_sentinel": c["n_sentinel"],
                "n_out_of_range": c["n_out_of_range"], "n_gap_intervals": c["n_gap"],
                "n_sensor_excluded_intervals": 0,
                "excluded_periods": "", "reasons": c["reasons"],
            })  # fmt: skip
    return pd.DataFrame(rows, columns=results.SCHEMAS["data_quality"])


def summary(cfg, inputs, windows, pd_frame, ev) -> dict:
    abnormal = pd_frame[pd_frame.daily_label != "normal"]
    by_label = {k: round(float(v), 3) for k, v in
                abnormal.groupby("daily_label").loss_kwh.sum().items()}  # fmt: skip
    lost = {k: by_label.get(k, 0.0) for k in LABELS}
    top = ev.sort_values("kwh_lost", ascending=False).head(3)
    findings = [
        {"rank": i, "text": f"{r.label}/{r.cause} on {r.panel_ids.replace(';', ', ')}",
         "kwh_lost": r.kwh_lost, "event_id": r.event_id}
        for i, r in enumerate(top.itertuples(), 1)
    ]  # fmt: skip
    block = {
        "actual_kwh": round(float(pd_frame.measured_kwh.sum()), 3),
        "expected_kwh": round(float(pd_frame.expected_kwh.sum()), 3),
        "kwh_lost_total": round(sum(lost.values()), 3),
        "kwh_lost_by_label": lost,
        "events_by_label": {k: int((ev.label == k).sum()) for k in LABELS},
        "n_dispatches": 1, "n_dispatch_panels": 1, "n_early_warnings": 1,
        "top_findings": findings,
        "repeat_repairs": [{
            "panel_id": "P05", "hub_id": "H02", "n_repairs": 2,
            "ticket_ids": ["SR-9003", "SR-9002"], "visit_dates": ["2025-10-20", "2025-11-03"],
            "root_cause": "loose connector",
            "permanent_fix": "Replace both connector halves with a matched pair from one maker",
        }],
        "truck_rolls_avoided": {"count": 1, "cost_usd": 350.0, "ticket_ids": ["SR-9001"]},
        "service_visits": {"total": 3, "fault_found": 2, "no_fault": 1},
    }  # fmt: skip
    return {
        "schema_version": 1, "run_id": "20251104T000000Z-fixture",
        "generated_at_utc": "2025-11-04T00:00:00Z", "site_id": cfg.site["site_id"],
        "config_hash": cfg.hash, "config": cfg.thresholds,
        "input_checksums": inputs.checksums,
        "files": {n: f"{n}.csv" for n in results.SCHEMAS},
        "windows": {w.name: {"start": str(w.start), "end": str(w.end), "days": w.days, **block}
                    for w in windows},
    }  # fmt: skip


def main() -> None:
    cfg = config.load_config(None, RAW / "site.json")
    inputs = load.load_inputs(RAW, cfg)
    windows = config.derive_windows(inputs.readings, cfg)
    pdaily, ev = panel_daily(inputs.panels), events()
    results.write_all(
        OUT, panel_daily=pdaily, events=ev, dispatch=dispatch(windows),
        data_quality=data_quality(windows), summary=summary(cfg, inputs, windows, pdaily, ev),
    )  # fmt: skip
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
