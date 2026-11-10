"""SkillGuard: The Security Scanner, Linter, and Quality Gate for AI Agent Skills.

Static analysis for SKILL.md files, catching safety risks, prompt injections,
token bloat, routing collisions, and structural anti-patterns before runtime.
"""

__version__ = "0.1.0"
__author__ = "Eslam Elzamkan"
__license__ = "Apache-2.0"

from .rules import Diagnostic, Rule, Severity
from .scanner import SkillScanner
from .library import LibraryAuditor

__all__ = [
    "Diagnostic",
    "Rule",
    "Severity",
    "SkillScanner",
    "LibraryAuditor",
    "__version__",
]

