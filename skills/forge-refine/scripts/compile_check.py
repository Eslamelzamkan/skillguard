#!/usr/bin/env python3
"""Stage: library-wide compliance check. Word-count cap, library-size cap,
per-domain consolidation flag, description-collision flag. Deterministic,
stdlib only. Non-fatal findings (consolidation, collision) are reported but
don't fail the check; word-count and library-size are hard caps.

Usage: python compile_check.py [--state-dir DIR]
Exit 0 if no hard-cap violation, 1 otherwise. Always prints the JSON report.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

MAX_BODY_WORDS = 1600
LIBRARY_CAP = 8
COLLISION_JACCARD = 0.6

STOPWORDS = {"use", "when", "the", "a", "an", "for", "to", "of", "and", "or",
             "not", "this", "is", "with", "on", "in", "it"}


def _read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _description(skill_md_text):
    m = re.search(r"description:\s*(.+)", skill_md_text)
    return m.group(1).strip() if m else ""


def _body_word_count(skill_md_text):
    m = re.match(r"^---\s*\n.*?\n---\s*\n(.*)$", skill_md_text, re.DOTALL)
    body = m.group(1) if m else skill_md_text
    return len(body.split())


def _tokens(description):
    words = re.findall(r"[a-z]+", description.lower())
    return {w for w in words if w not in STOPWORDS}


def check(state_dir):
    state = Path(state_dir)
    library = state / "library"
    ledger_by_name = {e["skill_name"]: e for e in _read_jsonl(state / "ledger.jsonl")}

    violations, consolidation_flags, collision_flags = [], [], []
    skills = [d for d in library.iterdir() if d.is_dir() and d.name != "_versions"] if library.exists() else []

    if len(skills) > LIBRARY_CAP:
        violations.append(f"library has {len(skills)} skills, cap is {LIBRARY_CAP}")

    descriptions = {}
    by_domain = defaultdict(list)
    for d in skills:
        skill_md = d / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""
        words = _body_word_count(text)
        if words > MAX_BODY_WORDS:
            violations.append(f"{d.name}: {words} words > {MAX_BODY_WORDS} cap")
        descriptions[d.name] = _description(text)
        domain = ledger_by_name.get(d.name, {}).get("domain", "unknown")
        by_domain[domain].append(d.name)

    for domain, names in by_domain.items():
        if len(names) > 1:
            consolidation_flags.append({"domain": domain, "skills": names})

    names = list(descriptions)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ta, tb = _tokens(descriptions[a]), _tokens(descriptions[b])
            if not ta or not tb:
                continue
            jaccard = len(ta & tb) / len(ta | tb)
            if jaccard >= COLLISION_JACCARD:
                collision_flags.append({"skills": [a, b], "jaccard": round(jaccard, 2)})

    return {
        "ok": not violations,
        "library_size": len(skills),
        "violations": violations,
        "consolidation_flags": consolidation_flags,
        "collision_flags": collision_flags,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default=".skill-forge")
    args = ap.parse_args()
    report = check(args.state_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
