import json
from dataclasses import asdict, dataclass
from datetime import date

from adlc.findings import BENCHMARK_SOURCE, CONFOUNDERS, Finding, band, band_text
from adlc.gitdata import ReworkResult
from adlc.metrics import DeliverySummary


def minutes(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value >= 120:
        return f"{value / 60:.1f} h"
    return f"{round(value)} min"


def rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def lines(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f}"


def summary_dict(summary: DeliverySummary) -> dict:
    return asdict(summary) | {"merged_per_week": summary.merged_per_week, "merged_per_author_per_week": summary.merged_per_author_per_week}


def build_baseline(
    repo: str,
    measured_on: date,
    window_days: int | None,
    summary: DeliverySummary,
    automation_prs: int,
    rework_result: ReworkResult | None,
    ai_reviewer_logins: list[str],
    limit: int = 0,
    findings: list[Finding] | None = None,
    assumptions: list[str] | None = None,
) -> dict:
    return {
        "tool": "adlc",
        "repo": repo,
        "measuredOn": measured_on.isoformat(),
        "windowDays": window_days,
        "coveredDays": round(summary.weeks * 7, 1),
        "limit": limit or None,
        "limitReached": bool(limit) and window_days is not None and summary.pull_requests >= limit,
        "aiReviewerLoginsExcluded": ai_reviewer_logins,
        "pullRequests": summary_dict(summary) | {"automationExcluded": automation_prs},
        "rework": asdict(rework_result) | {"churnRate": rework_result.churn_rate, "reworkRate21": rework_result.rework_rate_21} if rework_result else None,
        "findings": [asdict(finding) for finding in findings or []],
        "confounders": list(CONFOUNDERS) if findings else [],
        "benchmarkSource": BENCHMARK_SOURCE if findings else None,
        "assumptions": list(assumptions or []),
    }


def to_json(baseline: dict) -> str:
    return json.dumps(baseline, indent=2) + "\n"


@dataclass(frozen=True)
class Row:
    metric: str
    value: str
    band: str
    tier: str | None


def band_row(label: str, key: str, value: float | None, value_fmt, band_fmt, suffix: str = "") -> Row:
    if value is None:
        return Row(label, "n/a", "", None)
    return Row(label, value_fmt(value), band_text(key, value, band_fmt) + suffix, band(key, value))


def table_rows(baseline: dict) -> list[Row]:
    prs = baseline["pullRequests"]
    rw = baseline["rework"]
    rows = [
        Row("Pull requests", str(prs["pull_requests"]), "", None),
        Row("Merged per week", rate(prs["merged_per_week"]), "", None),
        band_row("Merged per author per week", "merge_frequency", prs["merged_per_author_per_week"], rate, lambda v: f"{v:g}"),
        Row("Open to merge, median", minutes(prs["median_cycle_minutes"]), "", None),
        band_row("Open to merge, 75th percentile", "open_to_merge", prs["p75_cycle_minutes"], minutes, minutes, " for pickup plus review"),
        Row("Time to first human review, median", minutes(prs["median_first_human_review_minutes"]), "", None),
        band_row("Time to first human review, 75th percentile", "pickup", prs["p75_first_human_review_minutes"], minutes, minutes),
        Row("Time to first human review, after an AI review", minutes(prs["median_first_human_review_after_ai_minutes"]), "", None),
        Row("Time to first human review, no AI review first", minutes(prs["median_first_human_review_without_ai_minutes"]), "", None),
        Row("First human review to merge, median", minutes(prs["median_review_minutes"]), "", None),
        band_row("First human review to merge, 75th percentile", "review", prs["p75_review_minutes"], minutes, minutes),
        Row("PR size, median changed lines", lines(prs["median_changed_lines"]), "", None),
        band_row("PR size, 75th percentile", "size", prs["p75_changed_lines"], lines, lambda v: f"{v:g}", " lines"),
    ]
    if rw:
        rows.append(band_row("Rework rate, code under 21 days old rewritten", "rework", rw["reworkRate21"], percent, percent))
        rows.append(Row(f"New code deleted again within {rw['age_days']} days", percent(rw["churnRate"]), "own trend", None))
    else:
        rows.append(Row("Rework", "not run", "", None))
    return rows


def coverage_line(baseline: dict) -> str:
    prs = baseline["pullRequests"]
    covered = baseline.get("coveredDays") or 0
    coverage = f"{prs['pull_requests']} merged pull requests covering the last {covered:g} days"
    if baseline.get("windowDays") is None:
        coverage = f"The {prs['pull_requests']} most recent merged pull requests, covering the last {covered:g} days"
    elif baseline.get("limitReached"):
        coverage += f" (the cap of {baseline['limit']} pull requests was reached before the {baseline['windowDays']} day window, use --limit N to cover more)"
    else:
        coverage += f" of a {baseline['windowDays']} day window"
    return f"Measured on {baseline['measuredOn']}. {coverage}."


def confounder_intro(baseline: dict) -> str:
    return f"Bands: {baseline['benchmarkSource']}. Before acting on a reading, check:"


CONTROL_LINE = "The cleanest comparison is the same team, same window, next quarter."


def footer_lines(baseline: dict) -> list[str]:
    prs = baseline["pullRequests"]
    rw = baseline["rework"]
    out = [f"Logins never counted as human reviewers: {', '.join(baseline['aiReviewerLoginsExcluded']) or 'none'}."]
    if prs.get("automationExcluded"):
        out.append(f"{prs['automationExcluded']} pull requests opened by automation accounts were left out.")
    if rw and rw["excluded_deleted_lines"]:
        out.append(f"Rework skipped {rw['excluded_deleted_lines']} deleted lines in generated, vendored, lock or secret files.")
    return out


def to_markdown(baseline: dict) -> str:
    out = [
        f"# Delivery baseline for {baseline['repo']}",
        "",
        coverage_line(baseline),
        "",
        "| Metric | Value | Band, LinearB 2026 p75 |",
        "| --- | ---: | --- |",
    ]
    out += [f"| {row.metric} | {row.value} | {row.band + ' ' if row.band else ''}|" for row in table_rows(baseline)]
    if baseline.get("findings"):
        out += ["", "## What stands out", ""]
        out += [f"- {finding['text']}" for finding in baseline["findings"]]
        out += ["", confounder_intro(baseline), ""]
        out += [f"- {item}" for item in baseline["confounders"]]
        out += ["", CONTROL_LINE]
    if baseline.get("assumptions"):
        out += ["", "## What this report assumes", ""]
        out += [f"- {item}" for item in baseline["assumptions"]]
    out += ["", *footer_lines(baseline)]
    return "\n".join(out) + "\n"
