<div align="center">

# 🛡️ SkillGuard

**The Static Security Scanner, Linter, and Quality Gate for AI Agent Skills (`SKILL.md`).**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-71%20passed-success.svg)](tests/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero%20(stdlib%20only)-blueviolet.svg)](#zero-dependencies)

*Works seamlessly across **Claude Code**, **Cursor**, **Google Antigravity**, **OpenAI Codex**, and **LangChain DeepAgents**.*

</div>

---

## ⚡ The Problem: Why Unchecked Agent Skills Fail

As autonomous coding agents adopt the `SKILL.md` paradigm, developers are writing, sharing, and auto-generating hundreds of skill packs. However, empirical research reveals severe pitfalls:

* **Negative Transfer (−1.3pp to −11.5pp):** Skills written without strict structural bounds and actionable specificity actually degrade agent performance by 25% to 47% ([arXiv:2602.12670](https://arxiv.org/abs/2602.12670), [arXiv:2605.23899](https://arxiv.org/abs/2605.23899)).
* **Security & Destructive Operations:** Unhedged skills instruct agents to execute permanent deletions (`rm -rf`, `DROP TABLE`), invite external users, or forward data outside workspace boundaries.
* **Prompt Injection Compliance:** Agents following instructions inside untrusted tool/email outputs treat injected text as commands without scope guards ([arXiv:2604.05172](https://arxiv.org/abs/2604.05172), [arXiv:2605.12015](https://arxiv.org/abs/2605.12015)).
* **Routing Collisions & Context Bloat:** Overlapping skill descriptions confuse the LLM router, while skills over 1,600 words dilute context and collapse lift from **+19.0pp to +10.1pp**.

**SkillGuard is the "ESLint + Snyk" for Agent Skills.** It catches defects, security vulnerabilities, routing collisions, and token bloat in milliseconds—before runtime.

---

## 🚀 Quick Start

### Installation

```bash
pip install skillguard-lint
```

*(Zero dependencies by default. Runs anywhere on Python 3.10+ using only the Python standard library).*

### 1. Lint and Check Skills

Scan an individual `SKILL.md` or a directory of skills:

```bash
skillguard check ./skills/
# Or use the fast alias:
skg check ./skills/
```

### 2. Security & Safety Audit

Audit specifically for destructive actions, credential leakage, and prompt injection patterns:

```bash
skillguard audit ./skills/
```

> **Smart Negation Detection:** SkillGuard understands English grammar and negative constraints. Unlike naive regex scripts, defensive sentences like `Never run rm -rf on the build directory` or scope-guard bullets like `- Avoid dropping tables` will **never** trigger false positives.

### 3. Detect Routing Collisions & Overlaps

Identify duplicate skills, trigger collisions, and excessive library accumulation:

```bash
# Pure-Python Lexical & Trigger Overlap (Default, <10ms, zero-dependency)
skillguard dedupe ./skills/

# Optional: Dense Vector Semantic Similarity (requires sentence-transformers)
skillguard dedupe ./skills/ --semantic
```

*(To use dense vector semantic embeddings, install the optional extra: `pip install "skillguard-lint[semantic]"`)*.

### 4. Scaffold a New Production-Ready Skill

Generate a clean, gold-standard, 100% compliant skill pack:

```bash
skillguard init git-conflict-resolver --description "Resolve git merge conflicts cleanly"
```

### 5. Inspect Library Token Footprint

```bash
skillguard stats ./skills/
```

---

## 🤖 GitHub Actions CI/CD Integration

Prevent broken or insecure agent skills from merging into your repository. Add this workflow to `.github/workflows/skill-audit.yml`:

```yaml
name: Skill Quality & Security Audit

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  audit-skills:
    name: Audit Agent Skills
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install skillguard-lint
      - run: skillguard check ./skills/ --format github
```

When run in GitHub Actions with `--format github`, SkillGuard automatically posts inline annotations directly on your pull request diffs!

---

## 📋 Diagnostic Rule Catalog

Run `skillguard rules` to inspect the full catalog:

| Code | Category | Severity | Name | Description |
|:---|:---|:---|:---|:---|
| **SF001** | Structure | `ERROR` | `missing-frontmatter` | Missing YAML frontmatter block (`--- ... ---`) |
| **SF002** | Structure | `ERROR` | `missing-required-metadata` | Frontmatter missing required `name` or `description` |
| **SF003** | Structure | `WARNING` | `nonstandard-metadata-key` | Non-standard metadata key in YAML frontmatter |
| **SF004** | Quality | `WARNING` | `missing-trigger-clause` | Description does not start triggers with `"Use when..."` |
| **SF005** | Structure | `ERROR` | `missing-pipeline-section` | Missing `## Pipeline` or `## Procedure` ordered steps |
| **SF006** | Safety | `ERROR` | `missing-scope-guard` | Missing `## Scope guard` boundary definitions |
| **SF007** | Quality | `WARNING` | `missing-not-in-scope` | Missing `## Not in scope` boundary section |
| **SF008** | Bloat | `WARNING` | `body-too-long` | Body exceeds 1,600 words (~2,000 tokens) |
| **SF009** | Quality | `WARNING` | `body-too-short` | Body is under 30 words (lacks actionable detail) |
| **SF101** | Security | `ERROR` | `destructive-command` | Irreversible deletion (`rm -rf`, `os.remove`, `Path.unlink`) |
| **SF102** | Security | `ERROR` | `destructive-database-action` | Destructive database op (`DROP TABLE`, `TRUNCATE`, `DELETE FROM`) |
| **SF103** | Security | `ERROR` | `data-exfiltration-risk` | Unauthorized external sending or auto-forwarding |
| **SF104** | Security | `ERROR` | `permission-escalation` | Public sharing (`anyone-with-link`, `setAdmin`) |
| **SF105** | Security | `ERROR` | `prompt-injection-pattern` | Instruction override (`ignore previous instructions`, verifier tamper) |
| **SF106** | Security | `ERROR` | `secret-credential-probing` | Harvesting environment variables or probing localhost |
| **SF107** | Security | `ERROR` | `dangerous-sidecar-file` | Unsafe pattern detected in `scripts/` or `references/` |
| **SF201** | Portability | `WARNING` | `absolute-path-leakage` | Absolute filesystem path (`C:\...`, `/home/...`) in body |
| **SF202** | Portability | `WARNING` | `hash-or-uuid-literal` | Hardcoded UUID or hash literal (overfitted lookup) |
| **SF301** | Library | `WARNING` | `skill-description-collision` | High trigger overlap (>55%) between skill descriptions |
| **SF302** | Library | `WARNING` | `library-size-exceeded` | Library exceeds 8 active skills (context dilution risk) |
| **SF303** | Library | `WARNING` | `domain-duplicate-skills` | Multiple active skills competing in the same domain |

---

## ⚙️ ESLint-Style Rule Suppression

SkillGuard supports granular inline directives identical to ESLint:

### 1. Disable Next Line

```markdown
<!-- skillguard-disable-next-line SF101 -->
Run rm -rf /tmp/test-cache to reset local test state.
```

### 2. Disable Multi-Line Block

```markdown
<!-- skillguard-disable SF101, SF102 -->
Execute shutil.rmtree(staging_dir)
Run DROP TABLE staging_users;
<!-- skillguard-enable SF101, SF102 -->
```

### 3. File-Level Suppression

```markdown
<!-- skillguard: ignore SF008, SF201 -->
```

### 4. CLI Suppression

```bash
skillguard check ./skills/ --ignore SF008,SF201
```

---

## 📚 Verified Research Foundations

SkillGuard's rules, heuristics, and thresholds are derived directly from published peer-reviewed AI agent benchmarks:

1. **SkillsBench ([arXiv:2602.12670](https://arxiv.org/abs/2602.12670)):**  
   *Xiangyi Li, Wenbo Chen, Yimin Liu, et al.*  
   *Key finding:* Uncurated self-generated skills deliver **−1.3pp** average lift (down to −11.5pp), while structured curated skills achieve **+16.6pp**. Focused modular skill registers consistently outperform bloated documentation packs.
2. **ClawsBench ([arXiv:2604.05172](https://arxiv.org/abs/2604.05172)):**  
   *Evaluating Capability and Safety of LLM Productivity Agents in Simulated Workspaces.*  
   *Key finding:* Adding domain skills without safety guardrails increases an agent's Unsafe Action Rate from **23% to 48%**. Introducing an explicit Scope Guard instruction layer cuts unsafe actions by **−21.9pp to −27.5pp** without hurting task capability.
3. **SkillFlow ([arXiv:2604.17308](https://arxiv.org/abs/2604.17308)):**  
   *Benchmarking Lifelong Skill Discovery and Evolution for Autonomous Agents.*  
   *Key finding:* Consolidating into 1 repeatedly-refined skill per domain beats accumulating multiple sibling skills (**+19.0pp vs +10.1pp**). Active library sizes beyond 8 skills lead to catastrophic routing interference.
4. **From Raw Experience to Skill Consumption ([arXiv:2605.23899](https://arxiv.org/abs/2605.23899)):**  
   *Zisu Huang, Jingwen Xu, Yifan Yang, et al.*  
   *Key finding:* Measures **25% to 47% negative transfer** in model-generated skills lacking procedural grounding and negative scoping (`## Not in scope`).
5. **SkillSafetyBench ([arXiv:2605.12015](https://arxiv.org/abs/2605.12015)):**  
   *Chang Jin, An Wang, Zeming Wei, et al.*  
   *Key finding:* Sidecar reference files and helper scripts are major attack vectors for prompt injection and sandbox escape. Validating `scripts/` and `references/` sidecars is essential for agent safety.

---

## 🏛️ Core Invariants

* **Zero Network, Stdlib Only:** Default runtime makes zero HTTP/network calls and has no external dependencies.
* **Sub-100ms Execution:** Built in pure Python for instantaneous execution in git pre-commit hooks and local terminals.
* **Non-Destructive:** Safe to execute across any private codebase or workspace.

---

## 📜 License

Apache-2.0 — Open source and enterprise ready.
