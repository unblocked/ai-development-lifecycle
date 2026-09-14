from datetime import UTC, datetime

from adlc.attribution import is_automation_authored, partition
from adlc.model import PullRequest

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


def pr(number: int, login: str, is_bot: bool = False) -> PullRequest:
    return PullRequest(number=number, created_at=T0, merged_at=T0, author_login=login, author_is_bot=is_bot)


def test_automation_authors_are_split_out():
    prs = [pr(1, "alice"), pr(2, "github-actions[bot]", True), pr(3, "svc-mirror"), pr(4, "claude[bot]", True)]
    kept, automation = partition(prs)
    assert [p.number for p in kept] == [1, 4]
    assert [p.number for p in automation] == [2, 3]
    assert is_automation_authored(pr(5, "robotics-team-lead")) is False
