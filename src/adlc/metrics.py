from dataclasses import dataclass
from statistics import median

from adlc.bots import is_bot_login
from adlc.model import PullRequest, Review


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


DEFAULT_AI_REVIEWER_LOGINS = frozenset(
    {"unblocked", "coderabbitai", "copilot-pull-request-reviewer", "greptile-apps", "cursor", "qodo-merge-pro", "sourcery-ai", "ellipsis-dev", "chatgpt-codex-connector", "devin-ai-integration"}
)
DECISION_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED"})


def is_ai_reviewer(review: Review, ai_reviewer_logins: frozenset[str]) -> bool:
    return review.author_login.lower() in ai_reviewer_logins or is_bot_login(review.author_login, review.author_is_bot)


def counts_as_review(review: Review, ai_reviewer_logins: frozenset[str]) -> bool:
    if review.code_comments is None:
        return True
    if is_ai_reviewer(review, ai_reviewer_logins):
        return review.code_comments > 0
    return review.state in DECISION_STATES or review.code_comments > 0


def counting_reviews(pr: PullRequest, ai_reviewer_logins: frozenset[str]) -> list[Review]:
    return [review for review in pr.reviews if counts_as_review(review, ai_reviewer_logins)]


def is_human_review(review: Review, ai_reviewer_logins: frozenset[str]) -> bool:
    return counts_as_review(review, ai_reviewer_logins) and not is_ai_reviewer(review, ai_reviewer_logins)


def human_reviews(pr: PullRequest, ai_reviewer_logins: frozenset[str]) -> list[Review]:
    return [review for review in pr.reviews if is_human_review(review, ai_reviewer_logins)]


def ai_reviews(pr: PullRequest, ai_reviewer_logins: frozenset[str]) -> list[Review]:
    return [review for review in counting_reviews(pr, ai_reviewer_logins) if is_ai_reviewer(review, ai_reviewer_logins)]


def has_any_review(pr: PullRequest, ai_reviewer_logins: frozenset[str] = DEFAULT_AI_REVIEWER_LOGINS) -> bool:
    return len(counting_reviews(pr, ai_reviewer_logins)) > 0


def cycle_time_minutes(pr: PullRequest) -> float:
    return (pr.merged_at - pr.created_at).total_seconds() / 60


def first_human_review_minutes(pr: PullRequest, ai_reviewer_logins: frozenset[str]) -> float | None:
    reviews = human_reviews(pr, ai_reviewer_logins)
    if not reviews:
        return None
    first = min(review.submitted_at for review in reviews)
    return (first - pr.created_at).total_seconds() / 60


def review_minutes(pr: PullRequest, ai_reviewer_logins: frozenset[str]) -> float | None:
    first = first_human_review_minutes(pr, ai_reviewer_logins)
    if first is None:
        return None
    return max(cycle_time_minutes(pr) - first, 0)


def first_ai_review_minutes(pr: PullRequest, ai_reviewer_logins: frozenset[str]) -> float | None:
    reviews = ai_reviews(pr, ai_reviewer_logins)
    if not reviews:
        return None
    first = min(review.submitted_at for review in reviews)
    return (first - pr.created_at).total_seconds() / 60


def ai_reviewed_before_human(pr: PullRequest, ai_reviewer_logins: frozenset[str]) -> bool | None:
    human = first_human_review_minutes(pr, ai_reviewer_logins)
    if human is None:
        return None
    ai = first_ai_review_minutes(pr, ai_reviewer_logins)
    return ai is not None and ai <= human


def first_human_review_split(prs: list[PullRequest], ai_reviewer_logins: frozenset[str]) -> tuple[list[float], list[float]]:
    after_ai: list[float] = []
    without_ai: list[float] = []
    for pr in prs:
        minutes = first_human_review_minutes(pr, ai_reviewer_logins)
        if minutes is None:
            continue
        (after_ai if ai_reviewed_before_human(pr, ai_reviewer_logins) else without_ai).append(minutes)
    return after_ai, without_ai


@dataclass(frozen=True)
class DeliverySummary:
    pull_requests: int
    median_cycle_minutes: float | None
    median_first_human_review_minutes: float | None
    reviewed_pull_requests: int
    weeks: float = 0
    active_authors: int = 0
    median_first_human_review_after_ai_minutes: float | None = None
    median_first_human_review_without_ai_minutes: float | None = None
    p75_cycle_minutes: float | None = None
    p75_first_human_review_minutes: float | None = None
    median_changed_lines: float | None = None
    p75_changed_lines: float | None = None
    median_review_minutes: float | None = None
    p75_review_minutes: float | None = None

    @property
    def merged_per_week(self) -> float | None:
        return self.pull_requests / self.weeks if self.weeks else None

    @property
    def merged_per_author_per_week(self) -> float | None:
        if not self.weeks or not self.active_authors:
            return None
        return self.pull_requests / self.active_authors / self.weeks


def span_weeks(prs: list[PullRequest]) -> float:
    if len(prs) < 2:
        return 0
    merged = [pr.merged_at for pr in prs]
    return max((max(merged) - min(merged)).total_seconds() / 604800, 1 / 7)


def summarize(prs: list[PullRequest], ai_reviewer_logins: frozenset[str] = DEFAULT_AI_REVIEWER_LOGINS, weeks: float | None = None) -> DeliverySummary:
    if not prs:
        return DeliverySummary(0, None, None, 0)
    cycle_times = [cycle_time_minutes(pr) for pr in prs]
    first_reviews = [minutes for minutes in (first_human_review_minutes(pr, ai_reviewer_logins) for pr in prs) if minutes is not None]
    reviewed = [pr for pr in prs if has_any_review(pr, ai_reviewer_logins)]
    after_ai, without_ai = first_human_review_split(prs, ai_reviewer_logins)
    sizes = [pr.changed_lines for pr in prs if pr.changed_lines]
    review_times = [m for m in (review_minutes(pr, ai_reviewer_logins) for pr in prs) if m is not None]
    return DeliverySummary(
        pull_requests=len(prs),
        median_cycle_minutes=median(cycle_times),
        median_first_human_review_minutes=median(first_reviews) if first_reviews else None,
        reviewed_pull_requests=len(reviewed),
        weeks=weeks if weeks is not None else span_weeks(prs),
        median_first_human_review_after_ai_minutes=median(after_ai) if after_ai else None,
        median_first_human_review_without_ai_minutes=median(without_ai) if without_ai else None,
        p75_cycle_minutes=percentile(cycle_times, 0.75),
        p75_first_human_review_minutes=percentile(first_reviews, 0.75) if first_reviews else None,
        median_changed_lines=median(sizes) if sizes else None,
        p75_changed_lines=percentile(sizes, 0.75) if sizes else None,
        median_review_minutes=median(review_times) if review_times else None,
        p75_review_minutes=percentile(review_times, 0.75) if review_times else None,
        active_authors=len({pr.author_login for pr in prs}),
    )
