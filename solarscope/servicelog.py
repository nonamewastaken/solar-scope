"""Stage 6a: tag service visits and find repeat repairs. See docs/contracts.md section 8."""

from dataclasses import dataclass

import pandas as pd

from .config import Config, Window


@dataclass(frozen=True)
class ServiceLog:
    visits: pd.DataFrame
    repeat_repairs: pd.DataFrame


def analyze(
    service_log: pd.DataFrame, events: pd.DataFrame, windows: list[Window], cfg: Config
) -> ServiceLog:
    """`windows` is part of the contract but unused: repeat_repairs is not filtered by window.
    summary.py shows a panel in a window when any of its repairs falls inside it (decision 4)."""
    sl = cfg.thresholds["servicelog"]
    return ServiceLog(
        visits=_tag_visits(service_log, events, sl, cfg.tz),
        repeat_repairs=_repeat_repairs(service_log, sl, cfg),
    )


def _tag_visits(service_log: pd.DataFrame, events: pd.DataFrame, sl: dict, tz: str) -> pd.DataFrame:
    ev = pd.DataFrame({
        "event_id": events["event_id"],
        "label": events["label"],
        "kwh_lost": events["kwh_lost"],
        "panels": events["panel_ids"].map(lambda v: set(str(v).split(";"))),
        "first": pd.to_datetime(events["start_local"], utc=True).dt.tz_convert(tz).dt.date,
        # end_local is exclusive, so the last day touched is the day of the last instant
        "last": (pd.to_datetime(events["end_local"], utc=True) - pd.Timedelta(microseconds=1))
        .dt.tz_convert(tz)
        .dt.date,
    })  # fmt: skip
    matched, explained, avoidable = [], [], []
    for v in service_log.itertuples():
        day = v.visit_date.date()
        since = (v.visit_date - pd.Timedelta(days=sl["match_window_days"])).date()
        hit = ev[(ev["first"] <= day) & (ev["last"] >= since)]
        mine = set(v.panel_list)
        hit = hit[~hit["panels"].map(mine.isdisjoint).astype(bool)]  # astype: empty hit
        best = hit.sort_values("kwh_lost", ascending=False)
        label = best["label"].iloc[0] if len(best) else ""
        matched.append(hit["event_id"].tolist())
        explained.append(label)
        avoidable.append(
            not v.fault_found and v.trigger != "scheduled" and label in sl["avoidable_labels"]
        )
    return service_log.assign(
        matched_event_ids=matched, explained_by=explained, avoidable=avoidable
    )


def _repeat_repairs(service_log: pd.DataFrame, sl: dict, cfg: Config) -> pd.DataFrame:
    cols = ["panel_id", "hub_id", "n_repairs", "ticket_ids", "visit_dates", "root_cause",
            "permanent_fix"]  # fmt: skip
    fixes = service_log[service_log["fault_found"]].sort_values("visit_date", kind="stable")
    fixes = fixes.explode("panel_list").rename(columns={"panel_list": "panel_id"})
    hub_of = {p["panel_id"]: p["hub_id"] for p in cfg.site["panels"]}
    rows = []
    # same fault type again: a string-wide fuse repair is not a repeat of a connector repair
    for (panel, _), g in fixes.groupby(["panel_id", "category"]):
        if len(g) < sl["repeat_min_repairs"]:
            continue
        last = g.iloc[-1]
        rows.append({
            "panel_id": panel, "hub_id": hub_of[panel], "n_repairs": len(g),
            "ticket_ids": g["ticket_id"].tolist(),
            "visit_dates": g["visit_date"].dt.strftime("%Y-%m-%d").tolist(),
            "root_cause": last["root_cause"],
            "permanent_fix": sl["permanent_fix"].get(last["category"], ""),
        })  # fmt: skip
    return pd.DataFrame(rows, columns=cols)
