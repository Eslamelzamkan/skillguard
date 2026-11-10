import json

from conftest import AUTHOR_SCRIPTS, run_cli, write_jsonl

AGGREGATE = AUTHOR_SCRIPTS / "aggregate.py"


def _run(domain, category, i, passed=False):
    return {
        "run_id": f"{domain}-{category}-{i}", "task_id": f"t-{domain}-{i}", "domain": domain,
        "skill_loaded": None, "passed": passed, "category": category if not passed else None,
        "detail": {"failed_assertions": [{"assertion": "equality", "expected": "1", "actual": "2"}]}
                  if category == "quality_below_threshold" else {},
        "timestamp": "2026-01-01T00:00:00Z",
    }


def test_severity_thresholds_and_tie_break(tmp_path):
    runs = [
        _run("docs", "quality_below_threshold", 1),
        _run("docs", "quality_below_threshold", 2),
        _run("docs", "crash", 1),
        _run("docs", "crash", 2),
        _run("math", "timeout", 1),
        _run("math", "timeout", 2),
        _run("math", "timeout", 3),
        _run("rare", "missing_artifact", 1),
        _run("docs", "quality_below_threshold", 3, passed=True),  # ignored: passing run
    ]
    write_jsonl(tmp_path / "runs.jsonl", runs)

    result = run_cli(AGGREGATE, ["--state-dir", str(tmp_path)])
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)

    by_domain = {d["domain"]: d for d in report}
    assert by_domain["math"]["domain_severity"] == "high"
    assert by_domain["math"]["dominant_category"] == "timeout"
    assert by_domain["docs"]["domain_severity"] == "medium"
    # tie between quality_below_threshold(2) and crash(2) -> fixed priority picks quality_below_threshold
    assert by_domain["docs"]["dominant_category"] == "quality_below_threshold"
    assert by_domain["rare"]["domain_severity"] == "low"

    # ranked highest severity first
    severities = [d["domain_severity"] for d in report]
    assert severities.index("high") < severities.index("medium") < severities.index("low")


def test_quality_below_threshold_carries_assertion_samples(tmp_path):
    write_jsonl(tmp_path / "runs.jsonl", [_run("docs", "quality_below_threshold", 1)])

    result = run_cli(AGGREGATE, ["--state-dir", str(tmp_path)])
    report = json.loads(result.stdout)
    cat = next(c for c in report[0]["categories"] if c["category"] == "quality_below_threshold")
    assert cat["assertion_samples"][0]["expected"] == "1"


def test_empty_runs_produces_empty_report(tmp_path):
    write_jsonl(tmp_path / "runs.jsonl", [])
    result = run_cli(AGGREGATE, ["--state-dir", str(tmp_path)])
    assert json.loads(result.stdout) == []
