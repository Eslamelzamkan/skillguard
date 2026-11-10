"""Command-line interface for SkillGuard."""

import argparse
import sys
from pathlib import Path
from typing import List, Set

from . import __version__
from .formatter import format_github, format_json, format_terminal
from .library import LibraryAuditor
from .rules import Diagnostic, Severity, RULES
from .scaffold import create_skill_scaffold
from .scanner import SkillScanner


def parse_ignore_list(ignore_str: str) -> Set[str]:
    if not ignore_str:
        return set()
    return {code.strip().upper() for code in ignore_str.split(",") if code.strip()}


def cmd_check(args) -> int:
    target_path = Path(args.path)
    if not target_path.exists():
        print(f"Error: Path '{target_path}' does not exist.", file=sys.stderr)
        return 1

    ignored = parse_ignore_list(args.ignore)
    scanner = SkillScanner(ignored_rules=ignored)

    diagnostics: List[Diagnostic] = []
    diagnostics.extend(scanner.scan_path(target_path))

    # Also audit library-level checks if target is a directory and not disabled
    if target_path.is_dir() and not getattr(args, "no_library", False):
        auditor = LibraryAuditor(target_path, use_semantic=getattr(args, "semantic", False))
        lib_diags = [d for d in auditor.audit_library() if d.rule.code not in ignored]
        diagnostics.extend(lib_diags)

    # Output formatting
    if args.format == "json":
        print(format_json(diagnostics))
    elif args.format == "github":
        print(format_github(diagnostics))
    else:
        print(format_terminal(diagnostics, verbose=args.verbose))

    has_errors = any(d.severity == Severity.ERROR for d in diagnostics)
    return 1 if has_errors else 0


def cmd_audit(args) -> int:
    """Security-focused audit (SF1xx, SF2xx only)."""
    target_path = Path(args.path)
    if not target_path.exists():
        print(f"Error: Path '{target_path}' does not exist.", file=sys.stderr)
        return 1

    ignored = parse_ignore_list(args.ignore)
    scanner = SkillScanner(ignored_rules=ignored)

    all_diags = scanner.scan_path(target_path)
    # Filter to security & portability rules only
    sec_diags = [d for d in all_diags if d.rule.code.startswith(("SF1", "SF2"))]

    if args.format == "json":
        print(format_json(sec_diags))
    elif args.format == "github":
        print(format_github(sec_diags))
    else:
        print(format_terminal(sec_diags, verbose=args.verbose))

    has_errors = any(d.severity == Severity.ERROR for d in sec_diags)
    return 1 if has_errors else 0


def cmd_dedupe(args) -> int:
    """Multi-skill library collision and token bloat check."""
    target_path = Path(args.path)
    if not target_path.is_dir():
        print(f"Error: Target '{target_path}' must be a directory containing skills.", file=sys.stderr)
        return 1

    ignored = parse_ignore_list(args.ignore)
    auditor = LibraryAuditor(target_path, use_semantic=getattr(args, "semantic", False))
    diagnostics = [d for d in auditor.audit_library() if d.rule.code not in ignored]

    if args.format == "json":
        print(format_json(diagnostics))
    elif args.format == "github":
        print(format_github(diagnostics))
    else:
        print(format_terminal(diagnostics, verbose=args.verbose))

    has_errors = any(d.severity == Severity.ERROR for d in diagnostics)
    return 1 if has_errors else 0


def cmd_init(args) -> int:
    try:
        path = create_skill_scaffold(args.name, Path(args.dir), description=args.description or "")
        print(f"✓ Created new production-ready skill scaffold at:\n  {path.resolve()}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_rules(args) -> int:
    """List all available diagnostic rules."""
    print(f"\nSkillGuard Diagnostic Rules (v{__version__}):\n")
    print(f"{'Code':<8} {'Category':<12} {'Severity':<10} {'Name':<32} {'Summary'}")
    print("-" * 90)
    for code, rule in sorted(RULES.items()):
        print(f"{rule.code:<8} {rule.category:<12} {rule.severity.value:<10} {rule.name:<32} {rule.summary}")
    print("\nRun `skillguard check <path>` (or `skg check <path>`) to validate skills.\n")
    return 0


def cmd_stats(args) -> int:
    """Calculate token and size statistics for skills."""
    target_path = Path(args.path)
    auditor = LibraryAuditor(target_path)
    skills = auditor.find_all_skills()

    if not skills:
        print("No skills found.")
        return 0

    print(f"\nSkill Library Statistics ({len(skills)} skills found):\n")
    print(f"{'Skill Name':<30} {'Words':<10} {'Est. Tokens':<15} {'Status'}")
    print("-" * 65)

    total_words = 0
    for sdir in skills:
        skill_md = sdir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        words = len(text.split())
        total_words += words
        est_tokens = int(words * 1.33)
        status = "Optimal" if 40 <= words <= 1600 else "Too Long" if words > 1600 else "Too Short"
        print(f"{sdir.name:<30} {words:<10} ~{est_tokens:<14} {status}")

    total_tokens = int(total_words * 1.33)
    print("-" * 65)
    print(f"{'Total Library Footprint':<30} {total_words:<10} ~{total_tokens:<14}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillguard",
        description="SkillGuard: The Security Scanner, Linter, and Quality Gate for AI Agent Skills.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = subparsers.add_parser("check", help="Lint and security-scan skills")
    p_check.add_argument("path", nargs="?", default=".", help="Path to SKILL.md or skills directory (default: current dir)")
    p_check.add_argument("--format", choices=["terminal", "json", "github"], default="terminal", help="Output format")
    p_check.add_argument("--verbose", "-v", action="store_true", help="Show remediation guidance")
    p_check.add_argument("--ignore", default="", help="Comma-separated rule codes to ignore (e.g. SF008,SF201)")
    p_check.add_argument("--no-library", action="store_true", help="Skip multi-skill library checks")
    p_check.add_argument("--semantic", action="store_true", help="Use dense vector embeddings for collision check (requires sentence-transformers)")
    p_check.set_defaults(func=cmd_check)

    # audit
    p_audit = subparsers.add_parser("audit", help="Security and safety audit (destructive ops, data exfil, injection)")
    p_audit.add_argument("path", nargs="?", default=".", help="Path to SKILL.md or skills directory")
    p_audit.add_argument("--format", choices=["terminal", "json", "github"], default="terminal", help="Output format")
    p_audit.add_argument("--verbose", "-v", action="store_true", help="Show remediation guidance")
    p_audit.add_argument("--ignore", default="", help="Comma-separated rule codes to ignore")
    p_audit.set_defaults(func=cmd_audit)

    # dedupe
    p_dedupe = subparsers.add_parser("dedupe", help="Analyze routing collisions, trigger overlap, and library caps")
    p_dedupe.add_argument("path", nargs="?", default=".", help="Path to skills directory")
    p_dedupe.add_argument("--format", choices=["terminal", "json", "github"], default="terminal", help="Output format")
    p_dedupe.add_argument("--verbose", "-v", action="store_true", help="Show remediation guidance")
    p_dedupe.add_argument("--ignore", default="", help="Comma-separated rule codes to ignore")
    p_dedupe.add_argument("--semantic", action="store_true", help="Use dense vector embeddings for collision check (requires sentence-transformers)")
    p_dedupe.set_defaults(func=cmd_dedupe)

    # init
    p_init = subparsers.add_parser("init", help="Scaffold a new production-ready skill pack")
    p_init.add_argument("name", help="Skill name (e.g. git-conflict-resolver)")
    p_init.add_argument("--dir", default=".", help="Target directory to create skill in (default: current dir)")
    p_init.add_argument("--description", default="", help="Skill description")
    p_init.set_defaults(func=cmd_init)

    # rules
    p_rules = subparsers.add_parser("rules", help="List all diagnostic rules and codes")
    p_rules.set_defaults(func=cmd_rules)

    # stats
    p_stats = subparsers.add_parser("stats", help="Token and word count statistics for skills")
    p_stats.add_argument("path", nargs="?", default=".", help="Path to skills directory")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

