"""Parse verifier output for one task attempt into a classified RunRecord.

Handles the two verifier shapes SkillsBench-style tasks use:
  - reward.txt containing "0" or "1"
  - CTRF json (pytest-json-ctrf) with per-test results and failure messages
  - optional expected_values.json for numeric-tolerance tasks

Stdlib only. Classification is deterministic pattern matching on the parsed
facts - no LLM call, no judgment call.
"""
import json
import re
from pathlib import Path

TIMEOUT_MARKERS = ("timeout", "timed out", "deadlineexceeded", "TimeoutExpired")
CRASH_MARKERS = ("Traceback (most recent call last)", "Error:", "Exception:")
MISSING_ARTIFACT_MARKERS = ("No such file or directory", "FileNotFoundError", "does not exist")


def parse_reward(state_task_dir):
    """Read reward.txt -> True/False, or None if absent."""
    p = Path(state_task_dir) / "reward.txt"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8").strip()
    return text == "1"


def parse_ctrf(state_task_dir):
    """Read a CTRF json report if present, return the raw dict or None."""
    p = Path(state_task_dir) / "ctrf.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _ctrf_failure_messages(ctrf):
    if not ctrf:
        return []
    tests = ctrf.get("results", {}).get("tests", [])
    return [t.get("message", "") or "" for t in tests if t.get("status") == "failed"]


def _extract_tolerance_detail(message):
    """Pull 'expected X, got Y' or assert-style numeric deltas out of a pytest message."""
    m = re.search(r"assert\s+abs\(([^)]+)\)\s*<\s*([\d.eE+-]+)", message)
    if m:
        return {"assertion": "tolerance", "raw": m.group(0)}
    m = re.search(r"assert\s+(.+?)\s*==\s*(.+)", message)
    if m:
        return {"assertion": "equality", "expected": m.group(2).strip(), "actual": m.group(1).strip()}
    return {"assertion": "unknown", "raw": message[:300]}


def classify(raw_facts):
    """Deterministic taxonomy: crash / missing_artifact / quality_below_threshold / timeout.

    raw_facts: {"reward": bool|None, "ctrf": dict|None, "stderr": str, "timed_out": bool}
    Returns (category, detail_dict). Only called when the run failed.
    """
    stderr = raw_facts.get("stderr") or ""
    if raw_facts.get("timed_out") or any(m.lower() in stderr.lower() for m in TIMEOUT_MARKERS):
        return "timeout", {"stderr_excerpt": stderr[-500:]}

    if any(m in stderr for m in MISSING_ARTIFACT_MARKERS):
        return "missing_artifact", {"stderr_excerpt": stderr[-500:]}

    messages = _ctrf_failure_messages(raw_facts.get("ctrf"))
    if messages:
        # A pytest run happened and produced structured assertion failures ->
        # the agent ran to completion but the output is wrong: dominant failure mode.
        details = [_extract_tolerance_detail(m) for m in messages[:5]]
        return "quality_below_threshold", {"failed_assertions": details, "count": len(messages)}

    if any(m in stderr for m in CRASH_MARKERS):
        return "crash", {"stderr_excerpt": stderr[-500:]}

    # Ran, produced no pytest failures we can parse, but reward was 0 -> treat
    # conservatively as quality_below_threshold (something about the output was wrong).
    return "quality_below_threshold", {"stderr_excerpt": stderr[-500:]}


def build_raw_facts(state_task_dir, stderr="", timed_out=False):
    return {
        "reward": parse_reward(state_task_dir),
        "ctrf": parse_ctrf(state_task_dir),
        "stderr": stderr,
        "timed_out": timed_out,
    }
