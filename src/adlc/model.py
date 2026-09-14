from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Review:
    author_login: str
    author_is_bot: bool
    submitted_at: datetime
    state: str = ""
    code_comments: int | None = None


@dataclass(frozen=True)
class PullRequest:
    number: int
    created_at: datetime
    merged_at: datetime
    author_login: str
    author_is_bot: bool
    reviews: tuple[Review, ...] = field(default_factory=tuple)
    changed_lines: int = 0


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def pull_request_from_dict(data: dict) -> PullRequest:
    reviews = tuple(
        Review(
            author_login=review.get("author", {}).get("login", "") or "",
            author_is_bot=bool(review.get("author", {}).get("is_bot", False)),
            submitted_at=parse_time(review["submittedAt"]),
            state=review.get("state", "") or "",
            code_comments=None if review.get("codeComments") is None else int(review["codeComments"]),
        )
        for review in data.get("reviews", [])
        if review.get("submittedAt")
    )
    author = data.get("author", {}) or {}
    return PullRequest(
        number=int(data["number"]),
        created_at=parse_time(data["createdAt"]),
        merged_at=parse_time(data["mergedAt"]),
        author_login=author.get("login", "") or "",
        author_is_bot=bool(author.get("is_bot", False)),
        reviews=reviews,
        changed_lines=int(data.get("changedLines", 0) or 0),
    )


def pull_request_to_dict(pr: PullRequest) -> dict:
    return {
        "number": pr.number,
        "createdAt": pr.created_at.isoformat(),
        "mergedAt": pr.merged_at.isoformat(),
        "author": {"login": pr.author_login, "is_bot": pr.author_is_bot},
        "changedLines": pr.changed_lines,
        "reviews": [
            {
                "author": {"login": review.author_login, "is_bot": review.author_is_bot},
                "submittedAt": review.submitted_at.isoformat(),
                "state": review.state,
                "codeComments": review.code_comments,
            }
            for review in pr.reviews
        ],
    }
