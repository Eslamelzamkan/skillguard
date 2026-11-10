<!-- skill-forge: ignore SF107 -->
# Deny patterns (judge-legible mirror of `safety_gate.py`)

Grounded in ClawsBench's violation taxonomy (arXiv:2604.05172): destructive
over-action, confidentiality leakage, unauthorized permission change, plus
generic injection/exfil/sandbox markers. A match is rejected unless the
surrounding line contains an explicit authorization qualifier ("only if the
instruction explicitly requires...", "with explicit user authorization").

| Category | Example patterns | Real-world action |
|---|---|---|
| Destructive (one-way-door) | `messages.delete`, `files.emptyTrash`, `events.delete`, `conversations.kick`, `rm -rf`, `DROP TABLE` | Irreversible delete/trash/kick across Gmail, Drive, Docs, Calendar, Slack, filesystem, DB |
| Leakage | `updateAutoForwarding`, `sendAs`, `forward...external`, `export...then...send` | Sending or auto-forwarding confidential content outside task scope |
| Permission | `permissions.create/update` with `anyone`/`writer`/`owner`, `anyone-with-link`, `transfer ownership`, `setAdmin` | Granting external access or elevating roles beyond task scope |
| Injection / exfil / sandbox | "ignore previous instructions", references to verifier/reward files, env-var enumeration, localhost probing, base64-encode-then-send | Prompt injection compliance, tampering with grading, sandbox escalation |

Scan covers `SKILL.md` body **and** any bundled `scripts/*` or
`references/*` files - a skill can smuggle an unsafe instruction into a
sidecar file as easily as into its own body (SkillSafetyBench,
arXiv:2605.12015).

Kept in sync by hand with `ALL_DENY` in `scripts/safety_gate.py`.
