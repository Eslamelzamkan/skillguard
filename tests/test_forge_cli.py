import json

from conftest import AUTHOR_SCRIPTS, run_cli

FORGE = AUTHOR_SCRIPTS / "forge.py"


def test_init_creates_state_dirs(tmp_path):
    result = run_cli(FORGE, ["--state-dir", str(tmp_path), "init"])
    assert result.returncode == 0
    for sub in ("candidates", "staging", "library"):
        assert (tmp_path / sub).is_dir()
    for f in ("runs.jsonl", "gate_log.jsonl", "ledger.jsonl"):
        assert (tmp_path / f).exists()


def test_log_run_parses_reward_and_classifies_failure(tmp_path):
    run_cli(FORGE, ["--state-dir", str(tmp_path), "init"])
    run_dir = tmp_path / "attempt-1"
    run_dir.mkdir()
    (run_dir / "reward.txt").write_text("0", encoding="utf-8")
    stderr_file = tmp_path / "stderr.txt"
    stderr_file.write_text("FileNotFoundError: output.csv does not exist", encoding="utf-8")

    result = run_cli(FORGE, ["--state-dir", str(tmp_path), "log-run",
                             "--task-id", "t1", "--domain", "docs",
                             "--run-dir", str(run_dir), "--stderr-file", str(stderr_file)])
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert record["passed"] is False
    assert record["category"] == "missing_artifact"

    logged = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(logged)["task_id"] == "t1"


def test_log_run_passing_attempt_has_no_category(tmp_path):
    run_cli(FORGE, ["--state-dir", str(tmp_path), "init"])
    run_dir = tmp_path / "attempt-2"
    run_dir.mkdir()
    (run_dir / "reward.txt").write_text("1", encoding="utf-8")

    result = run_cli(FORGE, ["--state-dir", str(tmp_path), "log-run",
                             "--task-id", "t2", "--domain", "docs", "--run-dir", str(run_dir)])
    record = json.loads(result.stdout)
    assert record["passed"] is True
    assert record["category"] is None


def test_log_probe_records_self_observed_failure(tmp_path):
    run_cli(FORGE, ["--state-dir", str(tmp_path), "init"])
    result = run_cli(FORGE, ["--state-dir", str(tmp_path), "log-probe",
                             "--task-id", "t1", "--domain", "docs",
                             "--category", "crash", "--note", "pandas.read_docx does not exist"])
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert record["passed"] is False
    assert record["detail"]["self_probed"] is True

    logged = json.loads((tmp_path / "runs.jsonl").read_text(encoding="utf-8").strip())
    assert logged["category"] == "crash"


def test_status_reports_empty_library_initially(tmp_path):
    run_cli(FORGE, ["--state-dir", str(tmp_path), "init"])
    result = run_cli(FORGE, ["--state-dir", str(tmp_path), "status"])
    status = json.loads(result.stdout)
    assert status["library"] == []
    assert status["staging"] == []
