import ast
import sys

from conftest import REPO_ROOT

STDLIB = sys.stdlib_module_names if hasattr(sys, "stdlib_module_names") else set()
DENY_CALL_FORMS = ("os.remove(", "os.unlink(", "shutil.rmtree(", "send2trash")


def all_shipped_scripts():
    return sorted((REPO_ROOT / "skills").rglob("*.py"))


def test_no_shipped_script_calls_a_deletion_primitive():
    for f in all_shipped_scripts():
        text = f.read_text(encoding="utf-8")
        for bad in DENY_CALL_FORMS:
            assert bad not in text, f"{f} calls {bad} - archive-by-move only, never delete"


def test_shipped_scripts_are_stdlib_only():
    if not STDLIB:
        return  # Python < 3.10: skip, no reliable stdlib module list available
    for f in all_shipped_scripts():
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [n.name.split(".")[0] for n in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules = [node.module.split(".")[0]] if node.module else []
            else:
                continue
            for m in modules:
                # sibling in-skill modules (schema, run_logger) are not stdlib but are shipped alongside
                local_modules = {"schema", "run_logger", "aggregate", "safety_gate", "ledger", "compile_check", "forge"}
                assert m in STDLIB or m in local_modules, f"{f} imports non-stdlib module `{m}`"


def test_no_network_calls_in_shipped_scripts():
    network_markers = ("urllib.request", "requests.", "http.client", "socket.socket", "urlopen(")
    for f in all_shipped_scripts():
        text = f.read_text(encoding="utf-8")
        for marker in network_markers:
            assert marker not in text, f"{f} contains a network call marker `{marker}`"


def test_skill_md_files_have_required_sections():
    for skill_md in sorted((REPO_ROOT / "skills").glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8").lower()
        assert text.startswith("---\nname:"), f"{skill_md} missing frontmatter"
        assert "description:" in text.split("---")[1]
        assert "use when" in text.split("---")[1], f"{skill_md} description doesn't start triggers with 'Use when'"
