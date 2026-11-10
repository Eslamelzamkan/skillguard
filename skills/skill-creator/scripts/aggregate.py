#!/usr/bin/env python3
"""Stage 2: deterministic failure aggregation across all logged runs.

Groups failures by (domain, category), applies fixed severity rules, and
surfaces the quality_below_threshold detail (the dominant failure mode) so
the authoring step gets concrete assertion/tolerance facts instead of
"test failed". No LLM call - pure counting and fixed thresholds.

Usage: python aggregate.py [--state-dir DIR]
Prints a JSON report to stdout, domains ranked by severity (highest first).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import state_dir, read_jsonl, FAILURE_CATEGORIES  # noqa: E402

# Fixed tie-break priority when two categories tie on count within a domain.
# quality_below_threshold ranked first: it is the dominant failure mode
# (structurally-correct-but-wrong-output) and the one authoring can most
# directly fix with concrete procedural guidance.
CATEGORY_PRIORITY = {
    "quality_below_threshold": 0,
    "crash": 1,
    "missing_artifact": 2,
    "timeout": 3,
}


def severity(count):
    if count >= 3:
        return "high"
    if count == 2:
        return "medium"
    return "low"


def aggregate(runs):
    by_domain = defaultdict(lambda: defaultdict(list))
    for r in runs:
        if r.get("passed"):
            continue
        by_domain[r["domain"]][r.get("category", "quality_below_threshold")].append(r)

    report = []
    for domain, cats in by_domain.items():
        cat_summaries = {}
        for cat, records in cats.items():
            entry = {
                "category": cat,
                "count": len(records),
                "severity": severity(len(records)),
                "run_ids": [r["run_id"] for r in records],
            }
            if cat == "quality_below_threshold":
                entry["assertion_samples"] = [
                    a for r in records for a in r.get("detail", {}).get("failed_assertions", [])
                ][:10]
            cat_summaries[cat] = entry

        # domain severity = worst category severity; ties broken by fixed priority
        worst = max(
            cat_summaries.values(),
            key=lambda e: (
                {"high": 2, "medium": 1, "low": 0}[e["severity"]],
                -CATEGORY_PRIORITY.get(e["category"], 99),
            ),
        )
        report.append({
            "domain": domain,
            "domain_severity": worst["severity"],
            "dominant_category": worst["category"],
            "categories": sorted(
                cat_summaries.values(),
                key=lambda e: CATEGORY_PRIORITY.get(e["category"], 99),
            ),
        })

    report.sort(key=lambda d: {"high": 2, "medium": 1, "low": 0}[d["domain_severity"]], reverse=True)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default=None)
    args = ap.parse_args()
    base = state_dir(args.state_dir)
    runs = read_jsonl(base / "runs.jsonl")
    print(json.dumps(aggregate(runs), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
