import re
import shutil

import pandas as pd
from conftest import FIXTURES

from solarscope import report

RESULTS = FIXTURES / "results"


def page_count(path) -> int:
    return len(re.findall(rb"/Type /Page(?!s)", path.read_bytes()))


def test_render_writes_two_six_page_pdfs(tmp_path):
    shutil.copytree(RESULTS, tmp_path / "r")
    paths = report.render(tmp_path / "r")
    assert sorted(p.name for p in paths) == ["report_180d.pdf", "report_365d.pdf"]
    assert [page_count(p) for p in paths] == [6, 6]


def test_pages_hold_the_fixture_numbers():
    pages = report.build_pages(RESULTS)
    assert set(pages) == {"365d", "180d"} and all(len(p) == 6 for p in pages.values())
    p1 = pages["365d"][0]
    assert "Energy lost: 1.23 kWh" in p1.lines
    assert any("Faults: 0.59 kWh" in line for line in p1.lines)
    dispatch = pages["365d"][2].tables[0]
    assert [r[0] for r in dispatch[1:]] == ["D001"] and dispatch[1][2] == "P02"
    assert pages["180d"][3].tables[0][1][0] == "P05"
    assert pages["365d"][4].tables[0][1][0] == "P03"


def test_empty_sections_and_row_cap(tmp_path):
    shutil.copytree(RESULTS, tmp_path / "r")
    ev = pd.read_csv(tmp_path / "r" / "events.csv")
    ev = pd.concat([ev] * 4)  # 24 events
    ev.to_csv(tmp_path / "r" / "events.csv", index=False)
    pd.read_csv(tmp_path / "r" / "dispatch.csv").iloc[0:0].to_csv(
        tmp_path / "r" / "dispatch.csv", index=False
    )
    pages = report.build_pages(tmp_path / "r")["365d"]
    assert len(pages[1].tables[1]) - 1 == report.TOP_EVENTS
    assert pages[2].lines == ["No faults need a truck roll in this window."]
    assert len(report.render(tmp_path / "r")) == 2
