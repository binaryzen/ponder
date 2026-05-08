# Prototype Roadmap — Local POC of Schema-Driven Inference

**Status:** draft, awaiting user resolution of blocking ambiguities
**Audience:** the user (software engineer, not a data scientist)
**Source material:** `design/interview.md`, `design/concepts.md` (Concepts 1–11), `CONTEXT.md`

---

## Posture

This document proposes a **roadmap for validating the Ponder schema-driven
inference architecture using locally-runnable generalist LLMs prompted to
simulate specialized components**, before committing to the originally
planned Lambda Labs / specialist-training path.

The pivot. Original Phase 1 assumed Lambda Labs from day 1, with Mistral-7B
served via vLLM in k3s. The local POC removes that dependency: a developer
laptop, a local LLM runtime (Ollama / llama.cpp), and the existing LangGraph
plumbing should be enough to demonstrate the architecture works in
principle. Specialist training comes after the POC validates the design.

What this implies. Anything the POC can validate without trained models is
**eligible for early validation**. Anything that fundamentally requires
trained specialists (e.g., quantization tradeoffs, structural-token
attention dynamics from Concept 3, latency floors of small specialized
models) is **out of POC scope** and gets deferred to the training phase.

The user explicitly wants natural-language deferrals: where a decision has
to be made but isn't urgent, the document records the decision as a NL
placeholder that gets tightened later. Each ambiguity below is tagged with
**NL-deferral viability**.

---

## Proposed roadmap (sequenced milestones)

These are ordered by dependency — each milestone unblocks the next.
Effort estimates are **order of magnitude only** and assume one engineer
working part-time. They do not include time spent answering the
ambiguities below.

### Milestone 0 — Local stack up (1–2 days)

Goal: a Python entry point that takes a turn and produces a response, using
a local generalist LLM, with no cluster.

- Swap `model_client.py` from vLLM HTTP to a local OpenAI-compatible
  endpoint (Ollama exposes one on `localhost:11434/v1`; llama.cpp via
  `llama-server` does too). The existing `model_client.generate()`
  signature should not need to change — the URL is already
  config-driven.
- Stub Hippocampus retrieval (return empty string or a fixed in-memory
  list). Qdrant is not needed for the schema-architecture demonstration
  itself.
- Skip Redis. The existing pipeline runs in-process via LangGraph and
  doesn't yet use Redis Streams (those are Phase 2 in `CONTEXT.md`).
- Confirm end-to-end: `ponder "hello"` returns text, no Docker, no k3s.

Validation: the existing Phase 1 graph runs locally against the local LLM,
producing intelligible output. This is **purely plumbing**; it doesn't
prove anything about schema-driven inference yet.

### Milestone 1 — Audit-stream skeleton (1–2 days)

Goal: surface auditability (Concept 11) as the first-class scaffold,
*before* introducing schemas. Doing this first means every later component
plugs into an existing trace, rather than auditability being retrofitted.

- Add an `AuditEvent` emitter (the data shape is already sketched in
  `interview.md`). Sink to a JSONL file for the POC; the structured-event
  abstraction the user committed to means swapping to Redis Streams later
  is trivial.
- Wrap each existing region (Thalamus, Hippocampus, Prefrontal, Broca)
  to emit `region_entered` / `region_exited` events with input and output
  payloads.
- Build a minimal trace viewer: a script that reads the JSONL and prints
  a tree of events for a given `trace_id`. No GUI.

Validation: every turn produces an auditable, replayable trace. This is
the substrate for Concept 11 and is testable without any schema work.

### Milestone 2 — Single-schema slot-completion demo (3–5 days)

Goal: prove the **three-stage schema mechanism** (recognize → select →
slot-fill, Concept 8) works end-to-end with one schema, using prompted
generalists.

- Pick **one** schema. Strong default: "unbound feedback loop" — it has a
  crisp ERG structure, clear named variants (overload / collapse /
  equilibrium), and is the user's worked example.
- Implement three prompted "specialist" components, each a generalist LLM
  with a system prompt that defines its role and required output format
  (the "prompt a generalist to simulate a specialist" methodology — see
  Ambiguity A3):
  - **Recognizer**: situation → ranked candidate schemas (in this
    milestone, just yes/no for the one schema).
  - **Selector**: pick the lens (trivial when there's one schema).
  - **Slot-filler**: given (situation, schema), generate slot-questions
    and propose answers.
- Wire them into the LangGraph pipeline as new nodes. They emit the
  same audit events as existing regions, plus schema-specific events
  (`schema_recognized`, `schema_selected`, `slot_filled`).
- Hand-author 5–10 narrative inputs (e.g., a thermostat oscillating, a
  social-media engagement spiral, a runaway training loop) and inspect
  outputs by hand.

Validation: for each input, the audit trace shows the schema recognition
decision, the slots that were proposed, and the proposed fillings. The
user can read the trace and tell whether the system "did the right
thing." No quantitative metric yet — the demo is qualitative.

### Milestone 3 — Multi-schema arbitration (3–5 days)

Goal: extend to **N schemas** to demonstrate the recognizer ranking and
the multi-schema arbitration question (Concept 8 open thread).

- Author 2–3 more schemas (candidates: "teacher teaching students,"
  "opposing trends in equilibrium," and one from the system-archetypes
  catalog like "limits to growth").
- Recognizer now returns ranked top-N candidates (the
  `RecognitionResult` data shape from `interview.md`).
- Implement both selection policies the user committed to:
  deterministic top-1 and stochastic softmax-over-top-N.
- Add narrative inputs that genuinely match more than one schema (the
  "consultant onboarding client" ambiguous case from Concept 7) and
  inspect how the system handles them.

Validation: the audit trace shows ranked candidates, the chosen lens,
and the slot-fill outputs. A handful of inputs where the schema choice
matters get inspected qualitatively. Concept 11's "schema application
trace" requirement is now demonstrably satisfied.

### Milestone 4 — Schema catalog + canonicalization scaffold (1 week)

Goal: scale from a hand-coded handful of schemas to a **catalog** large
enough to test whether the schema notation generalizes.

- Author the system-archetypes catalog (~12 patterns from Senge /
  Meadows). See Ambiguity A4 — start at 3 if 12 feels premature.
- Add a `notation_version` field on each schema (Concept 10).
- Build the simplest canonicalization mechanism: a hand-curated
  synonym table for the relationship predicates ("informs" ↔
  "teaches" ↔ "transmits-to"). Embedding-similarity fallback can come
  later. (Concept 10 Ambiguity A6.)
- Produce a small evaluation harness: 30–50 hand-tagged narratives,
  scored by hand against expected schema and slot-fill outputs.

Validation: the recognizer's accuracy on the hand-tagged set is
inspected. This is the first quantitative data point — it does not need
to be high; it just needs to be **measurable**, so improvements can be
tracked.

### Milestone 5 — Bridge artifacts toward training (1–2 weeks)

Goal: make the POC's outputs usable as training-data seeds, so the
move to specialist training has a concrete starting point.

- For each schema, dump (narrative, notation) pairs from POC runs into
  a structured corpus. These are the seed examples for Concept 9's
  paired training.
- Document where the prompted generalist disagrees with itself on
  repeat runs — disagreements mark the boundary of what training will
  need to harden.
- Spec out the training-side handoff: what specialist would replace
  each prompted role; what the input/output contract is; what
  evaluation metric carries over from POC qualitative inspection to
  training quantitative metric.

Validation: the user can point at a directory and say "this is what
the specialist for the recognizer needs to learn." Bridge to training
is no longer hand-wavy.

---

## What the POC can and cannot validate

A clear-eyed pass before listing ambiguities. The POC is honest about its
limits.

### Validatable in POC

- **Architecture coheres end-to-end.** The recognize → select →
  slot-fill decomposition runs as separable components with typed
  interfaces.
- **Auditability is structurally achievable.** Concept 11's trace
  structure can be demonstrated, inspected, and used to debug a turn —
  even if the contents of the trace are produced by prompted
  generalists rather than trained specialists.
- **The schema notation form is workable.** Whether the
  entities/relationships/cardinality/variants notation from Q9 is
  expressive enough to describe situations across surface domains is a
  notation-design question, not a training question. Hand-authoring
  schemas and applying them to varied narratives validates this.
- **The system archetypes catalog is a useful seed.** Whether ~12
  archetypes provide useful coverage on a sampling of input situations
  is testable by hand inspection.
- **Schema notation generalizes across surface domains.** This is the
  central claim from Concept 7. It's testable in POC by writing
  narratives in different domains (classroom / parenting / ML
  training) for the same schema and confirming the slot-filler
  produces structurally similar outputs.
- **Multi-schema arbitration policies are reasonable.** Whether top-1
  vs. softmax-over-top-N produces inspection-pass behavior on
  ambiguous narratives.

### NOT validatable in POC (deferred to training phase)

- **Quantization / distillation tradeoffs.** Concept 1's claim that
  small specialized models are sufficient. This requires actually
  training the small models.
- **The Concept 3 hypothesis** (information compression of opaque
  symbols increases proportional weight of structural tokens in
  attention). This is a training-dynamics claim. The POC can test
  whether prompts with placeholder symbols produce more
  schema-faithful outputs, but that's a different and weaker question.
- **Latency and cost targets.** Generalist LLMs are bigger and slower
  than the eventual specialists. Any latency number from the POC is
  pessimistic and not load-bearing.
- **Inter-annotator agreement on schema labels at scale.** Concept 7
  flagged this. Real evaluation needs many annotators on hundreds of
  examples — out of POC scope.
- **Catalog growth dynamics.** Whether the catalog stays bounded or
  sprawls (the CYC failure mode from Concept 4) only emerges with
  many domains and many users. POC at 3–12 schemas can't see this.

---

## Ambiguities by blocking severity, per milestone

Each entry follows the format the user requested:

> 1. **What's unclear**
> 2. **Why it matters (POC)**
> 3. **Context the user needs** (frontloaded data-science background)
> 4. **NL-deferral viability**
> 5. **Recommended default**

**Blocking severity legend.**
- **Hard block** — the milestone cannot start until this is decided.
- **Soft block** — the milestone can start with a default, but the
  default may need revisiting.
- **Tightening** — defer to a later milestone; not urgent.

---

### Blocking Milestone 0 — Local stack up

#### Ambiguity A1 — Local LLM choice
- **Severity:** Soft block.
- **What's unclear.** Which local LLM to use as the generalist
  substrate. Mistral-7B is in `CONTEXT.md` for the cluster path.
  Candidates for laptop: Mistral-7B (Q4 quantization, ~4GB RAM),
  Llama-3-8B (similar), Qwen2.5-7B, smaller options like Phi-3-mini
  (3.8B, ~2GB), or larger like Llama-3-70B-Instruct via API.
- **Why it matters (POC).** Affects fidelity of the
  prompted-specialist simulation. Too small → the model can't reliably
  follow a structured-output system prompt, and the architecture looks
  broken when in fact the substrate is too weak. Too large → can't run
  on the developer workstation, or runs at ~1 token/sec, ruining
  iteration speed.
- **Context the user needs.**
  - **Quantization** is the practice of reducing the precision of a
    model's weights (e.g., from 16-bit floats to 4-bit integers) to
    shrink memory footprint at small accuracy cost. A "Q4" Mistral-7B
    runs in ~4GB RAM instead of ~14GB.
  - **Instruction-following capability** of a 7B model is roughly:
    can reliably produce JSON given a clear schema in the prompt; can
    handle few-shot examples; struggles with very long context or
    deeply nested structure. A 3B model (Phi-3-mini) often slips on
    the JSON discipline.
  - **Local LLM runtimes:** Ollama is the easiest (one-command
    install, OpenAI-compatible API on `localhost:11434/v1`).
    llama.cpp via `llama-server` is more configurable but more
    setup. Both are equally good for the POC; pick whichever the
    user is fastest with.
- **NL-deferral viability.** High. The local LLM is a substitution
  layer; the architecture is independent of which model fills it. Try
  one, switch if it's too weak.
- **Recommended default.** Ollama running Llama-3.1-8B-Instruct
  (Q4_K_M). Better instruction-following than Mistral-7B in current
  benchmarks; comfortable on 16GB RAM laptops; OpenAI-compatible API
  drops in to existing `model_client.py` with a config change.

#### Ambiguity A2 — Stack subtraction extent
- **Severity:** Soft block.
- **What's unclear.** Should the POC run with just LangGraph + a local
  LLM, or also keep Redis (for the audit stream / blackboard) and
  Qdrant (for retrieval)? Current code uses Redis already.
- **Why it matters (POC).** Each removed dependency is one less thing
  to install and debug, but also one less thing the POC validates. If
  the audit stream is the centerpiece, having it on Redis Streams from
  day 1 means later integration is smoother.
- **Context the user needs.** No specialized ML knowledge needed.
  This is an engineering tradeoff: setup cost vs. fidelity to the
  eventual deployment.
- **NL-deferral viability.** High. The audit-event emitter is
  abstracted (the user committed to "structured event emitter
  pluggable into whatever stream"); JSONL file vs. Redis Streams is a
  swap.
- **Recommended default.** JSONL audit file; in-memory blackboard
  state (already what LangGraph provides via TypedDict); skip Qdrant
  entirely (Hippocampus stub). Add Redis only when an actual streaming
  consumer use case appears.

---

### Blocking Milestone 2 — Single-schema slot-completion demo

#### Ambiguity A3 — Prompted-specialist methodology
- **Severity:** Hard block. This is the central methodological choice
  of the POC.
- **What's unclear.** How exactly to "prompt a generalist to simulate a
  specialist." There are several techniques and they make different
  bets.
- **Why it matters (POC).** This is the load-bearing substitution
  the POC depends on. If the prompted generalist's outputs don't
  resemble what a trained specialist would produce, the architecture
  validation is illusory.
- **Context the user needs.** Background on the techniques:
  - **System-prompt role-definition.** A long system prompt that
    defines the role, the input format, the output format (often
    a JSON schema), and the rules. The model is asked to produce
    only the structured output. **Cheapest, weakest discipline.**
  - **Few-shot prompting.** The system prompt includes 3–10 worked
    examples of (input, expected output). The model imitates the
    examples. **Stronger; the examples carry most of the signal.**
  - **Constrained decoding.** At generation time, the decoder is
    constrained to produce only tokens consistent with a given
    grammar (e.g., a JSON schema). Tools: Outlines,
    lm-format-enforcer, Ollama's `format: json`. **Strongest
    structural guarantee; doesn't help with content quality.**
  - **Rationale distillation.** A trained specialist would learn
    from (input, structured-output, rationale-explaining-the-
    output) triples produced by a strong generalist. The POC
    methodology is the same as the data-generation step of
    rationale distillation — so POC outputs are directly usable
    as training data later.
  - These compose. Production approach is typically: system prompt
    + few-shot examples + constrained decoding for the JSON
    structure.
- **NL-deferral viability.** Partial. The user must commit to **a
  methodology**, but the prompts themselves can be iterated. NL
  placeholders inside the prompts ("this is the kind of variant you
  should look for") are fine.
- **Recommended default.** System prompt + 3–5 few-shot examples per
  specialist + Ollama's JSON-mode constrained decoding for output
  format. This is the cheapest combination that gets all three
  techniques working. Validate against trained-specialist target by
  *deferring* — record outputs now, compare against trained
  specialist's outputs in the bridge milestone.

#### Ambiguity A5 — Per-schema narrative count for POC
- **Severity:** Soft block. Affects evaluation harness and authoring
  effort.
- **What's unclear.** How many narratives per schema for the POC?
  Concept 9 names "hundreds per schema" as the eventual training
  target. The POC needs less, but how much less?
- **Why it matters (POC).** Too few narratives → inspection-only,
  insufficient to distinguish "the architecture works" from "we got
  lucky on three examples." Too many → authoring effort dominates the
  schedule.
- **Context the user needs.**
  - **Training-data scale.** AMR parsing community started with ~10K
    sentence-graph pairs. Modern instruction-tuning runs into
    millions. These are training scales. The POC is doing
    qualitative validation, not training, so two to three orders of
    magnitude less is fine.
  - **Statistical power vs. inspection coverage.** Quantitative
    accuracy claims need ~30+ examples per condition for any
    confidence. Qualitative inspection ("does the trace look
    right?") is informative at 5–10.
- **NL-deferral viability.** High. Start with 5 per schema, expand
  iteratively based on what's surfaced.
- **Recommended default.** 5 hand-authored narratives per schema for
  Milestone 2 (1 schema → 5 narratives); 10 per schema for
  Milestone 3 (3 schemas → 30 narratives total); 30–50 narratives
  total for Milestone 4's evaluation harness across the catalog.

#### Ambiguity A7 — Validation criteria for "POC successful"
- **Severity:** Hard block. Defines done.
- **What's unclear.** What specific behaviors must the POC demonstrate
  to be considered successful? Without this, the user doesn't know when
  to stop iterating and start the training-phase planning.
- **Why it matters (POC).** Avoids both premature commitment ("we
  built it, it must be good") and infinite scope creep ("one more
  schema and it'll be great").
- **Context the user needs.** No special ML background. This is
  a product-management question about exit criteria.
- **NL-deferral viability.** Low — the user should pick concrete
  criteria, even if NL-phrased.
- **Recommended default — proposed exit criteria.** All five must hold:
  1. A turn produces a complete audit trace from input through
     recognize → select → slot-fill → response, replayable from
     JSONL.
  2. At least 3 schemas, each applied successfully (by hand
     inspection) to at least 5 narratives in different surface
     domains.
  3. For at least one ambiguous narrative, the recognizer produces
     a ranked top-N and the selector picks one — both decisions
     visible in trace.
  4. For at least one schema, the slot-filler proposes candidate
     inferences (the "predictions about the situation that weren't
     in the input" from Concept 8) that the user can vouch for.
  5. The bridge corpus (Milestone 5) contains ≥ 30
     (narrative, notation) pairs that the user is willing to
     consider as training-data seeds.

---

### Blocking Milestone 3 — Multi-schema arbitration

#### Ambiguity A8 — Multi-schema selection policy default
- **Severity:** Soft block. The user already committed to "deterministic
  top-1 and stochastic softmax-over-top-N" as the two policies to ship,
  but didn't pick which is the **POC default**.
- **What's unclear.** Which selection policy runs by default in POC
  inspection? The choice affects the qualitative feel of outputs.
- **Why it matters (POC).** Inspection of whether the system "does
  the right thing" depends on the user knowing which policy was
  active. Switching policies between runs without flagging it muddles
  the inspection.
- **Context the user needs.**
  - **Top-1 deterministic** = always commit to the best-scoring
    schema. Simple, reproducible, can miss legitimate alternative
    framings.
  - **Softmax-over-top-N** = sample from a distribution weighted by
    score. Introduces variation, helps surface cases where the
    "second-best" schema would have been a better lens. Less
    reproducible per-run.
- **NL-deferral viability.** High. Configurable per-run; just need a
  default for the inspection cadence.
- **Recommended default.** Top-1 deterministic for the inspection
  cadence (reproducibility wins for debugging). Run softmax for a
  separate batch on ambiguous narratives only — the cases where
  tension between schemas is the whole point.

---

### Blocking Milestone 4 — Schema catalog + canonicalization

#### Ambiguity A4 — Initial catalog size and seed source
- **Severity:** Hard block for Milestone 4.
- **What's unclear.** Concept 7 names the system archetypes catalog
  (~12 patterns from Senge / Meadows) as candidate seed. Should the
  POC start with all ~12, or a smaller subset (3 was floated by the
  user)? And: are system archetypes the **right** seed at all?
- **Why it matters (POC).** The schema catalog is the surface area
  of the POC. Too many → authoring cost dominates and the user can't
  finish. Too few → can't tell whether the notation generalizes
  across structurally different patterns.
- **Context the user needs.**
  - **System archetypes** are a small set of recurring causal-loop
    patterns named in *The Fifth Discipline* (Senge) and Meadows'
    work: limits to growth, shifting the burden, tragedy of the
    commons, fixes that fail, escalation, success to the
    successful, drifting goals, accidental adversaries, growth
    and underinvestment, balancing process with delay, eroding
    goals, and a few others depending on the source. They have
    canonical causal-loop-diagram forms.
  - **Why they're a good POC seed.** Each comes with named expected
    behaviors (matching the user's `variants` field). Each has
    canonical structure (matching the entities/relationships
    notation). They span enough variety to test generalization.
  - **Why they might not be enough.** They are all **dynamic
    systems patterns**. Other schema types — "teacher teaching
    students" (relational asymmetry), "opposing trends in
    equilibrium" (force balance) — may not all reduce to causal
    loops. The user's own examples in Q6 mix archetype types
    with image-schema-style patterns (Lakoff & Johnson).
  - **Image schemas** (the Lakoff & Johnson reference in
    Concept 7) are pre-conceptual structures like CONTAINER,
    SOURCE-PATH-GOAL, BALANCE, FORCE-DYNAMIC. Smaller catalog
    (~10–20), more abstract.
- **NL-deferral viability.** Medium. Catalog choice is a load-bearing
  decision but the catalog itself can be specified in NL ("the
  ones from chapter X of Senge") rather than formalized upfront.
- **Recommended default.** Start with **3 schemas**, deliberately
  chosen to span types: one system archetype ("limits to growth"),
  one relational pattern ("teacher teaching students"), one balance
  pattern ("opposing trends in equilibrium"). If the notation form
  describes all three cleanly, expand to the full ~12 system
  archetypes for Milestone 4. If it doesn't, that's a notation-form
  finding before catalog scale-up.

#### Ambiguity A6 — Canonicalization mechanism for POC
- **Severity:** Soft block.
- **What's unclear.** Concept 10 lists five mechanisms (trained-in,
  synonym table, constrained decoding bias, embedding similarity,
  dedicated canonicalizer model). User committed to a "practical
  hybrid" eventually. What's the POC subset?
- **Why it matters (POC).** Without any canonicalization, the
  prompted recognizer will use synonymous predicates ("teaches" /
  "informs" / "transmits-to") and matching across narratives will
  silently fail. With heavy canonicalization, the POC validates a
  form that doesn't match the eventual production approach.
- **Context the user needs.**
  - **Predicate canonicalization** = mapping different surface
    forms ("teaches," "instructs") to a single canonical form
    ("instruct") so the recognizer can match across narratives.
  - **Trained-in canonicalization** is impossible in the POC by
    definition (no training).
  - **Synonym table post-processing** is a hand-curated dict
    `{"teaches": "instruct", "informs": "instruct"}` applied after
    the model emits its output. Cheapest. Auditable.
  - **Constrained decoding with logit bias** restricts the model
    to a fixed vocabulary at generation time. Clean, but only
    works if the canonical set is stable.
  - **Embedding-similarity** uses a sentence-encoder to merge
    near-synonyms automatically. Can over-merge silently (the
    Concept 10 caveat).
- **NL-deferral viability.** High. The user can NL-specify "prefer
  these predicates within this domain" and let the prompt do the
  work, then add a synonym table when sprawl shows up in inspection.
- **Recommended default.** No canonicalization in Milestones 2–3.
  Add a hand-curated synonym table in Milestone 4 once predicate
  sprawl is observed in inspection. Embedding-similarity is
  deferred entirely.

---

### Tightening (defer past POC)

#### Ambiguity A9 — Schema slot-filler architecture
- **Severity:** Tightening. Concept 8 flagged the slot-filler as the
  hardest piece (it does genuine generative inference). For the POC
  it's a prompted generalist; the question of what specific
  architecture eventually replaces it (a fine-tuned 7B? a larger
  model with constrained decoding? a separate retrieval step?) is
  part of the bridge-to-training conversation, not the POC.
- **NL-deferral viability.** Total — defer to training phase.
- **Recommended default.** Don't decide. Note in the bridge corpus
  which slot-fill outputs the user found weak — those mark where the
  trained slot-filler needs to do better.

#### Ambiguity A10 — Domain identification mechanism
- **Severity:** Tightening. The user already deferred this in the
  interview ("for Phase 1/2 prototype, default to fixed-value-in-
  Helm-values"). For local POC, fixed config value is fine.
- **NL-deferral viability.** Total.
- **Recommended default.** A `--domain <name>` CLI flag, defaulting
  to a generic domain. Every audit event records the domain from
  config. Real domain inference is a Phase 3+ concern.

#### Ambiguity A11 — Goal-evaluator and Conscience integration
- **Severity:** Tightening. `CONTEXT.md` open questions list these
  as Phase 2 concerns. The POC is about validating schema-driven
  inference, not about the goal-loop or Conscience. Don't open
  these threads during POC.
- **NL-deferral viability.** Total — outside POC scope.
- **Recommended default.** Skip both regions in POC. Auditability
  for them comes for free once the audit-stream skeleton exists.

#### Ambiguity A12 — Recognition mechanism (graph-pattern vs. embedding)
- **Severity:** Tightening — but worth flagging for the user.
  Concept 7 noted the user's recognition phrasing implies graph-
  homomorphism recognition rather than embedding-similarity. In POC
  the recognizer is a prompted generalist, which is **neither** —
  it's an LLM doing pattern-matching in latent space. The eventual
  architecture choice (graph-pattern matcher? trained encoder
  classifier? hybrid?) is a training-phase question, but POC
  outputs should be inspected for whether the prompted generalist
  is *behaving* graph-structurally (e.g., recognizing
  "feedback-loop" by structure rather than by surface keyword).
- **NL-deferral viability.** Partial. Defer the architecture choice;
  but include a manual inspection step in Milestone 3 that asks
  "did the recognizer match by structure or by surface keyword?"
- **Recommended default.** Defer architecture choice. Add the
  inspection question to Milestone 3 evaluation.

---

## Bridge to training (brief)

Once the POC exits successfully (per Ambiguity A7's exit criteria), the
move to specialist training has a concrete starting point:

1. **Recognizer.** Replaceable by a trained encoder + multi-head
   classifier (Concept 1's "tiny encoder-based classifier"). Training
   data: the bridge corpus, augmented with LLM-generated narrative
   variants per schema. Target scale: hundreds per schema (Concept 9).
2. **Slot-filler.** The hardest piece. Likely path: fine-tune a
   small generative model (Mistral-7B or similar) on (situation,
   schema, slot-questions, proposed-answers) tuples produced by the
   prompted generalist. This is **rationale distillation** —
   Orca/Phi methodology. POC outputs *are* the rationales.
3. **Selector.** Likely stays prompted or becomes a small policy
   model. Less load-bearing than the other two.
4. **Canonicalization.** Move from hand-curated synonym table to
   the practical hybrid (Concept 10): trained-in for high-frequency
   canonicals, embedding-similarity fallback, human curation
   backstop.
5. **Lambda Labs / k3s migration.** The original `CONTEXT.md`
   Phase 1 plan picks up here, mostly unchanged. The portability
   constraint (CONTEXT.md) means the migration cost is bounded.

---

## Summary of decisions the user needs to make before starting

The user can defer almost everything else, but these decisions block
specific milestones. NL phrasing is fine for all of them.

| Ambiguity | Blocks | Default if skipped |
|---|---|---|
| A1 — Local LLM choice | Milestone 0 | Llama-3.1-8B-Instruct via Ollama |
| A2 — Stack subtraction extent | Milestone 0 | JSONL audit, in-memory state, skip Redis & Qdrant |
| A3 — Prompted-specialist methodology | Milestone 2 (hard) | System prompt + 3–5 few-shot + JSON-mode |
| A4 — Initial catalog size & seed | Milestone 4 (hard) | 3 schemas spanning types; expand to ~12 if notation holds |
| A5 — Narratives per schema for POC | Milestone 2 | 5 / 10 / 30–50 over milestones |
| A6 — Canonicalization mechanism | Milestone 4 | None initially; hand synonym table when sprawl appears |
| A7 — POC exit criteria | Milestone 2 (hard, retroactive) | Five criteria proposed above |
| A8 — Selection policy default | Milestone 3 | Top-1 deterministic, softmax for ambiguous batch |
| A9 — Slot-filler architecture | (post-POC) | Defer to training phase |
| A10 — Domain identification | (none in POC) | `--domain` CLI flag |
| A11 — Goal evaluator / Conscience | (none in POC) | Skip in POC |
| A12 — Recognition mechanism | (post-POC) | Defer; add inspection question in Milestone 3 |

---

## Effort summary

Order-of-magnitude only.

| Milestone | Effort | Cumulative |
|---|---|---|
| 0 — Local stack up | 1–2 days | 1–2 days |
| 1 — Audit-stream skeleton | 1–2 days | 2–4 days |
| 2 — Single-schema demo | 3–5 days | 1–2 weeks |
| 3 — Multi-schema arbitration | 3–5 days | 2–3 weeks |
| 4 — Catalog + canonicalization | 1 week | 3–4 weeks |
| 5 — Bridge artifacts | 1–2 weeks | 1–1.5 months |

**Total POC duration: roughly 1–1.5 months of part-time engineer
effort**, contingent on the hard-block ambiguities (A3, A4, A7) being
resolved early. Not contingent on training infrastructure, GPU rental,
or cluster bringup.
