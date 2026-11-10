"""End-to-end integration of the deterministic evolution backbone, driving the
shipped CLIs exactly as the organizer's agent would (subprocess, no cross-skill
imports, no Docker, no LLM). Proves the full lifecycle composes:

  init -> fail-run -> author+gate(SHIP/DIAGNOSED) -> pass-run
       -> author+gate(SHIP/VERIFIED) -> promote -> compile_check(ok)
       -> outcomes -> CORE
"""
import json

from conftest import AUTHOR_SCRIPTS, run_cli, write_candidate

FORGE = AUTHOR_SCRIPTS / "forge.py"
GATE = AUTHOR_SCRIPTS / "safety_gate.py"       # bundled copy in skill-creator
LEDGER = AUTHOR_SCRIPTS / "ledger.py"
COMPILE = AUTHOR_SCRIPTS / "compile_check.py"


def _log_run(state, task, domain, passed, skill=None, run_id=None, reward="0"):
    run_dir = state / f"attempt-{run_id or task}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "reward.txt").write_text("1" if passed else reward, encoding="utf-8")
    args = ["--state-dir", str(state), "log-run", "--task-id", task,
            "--domain", domain, "--run-dir", str(run_dir)]
    if skill:
        args += ["--skill", skill]
    if run_id:
        args += ["--run-id", run_id]
    if not passed:
        # give the failure a classified stderr so aggregate has something concrete
        se = state / f"se-{run_id or task}.txt"
        se.write_text("AssertionError: expected 0.95, got 0.80", encoding="utf-8")
        args += ["--stderr-file", str(se)]
    r = run_cli(FORGE, args)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["run_id"]


def test_full_evolution_cycle(tmp_path):
    state = tmp_path / ".skill-forge"
    assert run_cli(FORGE, ["--state-dir", str(state), "init"]).returncode == 0

    # 1. attempt the task with no skill -> fail
    rid_fail = _log_run(state, "docs-task-1", "docs", passed=False, run_id="r-fail")

    # aggregate surfaces the failing domain deterministically
    agg = json.loads(run_cli(FORGE, ["--state-dir", str(state), "aggregate"]).stdout)
    assert agg and agg[0]["domain"] == "docs"

    # 2. author a candidate citing only the failure -> gate SHIPs it as DIAGNOSED
    #    (the robustness change: it ships even without a fail->pass pair).
    write_candidate(state, "docx-precision", evidence_ids=[rid_fail],
                    body_extra="Use python-docx set_cell_text with exact rounding.\n")
    g1 = run_cli(GATE, [str(state / "candidates" / "docx-precision"), "--state-dir", str(state)])
    assert g1.returncode == 0, g1.stdout
    assert json.loads(g1.stdout)["tier"] == "DIAGNOSED"

    # 3. the shipped skill is tried on the same domain -> pass
    rid_pass = _log_run(state, "docs-task-1", "docs", passed=True,
                        skill="docx-precision", run_id="r-pass")

    # 4. re-author citing the now-paired evidence -> gate SHIPs as VERIFIED
    write_candidate(state, "docx-precision", evidence_ids=[rid_fail, rid_pass],
                    body_extra="Use python-docx set_cell_text with exact rounding.\n")
    g2 = run_cli(GATE, [str(state / "candidates" / "docx-precision"), "--state-dir", str(state)])
    assert g2.returncode == 0, g2.stdout
    assert json.loads(g2.stdout)["tier"] == "VERIFIED"

    # 5. promote at the VERIFIED tier -> physically in library/
    p = run_cli(LEDGER, ["--state-dir", str(state), "promote", "docx-precision", "docs",
                         str(state / "candidates" / "docx-precision"),
                         "--run-ids", f"{rid_fail},{rid_pass}", "--tier", "VERIFIED"])
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["status"] == "VERIFIED"
    assert (state / "library" / "docx-precision" / "SKILL.md").exists()

    # 6. library passes the compliance caps
    c = run_cli(COMPILE, ["--state-dir", str(state)])
    assert c.returncode == 0, c.stdout
    assert json.loads(c.stdout)["ok"] is True

    # 7. two more paired confirmations on DISTINCT tasks -> CORE
    rp2 = _log_run(state, "docs-task-2", "docs", passed=True, skill="docx-precision", run_id="r-p2")
    run_cli(LEDGER, ["--state-dir", str(state), "outcome", "docx-precision",
                     "--result", "hit", "--run-id", rp2])
    rp3 = _log_run(state, "docs-task-3", "docs", passed=True, skill="docx-precision", run_id="r-p3")
    final = run_cli(LEDGER, ["--state-dir", str(state), "outcome", "docx-precision",
                             "--result", "hit", "--run-id", rp3])
    assert json.loads(final.stdout)["status"] == "CORE"


def test_regression_archives_skill_out_of_library(tmp_path):
    """A promoted skill that then fails repeatedly removes itself (anti-error-
    propagation) - end-to-end via the CLIs."""
    state = tmp_path / ".skill-forge"
    run_cli(FORGE, ["--state-dir", str(state), "init"])
    rid_fail = _log_run(state, "t", "docs", passed=False, run_id="r-fail")
    rid_pass = _log_run(state, "t", "docs", passed=True, skill="s", run_id="r-pass")
    write_candidate(state, "s", evidence_ids=[rid_fail, rid_pass])
    run_cli(LEDGER, ["--state-dir", str(state), "promote", "s", "docs",
                     str(state / "candidates" / "s"), "--run-ids", f"{rid_fail},{rid_pass}",
                     "--tier", "VERIFIED"])
    assert (state / "library" / "s").exists()

    # VERIFIED starts the counter at 3 (more slack). Two misses -> counter 1,
    # still alive; the third -> 0 -> archived, gone from library.
    run_cli(LEDGER, ["--state-dir", str(state), "outcome", "s", "--result", "miss"])
    r2 = run_cli(LEDGER, ["--state-dir", str(state), "outcome", "s", "--result", "miss"])
    assert json.loads(r2.stdout)["status"] != "ARCHIVED"
    assert (state / "library" / "s").exists()
    r3 = run_cli(LEDGER, ["--state-dir", str(state), "outcome", "s", "--result", "miss"])
    assert json.loads(r3.stdout)["status"] == "ARCHIVED"
    assert not (state / "library" / "s").exists()
    assert (state / "archive" / "s" / "SKILL.md").exists()


def test_diagnosed_skill_shortest_leash(tmp_path):
    """A DIAGNOSED (cold-start, unpaired) skill ships but is on the shortest
    leash: a single observed miss archives it."""
    state = tmp_path / ".skill-forge"
    run_cli(FORGE, ["--state-dir", str(state), "init"])
    rid = _log_run(state, "t", "docs", passed=False, run_id="r-probe")
    write_candidate(state, "d", evidence_ids=[rid])
    g = run_cli(GATE, [str(state / "candidates" / "d"), "--state-dir", str(state)])
    assert json.loads(g.stdout)["tier"] == "DIAGNOSED"
    run_cli(LEDGER, ["--state-dir", str(state), "promote", "d", "docs",
                     str(state / "candidates" / "d"), "--run-ids", rid, "--tier", "DIAGNOSED"])
    assert (state / "library" / "d").exists()
    r = run_cli(LEDGER, ["--state-dir", str(state), "outcome", "d", "--result", "miss"])
    assert json.loads(r.stdout)["status"] == "ARCHIVED"  # counter 1 -> 0 on one miss
    assert not (state / "library" / "d").exists()
