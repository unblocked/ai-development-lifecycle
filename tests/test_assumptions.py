from datetime import UTC, datetime, timedelta

from adlc.assumptions import FIXED_ASSUMPTIONS, build_assumptions
from adlc.metrics import DEFAULT_AI_REVIEWER_LOGINS
from adlc.model import PullRequest, Review

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


def pr(number: int, reviewers: tuple[str, ...], code_comments: int | None = None, state: str = "") -> PullRequest:
    return PullRequest(
        number=number,
        created_at=T0,
        merged_at=T0 + timedelta(hours=1),
        author_login="alice",
        author_is_bot=False,
        reviews=tuple(
            Review(author_login=login, author_is_bot=login.endswith("[bot]") or login == "unblocked", submitted_at=T0 + timedelta(minutes=5), state=state, code_comments=code_comments)
            for login in reviewers
        ),
    )


def test_assumptions_name_the_ai_reviewer_and_the_top_people():
    prs = [pr(1, ("unblocked", "bob")), pr(2, ("unblocked", "bob")), pr(3, ("carol",)), pr(4, ())]
    lines = build_assumptions(prs, DEFAULT_AI_REVIEWER_LOGINS)
    assert lines[0] == "AI reviewers with code comments: unblocked (2 PRs). Their reviews are not timed as human reviews. Any bot with code comments counts as one."
    assert lines[1] == "Most active human reviewers: bob (2), carol (1). If one is an AI tool under a user account, pass --ai-reviewer LOGIN."
    assert lines[2] == "1 of 4 pull requests had no review that counts and are left out of the review timings."
    assert lines[3:] == FIXED_ASSUMPTIONS


def test_assumptions_say_when_no_ai_reviewer_was_seen():
    prs = [pr(1, ("bob",), state="APPROVED", code_comments=0), pr(2, ("graphite-app[bot]",), state="COMMENTED", code_comments=0)]
    lines = build_assumptions(prs, DEFAULT_AI_REVIEWER_LOGINS)
    assert lines[0] == "No AI reviewer left code comments. If one runs under a user account, pass --ai-reviewer LOGIN."
    assert lines[1].startswith("Most active human reviewers: bob (1).")
    assert lines[2].startswith("1 of 2 pull requests had no review that counts and are left out")
