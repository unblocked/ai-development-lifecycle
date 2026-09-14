from dataclasses import dataclass
from statistics import median

from adlc.gitdata import ReworkResult
from adlc.metrics import cycle_time_minutes, first_human_review_minutes, first_human_review_split, percentile, review_minutes, span_weeks
from adlc.model import PullRequest

MIN_SAMPLE = 20
RELATIVE_GAP = 0.10
TOP_REVIEWERS = 3

BENCHMARK_SOURCE = "LinearB 2026 engineering benchmarks, 8.1 million pull requests, 75th percentile: elite is the top 10% of teams, good the top 30%, fair the top 60%"
TIERS = ("elite", "good", "fair", "needs focus")
LOWER_IS_BETTER = {
    "pickup": [60, 240, 960],
    "review": [180, 840, 1440],
    "open_to_merge": [240, 1080, 2400],
    "size": [100, 155, 228],
    "rework": [0.03, 0.05, 0.08],
}
HIGHER_IS_BETTER = {
    "merge_frequency": [2.0, 1.2, 0.66],
}


def band(metric: str, value: float) -> str:
    if metric in LOWER_IS_BETTER:
        for tier, limit in zip(TIERS, LOWER_IS_BETTER[metric], strict=False):
            if value < limit:
                return tier
        return TIERS[-1]
    for tier, limit in zip(TIERS, HIGHER_IS_BETTER[metric], strict=False):
        if value > limit:
            return tier
    return TIERS[-1]


def band_range(metric: str, tier: str, fmt) -> str:
    limits = LOWER_IS_BETTER.get(metric) or HIGHER_IS_BETTER.get(metric)
    index = TIERS.index(tier)
    lower_better = metric in LOWER_IS_BETTER
    if lower_better:
        if index == 0:
            return f"under {fmt(limits[0])}"
        if index == 3:
            return f"over {fmt(limits[2])}"
        return f"{fmt(limits[index - 1])} to {fmt(limits[index])}"
    if index == 0:
        return f"over {fmt(limits[0])}"
    if index == 3:
        return f"under {fmt(limits[2])}"
    return f"{fmt(limits[index])} to {fmt(limits[index - 1])}"


def band_text(metric: str, value: float, fmt) -> str:
    tier = band(metric, value)
    return f"{tier}, {band_range(metric, tier, fmt)}"


CONFOUNDERS = [
    "Team size and repository type: the benchmarks pool thousands of teams that ship differently.",
    "PR size and stacking: small stacked PRs compress cycle time and lift merge counts.",
    "Review policy: risk scoring, auto-merge and bot reviewers route PRs past people by design.",
    "Monorepos: one repository is read as one team.",
    "What else changed: a model upgrade, a freeze, a holiday, a reorganisation or new hires move every number.",
    "Definitions: LinearB cycle time runs from first commit to production, so open to merge is read against pickup plus review. Rework is computed from git blame here.",
]


@dataclass(frozen=True)
class Finding:
    key: str
    text: str


def minutes_text(value: float) -> str:
    if value >= 120:
        return f"{value / 60:.1f} h"
    return f"{round(value)} min"


def percent_text(value: float) -> str:
    return f"{value * 100:.0f}%"


def change_text(before: float, after: float) -> str:
    if not before:
        return "n/a"
    return f"{abs(after - before) / before * 100:.0f}%"


def split_halves(prs: list[PullRequest]) -> tuple[list[PullRequest], list[PullRequest]]:
    if len(prs) < 2:
        return prs, []
    merged = [pr.merged_at for pr in prs]
    midpoint = min(merged) + (max(merged) - min(merged)) / 2
    return [pr for pr in prs if pr.merged_at < midpoint], [pr for pr in prs if pr.merged_at >= midpoint]


def per_author_per_week(prs: list[PullRequest], weeks: float) -> float | None:
    authors = {pr.author_login for pr in prs}
    if not weeks or not authors:
        return None
    return len(prs) / len(authors) / weeks


def throughput_trend(prs: list[PullRequest]) -> tuple[float, float] | None:
    early, late = split_halves(sorted(prs, key=lambda pr: pr.merged_at))
    if len(early) < MIN_SAMPLE or len(late) < MIN_SAMPLE:
        return None
    before = per_author_per_week(early, span_weeks(early))
    after = per_author_per_week(late, span_weeks(late))
    if before is None or after is None:
        return None
    return before, after


def throughput_finding(prs: list[PullRequest]) -> Finding | None:
    weeks = span_weeks(prs)
    rate = per_author_per_week(prs, weeks)
    if rate is None or len(prs) < MIN_SAMPLE:
        return None
    text = f"Merged PRs per author per week: {rate:.1f} ({band_text('merge_frequency', rate, lambda v: f'{v:g}')})."
    trend = throughput_trend(prs)
    if trend is not None:
        before, after = trend
        if before and abs(after - before) / before >= RELATIVE_GAP:
            direction = "Up" if after > before else "Down"
            text += f" {direction} {change_text(before, after)} across the window, {before:.1f} to {after:.1f}."
        else:
            text += " Steady across the window."
    return Finding("throughput", text)


def cycle_time_finding(prs: list[PullRequest]) -> Finding | None:
    if len(prs) < MIN_SAMPLE:
        return None
    times = [cycle_time_minutes(pr) for pr in prs]
    p75 = percentile(times, 0.75)
    return Finding("cycle_time", f"Open to merge: {minutes_text(median(times))} median, {minutes_text(p75)} p75 ({band_text('open_to_merge', p75, minutes_text)} for pickup plus review).")


def pickup_finding(prs: list[PullRequest], ai_reviewer_logins: frozenset[str]) -> Finding | None:
    waits = [m for m in (first_human_review_minutes(pr, ai_reviewer_logins) for pr in prs) if m is not None]
    if len(waits) < MIN_SAMPLE:
        return None
    p75 = percentile(waits, 0.75)
    return Finding("pickup", f"First human review: {minutes_text(median(waits))} median, {minutes_text(p75)} p75 ({band_text('pickup', p75, minutes_text)}).")


def review_time_finding(prs: list[PullRequest], ai_reviewer_logins: frozenset[str]) -> Finding | None:
    times = [m for m in (review_minutes(pr, ai_reviewer_logins) for pr in prs) if m is not None]
    if len(times) < MIN_SAMPLE:
        return None
    p75 = percentile(times, 0.75)
    return Finding("review_time", f"First human review to merge: {minutes_text(median(times))} median, {minutes_text(p75)} p75 ({band_text('review', p75, minutes_text)}).")


def size_finding(prs: list[PullRequest]) -> Finding | None:
    sizes = [pr.changed_lines for pr in prs if pr.changed_lines]
    if len(sizes) < MIN_SAMPLE:
        return None
    p75 = percentile(sizes, 0.75)
    return Finding("size", f"PR size: {median(sizes):.0f} lines median, {p75:.0f} p75 ({band_text('size', p75, lambda v: f'{v:g}')}).")


def human_after_ai_finding(prs: list[PullRequest], ai_reviewer_logins: frozenset[str]) -> Finding | None:
    after_ai, without_ai = first_human_review_split(prs, ai_reviewer_logins)
    if len(after_ai) < MIN_SAMPLE or len(without_ai) < MIN_SAMPLE:
        return None
    with_median, without_median = median(after_ai), median(without_ai)
    if not without_median:
        return None
    gap = (with_median - without_median) / without_median
    pair = f"({minutes_text(with_median)} against {minutes_text(without_median)})"
    if abs(gap) < RELATIVE_GAP:
        return Finding("human_after_ai", f"People review about as fast with or without an AI reviewer first {pair}.")
    if gap > 0:
        return Finding("human_after_ai", f"People review {change_text(without_median, with_median)} later when an AI reviewer got there first {pair}. Do reviewers wait for the bot?")
    return Finding("human_after_ai", f"People review {change_text(without_median, with_median)} sooner when an AI reviewer got there first {pair}.")


def rework_finding(rework: ReworkResult | None) -> Finding | None:
    if rework is None or rework.rework_rate_21 is None or rework.lines_added < 500:
        return None
    text = f"Rework: {percent_text(rework.rework_rate_21)} of line changes in the last {rework.window_days} days rewrote code under 21 days old ({band_text('rework', rework.rework_rate_21, percent_text)})."
    if rework.churn_rate is not None:
        text += f" {percent_text(rework.churn_rate)} of new lines were deleted again within {rework.age_days} days."
    text += " If high, sample ten reworked PRs: missed decision, or the product moved?"
    return Finding("rework", text)


def build_findings(prs: list[PullRequest], ai_reviewer_logins: frozenset[str], rework: ReworkResult | None) -> list[Finding]:
    candidates = [
        throughput_finding(prs),
        cycle_time_finding(prs),
        pickup_finding(prs, ai_reviewer_logins),
        review_time_finding(prs, ai_reviewer_logins),
        human_after_ai_finding(prs, ai_reviewer_logins),
        size_finding(prs),
        rework_finding(rework),
    ]
    return [finding for finding in candidates if finding is not None]
