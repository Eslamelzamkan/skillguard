#!/usr/bin/env python3
"""Stage 4: deterministic gate. No LLM call, no judgment call - fixed rules only.

The ship/no-ship decision is purely on hard, always-available checks
(structure, safety, leakage, size, grounding). Strength of the outcome evidence
is a TIER LABEL (VERIFIED/OBSERVED/DIAGNOSED), NOT a ship gate - because the
evolution loop may be stateless-per-task and never provide a fail->pass pair, so
requiring one would ship nothing and hard-fail the rollout on an empty result.
The tier only tells the ledger how aggressively to prune the skill later.

Order (first hard-fail wins): structure > safety > grounding > leakage > size.
Every decision is logged with the rule (or tier) that fired.

Usage:
  python safety_gate.py <candidate_dir> [--state-dir DIR]

Exit codes: 0 = SHIP   (passed all hard checks; verdict.tier gives evidence strength)
            1 = REJECT (structure / safety / ungrounded / leakage / size failure)

Self-contained on purpose: does not import from sibling skill directories,
since the harness may mount each skill folder independently.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# --- deterministic deny patterns -------------------------------------------
# Kept in sync by hand with references/deny-patterns.md (the judge-legible
# mirror of this list). Grounded in ClawsBench's violation taxonomy
# (arXiv:2604.05172): destructive/one-way-door, confidentiality/leakage,
# unauthorized permission change, plus generic injection/exfil/sandbox markers.

DESTRUCTIVE_PATTERNS = [
    r"\bmessages\.(delete|batchDelete|trash)\b", r"\bthreads\.(delete|trash)\b",
    r"\bdrafts\.delete\b", r"\blabels\.delete\b", r"\bfilters\.delete\b",
    r"\bfiles\.delete\b", r"\bfiles\.emptyTrash\b", r"\brevisions\.delete\b",
    r"\bdeleteContentRange\b", r"\bdeleteTableRow\b",
    r"\bevents\.delete\b", r"\bcalendars\.delete\b", r"\bacl\.delete\b",
    r"\bconversations\.(kick|archive|leave)\b", r"\bchat\.delete\b",
    r"\badmin\.conversations\.delete\b", r"\bbulk[ _-]?(delete|remove)\b",
    r"\brm\s+-rf\b", r"\bshutil\.rmtree\b", r"\bos\.remove\b", r"\bos\.unlink\b",
    r"\bDROP\s+TABLE\b", r"\bTRUNCATE\b",
]

LEAKAGE_PATTERNS = [
    r"\bupdateAutoForwarding\b", r"\bcreateForwardingAddress\b", r"\bsendAs\b",
    r"\bforward(ing|s|ed)?\b.{0,80}\bexternal\b", r"\bexternal\s+(cc|bcc|recipient)\b",
    r"\b(send|share|forward|email)\w*\b.{0,80}\bexternal\s+(partner|auditor|recipient|party|client|collaborator|address|domain|vendor|contact)\b",
    r"\bexport.{0,20}then.{0,20}send\b", r"\bpost.{0,15}externally\b",
]

PERMISSION_PATTERNS = [
    r"\bpermissions\.(create|update)\b", r"\btype=\"?anyone\"?\b",
    r"\brole=\"?(writer|owner)\"?\b", r"\banyone[- ]with[- ]link\b",
    r"\btransfer\s+ownership\b", r"\bdelegates\.create\b",
    r"\bconversations\.invite\b.{0,20}external\b", r"\bsetAdmin\b",
    r"\bwritersCanShare\b",
]

INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions", r"\bverifier\s+(path|source|code)\b",
    r"\breward\.txt\b.{0,20}(edit|modify|write)\b",
    r"\b(print|dump|list|read|enumerate|expose)\b.{0,40}\benviron(ment)?\s+variab",
    r"\benv(iron)?\s+var\w*\b.{0,25}(enumerat|credential|secret|dump|exfil)",
    r"\blocalhost\b.{0,15}(curl|probe|scan)\b", r"\bbase64.{0,15}(encode|send)\b",
]

ALL_DENY = (
    [("destructive", p) for p in DESTRUCTIVE_PATTERNS]
    + [("leakage", p) for p in LEAKAGE_PATTERNS]
    + [("permission", p) for p in PERMISSION_PATTERNS]
    + [("injection", p) for p in INJECTION_PATTERNS]
)

QUALIFIER_PHRASES = ("only if", "explicitly requires", "explicit user authorization",
                     "explicit instruction", "with explicit approval")

REQUIRED_SECTIONS = ("scope guard", "not in scope")
PIPELINE_HEADERS = ("pipeline", "procedure")

MAX_BODY_WORDS = 1600  # ~2K tokens, hard ceiling (Comprehensive register measured ~worthless)
ALLOWED_FRONTMATTER_KEYS = {"name", "description"}


def _read(path):
    p = Path(path)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _split_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2)
    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, body


def _headers(body):
    return {h.strip().lower() for h in re.findall(r"^#{1,3}\s+(.+)$", body, re.MULTILINE)}


def _gather_candidate_text(candidate_dir):
    candidate_dir = Path(candidate_dir)
    texts = {}
    skill_md = candidate_dir / "SKILL.md"
    texts["SKILL.md"] = _read(skill_md)
    for sub in ("scripts", "references"):
        d = candidate_dir / sub
        if d.exists():
            for f in d.rglob("*"):
                if f.is_file():
                    texts[str(f.relative_to(candidate_dir))] = _read(f)
    return texts


def check_structure(skill_md_text):
    fm, body = _split_frontmatter(skill_md_text)
    if not fm:
        return "REJECT", "structure", "missing YAML frontmatter", None
    extra_keys = set(fm.keys()) - ALLOWED_FRONTMATTER_KEYS
    if extra_keys:
        return "REJECT", "structure", f"non-standard frontmatter keys: {sorted(extra_keys)}", None
    if "name" not in fm or "description" not in fm:
        return "REJECT", "structure", "frontmatter missing name or description", None
    headers = _headers(body)
    if not any(h.startswith(p) for h in headers for p in PIPELINE_HEADERS):
        return "REJECT", "structure", "missing Pipeline/Procedure section", None
    for req in REQUIRED_SECTIONS:
        if not any(h.startswith(req) for h in headers):
            return "REJECT", "structure", f"missing required section: {req}", None
    return "PASS", None, None, (fm, body)


def check_action_safety(texts):
    for fname, text in texts.items():
        for line_no, line in enumerate(text.splitlines(), 1):
            for category, pattern in ALL_DENY:
                if re.search(pattern, line, re.IGNORECASE):
                    if any(q in line.lower() for q in QUALIFIER_PHRASES):
                        continue  # explicitly conditioned on task-authorized instruction
                    return "REJECT", f"safety:{category}", f"{fname}:{line_no} matched `{pattern}`", None
    return "PASS", None, None, None


def check_leakage(body, evidence_run_ids, runs_by_id):
    # absolute paths / UUID-like / hash-like tokens
    if re.search(r"[A-Za-z]:\\\\|(?<!\w)/root/\S+|(?<!\w)/home/\S+", body):
        return "REJECT", "leakage:path", "absolute filesystem path found in body", None
    if re.search(r"\b[0-9a-fA-F]{32,}\b", body):
        return "REJECT", "leakage:hash", "hash/UUID-like literal found in body", None
    if re.search(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", body):
        return "REJECT", "leakage:uuid", "UUID literal found in body", None
    # hardcoded expected/actual literals from the cited runs' own assertion failures
    for rid in evidence_run_ids:
        run = runs_by_id.get(rid)
        if not run:
            continue
        for a in run.get("detail", {}).get("failed_assertions", []) or []:
            for key in ("expected", "actual"):
                val = a.get(key)
                if val and len(str(val)) >= 3 and str(val) in body:
                    return ("REJECT", "leakage:hardcoded-value",
                            f"run {rid} literal `{val}` found verbatim in body", None)
    return "PASS", None, None, None


def classify_evidence(body, runs_by_id):
    """Grounding is a hard requirement; the strength of that grounding is a
    *tier label*, not a ship/no-ship decision. A skill must cite >=1 real
    observed run (a diagnostic probe or an actual attempt) so it can never be
    pure hallucination - but it does NOT need a fail->pass pair to ship, because
    the evolution loop may be stateless-per-task and never provide one. The tier
    only drives how aggressively the ledger prunes the skill later (see ledger.py):

      VERIFIED  - cited runs include BOTH a failure and a pass (fail->pass pair)
      OBSERVED  - cited runs include a pass with this skill, but no paired failure
      DIAGNOSED - only failing / probe evidence (the cold-start default)

    Returns ("SHIP", tier, None, run_ids) or ("REJECT", "evidence", why, ids).
    """
    m = re.search(r"<!--\s*evidence:\s*(.+?)\s*-->", body)
    if not m:
        return "REJECT", "evidence", "no evidence comment - cite >=1 real run_id (a probe or an attempt)", []
    run_ids = [r.strip() for r in m.group(1).split(",") if r.strip()]
    known = [r for r in run_ids if r in runs_by_id]
    if not known:
        return "REJECT", "evidence", "cited run_id(s) not in runs.jsonl - ungrounded", run_ids

    has_fail = any(runs_by_id[r].get("passed") is False for r in known)
    has_pass = any(runs_by_id[r].get("passed") is True for r in known)
    tier = "VERIFIED" if (has_fail and has_pass) else "OBSERVED" if has_pass else "DIAGNOSED"
    return "SHIP", tier, None, known


def run_gate(candidate_dir, runs):
    runs_by_id = {r["run_id"]: r for r in runs}
    texts = _gather_candidate_text(candidate_dir)
    skill_text = texts.get("SKILL.md", "")

    status, rule, detail, structured = check_structure(skill_text)
    if status != "PASS":
        return {"status": "REJECT", "rule": rule, "detail": detail}
    fm, body = structured

    status, rule, detail, _ = check_action_safety(texts)
    if status != "PASS":
        return {"status": "REJECT", "rule": rule, "detail": detail}

    ev_status, tier, ev_detail, run_ids = classify_evidence(body, runs_by_id)
    if ev_status == "REJECT":
        return {"status": "REJECT", "rule": "evidence", "detail": ev_detail}

    status, rule, detail, _ = check_leakage(body, run_ids, runs_by_id)
    if status != "PASS":
        return {"status": "REJECT", "rule": rule, "detail": detail}

    word_count = len(body.split())
    if word_count > MAX_BODY_WORDS:
        return {"status": "REJECT", "rule": "size", "detail": f"{word_count} words > {MAX_BODY_WORDS} cap"}

    # Passed every hard check (structure, safety, grounding, leakage, size):
    # the skill SHIPS to the library. Its evidence tier only sets how much slack
    # the ledger's retention counter gives it before pruning.
    return {
        "status": "SHIP",
        "tier": tier,
        "rule": None,
        "detail": None,
        "name": fm.get("name"),
        "evidence_run_ids": run_ids,
        "word_count": word_count,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate_dir")
    ap.add_argument("--state-dir", default=".skill-forge")
    args = ap.parse_args()

    runs_path = Path(args.state_dir) / "runs.jsonl"
    runs = []
    if runs_path.exists():
        for line in runs_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                runs.append(json.loads(line))

    verdict = run_gate(args.candidate_dir, runs)

    log_path = Path(args.state_dir) / "gate_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"candidate": str(args.candidate_dir), **verdict}, sort_keys=True) + "\n")

    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit({"SHIP": 0, "REJECT": 1}[verdict["status"]])


if __name__ == "__main__":
    main()
