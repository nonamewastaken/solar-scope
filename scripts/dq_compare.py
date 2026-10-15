"""Run scripts/dq_eval.py on several DQ branches and put the results side by side.

    uv run scripts/dq_compare.py --input <input_folder> --injected output/injected

Each branch is checked out in its own git worktree under <out>/wt, so your working copy
is never touched. Writes <out>/<branch>.{real,injected}.json and <out>/comparison.md.
Default branches: the DQ base (ductring/sol-21-*) and every ductring/dq-alt-* branch.
"""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sh(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


def branches() -> list[str]:
    out = sh(
        "git",
        "branch",
        "--list",
        "ductring/sol-21-*",
        "ductring/dq-alt-*",
        "--format=%(refname:short)",
    )
    return out.split()


def checkout(branch: str, wt: Path) -> Path:
    path = wt / branch.replace("/", "_")
    if path.exists():
        sh("git", "checkout", "-q", "--detach", branch, cwd=path)
    else:
        sh("git", "worktree", "add", "-q", "--detach", str(path), branch)
    return path


def evaluate(path: Path, input_dir: Path, out: Path, truth: Path | None = None) -> dict:
    cmd = ["uv", "run", "--quiet", "python", "scripts/dq_eval.py", "--input", str(input_dir),
           "--out", str(out)]  # fmt: skip
    if truth:
        cmd += ["--truth", str(truth)]
    sh(*cmd, cwd=path)
    return json.loads(out.read_text())


def first(items: list[dict], **match) -> dict:
    return next((i for i in items if all(i.get(k) == v for k, v in match.items())), {})


def row(branch: str, real: dict, inj: dict) -> dict:
    r2, i3 = real["l2"], inj["l3"]
    px = r2["proxies"]
    h02 = first(r2["clock_offsets"], hub_id="H02")
    drift = first(r2["sensor_periods"], hub_id="H09", sensor="irradiance_wm2")
    hum = first(r2["sensor_periods"], hub_id="H09", sensor="humidity_pct")
    errs = [abs(f["start_err_days"]) for f in i3["faults"] if f["found"]]
    fb = {f["id"]: f for f in i3.get("fallback", [])}
    lf = {f["id"]: f for f in i3["faults"]}
    return {
        "branch": branch,
        "P1 H02 clock": f"{h02.get('offset_min', 'none')} {h02.get('start', '')}".strip(),
        "P1 conflicts": r2["n_conflict_records"],
        "P1 H02 Apr abnormal": px["abnormal_by_hub_month"].get("H02", {}).get("2026-04", 0),
        "P1 H02 usable % 365d": r2["usable_pct_by_hub"]["365d"].get("H02"),
        "P2 H09 drift from": drift.get("start", "none"),
        "P2 H09 loss 180d kWh": px["180d"]["loss_kwh_by_hub"].get("H09"),
        "P2 site loss 180d kWh": px["180d"]["loss_kwh"],
        "P2 F2 slow drift late d": lf["F2"].get("start_err_days"),
        "P2 F2 used err %": fb.get("F2", {}).get("median_abs_err_pct"),
        "P2 F3 step used err %": fb.get("F3", {}).get("median_abs_err_pct"),
        "P3 H09 humidity from": hum.get("start", "none"),
        "P3 F5 late d": lf["F5"].get("start_err_days"),
        "P4 S1 temp 327.6": i3["value_cases"].get("S1"),
        "P4 S2 irr 655.35 real": i3["value_cases"].get("S2"),
        "P4 S3 irr 327.6 night": i3["value_cases"].get("S3"),
        "L3 faults found": f"{i3['n_found']}/{i3['n_faults']}",
        "L3 mean start err d": round(sum(errs) / len(errs), 2) if errs else None,
        "L3 false alarms": len(i3["false_alarms"]),
        "seconds": real["seconds"],
    }


def markdown(rows: list[dict]) -> str:
    cols = list(rows[0])
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--injected", required=True, type=Path)
    p.add_argument("--out", type=Path, default=ROOT / "output" / "dq_compare")
    p.add_argument("--branches", nargs="*")
    args = p.parse_args()
    out = args.out.resolve()
    real_in, inj_in = args.input.resolve(), args.injected.resolve()
    truth = inj_in / "injected_faults.json"

    rows = []
    for b in args.branches or branches():
        path = checkout(b, out / "wt")
        name = b.replace("/", "_")
        print(f"{b}: real data ...", flush=True)
        real = evaluate(path, real_in, out / f"{name}.real.json")
        print(f"{b}: injected faults ...", flush=True)
        inj = evaluate(path, inj_in, out / f"{name}.injected.json", truth)
        rows.append(row(b, real, inj))
    (out / "comparison.json").write_text(json.dumps(rows, indent=1))
    (out / "comparison.md").write_text(markdown(rows))
    print(markdown(rows))


if __name__ == "__main__":
    main()
