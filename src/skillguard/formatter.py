"""Formatters for diagnostic output: Terminal (ANSI), JSON, and GitHub Actions."""

import json
import sys
from typing import List

from .rules import Diagnostic, Severity

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"


def supports_color() -> bool:
    """Check if stdout supports ANSI color escape sequences."""
    return sys.stdout.isatty()


def format_terminal(diagnostics: List[Diagnostic], verbose: bool = False) -> str:
    use_color = supports_color()
    lines = []

    # Sort diagnostics by file, then line, then severity
    sorted_diags = sorted(
        diagnostics,
        key=lambda d: (
            d.file_path,
            d.line or 0,
            0 if d.severity == Severity.ERROR else 1,
        ),
    )

    current_file = None
    for d in sorted_diags:
        if d.file_path != current_file:
            current_file = d.file_path
            header = f"\n{BOLD}{current_file}{RESET}" if use_color else f"\n{current_file}"
            lines.append(header)

        # Severity badge
        if d.severity == Severity.ERROR:
            badge = f"{RED}{BOLD}error{RESET}" if use_color else "error"
        elif d.severity == Severity.WARNING:
            badge = f"{YELLOW}{BOLD}warning{RESET}" if use_color else "warning"
        else:
            badge = f"{CYAN}{BOLD}info{RESET}" if use_color else "info"

        line_str = f":{d.line}" if d.line else ""
        col_str = f":{d.column}" if d.column else ""
        loc = f"{DIM}{line_str}{col_str}{RESET}" if use_color else f"{line_str}{col_str}"
        code = f"{MAGENTA}[{d.rule.code}]{RESET}" if use_color else f"[{d.rule.code}]"

        msg = d.formatted_message
        lines.append(f"  {loc:8} {badge:16} {code:8} {msg}")

        if d.snippet:
            snip = f"    {DIM}> {d.snippet}{RESET}" if use_color else f"    > {d.snippet}"
            lines.append(snip)

        if verbose and d.rule.remediation:
            hint = f"    {CYAN}Fix: {d.rule.remediation}{RESET}" if use_color else f"    Fix: {d.rule.remediation}"
            lines.append(hint)

    # Summary
    errors = sum(1 for d in diagnostics if d.severity == Severity.ERROR)
    warnings = sum(1 for d in diagnostics if d.severity == Severity.WARNING)

    summary_parts = []
    if errors:
        summary_parts.append(f"{RED}{BOLD}{errors} error{'s' if errors != 1 else ''}{RESET}" if use_color else f"{errors} errors")
    if warnings:
        summary_parts.append(f"{YELLOW}{BOLD}{warnings} warning{'s' if warnings != 1 else ''}{RESET}" if use_color else f"{warnings} warnings")

    if not diagnostics:
        return f"\n{GREEN}{BOLD}✓ All skill checks passed! Zero safety or quality defects detected.{RESET}\n" if use_color else "\n✓ All skill checks passed! Zero safety or quality defects detected.\n"

    status = ", ".join(summary_parts)
    return "\n".join(lines) + f"\n\nFound {status}.\n"


def format_json(diagnostics: List[Diagnostic]) -> str:
    data = []
    for d in diagnostics:
        data.append({
            "file": d.file_path,
            "line": d.line,
            "column": d.column,
            "rule_code": d.rule.code,
            "rule_name": d.rule.name,
            "category": d.rule.category,
            "severity": d.severity.value,
            "message": d.formatted_message,
            "snippet": d.snippet,
            "remediation": d.rule.remediation,
        })
    return json.dumps(data, indent=2)


def format_github(diagnostics: List[Diagnostic]) -> str:
    """GitHub Actions workflow commands for inline PR annotations."""
    lines = []
    for d in diagnostics:
        cmd = "error" if d.severity == Severity.ERROR else "warning"
        loc = f"file={d.file_path}"
        if d.line:
            loc += f",line={d.line}"
        if d.column:
            loc += f",col={d.column}"
        lines.append(f"::{cmd} {loc}::[{d.rule.code}] {d.formatted_message}")
    return "\n".join(lines)

