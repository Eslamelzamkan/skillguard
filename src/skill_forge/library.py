"""Library auditor: cross-skill analysis, collision detection, and token budgeting."""

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .rules import Diagnostic, Rule, RULES

STOPWORDS = {
    "use", "when", "the", "a", "an", "for", "to", "of", "and", "or",
    "not", "this", "is", "with", "on", "in", "it", "at", "by", "from",
    "that", "as", "be", "do", "you", "agent", "skill"
}

LIBRARY_CAP = 8
COLLISION_JACCARD_THRESHOLD = 0.55


class LibraryAuditor:
    """Performs library-wide analysis across a collection of skills.

    Engine:
      - Default: Fast, zero-dependency Lexical & Trigger Overlap Analysis
                 (Jaccard similarity on keyword tokens and n-grams).
      - Optional: Dense vector semantic analysis if `use_semantic=True`
                 and `sentence-transformers` is installed.
    """

    def __init__(self, root_dir: Path, use_semantic: bool = False):
        self.root_dir = Path(root_dir)
        self.use_semantic = use_semantic

    def find_all_skills(self) -> List[Path]:
        """Find all skill directories containing a SKILL.md under root_dir."""
        skill_dirs = []
        if (self.root_dir / "SKILL.md").exists():
            return [self.root_dir]
        for p in sorted(self.root_dir.rglob("SKILL.md")):
            # Ignore hidden or internal folders like .skill-forge or _versions
            if not any(part.startswith(".") or part.startswith("_") for part in p.parts):
                skill_dirs.append(p.parent)
        return skill_dirs

    def tokenize_description(self, description: str) -> Set[str]:
        words = re.findall(r"[a-z]{3,}", description.lower())
        return {w for w in words if w not in STOPWORDS}

    def audit_library(self) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        skills = self.find_all_skills()

        # SF302: Library size check (> 8 skills)
        if len(skills) > LIBRARY_CAP:
            diagnostics.append(
                Diagnostic(
                    rule=RULES["SF302"],
                    file_path=str(self.root_dir),
                    message=f"Library contains {len(skills)} skills (recommended cap: {LIBRARY_CAP}). Over-accumulation dilutes agent lift.",
                )
            )

        # Collect descriptions and metadata
        descriptions: Dict[str, str] = {}
        names: List[str] = []
        domains: Dict[str, List[str]] = defaultdict(list)

        for sdir in skills:
            skill_md = sdir / "SKILL.md"
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            desc_match = re.search(r"description:\s*(.+)", text)
            name_match = re.search(r"name:\s*(.+)", text)

            skill_name = name_match.group(1).strip() if name_match else sdir.name
            desc_text = desc_match.group(1).strip() if desc_match else ""

            descriptions[skill_name] = desc_text
            names.append(skill_name)

            # Guess domain from folder or name prefix
            domain = sdir.parent.name if sdir.parent != self.root_dir else skill_name.split("-")[0]
            domains[domain].append(skill_name)

        # SF301: Description collisions / routing interference
        if self.use_semantic:
            try:
                from sentence_transformers import SentenceTransformer, util
                model = SentenceTransformer("all-MiniLM-L6-v2")
                desc_texts = [descriptions[n] for n in names]
                embeddings = model.encode(desc_texts, convert_to_tensor=True)
                cosine_scores = util.cos_sim(embeddings, embeddings)

                for i, a in enumerate(names):
                    for j in range(i + 1, len(names)):
                        b = names[j]
                        score = float(cosine_scores[i][j])
                        if score >= 0.75:
                            diagnostics.append(
                                Diagnostic(
                                    rule=RULES["SF301"],
                                    file_path=str(self.root_dir),
                                    message=(
                                        f"High semantic vector similarity ({round(score * 100)}%) between `{a}` and `{b}`. "
                                        f"Overlapping intent causes routing confusion."
                                    ),
                                )
                            )
            except ImportError:
                diagnostics.append(
                    Diagnostic(
                        rule=RULES["SF301"],
                        file_path=str(self.root_dir),
                        message="Notice: 'sentence-transformers' not installed for dense semantic analysis. Falling back to pure-Python lexical trigger overlap. Install with: pip install skillguard[semantic]",
                    )
                )
                self.use_semantic = False

        if not self.use_semantic:
            # Default: Pure-Python Lexical & Trigger Overlap Analysis (Jaccard similarity)
            for i, a in enumerate(names):
                tokens_a = self.tokenize_description(descriptions[a])
                if not tokens_a:
                    continue
                for b in names[i + 1:]:
                    tokens_b = self.tokenize_description(descriptions[b])
                    if not tokens_b:
                        continue
                    intersection = tokens_a & tokens_b
                    union = tokens_a | tokens_b
                    jaccard = len(intersection) / len(union) if union else 0.0

                    if jaccard >= COLLISION_JACCARD_THRESHOLD:
                        shared_keywords = ", ".join(sorted(intersection)[:5])
                        diagnostics.append(
                            Diagnostic(
                                rule=RULES["SF301"],
                                file_path=str(self.root_dir),
                                message=(
                                    f"High lexical trigger overlap ({round(jaccard * 100)}%) between `{a}` and `{b}`. "
                                    f"Shared trigger tokens: [{shared_keywords}]. Causes routing confusion."
                                ),
                            )
                        )

        # SF303: Domain duplicate skills
        for domain, d_skills in domains.items():
            if len(d_skills) > 1 and domain not in ("skills", "tasks", "src"):
                diagnostics.append(
                    Diagnostic(
                        rule=RULES["SF303"],
                        file_path=str(self.root_dir),
                        message=f"Multiple skills found in domain '{domain}': {', '.join(d_skills)}. Consider consolidating into one skill.",
                    )
                )

        return diagnostics

