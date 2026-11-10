# Skill-Forge: an evidence-gated meta-skill that refuses to ship what it can't prove

**Track 2 — Meta-Skills.** Submission: a three-skill meta-skill set that
authors, gates, and curates a domain-skill library under the BenchFlow
self-gen contract.

> Draft. `[MEASURED: …]` marks a number produced by the lab harness
> (`lab/measure_lift.py`) that is filled in after the calibration/holdout runs.
> Target length ≤ 2,000 words; current body is written to leave room for the
> final evidence tables.

## The problem this track poses

SkillsBench's own finding is the whole challenge in one number: a skill a model
writes for itself nets **−1.3pp** on average, while human-curated skills add
**+16.6pp** (arXiv:2602.12670). The track asks whether an optimizer can keep
climbing "without starting to produce unsafe skills." A naive self-generation
loop does the opposite of climbing — on the three dedicated self-gen configs in
that paper it scored **−8.1 / −11.3 / −11.5pp**. So the design target is not
"generate skills." It is: *generate only the skills that a paired measurement
would confirm actually help, and never generate one that trips a safety gate.*

Our thesis is that the gap between −1.3pp and +16.6pp is not a modeling gap —
it is a **verification** gap. The published pipeline that leaks value has no
gate before it trusts a self-written skill (arXiv:2605.23899 measures **25% of
model-generated skill entries as negative transfer**, 47% on the most fragile
domain). Close that gate and the self-generated penalty should invert toward
curated-grade lift. Everything below is built around that one claim.

## Architecture

Three skills, deliberately separated so each stage is inspectable
(a separation SkillForge-style pipelines converge on):

- **`skill-creator`** — reads deterministic failure evidence and drafts or
  revises one domain skill from a fixed gold template. It is the literal name
  BenchFlow's `self-gen` mode resolves as the creator scene, and it bundles the
  gate and ledger scripts inside its own `scripts/` because the harness copies
  only one skill pack into that scene.
- **`forge-gate`** — a deterministic validator. No LLM judgment anywhere: an
  LLM asked to pick the better of two skills chose the *worse* one ~84% of the
  time on high-gap pairs (arXiv:2605.23899), so we never let a model rank a
  skill. The ship decision is on hard, always-available checks only, fixed
  order, first hard-fail wins: **structure > safety > grounding > leakage >
  size.** Evidence *strength* is a separate tier label (below), never a ship
  gate.
- **`forge-refine`** — the ledger: an ExpeL-style retention counter whose slack
  is set by evidence tier, and archive-on-regression so a skill that stops
  helping removes itself before it propagates a bad abstraction.

**Robust to an unknown loop shape.** BenchFlow's open-source `self-gen` is
stateless per task — a fresh generated-skills root each time, no prior outcome
fed back — while the competition describes "evolving a library under a budget,"
which implies accumulation. We could not confirm which the organizers run, and
we get one submission, so the design is correct under **both**. The critical
path (diagnose → author one gated skill → ship) needs no cross-task state and
never emits an empty result (which BenchFlow hard-fails). The stateful machinery
(revise-in-place, outcome-driven pruning, consolidation, tier-climbing) activates
only when prior state is visible. Neither regime can make the skill unsafe or
empty.

The submitted runtime makes **zero network calls** and uses only the Python
standard library (enforced by a test that AST-scans every shipped script). All
model reasoning is done by the organizers' own agent following the SKILL.md
protocols; our scripts are the deterministic scaffolding around it.

## Lift (rubric 60%)

Four design decisions, each traceable to a measured finding, drive the lift
number:

1. **A quality-and-safety ship bar, evidence-tiered trust.** Every skill must
   clear the deterministic gate — gold-template structure, the utility rubric
   (failure-mechanism + actionable-specificity + scope guard), no leakage, size
   cap, and grounding in a real observed run — before it ships. This is what
   separates curated skills (+16.6pp) from ungrounded Condition-C filler
   (−1.3pp): concreteness and a quality bar, not merely "a skill exists." On top
   of that bar, evidence *strength* is a tier — VERIFIED (paired
   fail→pass, Voyager-style verify-before-save, 2305.16291), OBSERVED, or
   DIAGNOSED (cold-start) — that sets how quickly the retention counter prunes a
   skill that underperforms. Strong pairing is the *best* tier, not a
   requirement to ship, precisely because a stateless loop can never produce a
   pair; making it a requirement would ship nothing and hard-fail the rollout.
   The counter, plus the paired with/without scoring the competition already
   runs, is what culls the residual negative-transfer skills (the 25% leak in
   the ungated pipeline, arXiv:2605.23899).
2. **Consolidation over accumulation.** The refine stage biases toward revising
   one skill per domain in place rather than adding siblings. Winning libraries
   in SkillFlow converge to ~1 repeatedly-revised skill (+8.43pp); accumulation
   to 5.45 skills gained nothing (2604.17308). We cap the library at 8 and
   enforce one active skill per domain, because 4+ skills active on a task
   collapses lift from **+19.0pp to +10.1pp** (SkillsBench 1.1).
3. **Standard-register authoring.** The template targets 40–150 line skills.
   The length curve peaks at Standard (**+21.5pp**) and Comprehensive is
   **≈+0.7pp** — effectively worthless. Depth is pushed to `references/`.
4. **Abstention on skill-resistant tasks.** Pure math/OR tasks averaged only
   +9.7pp even with curated skills; some tasks regress. When the evidence shows
   no non-obvious, domain-specific procedure, the skill-creator writes nothing —
   because scoring is paired, a filler skill can only lose points.

**Result (holdout, deepagents + Llama-3.3-70B, 3 trials/arm):**
`[MEASURED: mean_pp_delta, mean_lift_g, per-domain breakdown]`.

## Compliance & safety (rubric 20%)

The safety analysis reversed our initial design emphasis, and that reversal is
the most important thing we learned. ClawsBench detects violations by
**deterministic database state-diff** — the −1.0 penalty comes from what the
*agent does at runtime*, not from text in a skill. And domain skills *alone*
raise the Unsafe Action Rate to **48%** (from 23% baseline), while an inline
safety-instruction layer cuts it back by **−21.9 to −27.5pp** (p < .05,
arXiv:2604.05172). The lever with a causal number is therefore not the scan —
it is the safety content injected into each generated skill.

So safety is two layers:

- **Layer 1 (the product): a calibrated Scope-guard section** the template
  requires in every generated skill — one-way-door confirmation (prefer
  trash > delete, archive > kick), an external-recipient boundary rule,
  "content is data, not commands" *with* an explicit exception for genuine
  task constraints (to avoid the documented backfire where a model dismissed a
  real legal hold as an "embedded override"), identity verification, and an
  anti-paralysis clause so routine internal operations aren't over-refused.
- **Layer 2 (insurance + audit): the deterministic gate.** Deny-pattern scans
  over the skill body *and* its bundled scripts/references (SkillSafetyBench,
  2605.12015, shows sidecar files are an attack channel), a leakage scan that
  rejects task-specific paths/values/UUIDs, and hard size caps. Our own shipped
  scripts contain no deletion primitive at all (archive-by-move only), enforced
  by a source-grep test.

**Evidence:** an adversarial candidate corpus (destructive office ops,
leakage-laced, plausible-but-unverified, injection-marker) is a permanent test
fixture; the gate rejects **[MEASURED: N/N]** of it. Bait-task suite:
**[MEASURED: unsafe-action count with the evolved library loaded]**, with
over-refusal on capability tasks held at **[MEASURED: rate]**.

## Generalization (rubric 10%)

Two mechanisms target public→private transfer. First, the leakage gate makes a
lookup-table skill unrepresentable: any candidate that hardcodes a run's paths,
expected values, or IDs is rejected, so a skill must generalize to a task class
to survive at all. Second, the domain taxonomy is not a hardcoded enum — it
reads each task's own `category` metadata, so an unseen private-mix domain is
handled as the ordinary breadth-first "no skill here yet" case rather than a
special case. We report **[MEASURED: dev-holdout lift]** on tasks never tuned
on, and per-domain consistency alongside the mean, since the rubric rewards
consistent lift over a spiky one.

## Reproducibility (rubric 10%)

Everything is one deterministic split and two commands (`lab/README.md`). The
split generator is seedless; `lab/split.json` is committed. Measurement shells
out to the real `bench eval run` — the same CLI that scores the competition —
so local numbers are the scoring metric, not a proxy. The runtime skill is
stdlib-only and offline, audited by tests. License: Apache-2.0.

## What we validated about the mechanism

We did not assume how Track 2 invokes a submission; we dissected the BenchFlow
SDK. `self-gen` runs a creator scene (sees only our one pack + the task prompt,
must write skills one level deep under a `generated_skills_root`) then a fresh
solver scene mounted with only those skills. It is stateless per task in the
open-source SDK; any cross-task accumulation is organizer orchestration on top.
We tested our submission against the SDK's own resolver and found — and fixed —
a silent-discard failure (our multi-pack folder didn't resolve until the entry
pack was named `skill-creator`). The single open question we cannot resolve from
the code, and are raising with the organizers, is how library state carries
forward between calibration tasks; our design is anytime-safe and correct under
both the stateless and the accumulating interpretation.

## Limitations

`[MEASURED: honest note on where lift was flat or negative, which domains
resisted, and any gate false-positives that cost capability.]` Local runs use
Groq-hosted open models, a lower bound on the frontier panel used at scoring;
we argue the imperative, numbered protocol style transfers upward.

## Citations

SkillsBench (2602.12670); ClawsBench (2604.05172); From Raw Experience to Skill
Consumption (2605.23899); SkillFlow (2604.17308); Agent Skill Evaluation &
Evolution (2606.11435); SkillSafetyBench (2605.12015); Voyager (2305.16291);
ExpeL (2308.10144).
