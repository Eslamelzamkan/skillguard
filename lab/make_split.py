#!/usr/bin/env python3
"""Deterministically split the public SkillsBench corpus into dev-calibration
and dev-holdout, stratified by task category so both splits cover all domains.

This rehearses the real thing: we tune only on dev-calibration, and dev-holdout
stands in for the private bench-mix (never tuned on). Holdout is the local
decision metric; the live leaderboard is only a sanity check.

Deterministic (sorted by name, every 3rd task in each category stratum -> holdout).
No randomness, so the frozen lab/split.json is reproducible from this script alone.

Usage: python make_split.py --tasks-dir <skillsbench/tasks> [--out lab/split.json]
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

HOLDOUT_EVERY = 3  # 1 in 3 tasks per category -> holdout (~1/3 holdout, ~2/3 calibration)


def category_of(task_md_text):
    m = re.search(r"^\s*category:\s*(.+)$", task_md_text, re.MULTILINE)
    return m.group(1).strip().strip("\"'") if m else "uncategorized"


def build_split(tasks_dir):
    tasks_dir = Path(tasks_dir)
    by_cat = defaultdict(list)
    for task_md in sorted(tasks_dir.glob("*/task.md")):
        text = task_md.read_text(encoding="utf-8", errors="replace")
        by_cat[category_of(text)].append(task_md.parent.name)

    calibration, holdout = [], []
    for cat in sorted(by_cat):
        for i, name in enumerate(sorted(by_cat[cat])):
            (holdout if i % HOLDOUT_EVERY == HOLDOUT_EVERY - 1 else calibration).append(name)

    return {
        "holdout_every": HOLDOUT_EVERY,
        "n_calibration": len(calibration),
        "n_holdout": len(holdout),
        "calibration": sorted(calibration),
        "holdout": sorted(holdout),
        "by_category": {c: sorted(v) for c, v in sorted(by_cat.items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks-dir", required=True)
    ap.add_argument("--out", default=str(Path(__file__).parent / "split.json"))
    args = ap.parse_args()
    split = build_split(args.tasks_dir)
    Path(args.out).write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
    print(f"calibration={split['n_calibration']} holdout={split['n_holdout']} -> {args.out}")


if __name__ == "__main__":
    main()
