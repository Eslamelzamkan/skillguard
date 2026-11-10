# Authoring checklist

Run through this before writing a candidate to `candidates/`. Every rule
here has a measured cost for skipping it - not a style preference.

## Utility rubric (predicts whether a skill actually helps, arXiv:2605.23899)

A skill that scores well on all three below is measurably more likely to
produce positive paired lift (validated at 64-66% better-rate in controlled
comparison):

- [ ] **Failure-mechanism encoding** - names *why* the naive approach fails,
      not just what to do instead.
- [ ] **Actionable specificity** - exact API calls / function signatures /
      parameter values from the evidence, never a generic pointer ("use
      pandas for data processing" is the literal example of what fails).
- [ ] **High-risk-action blacklist** - if the domain touches anything
      destructive/external/permission-changing, the Scope guard names the
      specific actions to avoid (see `forge-gate/references/deny-patterns.md`).

## Length register (SkillsBench 1.1 length-curve data)

| Register | Measured mean lift | Verdict |
|---|---|---|
| Compact | +19.0pp | fine |
| **Standard (~40-150 lines)** | **+21.5pp (peak)** | **target this** |
| Detailed | +14.5pp | only if the domain genuinely needs it |
| Comprehensive | +0.7pp | effectively worthless - never write this |

Corroborated independently by `writing-skills` (github.com/obra/superpowers):
target <500 words for most skills, <200 words if it will load frequently.
If you're pushing past ~150 lines, move the excess to `references/*.md` -
loaded on demand, doesn't count against the in-context body.

## Description discipline (SDO)

- [ ] Starts with what it does, then "Use when <concrete triggers>."
- [ ] Includes "Not for <scope-out>" so mismatched tasks don't fire it.
- [ ] Contains the actual symptom/error words a fingerprint match would
      search for (exact exception names, file formats, tool names).
- [ ] **Does NOT summarize the procedure.** A description that previews the
      workflow gets followed *instead of* the body being read - documented
      failure mode (`writing-skills`): a two-stage process got collapsed to
      one stage because the description said "review between tasks" instead
      of just stating the trigger. State only when to fire, never how.
- [ ] Third person, technology-agnostic unless the skill is tech-specific.

## Match the section you emphasize to the failure category

| `aggregate.py` category | Emphasize in the candidate |
|---|---|
| `quality_below_threshold` | Pipeline states exactly what correct output IS (the shape, the exact values/format) - a positive recipe, not a list of things not to do. |
| `missing_artifact` | The required output becomes an explicit, numbered, un-skippable step. |
| `crash` | Critical rules table names the exact API misuse that crashed, and its fix. |
| `timeout` | Add the efficient path as its own step; name the slow path so it's avoided. |

(Rationale: prohibitions measurably backfire on wrong-shape/missing-element
failures - a positive recipe or structural slot wins head-to-head wording
tests, `writing-skills` "Match the Form to the Failure".)

## No nuance clauses, no unscoped exemptions

- [ ] No rule reads "don't X unless Y" - that reopens negotiation. If Y is
      real, write it as its own conditional keyed to an observable fact.
- [ ] No exemption bolted onto a rule ("this doesn't apply to Z") without
      restructuring the rule so it genuinely can't reach Z.

## Anti-patterns (reject on sight)

- [ ] Narrative tied to one specific run ("in trial 14 we saw...") instead
      of a generalized, reusable procedure.
- [ ] Multiple language variants of the same example.
- [ ] A flowchart used for a linear, non-branching process (use a numbered
      list) or code embedded inside flowchart node labels.
- [ ] Generic labels (`step1`, `helper2`) instead of semantic names.
- [ ] Non-standard frontmatter fields beyond `name` + `description`.

## Before writing the candidate

- [ ] Cited `run_id`(s) are real entries in `runs.jsonl` for this domain.
- [ ] Scope guard content matches the domain's actual risk (see
      `skill-template.md`) - not copy-pasted boilerplate on a domain with no
      destructive/external/permission surface.
- [ ] If nothing here can be checked honestly, apply the Abstention Rule
      instead of shipping a weak candidate.
