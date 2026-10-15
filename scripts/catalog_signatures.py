"""Throwaway plots for SOL-14: a panel's V, I, T and P against its hub mates, with hub irradiance.

    PYTHONPATH=. uv run python scripts/catalog_signatures.py --panels P13,P14 \
        --start 2025-11-01 --end 2025-11-10 [--input input/mvp1]

Writes PNGs to output/signatures/ (git-ignored). Uses load.load_inputs only, no cleaning:
values outside the valid ranges, and sentinels on V, I and T, are set to NaN before plotting.
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from solarscope import config, load  # noqa: E402

MEASURES = [("voltage_v", "V"), ("current_a", "A"), ("temp_c", "C")]


def nan_invalid(readings: pd.DataFrame, cfg: config.Config) -> pd.DataFrame:
    v = cfg.thresholds["validation"]
    r = readings.copy()
    for col, (lo, hi) in v["valid_ranges"].items():
        if col in r:
            r.loc[~r[col].between(lo, hi), col] = float("nan")
    # 327.6 is also a real irradiance value (SOL-12), so sentinels only apply to panel measures
    for sentinel in v["sentinel_values"]:
        for col, _ in MEASURES:
            r.loc[(r[col] - float(sentinel)).abs() <= v["sentinel_tolerance"], col] = float("nan")
    return r.drop_duplicates(["timestamp_utc", "panel_id"])


def weather_text(weather: pd.DataFrame, start: str, end: str) -> str:
    w = weather[weather["date"].between(start, end)]
    return "  ".join(
        f"{r.date:%m-%d}: SNWD {r.SNWD:g} ACSH {r.ACSH:g} TMAX {r.TMAX:g} PRCP {r.PRCP:g}"
        for r in w.itertuples()
    )


def plot_panel(r: pd.DataFrame, panel: str, weather: pd.DataFrame, args, out: Path) -> Path:
    hub = r.loc[r["panel_id"] == panel, "hub_id"].iloc[0]
    mates = r[(r["hub_id"] == hub) & (r["panel_id"] != panel)]
    me = r[r["panel_id"] == panel].copy()
    me["power_w"], mates = (
        me["voltage_v"] * me["current_a"],
        mates.assign(power_w=mates["voltage_v"] * mates["current_a"]),
    )
    fig, axes = plt.subplots(5, 1, figsize=(15, 11), sharex=True)
    g = me.set_index("timestamp_local")["irradiance_wm2"]
    axes[0].plot(g.index, g, color="goldenrod")
    axes[0].set_ylabel(f"{hub} G W/m2")
    for ax, (col, unit) in zip(axes[1:], [*MEASURES, ("power_w", "W")], strict=True):
        for _, m in mates.groupby("panel_id"):
            ax.plot(m["timestamp_local"], m[col], color="0.7", lw=0.8)
        ax.plot(me["timestamp_local"], me[col], color="C3", lw=1.2)
        ax.set_ylabel(f"{col} ({unit})")
    fig.suptitle(
        f"{panel} (red) vs hub mates (grey), {args.start} to {args.end}\n"
        + weather_text(weather, args.start, args.end),
        fontsize=8,
    )
    fig.tight_layout()
    path = out / f"{panel}_{args.start}_{args.end}.png"
    fig.savefig(path, dpi=80)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--panels", required=True, help="comma-separated, e.g. P13,P14")
    ap.add_argument("--start", required=True, help="local date, e.g. 2025-11-01")
    ap.add_argument("--end", required=True, help="local date, inclusive")
    ap.add_argument("--input", default="input/mvp1")
    args = ap.parse_args()
    cfg = config.load_config(None, Path(args.input) / "site.json")
    inputs = load.load_inputs(args.input, cfg)
    r = nan_invalid(inputs.readings, cfg)
    day = r["timestamp_local"].dt.tz_localize(None).dt.normalize()
    r = r[day.between(args.start, args.end)]
    out = Path("output/signatures")
    out.mkdir(parents=True, exist_ok=True)
    for panel in args.panels.split(","):
        print(plot_panel(r, panel, inputs.weather, args, out))


if __name__ == "__main__":
    main()
