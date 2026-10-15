"""Stage 6c: one 6-page PDF per report window, built only from the 5 result files.

build_pages formats numbers and filters by window. draw only puts Page objects on paper.
"""

import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

ROW_CAP = 12  # rows per table
TOP_EVENTS = 10  # events listed on page 2
CELL_CHARS = 44  # longest text in a table cell
RULES = [  # (label, path into summary.json config) shown on the Method page
    ("Valid ranges", "validation.valid_ranges"),
    ("Min irradiance for expected output (W/m2)", "expected.min_irradiance_wm2"),
    ("Peer reference period (days)", "expected.peer.reference_period_days"),
    ("Sensor drift tolerance", "quality.drift.ratio_tolerance"),
    ("Event grouping gap (intervals)", "classify.grouping.max_gap_intervals"),
    ("Slow-decline flag (%/month, % behind)", "decline.slope_threshold_pct_per_month"),
    ("Dispatch: only faults active at window end", "dispatch.require_active"),
]  # fmt: skip
LABEL_NAMES = {
    "fault": "Fault", "weather": "Weather", "sensor_issue": "Sensor issue",
    "data_issue": "Data issue", "early_warning": "Early warning", "unresolved": "Unresolved",
}  # fmt: skip


@dataclass
class Page:
    title: str
    lines: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)  # first row is the header


def kwh(x: float) -> str:
    return f"{x:,.2f} kWh"


def _clip(text: object, n: int = CELL_CHARS) -> str:
    s = str(text)
    return s if len(s) <= n else s[: n - 1] + "…"


def _in_window(events: pd.DataFrame, w: dict) -> pd.DataFrame:
    """Events whose local days overlap the window. end_local is exclusive."""
    # the first 10 characters of an ISO string are the local date
    first = events["start_local"].str[:10]
    end = pd.to_datetime(events["end_local"].str[:10])
    midnight = events["end_local"].str[11:19] == "00:00:00"
    last = (end - pd.to_timedelta(midnight.astype(int), unit="D")).dt.strftime("%Y-%m-%d")
    return events[(first <= w["end"]) & (last >= w["start"])]


def _capped(rows: list[list[str]], total_note: str) -> tuple[list[list[str]], list[str]]:
    note = [f"Showing {ROW_CAP} of {len(rows)} rows. {total_note}"] if len(rows) > ROW_CAP else []
    return rows[:ROW_CAP], note


def build_pages(results_dir: Path | str) -> dict[str, list[Page]]:
    d = Path(results_dir)
    summary = json.loads((d / "summary.json").read_text())
    events = pd.read_csv(d / "events.csv").fillna(
        {"first_flag_date": "", "projected_10pct_date": ""}
    )
    dispatch = pd.read_csv(d / "dispatch.csv")
    quality = pd.read_csv(d / "data_quality.csv").fillna({"excluded_periods": ""})
    return {
        name: [
            _summary_page(summary, w),
            _events_page(events, w),
            _dispatch_page(dispatch, name),
            _repeat_page(w),
            _warnings_page(events, w),
            _method_page(summary, quality, name, w),
        ]
        for name, w in summary["windows"].items()
    }


def _header(w: dict) -> str:
    return f"{w['start']} to {w['end']} ({w['days']} days)"


def _summary_page(summary: dict, w: dict) -> Page:
    lost, by = w["kwh_lost_total"], w["kwh_lost_by_label"]
    lines = [
        f"Site {summary['site_id']}, {_header(w)}",
        "",
        f"Energy produced: {kwh(w['actual_kwh'])}",
        f"Energy expected: {kwh(w['expected_kwh'])}",
        f"Energy lost: {kwh(lost)}",
        f"  Faults: {kwh(by['fault'])}",
        f"  Weather: {kwh(by['weather'])}",
        "",
        f"Truck rolls to send: {w['n_dispatches']} ({w['n_dispatch_panels']} panels)",
        f"Early warnings: {w['n_early_warnings']}",
        f"Truck rolls avoided: {w['truck_rolls_avoided']['count']}"
        f" (${w['truck_rolls_avoided']['cost_usd']:,.0f})",
        "",
        "Top findings",
    ]  # fmt: skip
    lines += [f"{f['rank']}. {f['text']}: {kwh(f['kwh_lost'])}" for f in w["top_findings"]]
    return Page("Summary", lines)


def _events_page(events: pd.DataFrame, w: dict) -> Page:
    ev = _in_window(events, w)
    ev = ev[ev["label"] != "early_warning"]
    by = ev.groupby(["label", "cause"]).agg(n=("event_id", "count"), kwh=("kwh_lost", "sum"))
    causes = [
        [LABEL_NAMES[lab], cause, str(int(r.n)), kwh(r.kwh)] for (lab, cause), r in by.iterrows()
    ]
    top = ev.sort_values("kwh_lost", ascending=False)
    rows = [[r.event_id, LABEL_NAMES[r.label], r.cause, r.start_local[:10], _clip(r.panel_ids, 18),
             kwh(r.kwh_lost)] for r in top.head(TOP_EVENTS).itertuples()]  # fmt: skip
    lines = [_header(w), f"Top {TOP_EVENTS} events by kWh lost. Full list: events.csv"]
    return Page("Fault or Weather", lines, [
        [["Label", "Cause", "Events", "kWh lost"], *causes[:ROW_CAP]],
        [["Event", "Label", "Cause", "Start", "Panels", "kWh lost"], *rows],
    ])  # fmt: skip


def _dispatch_page(dispatch: pd.DataFrame, window: str) -> Page:
    dp = dispatch[dispatch["window"] == window]
    rows = []
    for _, g in dp.groupby("dispatch_id", sort=True):
        first = g.iloc[0]
        rows.append([first["dispatch_id"], first["priority"], _clip(", ".join(g["panel_id"]), 24),
                     first["cause"], _clip(first["evidence"]), kwh(first["kwh_lost"])])  # fmt: skip
    shown, note = _capped(rows, "Full list: dispatch.csv")
    lines = note or ([] if rows else ["No faults need a truck roll in this window."])
    return Page("Dispatch List", lines, [
        [["ID", "Priority", "Panels", "Cause", "Evidence", "kWh lost"], *shown]
    ] if rows else [])  # fmt: skip


def _repeat_page(w: dict) -> Page:
    rr = w["repeat_repairs"]
    if not rr:
        return Page("Repeat Repairs", ["No panel repaired more than once."])
    rows = [[r["panel_id"], r["hub_id"], str(r["n_repairs"]), ", ".join(r["visit_dates"]),
             _clip(r["root_cause"]), _clip(r["permanent_fix"], 60)] for r in rr]  # fmt: skip
    shown, note = _capped(rows, "Full list: summary.json")
    return Page("Repeat Repairs", note, [
        [["Panel", "Hub", "Repairs", "Visit dates", "Root cause", "Permanent fix"], *shown]
    ])  # fmt: skip


def _warnings_page(events: pd.DataFrame, w: dict) -> Page:
    ew = _in_window(events, w)
    ew = ew[ew["label"] == "early_warning"]
    if ew.empty:
        return Page("Early Warnings", ["No panels are declining."])
    rows = [[r.panel_ids, f"{r.decline_rate_pct_per_month:.1f}%/month", r.first_flag_date,
             f"{r.current_deficit_pct:.1f}%", r.projected_10pct_date]
            for r in ew.itertuples()]  # fmt: skip
    shown, note = _capped(rows, "Full list: events.csv")
    return Page("Early Warnings", note, [
        [["Panel", "Decline rate", "First flagged", "Behind peers", "Projected 10% date"], *shown]
    ])  # fmt: skip


def _lookup(config: dict, path: str) -> object:
    for key in path.split("."):
        config = config[key]
    return config


def _method_page(summary: dict, quality: pd.DataFrame, window: str, w: dict) -> Page:
    q = quality[quality["window"] == window]
    rows = [[r.hub_id, r.row, f"{r.usable_pct:.2f}%", _clip(r.excluded_periods) or "none"]
            for r in q.itertuples()]  # fmt: skip
    shown, note = _capped(rows, "Full list: data_quality.csv")
    lines = [*note, "", "Rules used"]
    lines += [f"{label}: {_lookup(summary['config'], p)}" for label, p in RULES]
    lines += ["", f"Run ID: {summary['run_id']}", f"Config hash: {summary['config_hash'][:16]}"]
    lines += ["Input checksums (sha256, first 16):"]
    lines += [f"  {f}: {h[:16]}" for f, h in summary["input_checksums"].items()]
    return Page("Data Quality and Method", lines, [
        [["Hub", "Row", "Usable data", "Excluded periods"], *shown]
    ])  # fmt: skip


def draw(pages: list[Page], pdf_path: Path | str) -> None:
    """Only matplotlib here. Every number is already text on the Page."""
    with PdfPages(pdf_path) as pdf:
        for i, page in enumerate(pages, 1):
            fig = plt.figure(figsize=(8.5, 11))  # US Letter portrait
            fig.text(0.06, 0.95, page.title, fontsize=20, weight="bold", va="top")
            fig.text(0.94, 0.03, f"Page {i} of {len(pages)}", fontsize=8, ha="right")
            y = 0.90
            for line in page.lines:
                for part in textwrap.wrap(line, 95, subsequent_indent="    ") or [""]:
                    fig.text(0.06, y, part, fontsize=9.5, va="top")
                    y -= 0.022
            for table in page.tables:
                y -= 0.01
                height = 0.026 * len(table)
                ax = fig.add_axes([0.06, y - height, 0.88, height])
                ax.axis("off")
                t = ax.table(cellText=table[1:], colLabels=table[0], cellLoc="left",
                             bbox=[0, 0, 1, 1])  # fmt: skip
                t.auto_set_font_size(False)
                t.set_fontsize(7.5)
                y -= height + 0.01
            pdf.savefig(fig)
            plt.close(fig)


def render(results_dir: Path | str) -> list[Path]:
    """Write report_<window>.pdf next to the result files, one per window in summary.json."""
    out = []
    for name, pages in build_pages(results_dir).items():
        path = Path(results_dir) / f"report_{name}.pdf"
        draw(pages, path)
        out.append(path)
    return out
