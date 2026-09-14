import json
import re
import subprocess
import time
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

from adlc.bots import is_dependency_bot
from adlc.log import detail
from adlc.model import PullRequest, parse_time, pull_request_from_dict

PAGE_SIZE = 100

PULL_REQUESTS_QUERY = """
query($owner: String!, $name: String!, $pageSize: Int!, $cursor: String) {
  rateLimit { cost remaining resetAt }
  repository(owner: $owner, name: $name) {
    pullRequests(first: $pageSize, after: $cursor, states: [MERGED], orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        createdAt
        updatedAt
        mergedAt
        additions
        deletions
        author { login __typename }
        reviews(first: 50) { nodes { submittedAt state author { login __typename } comments(first: 1) { totalCount } } }
      }
    }
  }
}
"""


class GitHubError(RuntimeError):
    pass


class RateLimited(GitHubError):
    pass


def run_gh(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(["gh", *args], capture_output=True, text=True, errors="replace", cwd=cwd, check=False)
    if completed.returncode != 0:
        message = completed.stderr.strip() or f"gh {' '.join(args)} failed"
        if is_rate_limit(message):
            raise RateLimited(rate_limit_message())
        raise GitHubError(message)
    return completed.stdout


@cache
def repo_slug(repo_path: Path) -> str:
    return run_gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner", cwd=repo_path).strip()


RETRIES = 4


def graphql(query: str, variables: dict) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        flag = "-F" if isinstance(value, int) else "-f"
        args += [flag, f"{key}={value}"]
    for attempt in range(RETRIES):
        try:
            payload = json.loads(run_gh(*args))
            break
        except RateLimited:
            raise
        except GitHubError as error:
            if attempt == RETRIES - 1 or not is_transient(str(error)):
                raise
            time.sleep(2**attempt)
    if "errors" in payload and not payload.get("data"):
        message = json.dumps(payload["errors"])
        if is_rate_limit(message):
            raise RateLimited(rate_limit_message())
        raise GitHubError(message)
    return payload["data"]


def is_transient(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in ("connection reset", "timeout", "timed out", "502", "503", "504", "eof"))


def is_rate_limit(message: str) -> bool:
    return "rate limit" in message.lower()


def rate_limit_message() -> str:
    reset = graphql_reset_epoch()
    if reset is None:
        return "GitHub API rate limit reached. It resets within the hour."
    at = datetime.fromtimestamp(reset).astimezone()
    minutes = max(0, round((reset - time.time()) / 60))
    return f"GitHub API rate limit reached. It resets at {at:%H:%M} local time, in about {minutes} minutes."


def graphql_reset_epoch() -> int | None:
    completed = subprocess.run(["gh", "api", "graphql", "--include", "-f", "query={ viewer { login } }"], capture_output=True, text=True, errors="replace", check=False)
    match = re.search(r"^x-ratelimit-reset:\s*(\d+)", completed.stdout, re.IGNORECASE | re.MULTILINE)
    return int(match.group(1)) if match else None


def author_record(node: dict | None) -> dict:
    node = node or {}
    return {"login": node.get("login", "") or "", "is_bot": node.get("__typename") == "Bot"}


def record_from_node(node: dict) -> dict:
    return {
        "number": node["number"],
        "createdAt": node["createdAt"],
        "mergedAt": node["mergedAt"],
        "changedLines": int(node.get("additions") or 0) + int(node.get("deletions") or 0),
        "author": author_record(node.get("author")),
        "reviews": [
            {
                "submittedAt": review["submittedAt"],
                "state": review.get("state") or "",
                "codeComments": (review.get("comments") or {}).get("totalCount", 0),
                "author": author_record(review.get("author")),
            }
            for review in node["reviews"]["nodes"]
            if review.get("submittedAt")
        ],
    }


def merged_pull_requests(repo_path: Path, days: int | None, limit: int, ignored_authors: frozenset[str] = frozenset()) -> list[PullRequest]:
    owner, name = repo_slug(repo_path).split("/", 1)
    if days is None:
        return most_recently_merged(owner, name, limit, ignored_authors)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    prs: list[PullRequest] = []
    cursor = None
    stale_pages = 0
    page = 0
    skipped = 0
    while len(prs) < limit and stale_pages < 2:
        page += 1
        try:
            data = graphql(PULL_REQUESTS_QUERY, {"owner": owner, "name": name, "pageSize": min(PAGE_SIZE, limit - len(prs)), "cursor": cursor})
        except RateLimited as error:
            if not prs:
                raise
            budget_exhausted(len(prs), error)
            break
        connection = data["repository"]["pullRequests"]
        page_fresh = 0
        for node in connection["nodes"]:
            if parse_time(node["mergedAt"]) < cutoff:
                continue
            page_fresh += 1
            if wanted(node, ignored_authors):
                prs.append(pull_request_from_dict(record_from_node(node)))
            else:
                skipped += 1
            if len(prs) >= limit:
                break
        report_page(page, connection["nodes"], len(prs), skipped, data.get("rateLimit"))
        stale_pages = stale_pages + 1 if page_fresh == 0 else 0
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    return prs


def budget_exhausted(kept: int, error: RateLimited) -> None:
    detail(f"[yellow]{error} Continuing with the {kept} pull requests fetched so far.[/yellow]")


def report_page(page: int, nodes: list[dict], kept: int, skipped: int, rate_limit: dict | None) -> None:
    oldest = min((parse_time(node["mergedAt"]) for node in nodes), default=None)
    when = oldest.date().isoformat() if oldest else "n/a"
    budget = f", {rate_limit['remaining']} API points left" if rate_limit else ""
    detail(f"Page {page}: {len(nodes)} pull requests, oldest merged {when} [{kept} kept, {skipped} bot or ignored{budget}]")


def wanted(node: dict, ignored_authors: frozenset[str]) -> bool:
    login = (node.get("author") or {}).get("login", "") or ""
    return not is_dependency_bot(login) and login.lower() not in ignored_authors


def most_recently_merged(owner: str, name: str, count: int, ignored_authors: frozenset[str]) -> list[PullRequest]:
    collected: list[PullRequest] = []
    cursor = None
    page = 0
    skipped = 0
    while True:
        page += 1
        try:
            data = graphql(PULL_REQUESTS_QUERY, {"owner": owner, "name": name, "pageSize": PAGE_SIZE, "cursor": cursor})
        except RateLimited as error:
            if not collected:
                raise
            budget_exhausted(min(len(collected), count), error)
            break
        connection = data["repository"]["pullRequests"]
        nodes = connection["nodes"]
        if not nodes:
            break
        kept = [pull_request_from_dict(record_from_node(node)) for node in nodes if wanted(node, ignored_authors)]
        skipped += len(nodes) - len(kept)
        collected.extend(kept)
        collected.sort(key=lambda pr: pr.merged_at, reverse=True)
        report_page(page, nodes, min(len(collected), count), skipped, data.get("rateLimit"))
        oldest_update_walked = min(parse_time(node["updatedAt"]) for node in nodes)
        if len(collected) >= count and collected[count - 1].merged_at >= oldest_update_walked:
            break
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    return collected[:count]
