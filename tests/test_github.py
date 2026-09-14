from adlc import github
from adlc.github import most_recently_merged


def node(number: int, merged: str, updated: str) -> dict:
    return {
        "number": number,
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": updated,
        "mergedAt": merged,
        "additions": 1,
        "deletions": 0,
        "author": {"login": "dev"},
        "reviews": {"nodes": []},
    }


def pages(*page_nodes: list[dict]):
    calls: list[dict] = []

    def fake_graphql(query: str, variables: dict) -> dict:
        calls.append(variables)
        index = int(variables["cursor"] or 0)
        has_next = index + 1 < len(page_nodes)
        return {"repository": {"pullRequests": {"nodes": page_nodes[index], "pageInfo": {"hasNextPage": has_next, "endCursor": str(index + 1)}}}}

    return fake_graphql, calls


def test_most_recently_merged_keeps_paging_past_old_prs_that_were_touched_recently(monkeypatch):
    fake, calls = pages(
        [node(1, "2026-03-01T00:00:00Z", "2026-09-10T00:00:00Z"), node(2, "2026-09-09T00:00:00Z", "2026-09-09T00:00:00Z")],
        [node(3, "2026-09-08T00:00:00Z", "2026-09-08T00:00:00Z"), node(4, "2026-09-07T00:00:00Z", "2026-09-07T12:00:00Z")],
        [node(5, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")],
    )
    monkeypatch.setattr(github, "graphql", fake)
    prs = most_recently_merged("acme", "widgets", 2, frozenset())
    assert [pr.number for pr in prs] == [2, 3]
    assert len(calls) == 2


def test_most_recently_merged_stops_at_the_last_page(monkeypatch):
    fake, calls = pages([node(1, "2026-09-01T00:00:00Z", "2026-09-10T00:00:00Z")])
    monkeypatch.setattr(github, "graphql", fake)
    prs = most_recently_merged("acme", "widgets", 5, frozenset())
    assert [pr.number for pr in prs] == [1]
    assert len(calls) == 1


def test_most_recently_merged_drops_dependency_bots(monkeypatch):
    bot = node(9, "2026-09-09T12:00:00Z", "2026-09-09T12:00:00Z")
    bot["author"] = {"login": "dependabot[bot]"}
    fake, _ = pages([bot, node(2, "2026-09-09T00:00:00Z", "2026-09-09T00:00:00Z")])
    monkeypatch.setattr(github, "graphql", fake)
    assert [pr.number for pr in most_recently_merged("acme", "widgets", 2, frozenset())] == [2]


def test_rate_limit_errors_are_recognised_in_either_form():
    assert github.is_rate_limit("API rate limit already exceeded for user ID 1")
    assert github.is_rate_limit('[{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]')
    assert not github.is_rate_limit("connection reset by peer")


def test_rate_limit_on_the_first_page_is_raised(monkeypatch):
    def exhausted(query: str, variables: dict) -> dict:
        raise github.RateLimited("GitHub API rate limit reached.")

    monkeypatch.setattr(github, "graphql", exhausted)
    try:
        most_recently_merged("acme", "widgets", 5, frozenset())
    except github.RateLimited as error:
        assert "rate limit" in str(error)
    else:
        raise AssertionError("expected RateLimited")


def test_rate_limit_after_a_page_keeps_what_was_fetched(monkeypatch):
    calls: list[int] = []

    def one_page_then_exhausted(query: str, variables: dict) -> dict:
        calls.append(1)
        if len(calls) > 1:
            raise github.RateLimited("GitHub API rate limit reached.")
        return {"repository": {"pullRequests": {"nodes": [node(1, "2026-09-01T00:00:00Z", "2026-09-10T00:00:00Z")], "pageInfo": {"hasNextPage": True, "endCursor": "1"}}}}

    monkeypatch.setattr(github, "graphql", one_page_then_exhausted)
    monkeypatch.setattr(github, "detail", lambda message: None)
    assert [pr.number for pr in most_recently_merged("acme", "widgets", 5, frozenset())] == [1]


def test_reset_time_comes_from_the_graphql_response_headers(monkeypatch):
    class Completed:
        stdout = "HTTP/2.0 200 OK\nX-Ratelimit-Limit: 5000\nX-Ratelimit-Remaining: 0\nX-Ratelimit-Reset: 1789342195\n\n{}"

    monkeypatch.setattr(github.subprocess, "run", lambda *args, **kwargs: Completed())
    assert github.graphql_reset_epoch() == 1789342195
