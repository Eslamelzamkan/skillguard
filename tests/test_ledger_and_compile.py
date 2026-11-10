import json

from conftest import REFINE_SCRIPTS, run_cli, write_candidate, write_jsonl

LEDGER = REFINE_SCRIPTS / "ledger.py"
COMPILE_CHECK = REFINE_SCRIPTS / "compile_check.py"

RUNS = [
    {"run_id": "r-fail", "task_id": "t1", "domain": "docs", "skill_loaded": None,
     "passed": False, "category": "quality_below_threshold", "detail": {}, "timestamp": "x"},
    {"run_id": "r-pass-t1", "task_id": "t1", "domain": "docs", "skill_loaded": "s",
     "passed": True, "category": None, "detail": {}, "timestamp": "x"},
    {"run_id": "r-pass-t2", "task_id": "t2", "domain": "docs", "skill_loaded": "s",
     "passed": True, "category": None, "detail": {}, "timestamp": "x"},
    {"run_id": "r-pass-t3", "task_id": "t3", "domain": "docs", "skill_loaded": "s",
     "passed": True, "category": None, "detail": {}, "timestamp": "x"},
]


def test_promote_moves_candidate_into_library(tmp_path):
    write_jsonl(tmp_path / "runs.jsonl", RUNS)
    write_candidate(tmp_path, "s", evidence_ids=["r-fail", "r-pass-t1"])

    result = run_cli(LEDGER, ["--state-dir", str(tmp_path), "promote", "s", "docs",
                              str(tmp_path / "candidates" / "s"), "--run-ids", "r-fail,r-pass-t1",
                              "--tier", "VERIFIED"])
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "library" / "s" / "SKILL.md").exists()
    entry = json.loads(result.stdout)
    assert entry["status"] == "VERIFIED"
    assert entry["counter"] == 3  # VERIFIED tier starts with the most slack


def test_promote_default_tier_is_diagnosed(tmp_path):
    # Cold-start default: no --tier -> DIAGNOSED, counter 1 (shortest leash).
    write_jsonl(tmp_path / "runs.jsonl", RUNS)
    write_candidate(tmp_path, "s", evidence_ids=["r-fail"])
    result = run_cli(LEDGER, ["--state-dir", str(tmp_path), "promote", "s", "docs",
                              str(tmp_path / "candidates" / "s"), "--run-ids", "r-fail"])
    entry = json.loads(result.stdout)
    assert entry["status"] == "DIAGNOSED"
    assert entry["counter"] == 1


def test_repeated_miss_archives_skill(tmp_path):
    write_jsonl(tmp_path / "runs.jsonl", RUNS)
    write_candidate(tmp_path, "s", evidence_ids=["r-fail", "r-pass-t1"])
    run_cli(LEDGER, ["--state-dir", str(tmp_path), "promote", "s", "docs",
                     str(tmp_path / "candidates" / "s"), "--run-ids", "r-fail,r-pass-t1",
                     "--tier", "OBSERVED"])  # counter 2

    run_cli(LEDGER, ["--state-dir", str(tmp_path), "outcome", "s", "--result", "miss"])
    result = run_cli(LEDGER, ["--state-dir", str(tmp_path), "outcome", "s", "--result", "miss"])

    entry = json.loads(result.stdout)
    assert entry["status"] == "ARCHIVED"
    assert entry["counter"] == 0
    assert not (tmp_path / "library" / "s").exists()
    assert (tmp_path / "archive" / "s" / "SKILL.md").exists()


def test_core_promotion_needs_three_distinct_tasks(tmp_path):
    write_jsonl(tmp_path / "runs.jsonl", RUNS)
    write_candidate(tmp_path, "s", evidence_ids=["r-fail", "r-pass-t1"])
    run_cli(LEDGER, ["--state-dir", str(tmp_path), "promote", "s", "docs",
                     str(tmp_path / "candidates" / "s"), "--run-ids", "r-fail,r-pass-t1",
                     "--tier", "VERIFIED"])

    run_cli(LEDGER, ["--state-dir", str(tmp_path), "outcome", "s", "--result", "hit", "--run-id", "r-pass-t2"])
    result = run_cli(LEDGER, ["--state-dir", str(tmp_path), "outcome", "s", "--result", "hit", "--run-id", "r-pass-t3"])

    entry = json.loads(result.stdout)
    assert entry["status"] == "CORE"


def test_revision_snapshots_prior_version(tmp_path):
    write_jsonl(tmp_path / "runs.jsonl", RUNS)
    write_candidate(tmp_path, "s", evidence_ids=["r-fail", "r-pass-t1"], body_extra="v1 content\n")
    run_cli(LEDGER, ["--state-dir", str(tmp_path), "promote", "s", "docs",
                     str(tmp_path / "candidates" / "s"), "--run-ids", "r-fail,r-pass-t1"])

    write_candidate(tmp_path, "s-revised", evidence_ids=["r-fail", "r-pass-t2"], body_extra="v2 content\n")
    result = run_cli(LEDGER, ["--state-dir", str(tmp_path), "promote", "s", "docs",
                              str(tmp_path / "candidates" / "s-revised"), "--run-ids", "r-pass-t2"])

    entry = json.loads(result.stdout)
    assert entry["version"] == 2
    assert (tmp_path / "library" / "_versions" / "s" / "v1" / "SKILL.md").exists()
    assert "v2 content" in (tmp_path / "library" / "s" / "SKILL.md").read_text()


def test_compile_check_flags_library_cap_and_consolidation(tmp_path):
    write_jsonl(tmp_path / "runs.jsonl", [])
    ledger_entries = []
    for i in range(9):
        name = f"skill-{i}"
        d = tmp_path / "library" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Use when doing task {i}.\n---\nbody\n", encoding="utf-8")
        domain = "docs" if i < 2 else f"domain-{i}"  # first two share a domain -> consolidation flag
        ledger_entries.append({"skill_name": name, "domain": domain, "status": "VERIFIED",
                                "hits": 0, "misses": 0, "counter": 2, "evidence_run_ids": [], "version": 1})
    write_jsonl(tmp_path / "ledger.jsonl", ledger_entries)

    result = run_cli(COMPILE_CHECK, ["--state-dir", str(tmp_path)])
    report = json.loads(result.stdout)
    assert result.returncode == 1  # 9 skills > cap of 8
    assert any("cap" in v for v in report["violations"])
    assert any(f["domain"] == "docs" for f in report["consolidation_flags"])


def test_compile_check_passes_clean_library(tmp_path):
    write_jsonl(tmp_path / "runs.jsonl", [])
    d = tmp_path / "library" / "solo-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: solo-skill\ndescription: Use when parsing radar captures.\n---\nbody\n", encoding="utf-8")
    write_jsonl(tmp_path / "ledger.jsonl", [{"skill_name": "solo-skill", "domain": "radar", "status": "VERIFIED",
                                              "hits": 0, "misses": 0, "counter": 2, "evidence_run_ids": [], "version": 1}])

    result = run_cli(COMPILE_CHECK, ["--state-dir", str(tmp_path)])
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["ok"] is True
