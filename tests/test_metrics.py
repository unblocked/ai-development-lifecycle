from datetime import UTC, datetime, timedelta

from adlc.metrics import (
    DEFAULT_AI_REVIEWER_LOGINS,
    ai_reviewed_before_human,
    counts_as_review,
    first_human_review_minutes,
    first_human_review_split,
    has_any_review,
    is_ai_reviewer,
    is_human_review,
    percentile,
    span_weeks,
    summarize,
)
from adlc.model import PullRequest, Review

T0 = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def review(login: str, minutes_after: int, is_bot: bool = False, state: str = "", code_comments: int | None = None) -> Review:
    return Review(author_login=login, author_is_bot=is_bot, submitted_at=T0 + timedelta(minutes=minutes_after), state=state, code_comments=code_comments)


def pr(number: int, cycle_minutes: int, reviews: tuple[Review, ...] = ()) -> PullRequest:
    return PullRequest(
        number=number,
        created_at=T0,
        merged_at=T0 + timedelta(minutes=cycle_minutes),
        author_login="alice",
        author_is_bot=False,
        reviews=reviews,
    )


def test_ai_reviewer_and_bots_are_not_human():
    assert is_human_review(review("unblocked", 2), DEFAULT_AI_REVIEWER_LOGINS) is False
    assert is_human_review(review("coderabbitai", 2), DEFAULT_AI_REVIEWER_LOGINS) is False
    assert is_human_review(review("github-actions[bot]", 2), DEFAULT_AI_REVIEWER_LOGINS) is False
    assert is_human_review(review("some-app", 2, is_bot=True), DEFAULT_AI_REVIEWER_LOGINS) is False
    assert is_human_review(review("bob", 2), DEFAULT_AI_REVIEWER_LOGINS) is True


def test_bot_reviews_without_code_comments_are_not_reviews():
    graphite = review("graphite-app", 1, is_bot=True, state="COMMENTED", code_comments=0)
    unblocked = review("unblocked", 2, is_bot=True, state="COMMENTED", code_comments=3)
    unlisted_bot = review("some-review-app", 2, is_bot=True, state="COMMENTED", code_comments=1)
    assert counts_as_review(graphite, DEFAULT_AI_REVIEWER_LOGINS) is False
    assert counts_as_review(unblocked, DEFAULT_AI_REVIEWER_LOGINS) is True
    assert counts_as_review(unlisted_bot, DEFAULT_AI_REVIEWER_LOGINS) is True
    assert is_ai_reviewer(unlisted_bot, DEFAULT_AI_REVIEWER_LOGINS) is True
    assert has_any_review(pr(1, 60, reviews=(graphite,)), DEFAULT_AI_REVIEWER_LOGINS) is False
    assert has_any_review(pr(2, 60, reviews=(unblocked,)), DEFAULT_AI_REVIEWER_LOGINS) is True


def test_human_reviews_count_on_a_decision_or_a_code_comment():
    approve = review("bob", 5, state="APPROVED", code_comments=0)
    changes = review("bob", 5, state="CHANGES_REQUESTED", code_comments=0)
    inline = review("bob", 5, state="COMMENTED", code_comments=2)
    drive_by = review("bob", 5, state="COMMENTED", code_comments=0)
    legacy = review("bob", 5)
    assert is_human_review(approve, DEFAULT_AI_REVIEWER_LOGINS) is True
    assert is_human_review(changes, DEFAULT_AI_REVIEWER_LOGINS) is True
    assert is_human_review(inline, DEFAULT_AI_REVIEWER_LOGINS) is True
    assert is_human_review(drive_by, DEFAULT_AI_REVIEWER_LOGINS) is False
    assert is_human_review(legacy, DEFAULT_AI_REVIEWER_LOGINS) is True


def test_ai_review_only_ignores_status_bots():
    prs = [
        pr(1, 10, reviews=(review("graphite-app", 1, is_bot=True, state="COMMENTED", code_comments=0),)),
        pr(2, 10, reviews=(review("unblocked", 1, is_bot=True, state="COMMENTED", code_comments=2),)),
        pr(3, 10, reviews=(review("unblocked", 1, is_bot=True, state="COMMENTED", code_comments=2), review("bob", 5, state="APPROVED", code_comments=0))),
    ]
    summary = summarize(prs, DEFAULT_AI_REVIEWER_LOGINS)
    assert summary.reviewed_pull_requests == 2


def test_first_human_review_splits_by_whether_ai_commented_first():
    ai_first = pr(1, 60, reviews=(review("unblocked", 2, is_bot=True, code_comments=2), review("bob", 30, state="APPROVED", code_comments=0)))
    human_first = pr(2, 60, reviews=(review("bob", 10, state="APPROVED", code_comments=0), review("unblocked", 12, is_bot=True, code_comments=2)))
    no_ai = pr(3, 60, reviews=(review("carol", 20, state="APPROVED", code_comments=0),))
    status_only = pr(4, 60, reviews=(review("graphite-app", 1, is_bot=True, code_comments=0), review("carol", 40, state="APPROVED", code_comments=0)))
    assert ai_reviewed_before_human(ai_first, DEFAULT_AI_REVIEWER_LOGINS) is True
    assert ai_reviewed_before_human(human_first, DEFAULT_AI_REVIEWER_LOGINS) is False
    assert ai_reviewed_before_human(status_only, DEFAULT_AI_REVIEWER_LOGINS) is False
    assert ai_reviewed_before_human(pr(5, 60), DEFAULT_AI_REVIEWER_LOGINS) is None
    after_ai, without_ai = first_human_review_split([ai_first, human_first, no_ai, status_only], DEFAULT_AI_REVIEWER_LOGINS)
    assert after_ai == [30]
    assert without_ai == [10, 20, 40]
    summary = summarize([ai_first, human_first, no_ai, status_only], DEFAULT_AI_REVIEWER_LOGINS)
    assert summary.median_first_human_review_after_ai_minutes == 30
    assert summary.median_first_human_review_without_ai_minutes == 20


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 0.75) == 3.25
    assert percentile([5], 0.75) == 5


def test_summarize_reports_p75_and_pr_size():
    prs = [pr(i, 10 * (i + 1), reviews=(review("bob", 5 * (i + 1)),)) for i in range(4)]
    sized = [PullRequest(**{**p.__dict__, "changed_lines": 100 * (i + 1)}) for i, p in enumerate(prs)]
    summary = summarize(sized, DEFAULT_AI_REVIEWER_LOGINS)
    assert summary.p75_cycle_minutes == 32.5
    assert summary.p75_first_human_review_minutes == 16.25
    assert summary.median_changed_lines == 250
    assert summary.p75_changed_lines == 325


def test_first_human_review_ignores_the_ai_reviewer():
    sample = pr(1, 60, reviews=(review("unblocked", 2), review("bob", 15)))
    assert first_human_review_minutes(sample, DEFAULT_AI_REVIEWER_LOGINS) == 15


def test_first_human_review_is_none_when_only_bots_reviewed():
    sample = pr(1, 60, reviews=(review("unblocked", 2),))
    assert first_human_review_minutes(sample, DEFAULT_AI_REVIEWER_LOGINS) is None


def test_summarize_uses_medians_and_reviewed_prs_only():
    prs = [
        pr(1, 10, reviews=(review("bob", 5),)),
        pr(2, 20, reviews=(review("unblocked", 1),)),
        pr(3, 1000, reviews=(review("carol", 30),)),
        pr(4, 5),
    ]
    summary = summarize(prs, DEFAULT_AI_REVIEWER_LOGINS)
    assert summary.pull_requests == 4
    assert summary.median_cycle_minutes == 15
    assert summary.median_first_human_review_minutes == 17.5
    assert summary.reviewed_pull_requests == 3


def test_has_any_review():
    assert has_any_review(pr(1, 5)) is False
    assert has_any_review(pr(1, 5, reviews=(review("unblocked", 1),))) is True


def test_summarize_empty():
    summary = summarize([], DEFAULT_AI_REVIEWER_LOGINS)
    assert summary.pull_requests == 0
    assert summary.median_cycle_minutes is None
    assert summary.reviewed_pull_requests == 0


def test_throughput_uses_window_weeks_and_distinct_authors():
    prs = [pr(1, 10), pr(2, 10), pr(3, 10), pr(4, 10)]
    summary = summarize(prs, DEFAULT_AI_REVIEWER_LOGINS, weeks=2)
    assert summary.weeks == 2
    assert summary.active_authors == 1
    assert summary.merged_per_week == 2
    assert summary.merged_per_author_per_week == 2


def test_span_weeks_from_merge_dates():
    first = pr(1, 10)
    later = PullRequest(
        number=2,
        created_at=T0,
        merged_at=T0 + timedelta(days=14, minutes=10),
        author_login="bob",
        author_is_bot=False,
    )
    assert span_weeks([first, later]) == 2
    assert span_weeks([first]) == 0
