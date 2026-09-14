from datetime import date

from rich.console import Console

from adlc.findings import Finding
from adlc.gitdata import ReworkResult
from adlc.report import Row, build_baseline, table_rows
from adlc.terminal import band_cell, render
from tests.test_report import summary


def sample_baseline() -> dict:
    return build_baseline(
        repo="acme/widgets",
        measured_on=date(2026, 9, 7),
        window_days=90,
        summary=summary(),
        automation_prs=5,
        rework_result=ReworkResult(window_days=30, age_days=30, deleted_lines=189982, excluded_deleted_lines=27000, lines_added=150000, lines_added_then_deleted=21000, young_21_deleted_lines=13600),
        ai_reviewer_logins=["coderabbitai", "unblocked"],
        findings=[Finding("cycle_time", "Open to merge takes 24 min at the median and 40 min at the 75th percentile, elite, under 4.0 h for pickup plus review.")],
        assumptions=["No AI reviewer left code comments in this window."],
    )


def rendered(baseline: dict, width: int = 160) -> str:
    console = Console(record=True, width=width, force_terminal=False, color_system=None)
    render(baseline, console)
    return console.export_text()


def test_band_cell_styles_only_the_tier_word():
    cell = band_cell("good, 100 to 155 lines", "good")
    assert cell.plain == "good, 100 to 155 lines"
    assert [(span.start, span.end, span.style) for span in cell.spans] == [(0, 4, "bold cyan")]


def test_band_cell_without_a_tier_is_dim():
    cell = band_cell("own trend", None)
    assert cell.plain == "own trend"
    assert cell.style == "dim"


def test_table_rows_carry_band_and_tier():
    rows = table_rows(sample_baseline())
    by_metric = {row.metric: row for row in rows}
    assert by_metric["PR size, 75th percentile"] == Row("PR size, 75th percentile", "110", "good, 100 to 155 lines", "good")
    assert by_metric["Pull requests"] == Row("Pull requests", "100", "", None)


def test_render_prints_title_table_findings_and_assumptions():
    text = rendered(sample_baseline())
    assert text.startswith("Delivery baseline for acme/widgets ─")
    assert "Measured on 2026-09-07. 100 merged pull requests covering the last 28 days of a 90 day window." in text
    assert "Band, LinearB 2026 p75" in text
    assert "PR size, 75th percentile" in text
    assert "good, 100 to 155 lines" in text
    assert "What stands out" in text
    assert "What this report assumes" in text
    assert "Logins never counted as human reviewers" in text
    assert "|" not in text
