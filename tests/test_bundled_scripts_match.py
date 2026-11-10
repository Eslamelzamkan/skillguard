"""skill-creator bundles its own copies of safety_gate.py/ledger.py/compile_check.py
(see skill-creator/SKILL.md 'Runtime context') because BenchFlow self-gen only
copies one skill pack into the creator scene - sibling packs are dropped. This
guards against the two copies drifting apart."""
import filecmp

from conftest import REPO_ROOT

PAIRS = [
    ("forge-gate/scripts/safety_gate.py", "skill-creator/scripts/safety_gate.py"),
    ("forge-refine/scripts/ledger.py", "skill-creator/scripts/ledger.py"),
    ("forge-refine/scripts/compile_check.py", "skill-creator/scripts/compile_check.py"),
]


def test_bundled_copies_are_identical_to_source_of_truth():
    for source, bundled in PAIRS:
        a = REPO_ROOT / "skills" / source
        b = REPO_ROOT / "skills" / bundled
        assert a.exists() and b.exists()
        assert filecmp.cmp(a, b, shallow=False), f"{bundled} has drifted from {source} - re-sync it"
