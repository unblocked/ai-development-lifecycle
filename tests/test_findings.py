from datetime import UTC, datetime, timedelta

from adlc.findings import band, build_findings, cycle_time_finding, human_after_ai_finding, pickup_finding, review_time_finding, rework_finding, size_finding, split_halves, throughput_finding
from adlc.gitdata import ReworkResult
from adlc.metrics import DEFAULT_AI_REVIEWER_LOGINS
from adlc.model import PullRequest, Review

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


def pr(
    number: int, day: float, cycle_minutes: int, author: str = "alice", reviewers: tuple[str, ...] = ("bob",), review_after: int = 10, changed_lines: int = 0, ai_first: bool = False
) -> PullRequest:
    created = T0 + timedelta(days=day)
    reviews = [Review(author_login=login, author_is_bot=False, submitted_at=created + timedelta(minutes=review_after), state="APPROVED", code_comments=0) for login in reviewers]
    if ai_first:
        reviews.insert(0, Review(author_login="unblocked", author_is_bot=True, submitted_at=created + timedelta(minutes=2), state="COMMENTED", code_comments=2))
    return PullRequest(
        number=number,
        created_at=created,
        merged_at=created + timedelta(minutes=cycle_minutes),
        author_login=author,
        author_is_bot=False,
        reviews=tuple(reviews),
        changed_lines=changed_lines,
    )


def batch(start: int, count: int, cycle_minutes: int, **kwargs) -> list[PullRequest]:
    return [pr(start + i, day=i * 60 / count, cycle_minutes=cycle_minutes, **kwargs) for i in range(count)]


def test_split_halves_uses_the_midpoint_of_merge_dates():
    prs = [pr(1, 0, 10), pr(2, 10, 10), pr(3, 40, 10), pr(4, 60, 10)]
    early, late = split_halves(prs)
    assert [p.number for p in early] == [1, 2]
    assert [p.number for p in late] == [3, 4]


def test_throughput_reports_the_rate_and_the_trend():
    early = [pr(i, i, 60) for i in range(20)]
    late = [pr(100 + i, 40 + i * 0.5, 60) for i in range(40)]
    assert throughput_finding(early + late).text == "Merged PRs per author per week: 7.1 (elite, over 2). Up 95% across the window, 7.4 to 14.4."
    assert throughput_finding([pr(i, i, 60) for i in range(60)]).text == "Merged PRs per author per week: 7.1 (elite, over 2). Steady across the window."
    assert throughput_finding(early[:5]) is None


def test_cycle_time_names_the_benchmark_band():
    assert cycle_time_finding(batch(1, 30, 60)).text == "Open to merge: 60 min median, 60 min p75 (elite, under 4.0 h for pickup plus review)."
    assert cycle_time_finding(batch(1, 30, 10 * 60)).text == "Open to merge: 10.0 h median, 10.0 h p75 (good, 4.0 h to 18.0 h for pickup plus review)."
    assert cycle_time_finding(batch(1, 30, 100 * 60)).text == "Open to merge: 100.0 h median, 100.0 h p75 (needs focus, over 40.0 h for pickup plus review)."


def test_pickup_names_the_benchmark_band():
    assert pickup_finding(batch(1, 30, 60, review_after=30), DEFAULT_AI_REVIEWER_LOGINS).text == "First human review: 30 min median, 30 min p75 (elite, under 60 min)."
    assert pickup_finding(batch(1, 30, 60 * 24, review_after=10 * 60), DEFAULT_AI_REVIEWER_LOGINS).text == "First human review: 10.0 h median, 10.0 h p75 (fair, 4.0 h to 16.0 h)."
    assert review_time_finding(batch(1, 30, 60, review_after=30), DEFAULT_AI_REVIEWER_LOGINS).text == "First human review to merge: 30 min median, 30 min p75 (elite, under 3.0 h)."
    assert band("merge_frequency", 0.5) == "needs focus"
    assert band("size", 200) == "fair"


def test_size_names_the_benchmark_band():
    assert size_finding(batch(1, 30, 60, changed_lines=80)).text == "PR size: 80 lines median, 80 p75 (elite, under 100)."
    assert size_finding(batch(1, 30, 60, changed_lines=400)).text == "PR size: 400 lines median, 400 p75 (needs focus, over 228)."
    assert size_finding(batch(1, 30, 60)) is None


def test_human_after_ai_reading_in_both_directions():
    slower = batch(1, 25, 120, review_after=30, ai_first=True) + batch(100, 25, 120, review_after=20)
    assert human_after_ai_finding(slower, DEFAULT_AI_REVIEWER_LOGINS).text == "People review 50% later when an AI reviewer got there first (30 min against 20 min). Do reviewers wait for the bot?"
    faster = batch(1, 25, 120, review_after=10, ai_first=True) + batch(100, 25, 120, review_after=20)
    assert human_after_ai_finding(faster, DEFAULT_AI_REVIEWER_LOGINS).text == "People review 50% sooner when an AI reviewer got there first (10 min against 20 min)."
    same = batch(1, 25, 120, review_after=20, ai_first=True) + batch(100, 25, 120, review_after=21)
    assert human_after_ai_finding(same, DEFAULT_AI_REVIEWER_LOGINS).text == "People review about as fast with or without an AI reviewer first (20 min against 21 min)."
    assert human_after_ai_finding(batch(1, 5, 120, ai_first=True) + batch(100, 25, 120), DEFAULT_AI_REVIEWER_LOGINS) is None


def test_rework_reports_the_linearb_rate_with_a_band_and_the_churn_trend():
    assert (
        rework_finding(ReworkResult(30, 30, 1000, 0, 2000, 280, 60)).text
        == "Rework: 2% of line changes in the last 30 days rewrote code under 21 days old (elite, under 3%). 14% of new lines were deleted again within 30 days. If high, sample ten reworked PRs: missed decision, or the product moved?"
    )
    assert rework_finding(ReworkResult(30, 30, 1000, 0, 2000, 280, 300)).text.startswith("Rework: 10% of line changes in the last 30 days rewrote code under 21 days old (needs focus, over 8%).")
    assert rework_finding(ReworkResult(30, 30, 1000, 0, 100, 14, 5)) is None
    assert rework_finding(None) is None


def test_build_findings_orders_and_drops_missing():
    keys = [f.key for f in build_findings(batch(1, 30, 60, changed_lines=50), DEFAULT_AI_REVIEWER_LOGINS, None)]
    assert keys == ["throughput", "cycle_time", "pickup", "review_time", "size"]
