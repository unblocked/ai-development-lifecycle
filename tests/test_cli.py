import json
from pathlib import Path

import pytest

from adlc.cli import build_parser, main, parse_days


def test_parse_days_accepts_suffix():
    assert parse_days("90d") == 90
    assert parse_days("30") == 30


def test_sample_baseline_prints_a_table_and_writes_nothing(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["baseline", "--sample"]) == 0
    assert list(tmp_path.iterdir()) == []
    out = capsys.readouterr().out
    assert "Delivery baseline for" in out
    assert "Band, LinearB 2026 p75" in out
    assert "What stands out" in out


def test_output_dir_writes_markdown_and_json(tmp_path: Path, capsys):
    assert main(["baseline", "--sample", "--output-dir", str(tmp_path)]) == 0
    written = sorted(path.name for path in tmp_path.iterdir())
    assert len(written) == 2
    assert written[0].endswith(".json") and written[1].endswith(".md")
    data = json.loads((tmp_path / written[0]).read_text())
    assert data["tool"] == "adlc"
    assert data["pullRequests"]["pull_requests"] > 0
    assert data["findings"]


def test_markdown_format_prints_the_markdown_report(tmp_path: Path, capsys):
    assert main(["baseline", "--sample", "--format", "markdown"]) == 0
    assert capsys.readouterr().out.startswith("# Delivery baseline for ")


def test_json_format_prints_the_json_report(tmp_path: Path, capsys):
    assert main(["baseline", "--sample", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "adlc"


def test_limit_and_since_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["baseline", "--since", "30d", "--limit", "500"])


def test_limit_is_a_count_scope():
    args = build_parser().parse_args(["baseline", "--limit", "500"])
    assert args.limit == 500
    assert args.since == "90d"
