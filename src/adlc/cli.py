import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from importlib import resources
from pathlib import Path

from rich.console import Console

from adlc import __version__
from adlc.assumptions import build_assumptions
from adlc.attribution import partition
from adlc.findings import build_findings
from adlc.gitdata import GitError, ReworkResult, require_full_history, rework
from adlc.github import GitHubError, merged_pull_requests, repo_slug
from adlc.log import detail, log, step
from adlc.metrics import DEFAULT_AI_REVIEWER_LOGINS, span_weeks, summarize
from adlc.model import pull_request_from_dict
from adlc.report import build_baseline, to_json, to_markdown
from adlc.terminal import render

WINDOW_CAP = 1000


def parse_days(value: str) -> int:
    return int(value.strip().lower().removesuffix("d"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adlc", description="Measure how fast one repository ships and compare it with industry benchmarks.")
    parser.add_argument("--version", action="version", version=f"adlc {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    baseline = subparsers.add_parser("baseline", help="measure throughput, cycle time, review time, PR size and rework for one repository")
    baseline.add_argument("--repo-path", default=".", help="path to a local clone with a GitHub remote (default: current directory)")
    scope = baseline.add_mutually_exclusive_group()
    scope.add_argument("--since", default="90d", help="window for pull requests, for example 90d (default: 90d)")
    scope.add_argument("--limit", type=int, metavar="N", help="the N most recent merged pull requests, whatever their age, instead of a window")
    baseline.add_argument("--rework-window", default="30d", help="window of commits to scan for deletions (default: 30d)")
    baseline.add_argument("--rework-age", default="30d", help="a deleted line younger than this counts as rework (default: 30d)")
    baseline.add_argument("--skip-rework", action="store_true", help="skip the git blame pass, which is slow on large repositories")
    baseline.add_argument("--ai-reviewer", action="append", default=[], metavar="LOGIN", help="extra GitHub login to treat as an AI reviewer, repeatable")
    baseline.add_argument("--ignore-author", action="append", default=[], metavar="LOGIN", help="drop pull requests opened by this login, for mirror or sync bots, repeatable")
    baseline.add_argument("--output-dir", metavar="DIR", help="also write the report as Markdown and JSON into this directory")
    baseline.add_argument("--sample", action="store_true", help="run against the bundled sample dataset instead of a repository")
    baseline.add_argument("--format", choices=("table", "markdown", "json"), default="table", help="what to print (default: table)")
    return parser


def sample_data() -> dict:
    with resources.files("adlc.sample").joinpath("baseline-input.json").open() as handle:
        return json.load(handle)


def rework_from_dict(data: dict) -> ReworkResult:
    return ReworkResult(**data)


def run_baseline(args: argparse.Namespace) -> int:
    ai_reviewers = frozenset(DEFAULT_AI_REVIEWER_LOGINS | {login.lower() for login in args.ai_reviewer})
    window_days = None if args.limit else parse_days(args.since)
    limit = args.limit or WINDOW_CAP
    if args.sample:
        data = sample_data()
        repo = data["repo"]
        prs = [pull_request_from_dict(record) for record in data["pullRequests"]]
        rework_result = rework_from_dict(data["rework"])
        log(f"Using the bundled sample from {repo}. Nothing was fetched.")
    else:
        repo_path = Path(args.repo_path).resolve()
        repo = repo_slug(repo_path)
        rework_window = parse_days(args.rework_window)
        if not args.skip_rework:
            require_full_history(repo_path)
        total_steps = 2 if args.skip_rework else 3
        with ThreadPoolExecutor(max_workers=1) as background:
            rework_future = None
            if not args.skip_rework:
                step(1, total_steps, f"Scanning rework with git blame in the background, {rework_window} days of commits")
                rework_future = background.submit(rework, repo_path, rework_window, parse_days(args.rework_age))
            if window_days is None:
                step(2 if rework_future else 1, total_steps, f"Fetching the {limit} most recent merged pull requests for {repo}")
            else:
                step(2 if rework_future else 1, total_steps, f"Fetching merged pull requests for {repo} from the last {window_days} days")
            prs = merged_pull_requests(repo_path, window_days, limit, frozenset(login.lower() for login in args.ignore_author))
            detail(f"{len(prs)} pull requests fetched")
            if not prs:
                raise GitHubError("no merged pull requests came back, so there is nothing to measure")
            if rework_future:
                if not rework_future.done():
                    detail("Waiting for the rework scan to finish")
                rework_result = rework_future.result()
            else:
                rework_result = None
        step(total_steps, total_steps, "Computing metrics")
    kept, automation = partition(prs)
    baseline = build_baseline(
        repo=repo,
        measured_on=date.today(),
        window_days=window_days,
        summary=summarize(kept, ai_reviewers, span_weeks(kept)),
        automation_prs=len(automation),
        rework_result=rework_result,
        ai_reviewer_logins=sorted(ai_reviewers),
        limit=0 if args.sample else limit,
        findings=build_findings(kept, ai_reviewers, rework_result),
        assumptions=build_assumptions(kept, ai_reviewers),
    )
    if args.format == "markdown":
        print(to_markdown(baseline))
    elif args.format == "json":
        print(to_json(baseline), end="")
    else:
        render(baseline, Console())
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = f"adlc-baseline-{date.today().isoformat()}"
        (output_dir / f"{stem}.json").write_text(to_json(baseline))
        (output_dir / f"{stem}.md").write_text(to_markdown(baseline))
        log(f"[dim]Wrote {output_dir / stem}.md and {output_dir / stem}.json[/dim]")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "baseline":
            return run_baseline(args)
    except (GitError, GitHubError) as error:
        log(f"[red]adlc:[/red] {error}")
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
