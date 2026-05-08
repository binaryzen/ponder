# Design Interview

A running conversation. Each entry is a question, the answer, and any
follow-up or reflection. The goal is to make the user's intuitions explicit
enough that they can be checked against ML methodology.

---

## Session 1 — initial framing

### Stated intent (summary)

The user wants to build a modular framework where specialized components,
each trained for a specific reasoning function, can be composed into a
larger system. The training approach involves:

- Curating content that enforces specific schemas of reasoning or
  understanding.
- Running a generalized model through a process that biases its weights
  toward those schemas.
- Distilling and quantizing to minimize the output space and resource cost.

The user has abstract ideas about how to leverage the structure of input
content during this process and wants to ground them in actual data science
methodology, then quantify the gain/loss tradeoffs.

---

### Q1 — Pick one component. Make it concrete.

**User answer:** A **qualitative categorizer**. Given some portion of context,
output a structured response — a payload of quality categories with scalar or
nominal values.

Two concrete instances:

- **Risk categorizer**: `{ maliciousPrompt: "low", fraudulentIntent: "low", goalMisalignment: "high", ... }`. Trained on risks of a specific domain.
- **Goal categorizer**: `{ solvePhase: "gather-info", condition: "acquired ${QUESTION_001} intent" }`.

**Output-space constraint:** vocabulary is large but limited; favors verbose
multi-token labels over nuanced single tokens; uses contextual tokens
(`${QUESTION_NNN}`) to reference concepts outside the model's conceptual
domain.

**Reflection (Claude):** the risk categorizer alone is multi-label
classification (encoder + N heads, no generation needed). The goal
categorizer's `${QUESTION_001}` references force generative architecture
because variable-binding outputs aren't naturally classifier-shaped. The
contextual reference mechanism is therefore the load-bearing design choice.

---

### Q2 — Operational nature of contextual references

**User answer:** Two distinct purposes for contextual references:

1. **Symbolic abstraction.** Like `A`, `B`, `C` in `if A > B and B > C then A > C`. Tokens are placeholders for generalizing a pattern of reasoning. Form, not content.
2. **Information compression.** Reducing the amount of information in the parameters so as to enhance the effect of useful tokens on outcomes. Opaque references squeeze out distracting content so structural tokens dominate the forward pass.

**Mapping (see concepts.md):**

- (1) → Symbol Tuning (Wei et al. 2023); systematic-generalization literature.
- (2) → adjacent to information bottleneck (Tishby) but no direct paper found
  that frames it this way. **Possible novel claim, worth dedicated literature
  review.**

The combination of (1) and (2) as a single coherent design principle is the
distinguishing feature of the user's framing.

---

### Q3 — Why verbosity for precision

**User answer:** (c) — training-signal density — is "kind of" the answer, but
the bigger motivation is system-level: bias toward a curated set of
**relationships, verbs, and adjectives**, and operate with this vocabulary
internally. Engineering wins:

- **Cacheable processes** — bounded output spaces enable memoization
- **Reduced non-determinism** — fewer equivalent expressions for the same idea
- **Modular boundaries** — "less wrinkly data shapes" between components

This promotes the vocabulary from a training-data choice to a
**system-level interface contract**. Free-form natural language is reserved
for the I/O boundary; inter-region communication uses the constrained
vocabulary.

→ See concepts.md, Concept 4 (Controlled internal vocabulary as system
contract).

**Tensions to track:**

- Vocabulary design is historically the hardest part (CYC, FrameNet lessons).
- "Determinism" with LLMs requires fixing temperature, decoding strategy, and
  model weights — the cache key must be designed explicitly.

---

### Q4 — Training corpus generation (deferred)

Now downstream of Q5 — vocabulary construction. Once vocabulary is defined,
"examples that use it" is the corpus criterion. Will come back to Q4 once Q5
is answered.

---

### Q5 — Vocabulary construction

**User answer (partial):** Vocabulary is **domain-scoped**. Determined by the
problem domain, applies to a "subnet of model nodes." Not global, not
per-component — per-domain.

**Worked example:** an engineering-specification domain. Vocabulary includes
deontic operators (MUST, SHALL, SHALL NOT, etc.) with their RFC-2119-precise
semantics. Rules are expressed in this controlled language with contextual
variable bindings:

```
${structure} SHALL NOT ABUT PUBLIC EASEMENT WITH HEIGHT TRANSFER GREATER THAN 1/8
```

**Larger pattern surfaced:** the example revealed a three-stage component
pipeline that is itself a generalizable architecture (see Concept 5):

1. **Categorization** — the entity (ramp) is classified into a regulatory
   typology (`structure abutting public easement`).
2. **Rule retrieval** — for that category, a validation context produces
   applicable rules.
3. **Strict-evaluation decision** — operates on supplied rules + parallel
   acceptance criteria; emits verdicts. Closed-world: brings no own domain
   knowledge, every verdict traces to specific rules.

This pattern generalizes the existing **Conscience** region in the spec:
rules-in, evaluation-out, no own knowledge.

→ See concepts.md, Concept 5 (Categorization → Rule Retrieval → Strict
Evaluation pipeline) and Concept 6 (Closed-world strict evaluation).

Sub-questions still open from Q5:

- Vocabulary mutability — fixed at training time vs. extensible? (Affects
  caching and fine-tuning.)
- Cross-domain interaction — when a system spans multiple domains
  (engineering + regulatory + accessibility), how do their vocabularies
  interact?

These can be picked up after Q6.

---

### Q6 — What is the decision component doing computationally?

**User answer:** (b) and (c) both sound close, but the framing isn't quite
right. The actual goal isn't constraint evaluation. It's **representing how
little systems of ideas in semi-constrained domains work**.

**Significant redirection:** controlled vocabulary was a means, not an end.
The end is reducing ambiguity so the *structural pattern* of a situation can
be exposed and learned. The components produce **schemas — entity-
relationship graphs that describe archetypical systems** — not rules.

**User examples of what schemas are:**

- "teacher teaching students"
- "unbound feedback loop"
- "opposing trends in equilibrium"

These are dynamics that recur across radically different content domains.
The same "teacher teaching students" graph applies to a literal classroom, a
parent and child, a training algorithm and its model, a consultant and
client.

**Reframing earlier concepts in this light:**

- **Concept 4 (controlled vocabulary)** is now a means: vocabulary
  constraint exposes structural pattern by suppressing surface variation.
- **Concept 5 (three-stage pipeline)** was specific to compliance checking;
  it remains valid for that subdomain but is no longer the central
  architectural pattern.
- **Concept 6 (closed-world strict evaluation)** likewise narrows in scope —
  applies to verification components but not to the broader schema-
  extraction architecture.

→ See concepts.md, Concept 7 (Abstract relational schemas).

---

### Q7 — Downstream use of schemas

**User answer:** Schemas serve two related functions:

1. **Recognition + reference.** Given a problem, the schema recognition
   model selects some schemas that fit. These schemas are referenced in
   context for downstream reasoning.
2. **Lens application at higher reasoning.** The model selects a schema
   and uses it to **set the perspective of approach** to solving — or at
   least **holds up the situation to that lens to elicit insights**, which
   may **populate elements of the schema previously unarticulated**.

**Crystallization — operational definition of reasoning in Ponder:**

> Reasoning is the process of selecting schemas, applying them to
> situations, and completing the slots they create.

This is **schema-driven inference** in the cognitive-psychology sense /
**candidate inference** in Gentner's structure-mapping vocabulary / **slot
completion** in frame semantics. Qualitatively distinct from
classification, constraint-checking, or rule-following: it is
**interrogative** — the schema generates questions; the questions structure
inquiry.

→ See concepts.md, Concept 8 (Schema-driven inference as the reasoning
mechanism).

**Three separable functions identified:**

1. **Schema recognizer** — situation → ranked candidate schemas
2. **Schema selector / lens-chooser** — choose which candidate to apply
3. **Slot-filler / probe** — generate slot-questions and propose answers
   (the hardest piece; doing genuine generative inference)

**Provisional Ponder mapping:** Hippocampus = retrieval; Prefrontal =
selection + planning under chosen lens; Wernicke = slot-filler probe.

**Open thread (not yet decided):** multi-schema parallelism. When several
schemas apply simultaneously ("consultant onboarding client" can be
teacher/student AND merchant/service AND healer/patient), do they
complement, conflict, or get arbitrated? User hinted at selecting "some
schemas" — plural — but hasn't committed to whether the system holds
multiple in tension or commits to one for action.

---

### Q8 — Schema as a data structure

**User answer:** ERG-like (entity-relationship graph). A schema identifies:

- **Entities**
- **Relationships**
- **Cardinality**

A schema may also be associated with **variations on dynamics** and
**emergent behaviors** — beyond what ERG alone supports.

**Catalog:** learned / on demand. Not a fixed catalog.

**Training methodology:** generate **schematic narratives** to reinforce
the schemas, paired with structured notation. Train on (narrative,
notation) pairs.

→ See concepts.md, Concept 9 (Schematic narrative paired training).

**Architectural implications:**

- ERG is structural and static. Dynamics + emergence require notation
  extension. Candidates: causal loop diagrams, conceptual graphs (Sowa),
  Petri nets / state charts, or augmented ERG with typed annotations
  (temporal, causal polarity, feedback markers, emergence tags).
- "On demand" means schema cache is selective, not total. Recognition
  (retrieval of known) and generation (synthesis of novel) are separable
  operations.

---

### Q9 — Schema notation primitives

#### Q9.2 — Relationship types

**User answer:** Open NL predicates, with a mechanism to prefer a set for a
given domain to reduce occurrence of "multiple things that should be one
thing" (synonym sprawl). Provisional — chosen until the design space is
better understood.

**Architectural mapping:** open vocabulary + domain canonicalization. This
matches the evolution of mature controlled vocabularies (MeSH, SNOMED-CT,
LOINC).

**Mechanism options for canonicalization:**

- Trained-in (corpus-driven; inflexible after training)
- Synonym-table post-processing (fast, hand-curated tables)
- Constrained decoding with logit bias (elegant, inference-time coupling)
- Embedding-similarity collapsing (automated, risks false merges)
- Dedicated canonicalizer model (flexible, adds component)

Practical hybrid likely: trained-in canonicals + embedding-similarity
fallback + human curation backstop.

→ See concepts.md, Concept 10 (Open notation with domain canonicalization).

**Implications now load-bearing:**

- Notation versioning. Each (narrative, notation) pair must record
  notation version; migrations must exist.
- Domain identification. The system must determine which domain to apply
  canonicalization for, and handle multi-domain situations.

#### Q9.4 + Q9.5 — Dynamics and emergence (resolved by simplification)

**User answer (worked example: feedback system):** A feedback system can
overload, collapse, or find equilibrium. These are variant emergent
behaviors of the same underlying schema. Crucially: **they don't need
formal/structured definition** to be useful. Recognizing a system as a
feedback system *immediately gives you three potential behaviors to
expect*, and the named labels are sufficient for problem-solving.

**Implication — schema notation simplifies:**

Dynamics and emergence are not first-class primitives in the notation.
They are listed as **named variant behaviors** associated with the schema.
Their semantic content lives in the narratives the model was trained on,
not in formal operators in the notation.

**Crystallized schema notation form:**

```
schema = {
  entities: [...],
  relationships: [...],   # open NL with domain canonicalization
  cardinality: [...],     # standard ER
  variants: [...],        # named expected behaviors
  domain: ...,
  notation_version: ...
}
```

This matches the **system archetypes literature** convention: structural
pattern + small set of named expected outcomes.

→ See concepts.md, Concept 7 (updated with crystallized notation form).

#### Q9.1 + Q9.3 — Defaults proposed

- Q9.1 (entity types) — open NL, mirroring relationships
- Q9.3 (cardinality) — standard ER (1:1, 1:N, M:N)

Awaiting confirmation or push-back.

#### User-named system-level commitment: Auditability

User stated the key facility of the schema mechanism is **the ability to
audit the findings and usage of them**. Pulling this thread together with
Concept 6's auditability emphasis: auditability is now a **cross-cutting
system commitment**, not a local property of one component.

Operational implications:

1. Trace of which schemas were applied at each reasoning step
2. Tagging of candidate inferences with originating schema
3. Traceability of anticipated behaviors to schema recognition
4. Provenance chain unrollable from any conclusion

→ See concepts.md, Concept 11 (Auditability as system commitment).

#### Recognition mechanism implication

User's phrasing of the recognition criterion ("one of its inputs is
affected by an output") is a **structural rule**, not an embedding-distance
match. This implies recognizer architecture should support graph-pattern
matching / graph homomorphism, which is more interpretable and audit-
friendly than embedding similarity. Worth committing to when recognizer
architecture is specified.

---

### Open architectural threads — all answered

#### Domain identification

**User answer:** A degree of freedom. Another component, or a fixed value,
is the authoritative source. Schema components do not infer domain — they
receive it as input.

**Architectural commitment:** schema components have a `domain` input slot;
whatever populates it is a separable concern. For Phase 1/2 prototype,
default to fixed-value-in-Helm-values; defer the classifier mechanism.

#### Multi-schema arbitration

**User answer:** Will work out finer mechanisms for rotating strategies
later. For now: top-N sorted candidates with randomization options.

**Architectural commitment:** recognizer outputs ranked candidates, not a
single answer. Selection policy is separable and configurable. Two
defaults to ship: deterministic (top-1) and stochastic (softmax-weighted
sampling over top-N). Bandit-policy-style abstraction; easy to swap
strategies as more sophisticated arbitration is developed.

#### Provenance / audit trace structure

**User answer:** Structured event emitter. Plug into whatever messaging
endpoint or data stream is appropriate; tech stack / deployment to be
finalized. Async abstraction.

**Architectural commitment:** auditable events are emitted as structured
records to a stream. Integrates cleanly with existing Ponder Redis Streams
message bus — adding an audit stream is incremental. Emit/consume
decoupling means sinks are swappable per environment.

---

### Crystallized data shapes (sketches)

```
RecognitionResult {
  candidates: [SchemaMatch],    # ranked, top-N
  domain: str,                  # received from authoritative source
  trace_id: str
}

SchemaMatch {
  schema_id: str,
  schema_version: str,
  match_score: float,
  match_evidence: [...]
}

SelectionPolicy {
  mode: "deterministic" | "stochastic",
  top_n: int,
  temperature: float | null
}

AuditEvent {
  trace_id: str,
  parent_event_id: str | null,
  emitted_at: timestamp,
  event_type: enum,
  region: str,
  domain: str,
  notation_version: str,
  payload: {...}
}
```

Final shapes will be refined during implementation. Structure determined
by the architectural decisions above.

---

### Pause point

Interview has converged the schema-driven inference design. Architectural
decisions are coherent across Concepts 1–11.

**Remaining work, organized:**

1. Formalize data-structure sketches → `design/data-structures.md` ✓ (v1 written)
2. Fold design into `CONTEXT.md` and spec doc as Phase 2+ addendum
3. Prototype roadmap — what to build first; system archetypes catalog
   (~12 patterns) as starting target

---

### Session 2 — scaffolding decisions

After three parallel ambiguity-surfacing passes (see
`ambiguities-data-structures.md`, `ambiguities-spec-integration.md`,
`ambiguities-prototype-roadmap.md`), the user committed to scaffolding-level
decisions that unblock data-structure formalization:

- **Entity ID format:** UUID v4
- **Notation versioning:** monotonic integer
- **ID reference convention:** URN-like, context-dependent
  - Bare UUID within a single domain
  - `<domain>:<uuid>` when crossing contexts
  - `<domain>:<uuid>@<version>` for versioned schema references
- **Audit format:** reasonable default v1; iterate when missing something —
  "getting the plumbing in place is good"

**Outcome:** `design/data-structures.md` written as the v1 normative
artifact. Covers Schema, RecognitionResult, SchemaMatch, SelectionPolicy,
SelectionResult, AuditEvent. v1 is intentionally loose where notation
versioning makes future tightening safe.

**Now unblocked:**

- Roadmap M0 (local stack swap to local LLM): config flip; can ship.
- Roadmap M1 (audit-stream skeleton): event schema fully specified; can build.
- Most data-structures ambiguities now resolved by the v1 specs or by being
  safely NL-deferred.

**Still pending:**

- Spec integration ambiguities (`ambiguities-spec-integration.md`) —
  particularly Conscience-as-degenerate-case resolution (B3) and
  source-of-truth doc decision (A1).
- Roadmap A3 (prompted-specialist methodology) — needed before M2.
- Roadmap A4 (catalog scope: full ~12 archetypes vs. start at 3).
- Roadmap A7 (POC exit criteria).

---

### Session 3 — additional scaffolding decisions

**A1 (source-of-truth doc):** Markdown is canonical. `CONTEXT.md` is the
working source of truth. The `.docx` is auxiliary / archival. **Drift-check
process** added as a standing practice — periodic alignment check between
`CONTEXT.md` and `design/` files using a lower-cost model. Saved to
auto-memory.

**B3 (Conscience-as-degenerate-case):** Deferred until POC experimentation.
Component roles will be reconfigured based on what actually works in the
functional problem-solving space. The schema-driven inference pipeline has
no fixed region home until then — POC builds it as a new component;
merging / superseding / coexistence with Conscience is a post-observation
decision.

**Implicit deferral of related ambiguities under the same principle:**

- B1 (new region vs. extension): defer
- B2 (naming convention): defer
- C1 (blackboard schema additions): tactically minimal — add what M1/M2
  need, no more
- F1 (Helm extensions): defer until deployment

**D1 (audit stream placement) — committed default:**

Separate Redis Stream (`ponder:<unit>:audit`) alongside the existing
inter-region cognitive stream. Cleaner for POC; trivial to converge into
the cognitive stream later if desirable.

**Now unblocked:**

- Roadmap M0 (local stack swap)
- Roadmap M1 (audit-stream skeleton — fully specified end-to-end)

**Pending only when M2 is on deck:**

- A3 (prompted-specialist methodology)
- A4 (catalog scope)
- A7 (POC exit criteria) — see Session 3 continuation below

---

### Session 4 — audit-viewer interface contract (pin)

User raised the consumption side of the audit stream during M0 wait time.
Requirement: **a service-abstracted interface** so multiple front-ends
(CLI viewer first, web viewer later) consume the same API without
coupling through Redis specifics.

**Captured in `design/audit-interface.md`:**

- Resource model — every queryable subset of system state is a named
  resource at a stable URL path
- Cursor-based, read-forward pagination using Redis Stream IDs as cursors
- SSE endpoint for live tailing (`/events/tail`)
- OpenTelemetry field-naming alignment for AuditEvent (rename
  `event_id`→`span_id`, `parent_event_id`→`parent_span_id`, etc.) — done
  now is free; done later is migration work
- CLI viewer UX: nimble, single-keypress actions (vim-style), three modes
  (traces list / trace detail / live tail)
- Implementation deferrals: framework choice (FastAPI candidate),
  TUI library (Textual candidate), live-tail transport (SSE preferred)

**Affects M1 scope.** AuditEvent field renames should happen *before* M1
starts emitting events. The service skeleton itself is M1 work.

---

### Session 3 continuation — POC framing expanded

User's framing of POC reveals a richer scope than the original roadmap
captured. POC runs **two parallel tracks of experimentation**:

#### Track 1 — Composability

The POC must validate that the orchestration substrate supports the
**useful degrees of freedom around component orchestration**. Specifically,
two activation patterns crossed with two communication patterns:

| | Push to component input | Shared context (async) |
|---|---|---|
| **Fire on demand** | DAG-style invocation | Blackboard write on call |
| **Rate-limited loop** | Periodic input emission | Periodic blackboard update |

Plus **contextual modulation** — activation/rate determined by contextual
state or explicit inputs. Specialists must be configurable to throttle or
wake based on state.

All primitives are in the existing stack (LangGraph for DAG, Redis Streams
for pub/sub, Redis Hash for blackboard, scheduler for cadence). What needs
validation is that they compose flexibly across the matrix.

#### Track 2 — Specialist suitability

Prompted specialists are not standing in for trained specialists in a
*quality* sense. They are **demonstrating the orchestration's headroom**.
Trained specialists will generally perform at least as well as prompted
ones on the same task, so prompted-specialist quality functions as a
useful lower bound on what the architecture can deliver.

The question the POC answers is: **does the orchestrated approach produce
results of acceptable quality?**

- If yes → training specialized models is justified investment
- If no → architecture needs revision *before* training is on the table

#### POC exit criteria (A7 — committed)

POC exits when **both tracks** produce evidence sufficient to commit to
either:

(a) training specialized models, or
(b) revising the architecture

**Composability evidence:** each cell of the activation × communication
matrix has a working specialist with an audit trace; at least one cell
demonstrates contextual rate/activation modulation.

**Suitability evidence:** end-to-end output of acceptable quality on a
defined task set, with the audit trail demonstrating that schema-driven
inference is doing real work — not merely scaffolding around an LLM that
would have produced the same output unaided.

**Acceptable-quality threshold:** deferred until post-build. Setting it
pre-build risks anchoring on the wrong metrics; failure modes that emerge
in practice are the ones that matter. End-to-end testing and parameters
of acceptance follow initial build + unit/integration test validation.

POC is explicitly iterative — multiple cycles expected, expected to
produce interesting insights along the way.

#### Roadmap update — composability woven into M0–M5

Composability checkpoints are added to existing milestones rather than
parallelized:

- M2 — fire-on-demand + push (single-schema demo, already covered)
- M3 — adds fire-on-demand + shared-context (selection writes to
  blackboard for downstream consumers)
- **M3.5 (new)** — rate-limited loop + push (recognizer that periodically
  re-evaluates and emits to downstream input queue)
- M4 — adds rate-limited loop + shared-context (background canonicalizer
  running on cadence, updating shared canonical-predicate map)
- **M-comp gate** before M5 — all four cells have a working specialist;
  at least one cell demonstrates contextual modulation

A4 (catalog scope) and A3 (prompted-specialist methodology) still pending
when M2 is on deck.

---
