from datetime import date

from adlc.findings import Finding
from adlc.gitdata import ReworkResult
from adlc.metrics import DeliverySummary
from adlc.report import build_baseline, to_markdown


def summary() -> DeliverySummary:
    return DeliverySummary(
        pull_requests=100,
        median_cycle_minutes=24,
        median_first_human_review_minutes=8,
        reviewed_pull_requests=76,
        weeks=4,
        active_authors=10,
        median_first_human_review_after_ai_minutes=12,
        median_first_human_review_without_ai_minutes=6,
        p75_cycle_minutes=40,
        p75_first_human_review_minutes=15,
        median_changed_lines=60,
        p75_changed_lines=110,
        median_review_minutes=14,
        p75_review_minutes=30,
    )


def test_markdown_report_is_exact():
    baseline = build_baseline(
        repo="acme/widgets",
        measured_on=date(2026, 9, 7),
        window_days=90,
        summary=summary(),
        automation_prs=5,
        rework_result=ReworkResult(window_days=30, age_days=30, deleted_lines=189982, excluded_deleted_lines=27000, lines_added=150000, lines_added_then_deleted=21000, young_21_deleted_lines=13600),
        ai_reviewer_logins=["coderabbitai", "unblocked"],
    )
    expected = """# Delivery baseline for acme/widgets

Measured on 2026-09-07. 100 merged pull requests covering the last 28 days of a 90 day window.

| Metric | Value | Band, LinearB 2026 p75 |
| --- | ---: | --- |
| Pull requests | 100 | |
| Merged per week | 25.0 | |
| Merged per author per week | 2.5 | elite, over 2 |
| Open to merge, median | 24 min | |
| Open to merge, 75th percentile | 40 min | elite, under 4.0 h for pickup plus review |
| Time to first human review, median | 8 min | |
| Time to first human review, 75th percentile | 15 min | elite, under 60 min |
| Time to first human review, after an AI review | 12 min | |
| Time to first human review, no AI review first | 6 min | |
| First human review to merge, median | 14 min | |
| First human review to merge, 75th percentile | 30 min | elite, under 3.0 h |
| PR size, median changed lines | 60 | |
| PR size, 75th percentile | 110 | good, 100 to 155 lines |
| Rework rate, code under 21 days old rewritten | 4% | good, 3% to 5% |
| New code deleted again within 30 days | 14% | own trend |

Logins never counted as human reviewers: coderabbitai, unblocked.
5 pull requests opened by automation accounts were left out.
Rework skipped 27000 deleted lines in generated, vendored, lock or secret files.
"""
    assert to_markdown(baseline) == expected


def test_markdown_report_renders_findings_confounders_and_assumptions():
    baseline = build_baseline(
        repo="acme/widgets",
        measured_on=date(2026, 9, 7),
        window_days=90,
        summary=summary(),
        automation_prs=0,
        rework_result=None,
        ai_reviewer_logins=[],
        findings=[Finding("cycle_time", "Cycle time is 24 min at the median and 40 min at the 75th percentile, inside the elite band of under 25 hours.")],
        assumptions=["No AI reviewer left code comments in this window."],
    )
    text = to_markdown(baseline)
    expected = """| Rework | not run | |

## What stands out

- Cycle time is 24 min at the median and 40 min at the 75th percentile, inside the elite band of under 25 hours.

Bands: LinearB 2026 engineering benchmarks, 8.1 million pull requests, 75th percentile: elite is the top 10% of teams, good the top 30%, fair the top 60%. Before acting on a reading, check:

- Team size and repository type: the benchmarks pool thousands of teams that ship differently.
- PR size and stacking: small stacked PRs compress cycle time and lift merge counts.
- Review policy: risk scoring, auto-merge and bot reviewers route PRs past people by design.
- Monorepos: one repository is read as one team.
- What else changed: a model upgrade, a freeze, a holiday, a reorganisation or new hires move every number.
- Definitions: LinearB cycle time runs from first commit to production, so open to merge is read against pickup plus review. Rework is computed from git blame here.

The cleanest comparison is the same team, same window, next quarter.

## What this report assumes

- No AI reviewer left code comments in this window.

Logins never counted as human reviewers: none.
"""
    assert expected in text
    assert baseline["confounders"][0].startswith("Team size")


def test_markdown_report_without_pull_requests():
    baseline = build_baseline(
        repo="acme/widgets",
        measured_on=date(2026, 9, 7),
        window_days=30,
        summary=DeliverySummary(0, None, None, 0),
        automation_prs=0,
        rework_result=None,
        ai_reviewer_logins=[],
    )
    text = to_markdown(baseline)
    assert "| Rework | not run | |" in text
    assert "0 merged pull requests covering the last 0 days of a 30 day window." in text


def test_markdown_report_warns_when_the_limit_truncated_the_window():
    baseline = build_baseline(
        repo="acme/widgets",
        measured_on=date(2026, 9, 7),
        window_days=90,
        summary=DeliverySummary(300, 36, 15, 239, weeks=1.0, active_authors=16),
        automation_prs=0,
        rework_result=None,
        ai_reviewer_logins=[],
        limit=300,
    )
    text = to_markdown(baseline)
    assert "300 merged pull requests covering the last 7 days (the cap of 300 pull requests was reached before the 90 day window, use --limit N to cover more)" in text
    assert "| Merged per week | 300.0 | |" in text


def test_markdown_report_describes_a_count_scope_without_a_window():
    baseline = build_baseline(
        repo="acme/widgets",
        measured_on=date(2026, 9, 7),
        window_days=None,
        summary=DeliverySummary(500, 36, 15, 239, weeks=1.0, active_authors=3),
        automation_prs=0,
        rework_result=None,
        ai_reviewer_logins=[],
        limit=500,
    )
    text = to_markdown(baseline)
    assert "Measured on 2026-09-07. The 500 most recent merged pull requests, covering the last 7 days." in text
    assert "use --limit" not in text
    assert baseline["windowDays"] is None
    assert baseline["limit"] == 500
    assert baseline["limitReached"] is False
