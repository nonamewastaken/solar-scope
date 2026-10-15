"""SolarScope one-command entry point.

    uv run run.py --input <input_folder> --output <output_folder> [--config config/thresholds.yaml]
                  [--set dq.clock_offset=exclude --set dq.drift=contract ...]

Runs Stages 1-3 (load, clean, quality). The remaining stages are wired in SOL-17.
`--set key=value` overrides any config key for this run. The data-quality approaches are the
`dq.*` keys (docs/dq_options.md). The choice is part of the config hash.
"""

import argparse
from pathlib import Path

from solarscope import clean, config, load, quality


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--config", type=Path, default=config.DEFAULT_CONFIG)
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = p.parse_args()

    cfg = config.load_config(args.config, args.input / "site.json", args.set)
    inputs = load.load_inputs(args.input, cfg)
    print(f"site {cfg.site['site_id']} | config {cfg.hash[:12]} | {len(inputs.readings):,} rows")
    print("data quality: " + ", ".join(f"{k}={v}" for k, v in cfg.thresholds["dq"].items()))
    windows = config.derive_windows(inputs.readings, cfg)
    for w in windows:
        print(f"  window {w.name}: {w.start} to {w.end} ({w.days} days)")

    qual = quality.assess(clean.clean(inputs, cfg), inputs, windows, cfg)
    dq = qual.data_quality[qual.data_quality["window"] == windows[0].name]
    print(f"usable data per hub, window {windows[0].name}:")
    for r in dq.itertuples():
        print(f"  {r.hub_id}: {r.usable_pct:6.2f} %  {r.reasons}")


if __name__ == "__main__":
    main()
