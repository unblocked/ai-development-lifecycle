from adlc.bots import is_automation_login
from adlc.model import PullRequest


def is_automation_authored(pr: PullRequest) -> bool:
    return is_automation_login(pr.author_login, pr.author_is_bot)


def partition(prs: list[PullRequest]) -> tuple[list[PullRequest], list[PullRequest]]:
    kept = [pr for pr in prs if not is_automation_authored(pr)]
    automation = [pr for pr in prs if is_automation_authored(pr)]
    return kept, automation
