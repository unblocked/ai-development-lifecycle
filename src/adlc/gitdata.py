import os
import re
import subprocess
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from adlc.log import detail

DEFAULT_EXCLUDED_PATHS = re.compile(
    r"(^|/)(secrets?/|vendor/|node_modules/|dist/|build/|generated/)"
    r"|\.(patch|lock|snap|min\.js|min\.css|pb\.go|generated\.\w+)$"
    r"|(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|Cargo\.lock|poetry\.lock|Gemfile\.lock|go\.sum)$"
)


class GitError(RuntimeError):
    pass


def run_git(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise GitError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def is_shallow(repo_path: Path) -> bool:
    return run_git(repo_path, "rev-parse", "--is-shallow-repository").strip() == "true"


def require_full_history(repo_path: Path) -> None:
    if is_shallow(repo_path):
        raise GitError("This is a shallow clone. git blame dates every older line to the clone boundary, which makes the rework number meaningless. Run `git fetch --unshallow` and try again.")


@dataclass(frozen=True)
class ReworkResult:
    window_days: int
    age_days: int
    deleted_lines: int
    excluded_deleted_lines: int
    lines_added: int
    lines_added_then_deleted: int
    young_21_deleted_lines: int = 0

    @property
    def churn_rate(self) -> float | None:
        return self.lines_added_then_deleted / self.lines_added if self.lines_added else None

    @property
    def rework_rate_21(self) -> float | None:
        changed = self.lines_added + self.deleted_lines
        return self.young_21_deleted_lines / changed if changed else None


def lines_added(repo_path: Path, window_days: int, excluded: re.Pattern) -> int:
    total = 0
    for line in run_git(repo_path, "log", f"--since={window_days} days ago", "--no-merges", "--numstat", "--no-renames", "--format=").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and not excluded.search(parts[2]):
            total += int(parts[0])
    return total


HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))?", re.MULTILINE)
BLAME_SHA = re.compile(r"^[0-9a-f]{40} ")


DIFF_FILE = re.compile(r"^diff --git a/(.*?) b/(.*)$")


def deleted_ranges_by_file(repo_path: Path, sha: str) -> dict[str, list[tuple[int, int]]]:
    ranges: dict[str, list[tuple[int, int]]] = {}
    path = None
    for line in run_git(repo_path, "show", "--format=", "-U0", "--no-renames", sha).splitlines():
        header = DIFF_FILE.match(line)
        if header:
            path = header.group(1)
            continue
        hunk = HUNK_HEADER.match(line)
        if hunk and path:
            start, count = int(hunk.group(1)), int(hunk.group(2) or 1)
            if count:
                ranges.setdefault(path, []).append((start, count))
    return ranges


def blame_origins(repo_path: Path, sha: str, path: str, ranges: list[tuple[int, int]]) -> list[tuple[str, int]]:
    args = ["blame", "--line-porcelain"]
    for start, count in ranges:
        args += ["-L", f"{start},+{count}"]
    origins = []
    origin = None
    for line in run_git(repo_path, *args, f"{sha}^", "--", path).splitlines():
        if BLAME_SHA.match(line):
            origin = line.split()[0]
        elif line.startswith("author-time ") and origin:
            origins.append((origin, int(line.split()[1])))
    return origins


def scan_commit(job: tuple[str, str, int, str]) -> tuple[str, int, list[tuple[str, str, int]]]:
    repo, sha, deleted_at, excluded_pattern = job
    repo_path = Path(repo)
    excluded = re.compile(excluded_pattern)
    found = []
    try:
        by_file = deleted_ranges_by_file(repo_path, sha)
    except GitError:
        return sha, deleted_at, found
    for path, ranges in by_file.items():
        if excluded.search(path):
            found.extend((path, "", 0) for _ in range(sum(count for _, count in ranges)))
            continue
        try:
            origins = blame_origins(repo_path, sha, path, ranges)
        except GitError:
            continue
        for origin, author_time in origins:
            found.append((path, origin, author_time))
    return sha, deleted_at, found


def rework(
    repo_path: Path,
    window_days: int = 30,
    age_days: int = 30,
    excluded: re.Pattern = DEFAULT_EXCLUDED_PATHS,
    workers: int | None = None,
) -> ReworkResult:
    require_full_history(repo_path)
    window_commits = run_git(repo_path, "log", f"--since={window_days} days ago", "--no-merges", "--pretty=%H %ct").splitlines()
    window_shas = {line.split()[0] for line in window_commits}
    added = lines_added(repo_path, window_days, excluded)
    jobs = [(str(repo_path), sha, int(ts), excluded.pattern) for sha, ts in (line.split() for line in window_commits)]
    detail(f"Rework: {len(jobs)} commits in the last {window_days} days, {added} lines added")
    deleted = young_21 = excluded_deleted = added_then_deleted = 0
    checkpoint = max(1, len(jobs) // 10)
    with ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1)) as pool:
        for done, (_sha, deleted_at, found) in enumerate(pool.map(scan_commit, jobs, chunksize=4), start=1):
            if done % checkpoint == 0 or done == len(jobs):
                detail(f"Rework: blamed {done}/{len(jobs)} commits, {deleted} deleted lines so far")
            for path, origin, author_time in found:
                if excluded.search(path):
                    excluded_deleted += 1
                    continue
                deleted += 1
                if deleted_at - author_time < 21 * 86400:
                    young_21 += 1
                if deleted_at - author_time < age_days * 86400 and origin in window_shas:
                    added_then_deleted += 1
    return ReworkResult(
        window_days=window_days,
        age_days=age_days,
        deleted_lines=deleted,
        excluded_deleted_lines=excluded_deleted,
        lines_added=added,
        lines_added_then_deleted=added_then_deleted,
        young_21_deleted_lines=young_21,
    )
