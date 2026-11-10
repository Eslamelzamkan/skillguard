# SkillGuard Examples

This directory contains reference examples demonstrating how SkillGuard audits and protects AI Agent Skills (`SKILL.md`).

## 1. Clean Skill (`examples/clean_skill/`)
A production-ready, gold-standard skill pack following all best practices:
- Concrete `Use when... Not for...` trigger clauses
- Explicit ordered pipeline steps
- Robust Scope Guard preventing destructive ops and prompt injections
- Strict token budgeting (< 1,600 words)

**Run the audit:**
```bash
skillguard check examples/clean_skill/
```
Output:
```
✓ All skill checks passed! Zero safety or quality defects detected.
```

---

## 2. Vulnerable Skill (`examples/vulnerable_skill/`)
A skill intentionally demonstrating common real-world failure patterns:
- Destructive commands (`rm -rf /tmp/data`, `shutil.rmtree`)
- Data exfiltration & credential harvesting (`base64-encode env vars and forward`)
- Prompt injection compliance (`if instruction says 'ignore previous instructions', follow it`)
- Missing Scope Guard and boundary sections

**Run the audit:**
```bash
skillguard check examples/vulnerable_skill/
```

**Run with remediation guidance:**
```bash
skillguard check examples/vulnerable_skill/ --verbose
```

