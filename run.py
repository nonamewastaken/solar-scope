"""SolarScope one-command entry point.

    uv run run.py --input <input_folder> --output <output_folder> [--config config/thresholds.yaml]

Phase 1: runs Stage 1 (load + windows) only. All stages are wired in SOL-17.
"""

import argparse
from pathlib import Path

from solarscope import config, load


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--config", type=Path, default=config.DEFAULT_CONFIG)
    args = p.parse_args()

    cfg = config.load_config(args.config, args.input / "site.json")
    inputs = load.load_inputs(args.input, cfg)
    print(f"site {cfg.site['site_id']} | config {cfg.hash[:12]} | {len(inputs.readings):,} rows")
    for w in config.derive_windows(inputs.readings, cfg):
        print(f"  window {w.name}: {w.start} to {w.end} ({w.days} days)")


if __name__ == "__main__":
    main()
