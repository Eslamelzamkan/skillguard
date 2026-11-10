"""Shared data model for Skill-Forge state files. Stdlib only, no network.

State directory contract (all three meta-skills read/write here):
  <state>/runs.jsonl       append-only RunRecord log
  <state>/candidates/      candidate skill folders pending the gate
  <state>/staging/         unpromoted candidate drafts
  <state>/library/         gate-passed skills (DIAGNOSED, OBSERVED, VERIFIED, CORE)
  <state>/gate_log.jsonl   append-only gate decisions (written by forge-gate)
  <state>/ledger.jsonl     per-skill lifecycle state (written by forge-refine)
"""
import json
import os
from pathlib import Path

STATE_DIR_ENV = "SKILL_FORGE_STATE"
DEFAULT_STATE_DIR = ".skill-forge"

FAILURE_CATEGORIES = (
    "crash",
    "missing_artifact",
    "quality_below_threshold",
    "timeout",
)

LEDGER_STATUSES = ("DIAGNOSED", "OBSERVED", "VERIFIED", "CORE", "ARCHIVED")


def state_dir(explicit=None):
    path = Path(explicit or os.environ.get(STATE_DIR_ENV) or DEFAULT_STATE_DIR)
    return path


def ensure_state_dirs(base):
    base = Path(base)
    for sub in ("candidates", "staging", "library"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    for f in ("runs.jsonl", "gate_log.jsonl", "ledger.jsonl"):
        p = base / f
        if not p.exists():
            p.touch()
    return base


def append_jsonl(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def make_run_record(run_id, task_id, domain, skill_loaded, passed, category=None,
                     detail=None, timestamp=None):
    """A single attempt at a task: with or without a skill loaded, pass/fail per verifier."""
    if passed not in (True, False):
        raise ValueError("passed must be boolean")
    if not passed and category not in FAILURE_CATEGORIES:
        raise ValueError(f"category must be one of {FAILURE_CATEGORIES} when passed=False")
    return {
        "run_id": run_id,
        "task_id": task_id,
        "domain": domain,
        "skill_loaded": skill_loaded,  # skill name or None
        "passed": passed,
        "category": category,
        "detail": detail or {},
        "timestamp": timestamp,
    }


def make_ledger_entry(skill_name, domain, status="DIAGNOSED", hits=0, misses=0,
                       counter=1, evidence_run_ids=None, version=1, superseded_by=None):
    if status not in LEDGER_STATUSES:
        raise ValueError(f"status must be one of {LEDGER_STATUSES}")
    return {
        "skill_name": skill_name,
        "domain": domain,
        "status": status,
        "hits": hits,
        "misses": misses,
        "counter": counter,  # ExpeL-style retention counter: DIAGNOSED=1, OBSERVED=2, VERIFIED=3
        "evidence_run_ids": evidence_run_ids or [],
        "version": version,
        "superseded_by": superseded_by,
    }
