#!/usr/bin/env python3
"""Skill-Forge CLI (skill-creator). Stdlib only, no network.

Subcommands:
  init                  create the state directory structure
  log-run               record one verifier-scored task attempt (reward.txt-backed)
  log-probe             record a self-observed failure with no verifier score yet
                         (cold-start case: authoring happens before any solver/verifier
                         run exists for this task - see skill-creator/SKILL.md)
  aggregate             print the deterministic failure-aggregation report
  status                print current library / staging / ledger summary

State directory defaults to ./.skill-forge (override with --state-dir or
SKILL_FORGE_STATE). All three meta-skills (skill-creator, forge-gate,
forge-refine) share this directory via plain files - no cross-skill Python
imports, since the harness may load each skill's folder independently.
"""
import argparse
import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import state_dir, ensure_state_dirs, append_jsonl, read_jsonl, make_run_record, FAILURE_CATEGORIES  # noqa: E402
from run_logger import build_raw_facts, classify  # noqa: E402
import aggregate as aggregate_mod  # noqa: E402

_counter = itertools.count(1)


def cmd_init(args):
    base = ensure_state_dirs(state_dir(args.state_dir))
    print(f"initialized {base.resolve()}")


def cmd_log_run(args):
    base = state_dir(args.state_dir)
    ensure_state_dirs(base)

    stderr = ""
    if args.stderr_file:
        stderr = Path(args.stderr_file).read_text(encoding="utf-8", errors="replace")

    raw = build_raw_facts(args.run_dir, stderr=stderr, timed_out=args.timed_out)
    passed = raw["reward"]
    if passed is None:
        print("error: reward.txt not found in --run-dir", file=sys.stderr)
        sys.exit(1)

    category, detail = (None, {})
    if not passed:
        category, detail = classify(raw)

    run_id = args.run_id or f"{args.task_id}-{next(_counter)}"
    record = make_run_record(
        run_id=run_id,
        task_id=args.task_id,
        domain=args.domain,
        skill_loaded=args.skill,
        passed=passed,
        category=category,
        detail=detail,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    append_jsonl(base / "runs.jsonl", record)
    print(json.dumps(record, indent=2, sort_keys=True))


def cmd_log_probe(args):
    """Record a self-observed failure with no verifier score - the cold-start case
    where authoring happens before any solver/verifier run exists for this task.
    Always passed=False (a probe can only observe friction, never a confirmed pass);
    this is deliberate - it can motivate a HYPOTHESIS-staged candidate but can never
    by itself pair into a COMMIT, which requires an actual verifier-confirmed pass."""
    base = state_dir(args.state_dir)
    ensure_state_dirs(base)
    if args.category not in FAILURE_CATEGORIES:
        print(f"error: category must be one of {FAILURE_CATEGORIES}", file=sys.stderr)
        sys.exit(1)
    run_id = args.run_id or f"{args.task_id}-probe-{next(_counter)}"
    record = make_run_record(
        run_id=run_id, task_id=args.task_id, domain=args.domain, skill_loaded=None,
        passed=False, category=args.category,
        detail={"self_probed": True, "note": args.note or ""},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    append_jsonl(base / "runs.jsonl", record)
    print(json.dumps(record, indent=2, sort_keys=True))


def cmd_aggregate(args):
    base = state_dir(args.state_dir)
    runs = read_jsonl(base / "runs.jsonl")
    print(json.dumps(aggregate_mod.aggregate(runs), indent=2, sort_keys=True))


def cmd_status(args):
    base = state_dir(args.state_dir)
    ensure_state_dirs(base)
    library = sorted(p.name for p in (base / "library").iterdir() if p.is_dir())
    staging = sorted(p.name for p in (base / "staging").iterdir() if p.is_dir())
    ledger = read_jsonl(base / "ledger.jsonl")
    latest = {}
    for e in ledger:
        latest[e["skill_name"]] = e  # last write wins - ledger.py appends, this takes newest
    print(json.dumps({
        "library": library,
        "staging": staging,
        "ledger": list(latest.values()),
    }, indent=2, sort_keys=True))


def main():
    ap = argparse.ArgumentParser(prog="forge")
    ap.add_argument("--state-dir", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    p = sub.add_parser("log-run")
    p.add_argument("--task-id", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--skill", default=None, help="skill name loaded for this attempt, if any")
    p.add_argument("--run-dir", required=True, help="dir containing reward.txt (+ optional ctrf.json)")
    p.add_argument("--stderr-file", default=None)
    p.add_argument("--timed-out", action="store_true")
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_log_run)

    p = sub.add_parser("log-probe")
    p.add_argument("--task-id", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--category", required=True, choices=FAILURE_CATEGORIES)
    p.add_argument("--note", default=None)
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_log_probe)

    sub.add_parser("aggregate").set_defaults(func=cmd_aggregate)
    sub.add_parser("status").set_defaults(func=cmd_status)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
