"""The 5 official result files: column schemas and atomic writes. See docs/contracts.md §9."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd

SCHEMAS: dict[str, list[str]] = {
    "data_quality": [
        "window", "window_start", "window_end", "hub_id", "row",
        "expected_intervals", "received_records", "usable_pct",
        "n_duplicate", "n_conflict", "n_missing", "n_sentinel", "n_out_of_range",
        "n_gap_intervals", "n_sensor_excluded_intervals", "excluded_periods", "reasons",
    ],
    "panel_daily": [
        "date", "panel_id", "hub_id", "row", "string_id", "n_intervals_used",
        "measured_kwh", "expected_kwh", "loss_kwh", "peer_ratio", "irradiance_source",
        "rolling_peer_ratio", "decline_slope_pct_per_month", "decline_flag", "daily_label",
    ],
    "events": [
        "event_id", "label", "cause", "scope", "hub_ids", "panel_ids",
        "start_local", "end_local", "duration_h", "kwh_lost", "status", "evidence",
        "first_flag_date", "decline_rate_pct_per_month", "current_deficit_pct",
        "projected_10pct_date",
    ],
    "dispatch": [
        "window", "dispatch_id", "priority", "panel_id", "hub_id", "row", "event_id",
        "cause", "evidence", "kwh_lost", "first_seen_local", "recommended_action",
    ],
}  # fmt: skip
SUMMARY_KEYS = [
    "schema_version", "run_id", "generated_at_utc", "site_id", "config_hash", "config",
    "input_checksums", "files", "windows",
]  # fmt: skip


def _atomic_write(path: Path, text: str) -> None:
    """Write to a temp file in the same folder, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _to_file_value(col: pd.Series) -> pd.Series:
    if isinstance(col.dtype, pd.DatetimeTZDtype):
        return col.map(lambda t: "" if pd.isna(t) else t.isoformat())
    if pd.api.types.is_datetime64_dtype(col):
        return col.dt.strftime("%Y-%m-%d")
    if col.map(lambda v: isinstance(v, list)).any():
        return col.map(lambda v: ";".join(map(str, v)) if isinstance(v, list) else v)
    return col


def write_csv(df: pd.DataFrame, name: str, out_dir: Path | str) -> Path:
    expected = SCHEMAS[name]
    if list(df.columns) != expected:
        raise ValueError(
            f"{name}.csv columns do not match the contract.\n"
            f"  expected: {expected}\n  got:      {list(df.columns)}"
        )
    path = Path(out_dir) / f"{name}.csv"
    _atomic_write(path, df.apply(_to_file_value).to_csv(index=False))
    return path


def write_summary(summary: dict, out_dir: Path | str) -> Path:
    missing = [k for k in SUMMARY_KEYS if k not in summary]
    if missing:
        raise ValueError(f"summary.json is missing keys: {missing}")
    path = Path(out_dir) / "summary.json"
    _atomic_write(path, json.dumps(summary, indent=2, default=str))
    return path


def write_all(out_dir: Path | str, *, summary: dict, **frames: pd.DataFrame) -> list[Path]:
    """Write the 4 CSVs and summary.json. Every frame must be present."""
    if set(frames) != set(SCHEMAS):
        raise ValueError(f"need exactly {sorted(SCHEMAS)}, got {sorted(frames)}")
    paths = [write_csv(df, name, out_dir) for name, df in frames.items()]
    return [*paths, write_summary(summary, out_dir)]
