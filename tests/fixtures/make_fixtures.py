"""Regenerate the raw + loaded fixture dataset. Run: uv run python tests/fixtures/make_fixtures.py

2 hubs x 3 local days (2025-11-01..03, incl. the DST fall-back day) with every edge case
listed in tests/fixtures/README.md. The loaded file is built here with the stdlib, NOT with
solarscope.load, so test_load compares two independent implementations.
"""

import copy
import csv
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
RAW, LOADED = HERE / "raw", HERE / "loaded"
REAL_SITE = HERE.parent.parent / "input" / "mvp1" / "site.json"
TZ = ZoneInfo("America/New_York")
START = datetime(2025, 11, 1, 4, tzinfo=UTC)  # 2025-11-01 00:00 EDT
END = datetime(2025, 11, 4, 5, tzinfo=UTC)  # 2025-11-04 00:00 EST
STEP = timedelta(minutes=15)
HUBS = {"H01": ["P01", "P02", "P03"], "H02": ["P04", "P05", "P06"]}
SLOTS = ["p1", "p2", "p3"]
COLS = ["timestamp_utc", "hub_id", "irradiance_wm2", "humidity_pct"] + [
    f"{s}_{m}" for s in SLOTS for m in ("voltage_v", "current_a", "temp_c")
]


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def clean_record(t: datetime, hub: str) -> dict:
    solar_h = t.hour + t.minute / 60 - 5  # sun time, no DST jump
    g = max(0.0, 700 * math.sin(math.pi * (solar_h - 7) / 10)) if 7 < solar_h < 17 else 0.0
    rec = {
        "timestamp_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hub_id": hub,
        "irradiance_wm2": round(g, 1),
        "humidity_pct": 70.0 if hub == "H01" else 72.0,
    }
    for i, slot in enumerate(SLOTS):
        temp = round(8 + g / 40 + i * 0.1, 1)
        rec[f"{slot}_voltage_v"] = round(37.1 * (1 - 0.0027 * (temp - 25)), 2) if g else 0.0
        rec[f"{slot}_current_a"] = round(10.78 * g / 1000 * (1 - 0.01 * i), 3)
        rec[f"{slot}_temp_c"] = temp
    return rec


def build_raw_records() -> list[dict]:
    records, t, n = [], START, 0
    while t < END:
        hubs = ["H01", "H02"] if n % 2 == 0 else ["H02", "H01"]  # received order, not sorted
        records += [clean_record(t, h) for h in hubs]
        t, n = t + STEP, n + 1

    def find(stamp: str, hub: str) -> dict:
        return next(r for r in records if r["timestamp_utc"] == stamp and r["hub_id"] == hub)

    # edge cases (see README.md)
    records.append(dict(find("2025-11-01T16:00:00Z", "H01")))  # exact duplicate
    conflict = dict(find("2025-11-01T17:00:00Z", "H02"))
    conflict["p2_current_a"] = 2.0  # conflicting duplicate
    records.append(conflict)
    find("2025-11-03T17:00:00Z", "H01")["p1_temp_c"] = -40.0  # sentinel (thermistor open)
    find("2025-11-03T18:00:00Z", "H02")["p3_current_a"] = 655.35  # sentinel (ADC overflow)
    find("2025-11-01T18:00:00Z", "H02")["humidity_pct"] = 104.5  # out of range
    find("2025-11-03T18:00:00Z", "H01")["p2_voltage_v"] = 52.3  # out of range
    find("2025-11-01T19:00:00Z", "H01")["p3_voltage_v"] = None  # missing
    find("2025-11-03T15:00:00Z", "H02")["irradiance_wm2"] = None  # missing
    gap = {f"2025-11-03T19:{m:02d}:00Z" for m in (0, 15, 30, 45)}  # H02 offline 1 h
    return [r for r in records if not (r["hub_id"] == "H02" and r["timestamp_utc"] in gap)]


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, header, lineterminator="\n")
        w.writeheader()
        w.writerows({k: "" if v is None else v for k, v in r.items()} for r in rows)


def build_site() -> dict:
    site = copy.deepcopy(json.loads(REAL_SITE.read_text()))
    site.update(site_id="SS-FIXTURE-001", site_name="Fixture: 2 hubs, 1 row",
                monitoring_start="2025-11-01")  # fmt: skip
    site["array_geometry"].update(rows=1, panels_per_row=6, row_notes={})
    panels = [p for ps in HUBS.values() for p in ps]
    site["electrical"]["strings"] = [
        {"string_id": "S1", "row": "R1", "fuse_a": 15, "panels": panels}
    ]
    site["module"]["count"] = 6
    site["hubs"] = [h for h in site["hubs"] if h["hub_id"] in HUBS]
    site["panels"] = [p for p in site["panels"] if p["hub_id"] in HUBS]
    return site


def main() -> None:
    RAW.mkdir(exist_ok=True)
    LOADED.mkdir(exist_ok=True)
    records = build_raw_records()
    write_csv(RAW / "readings.csv", COLS, records)

    site = build_site()
    (RAW / "site.json").write_text(json.dumps(site, indent=2) + "\n")

    weather_cols = ["STATION", "NAME", "DATE", "AWND", "PRCP", "SNOW", "SNWD", "TAVG",
                    "TMAX", "TMIN", "ACSH", "WT01", "WT03", "WT18"]  # fmt: skip
    stn = {"STATION": "USW00014733", "NAME": "BUFFALO NIAGARA INTERNATIONAL, NY US"}
    write_csv(RAW / "weather.csv", weather_cols, [
        {**stn, "DATE": "2025-11-01", "AWND": 8.1, "PRCP": 0.0, "SNOW": 0.0, "SNWD": 0.0,
         "TAVG": 48, "TMAX": 55, "TMIN": 41, "ACSH": 20},
        {**stn, "DATE": "2025-11-02", "AWND": 12.4, "PRCP": 0.31, "SNOW": 0.0, "SNWD": 0.0,
         "TAVG": 45, "TMAX": 50, "TMIN": 39, "ACSH": 95, "WT01": 1},
        {**stn, "DATE": "2025-11-03", "AWND": 6.0, "PRCP": 0.0, "SNOW": 0.0, "SNWD": 0.0,
         "TAVG": 44, "TMAX": 52, "TMIN": 37, "ACSH": 35},
    ])  # fmt: skip

    svc_cols = ["ticket_id", "visit_date", "arrival_time_local", "trigger", "hub_ids",
                "panel_ids", "reported_issue", "finding", "action_taken", "fault_found",
                "root_cause", "category", "tech_hours", "parts_cost_usd", "parts_used",
                "truck_roll_cost_usd"]  # fmt: skip
    write_csv(RAW / "service_log.csv", svc_cols, [
        {"ticket_id": "SR-9001", "visit_date": "2025-11-02", "arrival_time_local": "10:00",
         "trigger": "customer_call", "hub_ids": "ALL", "panel_ids": "ALL",
         "reported_issue": "Output low today", "finding": "No fault found. Overcast and rain",
         "action_taken": "None", "fault_found": "N", "root_cause": "overcast weather",
         "category": "weather", "tech_hours": 1.0, "parts_cost_usd": 0, "parts_used": "",
         "truck_roll_cost_usd": 350},
        {"ticket_id": "SR-9002", "visit_date": "2025-11-03", "arrival_time_local": "13:30",
         "trigger": "monitoring_alert", "hub_ids": "H02", "panel_ids": "P05",
         "reported_issue": "P05 intermittent zero output", "finding": "Loose MC4 connector",
         "action_taken": "Reseated connector", "fault_found": "Y",
         "root_cause": "loose connector", "category": "wiring", "tech_hours": 1.5,
         "parts_cost_usd": 12, "parts_used": "strain relief clip", "truck_roll_cost_usd": 350},
    ])  # fmt: skip

    # loaded: long format per docs/contracts.md §2, built independently of solarscope.load
    slot_map = {(h["hub_id"], s): p for h in site["hubs"] for s, p in h["panels"].items()}
    panel_info = {p["panel_id"]: p for p in site["panels"]}
    long = []
    for raw_row, r in enumerate(records):
        t = ts(r["timestamp_utc"])
        local = t.astimezone(TZ)
        for slot in SLOTS:
            pid = slot_map[(r["hub_id"], slot)]
            long.append({
                "raw_row": raw_row, "timestamp_utc": t.isoformat(),
                "timestamp_local": local.isoformat(), "local_date": local.date().isoformat(),
                "hub_id": r["hub_id"], "row": panel_info[pid]["row"],
                "string_id": panel_info[pid]["string_id"], "panel_id": pid, "slot": slot,
                "irradiance_wm2": r["irradiance_wm2"], "humidity_pct": r["humidity_pct"],
                "voltage_v": r[f"{slot}_voltage_v"], "current_a": r[f"{slot}_current_a"],
                "temp_c": r[f"{slot}_temp_c"],
            })  # fmt: skip
    long.sort(key=lambda x: (x["timestamp_utc"], x["hub_id"], x["raw_row"], x["slot"]))
    write_csv(LOADED / "readings.csv", list(long[0]), long)


if __name__ == "__main__":
    main()
