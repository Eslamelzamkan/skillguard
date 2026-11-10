# Contributing to SkillGuard 🛡️

Thank you for your interest in contributing to SkillGuard! We welcome contributions to make AI Agent Skills safer, more reliable, and higher quality.

---

## 🛠️ Local Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/eslamelzamkan/skillguard.git
   cd skillguard
   ```

2. Install in editable mode:
   ```bash
   pip install -e .
   ```

3. Run the test suite:
   ```bash
   python -m pytest tests/ -v
   ```

---

## 📋 Adding a New Diagnostic Rule

All diagnostic rules follow a standard identifier format:
* `SF0xx`: Structure, Formatting & Frontmatter
* `SF1xx`: Safety, Security & Destructive Operations
* `SF2xx`: Portability & Information Leakage
* `SF3xx`: Multi-Skill Library Health & Collisions

### Steps to Add a Rule:
1. Register the rule in `src/skillguard/rules.py` with its code, name, category, severity, summary, description, and remediation advice.
2. Implement the static detection logic in `src/skillguard/scanner.py` (or `library.py`).
3. Add positive and negative test cases in `tests/test_skillguard.py`.
4. Ensure all tests pass with `pytest`.
5. Update the Rule Catalog in `README.md`.

---

## 🧪 Testing Invariants

Every change must maintain SkillGuard's core invariants:
* **Zero Dependencies at Runtime:** The core CLI must run on Python 3.10+ using only the standard library.
* **Non-Destructive:** SkillGuard must never delete or overwrite user files without explicit flags.
* **Deterministic:** Rule verdicts must be deterministic and never rely on non-deterministic LLM calls.

---

## 📜 License

By contributing to SkillGuard, you agree that your contributions will be licensed under the project's [Apache-2.0 License](LICENSE).

