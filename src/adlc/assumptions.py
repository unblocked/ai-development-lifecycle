from collections import Counter

from adlc.metrics import ai_reviews, has_any_review, human_reviews
from adlc.model import PullRequest

TOP_REVIEWERS = 5

FIXED_ASSUMPTIONS = [
    "All code is treated as AI-assisted. There is no agent-versus-human split.",
    "Only merged pull requests count. Commits straight to the default branch do not.",
    "A review is a human approval or change request, or any review with an inline code comment. Bot status comments are not reviews.",
    "Rework counts every young line deleted, including refactors and removed features.",
    "One repository is one team. A monorepo mixes teams.",
]


def review_counts(prs: list[PullRequest], ai_reviewer_logins: frozenset[str], human: bool) -> Counter[str]:
    counts: Counter[str] = Counter()
    for pr in prs:
        reviews = human_reviews(pr, ai_reviewer_logins) if human else ai_reviews(pr, ai_reviewer_logins)
        for login in {review.author_login for review in reviews if review.author_login}:
            counts[login] += 1
    return counts


def ai_reviewer_assumption(prs: list[PullRequest], ai_reviewer_logins: frozenset[str]) -> str:
    seen = review_counts(prs, ai_reviewer_logins, human=False)
    if seen:
        listed = ", ".join(f"{login} ({count} PRs)" for login, count in seen.most_common())
        return f"AI reviewers with code comments: {listed}. Their reviews are not timed as human reviews. Any bot with code comments counts as one."
    return "No AI reviewer left code comments. If one runs under a user account, pass --ai-reviewer LOGIN."


def top_reviewer_assumption(prs: list[PullRequest], ai_reviewer_logins: frozenset[str]) -> str:
    people = review_counts(prs, ai_reviewer_logins, human=True).most_common(TOP_REVIEWERS)
    if not people:
        return "No human reviews were found in this window."
    listed = ", ".join(f"{login} ({count})" for login, count in people)
    return f"Most active human reviewers: {listed}. If one is an AI tool under a user account, pass --ai-reviewer LOGIN."


def unreviewed_assumption(prs: list[PullRequest], ai_reviewer_logins: frozenset[str]) -> str:
    if not prs:
        return "No pull requests were found in this window."
    unreviewed = sum(1 for pr in prs if not has_any_review(pr, ai_reviewer_logins))
    return f"{unreviewed} of {len(prs)} pull requests had no review that counts and are left out of the review timings."


def build_assumptions(prs: list[PullRequest], ai_reviewer_logins: frozenset[str]) -> list[str]:
    return [ai_reviewer_assumption(prs, ai_reviewer_logins), top_reviewer_assumption(prs, ai_reviewer_logins), unreviewed_assumption(prs, ai_reviewer_logins), *FIXED_ASSUMPTIONS]
