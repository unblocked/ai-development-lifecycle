# adlc

Measure how fast one repository ships, on your own machine, and compare the numbers with industry benchmarks.

AI coding tools report acceptance rates, active users and lines generated. None of that says whether the team ships more. `adlc` looks at what happens after the code is written: how many pull requests merge, how long they take, how long people take to review them, how big they are, and how much new code gets rewritten.

It reads GitHub through your own `gh` login and prints the result in the terminal. Nothing is uploaded, and nothing is written to disk unless you ask.

## What it measures

| Metric | What it is |
| --- | --- |
| Throughput | Merged PRs per week, and per author per week |
| Open to merge | Time from PR open to merge |
| Time to first human review | Time from PR open to the first review by a person. Bots and AI reviewers are ignored. Also shown split by whether an AI reviewer had commented first |
| First human review to merge | Time from that first review to merge |
| PR size | Lines changed |
| Rework | Share of all line changes that rewrote code less than 21 days old, from `git blame`. Rework is a rough proxy for churn caused by AI: code that was generated, merged, and then had to be rewritten because it was wrong, sloppy or did not fit the codebase |

Times are reported as median and 75th percentile. Each 75th percentile is placed in a band from the [LinearB 2026 engineering benchmarks](https://linearb.helpdocs.io/article/d2v8kqzxzd-metrics-community-benchmarks): elite, good, fair or needs focus.

## Install

You need [uv](https://docs.astral.sh/uv/), `git` and the [GitHub CLI](https://cli.github.com/), signed in with `gh auth login`.

Run it without installing:

```bash
uvx --from git+https://github.com/unblocked/ai-development-lifecycle.git adlc baseline --since 90d
```

Or put `adlc` on your path:

```bash
uv tool install git+https://github.com/unblocked/ai-development-lifecycle.git
```

## Run it

From inside a full clone of the repository:

```bash
adlc baseline --since 90d
```

Or the most recent N merged pull requests, whatever their age:

```bash
adlc baseline --limit 3000
```

The clone must have full history. On a shallow clone `git blame` cannot date old lines, so `adlc` stops and tells you. Run `git fetch --unshallow`, or pass `--skip-rework`.

A run of 300 pull requests takes under a minute. The rework pass takes a few minutes on a large monorepo. Add `--skip-rework` for a quick first look.

No repository to hand? Run the bundled sample:

```bash
adlc baseline --sample
```

## What you get

```
Delivery baseline for cline/cline ─────────────────────────────────────────────────────────────────────
Measured on 2026-09-13. 299 merged pull requests covering the last 57.9 days of a 90 day window.
Metric                                            Value   Band, LinearB 2026 p75
───────────────────────────────────────────────────────────────────────────────────────────────────────
Pull requests                                       299
Merged per week                                    36.1
Merged per author per week                          1.9   good, 1.2 to 2
Open to merge, median                             4.0 h
Open to merge, 75th percentile                   34.6 h   fair, 18.0 h to 40.0 h for pickup plus review
Time to first human review, median                2.3 h
Time to first human review, 75th percentile      18.3 h   needs focus, over 16.0 h
Time to first human review, after an AI review   91 min
Time to first human review, no AI review first    5.7 h
First human review to merge, median              48 min
First human review to merge, 75th percentile     16.0 h   fair, 14.0 h to 24.0 h
PR size, median changed lines                       210
PR size, 75th percentile                            657   needs focus, over 228 lines
Rework rate, code under 21 days old rewritten        7%   fair, 5% to 8%
New code deleted again within 30 days                6%   own trend

What stands out
  • Merged PRs per author per week: 1.9 (good, 1.2 to 2).
  • Open to merge: 4.0 h median, 34.6 h p75 (fair, 18.0 h to 40.0 h for pickup plus review).
  • First human review: 2.3 h median, 18.3 h p75 (needs focus, over 16.0 h).
  • People review 73% sooner when an AI reviewer got there first (91 min against 5.7 h).
  • ...

Caveats
  • ...

What this report assumes
  • AI reviewers with code comments: greptile-apps (141 PRs), ...
  • ...
```

Add `--output-dir DIR` to also write the report as Markdown and JSON, or `--format markdown` or `--format json` to print one of those instead of the table.

## Options

| Flag | Default | What it does |
| --- | --- | --- |
| `--since 90d` | 90 days | Window for pull requests, capped at 1,000 |
| `--limit N` | off | The N most recent merged PRs instead of a window |
| `--skip-rework` | off | Skip the `git blame` pass |
| `--rework-window 30d` | 30 days | Commits to scan for rework |
| `--rework-age 30d` | 30 days | Age under which a deleted line counts as rework in the second rework row |
| `--ai-reviewer LOGIN` | built-in list | Treat this GitHub login as an AI reviewer. Repeatable |
| `--ignore-author LOGIN` | none | Drop PRs opened by this login, for mirror or sync bots. Repeatable |
| `--format table` | table | Print `table`, `markdown` or `json` |
| `--output-dir DIR` | off | Also write `adlc-baseline-YYYY-MM-DD.md` and `.json` into this directory |
| `--repo-path .` | current directory | Path to the clone |

## Reading the numbers

- Bands come from the [LinearB 2026 engineering benchmarks](https://linearb.helpdocs.io/article/d2v8kqzxzd-metrics-community-benchmarks).
- Compare a team with its own earlier baseline first, and with the benchmarks second.
- Report per team, never per person.
- Measure again in a quarter with the same window. The second measurement is the useful one.

## Related

- [engineering-social-graph](https://github.com/unblocked/engineering-social-graph): who reviews whom and where the experts are, from the same PR history
- [The Context Maturity Field Guide](https://getunblocked.com/context-maturity)

## License

MIT
