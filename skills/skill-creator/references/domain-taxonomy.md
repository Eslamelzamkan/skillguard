# Domain taxonomy

## Domain = the task's own declared category, not a hardcoded list

The private bench-mix explicitly includes "held-out capability tasks in new
domains" (competition rules). A fixed, hand-written enum of domains would
silently misclassify or ignore anything not on the list. Instead:

- **`domain`** for every `RunRecord` and skill = the task's own `category`
  field (BenchFlow `task.md` frontmatter ships `metadata.category` and
  `metadata.subcategory` on every task - read it directly, don't invent one).
- **`subcategory`** is a secondary fingerprint tag: use it to disambiguate
  when a category is broad (e.g. "data-processing" spans many subcategories
  with different failure modes).
- **Retrieval fingerprint** = category + subcategory + a keyword extraction
  from the task prompt (file extensions mentioned, tool/library names,
  error-shaped phrases). This is the same information a human would use to
  pick which reference doc to open - no embeddings, no network, just
  substring/keyword matching against each library skill's `description`.

This makes the taxonomy self-extending: a brand-new private-mix domain gets
its own category label straight from the task metadata, and `skill-creator`
treats "no VERIFIED skill exists for this category yet" as the normal
breadth-first case - no special-casing needed for unseen domains.

## Skill-resistant prior (bias abstention early, before evidence accumulates)

Published SkillsBench domain-level lift data shows some task shapes resist
skills even when curated: pure mathematical/operations-research and
reasoning-only tasks measured **+9.7pp mean lift** (lowest of the reported
domains), vs. **+28.8 to +51.9pp** for domains with dense, encodable
domain-specific procedure (natural science, manufacturing, healthcare).

Treat any task whose category/subcategory suggests **pure symbolic
reasoning, proof, or optimization with no domain-specific API or regulatory
knowledge involved** as a prior candidate for the Abstention Rule in
`SKILL.md` - only override the prior once concrete, non-obvious,
evidence-backed procedural content actually appears (e.g. a specific solver
API misuse, not "think more carefully").

This is a **prior**, not a hard rule: `forge-refine`'s ledger is the authority
once outcomes exist for a category. If a skill in a "resistant" category keeps
passing when loaded (its retention counter climbs rather than draining to zero),
keep it - the prior only governs the decision at authoring time, before any
outcome is observed. And note the prior never means "author nothing": on a
skill-resistant task the fallback is still a minimal harness-alignment skill
(see the Abstention Rule in `SKILL.md`), never an empty result.
