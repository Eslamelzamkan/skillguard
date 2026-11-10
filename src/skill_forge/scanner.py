"""Skill scanner: static analysis of SKILL.md and its sidecars."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .rules import Diagnostic, Rule, RULES


# --- Pattern Definitions -----------------------------------------------------

DESTRUCTIVE_PATTERNS = [
    r"\bmessages\.(delete|batchDelete|trash)\b",
    r"\bthreads\.(delete|trash)\b",
    r"\bdrafts\.delete\b",
    r"\blabels\.delete\b",
    r"\bfilters\.delete\b",
    r"\bfiles\.delete\b",
    r"\bfiles\.emptyTrash\b",
    r"\brevisions\.delete\b",
    r"\bdeleteContentRange\b",
    r"\bdeleteTableRow\b",
    r"\bevents\.delete\b",
    r"\bcalendars\.delete\b",
    r"\bacl\.delete\b",
    r"\bconversations\.(kick|archive|leave)\b",
    r"\bchat\.delete\b",
    r"\badmin\.conversations\.delete\b",
    r"\bbulk[ _-]?(delete|remove)\b",
    r"\brm\s+-[rRfF]+\b",
    r"\bdel\s+/[fFqQsS]+\b",
    r"\bshutil\.rmtree\b",
    r"\bos\.(remove|unlink)\b",
    r"\b(pathlib\.)?Path\b.*?\.(unlink|rmdir)\b",
    r"\bDROP\s+TABLE\b",
    r"\bTRUNCATE\b",
    r"\bDELETE\s+FROM\b",
]

LEAKAGE_PATTERNS = [
    r"\bupdateAutoForwarding\b",
    r"\bcreateForwardingAddress\b",
    r"\bsendAs\b",
    r"\bforward(ing|s|ed)?\b.{0,80}\bexternal\b",
    r"\bexternal\s+(cc|bcc|recipient)\b",
    r"\b(send|share|forward|email)\w*\b.{0,80}\b(external|third[ -]?party|outside)\s+(partner|auditor|recipient|party|client|collaborator|address|domain|vendor|contact|user)\b",
    r"\bexport.{0,20}then.{0,20}send\b",
    r"\bpost.{0,15}externally\b",
]

PERMISSION_PATTERNS = [
    r"\bpermissions\.(create|update)\b",
    r"\btype=\"?anyone\"?\b",
    r"\brole=\"?(writer|owner)\"?\b",
    r"\banyone[- ]with[- ]link\b",
    r"\btransfer\s+ownership\b",
    r"\bdelegates\.create\b",
    r"\bconversations\.invite\b.{0,20}external\b",
    r"\bsetAdmin\b",
    r"\bwritersCanShare\b",
]

INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"\bverifier\s+(path|source|code)\b",
    r"\breward\.txt\b.{0,20}(edit|modify|write)\b",
    r"\b(print|dump|list|read|enumerate|expose)\b.{0,40}\benviron(ment)?\s+variab",
    r"\benv(iron)?\s+var\w*\b.{0,25}(enumerat|credential|secret|dump|exfil)",
    r"\blocalhost\b.{0,15}(curl|probe|scan)\b",
    r"\bbase64.{0,15}(encode|send)\b",
]

QUALIFIER_PHRASES = (
    "only if",
    "explicitly requires",
    "explicit user authorization",
    "explicit instruction",
    "with explicit approval",
    "with user approval",
)

NEGATION_MARKERS = (
    "never ",
    "never\t",
    "do not ",
    "don't ",
    "avoid ",
    "avoiding ",
    "refuse to ",
    "refuse ",
    "prohibit ",
    "prohibiting ",
    "disallow ",
    "disallowing ",
    "prevent ",
    "preventing ",
    "without ",
    "without running ",
    "must not ",
    "should not ",
    "cannot ",
    "can not ",
    "ensure you don't ",
    "ensure not to ",
    "warn against ",
    "instead of ",
    "rather than ",
)

DISABLE_NEXT_LINE_PATTERN = re.compile(
    r"<!--\s*(?:skillguard|skill-forge)[-:]disable-next-line(?:\s+([A-Za-z0-9_,\s]+))?\s*-->",
    re.IGNORECASE,
)
DISABLE_BLOCK_PATTERN = re.compile(
    r"<!--\s*(?:skillguard|skill-forge)[-:]disable(?:\s+([A-Za-z0-9_,\s]+))?\s*-->",
    re.IGNORECASE,
)
ENABLE_BLOCK_PATTERN = re.compile(
    r"<!--\s*(?:skillguard|skill-forge)[-:]enable(?:\s+([A-Za-z0-9_,\s]+))?\s*-->",
    re.IGNORECASE,
)
FILE_IGNORE_PATTERN = re.compile(
    r"<!--\s*(?:skillguard|skill-forge):\s*ignore\s+([^>]+)-->",
    re.IGNORECASE,
)


def is_negative_guardrail(line: str, match_start: int) -> bool:
    """Checks if the pattern matched on `line` is governed by a negative constraint or prohibition."""
    line_lower = line.lower()
    clean_line = line_lower.strip().lstrip("-*#>0123456789. \t")

    # 1. Whole line begins with a prohibition
    for marker in NEGATION_MARKERS:
        if clean_line.startswith(marker):
            return True

    # 2. Preceding clause in the same line/sentence (e.g. "make sure to avoid rm -rf", "do not use shutil.rmtree")
    prefix = line_lower[:match_start]
    # Split by clause boundaries
    clause = re.split(r"[;.]|(\bbut\b)|(\bhowever\b)", prefix)[-1] or ""
    for marker in NEGATION_MARKERS:
        if marker in clause:
            return True

    return False


ALLOWED_FRONTMATTER_KEYS = {"name", "description"}
REQUIRED_SECTION_PIPELINE = ("pipeline", "procedure")
REQUIRED_SECTION_SCOPE_GUARD = "scope guard"
REQUIRED_SECTION_NOT_IN_SCOPE = "not in scope"

MAX_BODY_WORDS = 1600
MIN_BODY_WORDS = 30


class SkillScanner:
    """Scans single skill folders or SKILL.md files for defects and security issues."""

    def __init__(self, ignored_rules: Optional[Set[str]] = None):
        self.ignored_rules = set(ignored_rules or [])

    def scan_path(self, target: Path) -> List[Diagnostic]:
        """Scan a path which can be a SKILL.md file or a skill directory."""
        target = Path(target)
        if target.is_file():
            if target.name.lower() == "skill.md":
                return self.scan_skill_directory(target.parent)
            return self.scan_file_directly(target)
        elif target.is_dir():
            skill_md = target / "SKILL.md"
            if skill_md.exists():
                return self.scan_skill_directory(target)
            else:
                # If directory doesn't have SKILL.md directly, search subdirectories
                diagnostics = []
                for child_md in sorted(target.rglob("SKILL.md")):
                    diagnostics.extend(self.scan_skill_directory(child_md.parent))
                return diagnostics
        return []

    def scan_file_directly(self, file_path: Path) -> List[Diagnostic]:
        file_path = Path(file_path)
        if not file_path.exists():
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
        return self._scan_skill_text(text, str(file_path))

    def scan_skill_directory(self, skill_dir: Path) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return diagnostics

        skill_text = skill_md.read_text(encoding="utf-8", errors="replace")
        diagnostics.extend(self._scan_skill_text(skill_text, str(skill_md)))

        # Also audit sidecar files (scripts/ and references/) for security issues
        for sub in ("scripts", "references"):
            sub_dir = skill_dir / sub
            if sub_dir.exists():
                for f in sub_dir.rglob("*"):
                    if f.is_file() and not f.name.endswith(".pyc"):
                        sidecar_text = f.read_text(encoding="utf-8", errors="replace")
                        sidecar_diags = self._scan_sidecar_text(sidecar_text, str(f))
                        diagnostics.extend(sidecar_diags)

        return [d for d in diagnostics if d.rule.code not in self.ignored_rules]

    def _split_frontmatter(self, text: str) -> Tuple[Dict[str, str], str, int]:
        """Returns (frontmatter_dict, body_text, frontmatter_line_count)."""
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not m:
            return {}, text, 0
        fm_text, body = m.group(1), m.group(2)
        fm = {}
        for line in fm_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
        line_count = len(fm_text.splitlines()) + 2
        return fm, body, line_count

    def _extract_headers(self, body: str) -> List[Tuple[str, int]]:
        """Extracts markdown headers and their 1-indexed line numbers in body."""
        headers = []
        for i, line in enumerate(body.splitlines(), 1):
            m = re.match(r"^#{1,3}\s+(.+)$", line)
            if m:
                headers.append((m.group(1).strip().lower(), i))
        return headers

    def _scan_skill_text(self, text: str, file_path: str) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []

        # Check inline file-level ignore comments: e.g. <!-- skillguard: ignore SF008, SF101 -->
        local_ignores = set(self.ignored_rules)
        for m in FILE_IGNORE_PATTERN.finditer(text):
            for code in m.group(1).split(","):
                local_ignores.add(code.strip().upper())

        fm, body, fm_lines = self._split_frontmatter(text)

        # SF001: Missing YAML frontmatter
        if not fm:
            if "SF001" not in local_ignores:
                diagnostics.append(Diagnostic(rule=RULES["SF001"], file_path=file_path, line=1))
        else:
            # SF002: Missing required metadata
            missing_keys = [k for k in ("name", "description") if k not in fm or not fm[k]]
            if missing_keys and "SF002" not in local_ignores:
                diagnostics.append(
                    Diagnostic(
                        rule=RULES["SF002"],
                        file_path=file_path,
                        line=1,
                        message=f"Frontmatter missing required keys: {', '.join(missing_keys)}",
                    )
                )

            # SF003: Non-standard metadata keys
            extra_keys = set(fm.keys()) - ALLOWED_FRONTMATTER_KEYS
            if extra_keys and "SF003" not in local_ignores:
                diagnostics.append(
                    Diagnostic(
                        rule=RULES["SF003"],
                        file_path=file_path,
                        line=1,
                        message=f"Non-standard metadata keys: {', '.join(sorted(extra_keys))}",
                    )
                )

            # SF004: Description trigger check
            desc = fm.get("description", "").lower()
            if desc and "use when" not in desc and "SF004" not in local_ignores:
                diagnostics.append(
                    Diagnostic(
                        rule=RULES["SF004"],
                        file_path=file_path,
                        line=2,
                        message="Description should specify triggers starting with 'Use when...'",
                    )
                )

        headers_with_lines = self._extract_headers(body)
        header_names = [h[0] for h in headers_with_lines]

        # SF005: Pipeline / Procedure header
        if not any(any(h.startswith(p) for p in REQUIRED_SECTION_PIPELINE) for h in header_names):
            if "SF005" not in local_ignores:
                diagnostics.append(Diagnostic(rule=RULES["SF005"], file_path=file_path, line=fm_lines + 1))

        # SF006: Scope guard section
        if not any(h.startswith(REQUIRED_SECTION_SCOPE_GUARD) for h in header_names):
            if "SF006" not in local_ignores:
                diagnostics.append(Diagnostic(rule=RULES["SF006"], file_path=file_path, line=fm_lines + 1))

        # SF007: Not in scope section
        if not any(h.startswith(REQUIRED_SECTION_NOT_IN_SCOPE) for h in header_names):
            if "SF007" not in local_ignores:
                diagnostics.append(Diagnostic(rule=RULES["SF007"], file_path=file_path, line=fm_lines + 1))

        # SF008 / SF009: Length / Bloat checks
        words = len(body.split())
        if words > MAX_BODY_WORDS and "SF008" not in local_ignores:
            diagnostics.append(
                Diagnostic(
                    rule=RULES["SF008"],
                    file_path=file_path,
                    line=fm_lines + 1,
                    message=f"Skill body exceeds recommended cap: {words} words (cap: {MAX_BODY_WORDS})",
                )
            )
        elif words < MIN_BODY_WORDS and "SF009" not in local_ignores:
            diagnostics.append(
                Diagnostic(
                    rule=RULES["SF009"],
                    file_path=file_path,
                    line=fm_lines + 1,
                    message=f"Skill body too short: {words} words (minimum: {MIN_BODY_WORDS})",
                )
            )

        # Security & Leakage scans per line with ESLint-style directive support
        all_lines = text.splitlines()
        disabled_next_line: Set[str] = set()
        block_disabled: Set[str] = set()
        in_scope_guard = False

        for line_no, line in enumerate(all_lines, 1):
            line_strip = line.strip()

            # Track section boundaries (Scope guard section is inherently defensive)
            if line_strip.startswith("#"):
                h_low = line_strip.lower()
                if "scope guard" in h_low:
                    in_scope_guard = True
                elif any(h_low.startswith(p) for p in ("# ", "## ", "### ")) and "scope guard" not in h_low:
                    in_scope_guard = False

            # Check directive: disable-next-line
            m_next = DISABLE_NEXT_LINE_PATTERN.search(line)
            if m_next:
                r_str = m_next.group(1)
                disabled_next_line = {r.strip().upper() for r in r_str.split(",")} if r_str else {"*"}
                continue

            # Check directive: block disable
            m_dis = DISABLE_BLOCK_PATTERN.search(line)
            if m_dis:
                r_str = m_dis.group(1)
                block_disabled.update(r.strip().upper() for r in r_str.split(",")) if r_str else block_disabled.add("*")
                continue

            # Check directive: block enable
            m_en = ENABLE_BLOCK_PATTERN.search(line)
            if m_en:
                r_str = m_en.group(1)
                if r_str:
                    block_disabled.difference_update(r.strip().upper() for r in r_str.split(","))
                else:
                    block_disabled.clear()
                continue

            # Active disabled rules for this line
            active_ignores = local_ignores | block_disabled | disabled_next_line
            # Reset next-line ignore for the following line
            disabled_next_line = set()

            if "*" in active_ignores:
                continue

            line_lower = line.lower()
            clean_line = line_lower.strip().lstrip("-*#|> \t")

            # Check if whole line has explicit qualifier phrase
            has_explicit_qualifier = any(q in line_lower for q in QUALIFIER_PHRASES)

            # SF101: Destructive command
            if "SF101" not in active_ignores:
                for pattern in DESTRUCTIVE_PATTERNS:
                    m = re.search(pattern, line, re.IGNORECASE)
                    if m:
                        is_guarded = has_explicit_qualifier or is_negative_guardrail(line, m.start()) or (in_scope_guard and clean_line.startswith(("prefer ", "never ", "do not ", "avoid ")))
                        if not is_guarded:
                            diagnostics.append(
                                Diagnostic(
                                    rule=RULES["SF101"],
                                    file_path=file_path,
                                    line=line_no,
                                    message=f"Destructive action matched `{pattern}` without explicit authorization phrasing",
                                    snippet=line.strip()[:100],
                                )
                            )
                            break

            # SF103: Data exfiltration
            if "SF103" not in active_ignores:
                for pattern in LEAKAGE_PATTERNS:
                    m = re.search(pattern, line, re.IGNORECASE)
                    if m:
                        is_guarded = has_explicit_qualifier or is_negative_guardrail(line, m.start()) or (in_scope_guard and clean_line.startswith(("never ", "do not ", "avoid ", "refuse ")))
                        if not is_guarded:
                            diagnostics.append(
                                Diagnostic(
                                    rule=RULES["SF103"],
                                    file_path=file_path,
                                    line=line_no,
                                    message=f"Potential exfiltration pattern matched `{pattern}`",
                                    snippet=line.strip()[:100],
                                )
                            )
                            break

            # SF104: Permission escalation
            if "SF104" not in active_ignores:
                for pattern in PERMISSION_PATTERNS:
                    m = re.search(pattern, line, re.IGNORECASE)
                    if m:
                        is_guarded = has_explicit_qualifier or is_negative_guardrail(line, m.start()) or in_scope_guard
                        if not is_guarded:
                            diagnostics.append(
                                Diagnostic(
                                    rule=RULES["SF104"],
                                    file_path=file_path,
                                    line=line_no,
                                    message=f"Permission escalation matched `{pattern}`",
                                    snippet=line.strip()[:100],
                                )
                            )
                            break

            # SF105: Prompt injection / instruction override
            if "SF105" not in active_ignores:
                for pattern in INJECTION_PATTERNS:
                    m = re.search(pattern, line, re.IGNORECASE)
                    if m:
                        is_guarded = has_explicit_qualifier or is_negative_guardrail(line, m.start()) or in_scope_guard
                        if not is_guarded:
                            diagnostics.append(
                                Diagnostic(
                                    rule=RULES["SF105"],
                                    file_path=file_path,
                                    line=line_no,
                                    message=f"Instruction override/injection matched `{pattern}`",
                                    snippet=line.strip()[:100],
                                )
                            )
                            break

            # SF201: Absolute path leakage
            if "SF201" not in active_ignores:
                if re.search(r"[A-Za-z]:\\\\|(?<!\w)/root/\S+|(?<!\w)/home/\S+", line):
                    diagnostics.append(
                        Diagnostic(
                            rule=RULES["SF201"],
                            file_path=file_path,
                            line=line_no,
                            message="Absolute filesystem path found (compromises portability)",
                            snippet=line.strip()[:100],
                        )
                    )

            # SF202: Hash / UUID literal leakage
            if "SF202" not in active_ignores:
                if re.search(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", line) or re.search(r"\b[0-9a-fA-F]{32,}\b", line):
                    diagnostics.append(
                        Diagnostic(
                            rule=RULES["SF202"],
                            file_path=file_path,
                            line=line_no,
                            message="UUID or hash literal found (indicates over-fitted or non-generalizable rule)",
                            snippet=line.strip()[:100],
                        )
                    )

        return diagnostics

    def _scan_sidecar_text(self, text: str, file_path: str) -> List[Diagnostic]:
        """Scans bundled scripts or references for security threats."""
        local_ignores = set(self.ignored_rules)
        for m in re.finditer(r"<!--\s*skill-forge:\s*ignore\s+([^>]+)-->", text):
            for code in m.group(1).split(","):
                local_ignores.add(code.strip())

        if "SF107" in local_ignores:
            return []

        diagnostics = []
        for line_no, line in enumerate(text.splitlines(), 1):
            line_lower = line.lower()
            clean_line = line_lower.strip().lstrip("-*#| ")
            is_defensive = any(clean_line.startswith(p) for p in PROHIBITION_PREFIXES)
            has_qualifier = is_defensive or any(q in line_lower for q in QUALIFIER_PHRASES)

            for pattern in DESTRUCTIVE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE) and not has_qualifier:
                    diagnostics.append(
                        Diagnostic(
                            rule=RULES["SF107"],
                            file_path=file_path,
                            line=line_no,
                            message=f"Dangerous command in sidecar file: matched `{pattern}`",
                            snippet=line.strip()[:100],
                        )
                    )
                    break
            for pattern in INJECTION_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    diagnostics.append(
                        Diagnostic(
                            rule=RULES["SF107"],
                            file_path=file_path,
                            line=line_no,
                            message=f"Injection marker in sidecar file: matched `{pattern}`",
                            snippet=line.strip()[:100],
                        )
                    )
                    break
        return [d for d in diagnostics if d.rule.code not in local_ignores]
