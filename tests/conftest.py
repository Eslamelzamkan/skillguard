import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
AUTHOR_SCRIPTS = REPO_ROOT / "skills" / "skill-creator" / "scripts"
GATE_SCRIPTS = REPO_ROOT / "skills" / "forge-gate" / "scripts"
REFINE_SCRIPTS = REPO_ROOT / "skills" / "forge-refine" / "scripts"


def run_cli(script_path, args, cwd=None):
    """Invoke a skill script the same way the agent would: a
    plain subprocess call, no package imports across skill directories."""
    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        capture_output=True, text=True, cwd=cwd,
    )
    return result


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def write_candidate(base, name, description="Use when X happens. Not for Y.",
                     body_extra="", sections=True, evidence_ids=(), frontmatter_extra=""):
    d = base / "candidates" / name
    d.mkdir(parents=True, exist_ok=True)
    sections_text = ""
    if sections:
        sections_text = (
            "\n## Pipeline (do every step in order)\n1. Do the thing.\n"
            "\n## Critical rules\n| Rule | Why |\n|---|---|\n| Do X | Because Y |\n"
            "\n## Scope guard\n- Prefer reversible operations over irreversible ones.\n"
            "\n## Not in scope\n- Unrelated tasks.\n"
        )
    evidence_line = ""
    if evidence_ids:
        evidence_line = f"\n<!-- evidence: {', '.join(evidence_ids)} -->\n"
    text = (
        f"---\nname: {name}\ndescription: {description}\n{frontmatter_extra}---\n\n"
        f"# {name}\n\nOne-line purpose.\n{sections_text}{body_extra}{evidence_line}"
    )
    (d / "SKILL.md").write_text(text, encoding="utf-8")
    return d
