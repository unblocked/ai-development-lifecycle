import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from adlc.gitdata import rework
from adlc.github import merged_pull_requests, repo_slug
from adlc.model import pull_request_to_dict


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: make_sample.py /path/to/full/clone [window_days] [rework_window_days] [ignored_author ...]", file=sys.stderr)
        return 2
    repo_path = Path(argv[1]).resolve()
    window_days = int(argv[2]) if len(argv) > 2 else 365
    rework_window = int(argv[3]) if len(argv) > 3 else 90
    slug = repo_slug(repo_path)
    prs = merged_pull_requests(repo_path, window_days, 300, frozenset(argv[4:]))
    result = rework(repo_path, rework_window, 30)
    data = {
        "repo": slug,
        "windowDays": window_days,
        "pullRequests": [pull_request_to_dict(pr) for pr in prs],
        "rework": asdict(result),
    }
    target = Path(__file__).resolve().parent.parent / "src" / "adlc" / "sample" / "baseline-input.json"
    target.write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote {target} with {len(prs)} pull requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
