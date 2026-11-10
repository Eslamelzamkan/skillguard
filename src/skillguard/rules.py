"""Rule definitions and diagnostics for Skill-Forge."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Rule:
    code: str
    name: str
    category: str
    severity: Severity
    summary: str
    description: str
    remediation: str


@dataclass
class Diagnostic:
    rule: Rule
    file_path: str
    line: Optional[int] = None
    column: Optional[int] = None
    message: Optional[str] = None
    snippet: Optional[str] = None

    @property
    def severity(self) -> Severity:
        return self.rule.severity

    @property
    def formatted_message(self) -> str:
        return self.message or self.rule.summary


# --- Rule Registry -----------------------------------------------------------

RULES = {
    # SF0xx: Structure, Metadata & Format
    "SF001": Rule(
        code="SF001",
        name="missing-frontmatter",
        category="structure",
        severity=Severity.ERROR,
        summary="Missing YAML frontmatter block (--- ... ---)",
        description="Every SKILL.md must start with a YAML frontmatter block specifying its name and triggers.",
        remediation="Add `---` at the top of the file followed by `name:` and `description:`.",
    ),
    "SF002": Rule(
        code="SF002",
        name="missing-required-metadata",
        category="structure",
        severity=Severity.ERROR,
        summary="Frontmatter is missing required 'name' or 'description'",
        description="The agent framework requires both `name` (identifier) and `description` (routing instruction).",
        remediation="Ensure frontmatter has both `name: <noun-phrase>` and `description: <triggers>`.",
    ),
    "SF003": Rule(
        code="SF003",
        name="nonstandard-metadata-key",
        category="structure",
        severity=Severity.WARNING,
        summary="Non-standard key in YAML frontmatter",
        description="Standard agent skills specify only 'name' and 'description'. Unknown keys may break parsers.",
        remediation="Remove extra metadata keys or ensure they are supported by your target agent harness.",
    ),
    "SF004": Rule(
        code="SF004",
        name="missing-trigger-clause",
        category="quality",
        severity=Severity.WARNING,
        summary="Description does not start triggers with 'Use when...'",
        description="Agent routers select skills based on concrete triggers. Best practice demands starting triggers with 'Use when...'.",
        remediation="Format the description as: '<What it does>. Use when <symptoms/triggers>. Not for <out-of-scope>.'",
    ),
    "SF005": Rule(
        code="SF005",
        name="missing-pipeline-section",
        category="structure",
        severity=Severity.ERROR,
        summary="Missing 'Pipeline' or 'Procedure' section header",
        description="A skill must provide an explicit, ordered sequence of operational steps for the agent.",
        remediation="Add a `## Pipeline (do every step in order)` or `## Procedure` header with numbered steps.",
    ),
    "SF006": Rule(
        code="SF006",
        name="missing-scope-guard",
        category="safety",
        severity=Severity.ERROR,
        summary="Missing 'Scope guard' section",
        description="Skills without an explicit Scope Guard increase agent unsafe action rates by over 20pp (arXiv:2604.05172).",
        remediation="Add a `## Scope guard` section defining boundaries (e.g. trash > delete, content is data not commands).",
    ),
    "SF007": Rule(
        code="SF007",
        name="missing-not-in-scope",
        category="quality",
        severity=Severity.WARNING,
        summary="Missing 'Not in scope' boundary section",
        description="Negative scoping prevents negative transfer and hallucinated skill application outside its domain.",
        remediation="Add a `## Not in scope` section listing operations or task types this skill must NOT be used for.",
    ),
    "SF008": Rule(
        code="SF008",
        name="body-too-long",
        category="bloat",
        severity=Severity.WARNING,
        summary="Skill body exceeds 1,600 words (~2,000 tokens)",
        description="Overly long skills provide negative or negligible lift (+0.7pp vs +21.5pp for standard size) and consume excessive tokens.",
        remediation="Condense prose into concise steps. Move detailed documentation or examples to references/ files.",
    ),
    "SF009": Rule(
        code="SF009",
        name="body-too-short",
        category="quality",
        severity=Severity.WARNING,
        summary="Skill body is under 30 words",
        description="The skill lacks sufficient actionable detail to guide the agent.",
        remediation="Expand the pipeline with specific steps, API usage, or domain failure mechanisms.",
    ),

    # SF1xx: Safety, Destructive Commands & Security
    "SF101": Rule(
        code="SF101",
        name="destructive-command",
        category="security",
        severity=Severity.ERROR,
        summary="Potentially destructive filesystem command detected without explicit qualification",
        description="Patterns like rm -rf, os.remove, shutil.rmtree, or Path.unlink can cause permanent data loss.",
        remediation="Replace irreversible deletion with trash/archive verbs, or explicitly condition with 'only if explicitly authorized'.",
    ),
    "SF102": Rule(
        code="SF102",
        name="destructive-database-action",
        category="security",
        severity=Severity.ERROR,
        summary="Destructive database operation (DROP TABLE, TRUNCATE, mass DELETE) detected",
        description="Unhedged database drops or truncates destroy persistent state and violate safety boundaries.",
        remediation="Avoid raw DROP/TRUNCATE in general skills, or require explicit user confirmation.",
    ),
    "SF103": Rule(
        code="SF103",
        name="data-exfiltration-risk",
        category="security",
        severity=Severity.ERROR,
        summary="Potential data exfiltration or external forwarding pattern detected",
        description="Instructions that forward data to external endpoints, auditors, or configure auto-forwarding pose data leakage risks.",
        remediation="Ensure communication targets stay strictly within the task's stated recipient boundaries.",
    ),
    "SF104": Rule(
        code="SF104",
        name="permission-escalation",
        category="security",
        severity=Severity.ERROR,
        summary="Unauthorized permission change or public sharing detected",
        description="Setting public permissions (type=anyone, anyone-with-link) or admin privileges without isolation.",
        remediation="Restrict access to the task-specified collaborators only.",
    ),
    "SF105": Rule(
        code="SF105",
        name="prompt-injection-pattern",
        category="security",
        severity=Severity.ERROR,
        summary="Potential prompt injection or instruction override phrase detected",
        description="Phrases like 'ignore all previous instructions' or tampering with verifier/reward files.",
        remediation="Remove override phrases. Rephrase guidance objectively.",
    ),
    "SF106": Rule(
        code="SF106",
        name="secret-credential-probing",
        category="security",
        severity=Severity.ERROR,
        summary="Probing environment variables or local network for credentials",
        description="Dumping environment variables, scanning localhost ports, or base64-exfiltrating credentials.",
        remediation="Read only the specific environment variables designated for the task.",
    ),
    "SF107": Rule(
        code="SF107",
        name="dangerous-sidecar-file",
        category="security",
        severity=Severity.ERROR,
        summary="Security violation detected in bundled script or reference file",
        description="Sidecar files in scripts/ or references/ are an attack surface and must pass security checks.",
        remediation="Clean up the referenced script or document to eliminate unsafe patterns.",
    ),

    # SF2xx: Leakage, Grounding & Portability
    "SF201": Rule(
        code="SF201",
        name="absolute-path-leakage",
        category="portability",
        severity=Severity.WARNING,
        summary="Hardcoded absolute filesystem path found in skill body",
        description="Absolute paths (e.g. C:\\... or /home/...) make skills non-portable and leak private environment paths.",
        remediation="Use relative paths or parameterized paths (e.g. `<workspace>/path`).",
    ),
    "SF202": Rule(
        code="SF202",
        name="hash-or-uuid-literal",
        category="portability",
        severity=Severity.WARNING,
        summary="Hardcoded UUID or long cryptographic hash literal found in body",
        description="Hardcoded UUIDs or run hashes indicate over-fitted lookup table skills rather than general procedures.",
        remediation="Replace specific UUIDs/hashes with descriptive placeholders or variables.",
    ),

    # SF3xx: Multi-Skill Library Health & Collisions
    "SF301": Rule(
        code="SF301",
        name="skill-description-collision",
        category="library",
        severity=Severity.WARNING,
        summary="High trigger overlap (>55%) between two skill descriptions in library",
        description="Skills with overlapping trigger words or similar intent confuse the LLM router and cause routing instability.",
        remediation="Differentiate trigger keywords, clarify distinct use-cases, or consolidate into one skill.",
    ),
    "SF302": Rule(
        code="SF302",
        name="library-size-exceeded",
        category="library",
        severity=Severity.WARNING,
        summary="Library contains more than 8 active skills",
        description="Libraries with more than 8 active skills collapse agent lift from +19pp to +10pp due to context dilution.",
        remediation="Prune under-used skills or consolidate multiple domain skills into unified reference packs.",
    ),
    "SF303": Rule(
        code="SF303",
        name="domain-duplicate-skills",
        category="library",
        severity=Severity.WARNING,
        summary="Multiple active skills assigned to the same domain",
        description="Having multiple competing skills in one domain hurts performance; consolidation yields higher lift.",
        remediation="Merge multiple domain skills into one well-structured, multi-step domain procedure.",
    ),
}

