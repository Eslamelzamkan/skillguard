#!/usr/bin/env python3
"""Stage 5/6: ledger - promotion, ExpeL-style retention counter, rollback.

Append-only: current state of a skill = its most recent ledger.jsonl entry.
Self-contained (no imports from sibling skill folders) since the harness may
mount each skill directory independently.

Subcommands:
  promote  <name> <domain> <candidate_dir>   move a gate-COMMITted candidate into library/
  outcome  <name> --result hit|miss          ExpeL counter: +1 hit, -1 miss, archive at 0
  status   [<name>]                          print current ledger state

Usage: python ledger.py <subcommand> ... --state-dir DIR
"""
import argparse
import json
import shutil
from pathlib import Path

STATUSES = ("DIAGNOSED", "OBSERVED", "VERIFIED", "CORE", "ARCHIVED")
CORE_THRESHOLD = 3  # confirmations on distinct tasks

# Retention-counter start by evidence tier: stronger evidence buys more slack
# before the counter hits 0 and the skill self-archives. A DIAGNOSED skill
# (cold-start, no outcome yet) is on the shortest leash - one observed miss and
# it's gone; a VERIFIED (fail->pass paired) skill survives a couple of misses.
TIER_START_COUNTER = {"DIAGNOSED": 1, "OBSERVED": 2, "VERIFIED": 3}


def _read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _append_jsonl(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def latest_entries(ledger):
    latest = {}
    for e in ledger:
        latest[e["skill_name"]] = e  # append-only log, last write wins
    return latest


def distinct_tasks(run_ids, runs_by_id):
    return {runs_by_id[r]["task_id"] for r in run_ids if r in runs_by_id}


def cmd_promote(args):
    state = Path(args.state_dir)
    library_dir = state / "library" / args.name
    versions_dir = state / "library" / "_versions" / args.name

    version = 1
    if library_dir.exists():
        versions_dir.mkdir(parents=True, exist_ok=True)
        version = len(list(versions_dir.glob("v*"))) + 2
        shutil.move(str(library_dir), str(versions_dir / f"v{version - 1}"))

    shutil.copytree(args.candidate_dir, library_dir)

    ledger = _read_jsonl(state / "ledger.jsonl")
    prior = latest_entries(ledger).get(args.name)
    evidence = sorted(set((prior or {}).get("evidence_run_ids", [])) | set(args.run_ids.split(",")))
    tier = args.tier if args.tier in TIER_START_COUNTER else "DIAGNOSED"
    # a re-promotion (revision) keeps the better of prior/new tier's counter slack
    start_counter = max(TIER_START_COUNTER[tier], (prior or {}).get("counter", 0))
    entry = {
        "skill_name": args.name,
        "domain": args.domain,
        "status": tier,
        "hits": (prior or {}).get("hits", 0),
        "misses": (prior or {}).get("misses", 0),
        "counter": start_counter,
        "evidence_run_ids": evidence,
        "version": version,
    }
    _append_jsonl(state / "ledger.jsonl", entry)
    print(json.dumps(entry, indent=2, sort_keys=True))


def cmd_outcome(args):
    state = Path(args.state_dir)
    ledger = _read_jsonl(state / "ledger.jsonl")
    runs_by_id = {r["run_id"]: r for r in _read_jsonl(state / "runs.jsonl")}
    latest = latest_entries(ledger)
    prior = latest.get(args.name)
    if not prior:
        raise SystemExit(f"no ledger entry for {args.name} - promote it first")

    hits, misses, counter = prior["hits"], prior["misses"], prior["counter"]
    evidence = list(prior["evidence_run_ids"])
    if args.run_id:
        evidence.append(args.run_id)

    if args.result == "hit":
        hits += 1
        counter += 1
    else:
        misses += 1
        counter -= 1

    status = prior["status"]
    n_distinct = len(distinct_tasks(evidence, runs_by_id))
    if counter <= 0:
        status = "ARCHIVED"
        archive_dir = state / "archive" / args.name
        library_dir = state / "library" / args.name
        if library_dir.exists():
            archive_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(library_dir), str(archive_dir))
    elif status != "ARCHIVED":
        # climb tiers as confirmations accrue: a DIAGNOSED skill that keeps
        # passing earns trust. CORE once it holds across >=3 distinct tasks.
        if n_distinct >= CORE_THRESHOLD and hits >= 2:
            status = "CORE"
        elif args.result == "hit" and status == "DIAGNOSED":
            status = "OBSERVED"
        elif args.result == "hit" and status == "OBSERVED" and hits >= 2:
            status = "VERIFIED"

    entry = {**prior, "hits": hits, "misses": misses, "counter": counter,
              "evidence_run_ids": sorted(set(evidence)), "status": status}
    _append_jsonl(state / "ledger.jsonl", entry)
    print(json.dumps(entry, indent=2, sort_keys=True))


def cmd_status(args):
    state = Path(args.state_dir)
    ledger = _read_jsonl(state / "ledger.jsonl")
    latest = latest_entries(ledger)
    if args.name:
        print(json.dumps(latest.get(args.name), indent=2, sort_keys=True))
    else:
        print(json.dumps(list(latest.values()), indent=2, sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default=".skill-forge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("promote")
    p.add_argument("name")
    p.add_argument("domain")
    p.add_argument("candidate_dir")
    p.add_argument("--run-ids", required=True, help="comma-separated evidence run_ids")
    p.add_argument("--tier", default="DIAGNOSED", choices=list(TIER_START_COUNTER),
                   help="evidence tier from the gate verdict (sets retention slack)")
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("outcome")
    p.add_argument("name")
    p.add_argument("--result", choices=["hit", "miss"], required=True)
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_outcome)

    p = sub.add_parser("status")
    p.add_argument("name", nargs="?", default=None)
    p.set_defaults(func=cmd_status)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
