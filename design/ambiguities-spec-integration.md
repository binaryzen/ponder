# Spec-Integration Ambiguities — Schema-Driven Inference

A surface-the-questions document. The schema-driven inference design
(captured in `design/concepts.md` Concepts 1–11 and `design/interview.md`)
has converged internally, but the **integration touchpoints with the
existing Ponder spec** (`CONTEXT.md` + `synthetic-mind-spec.docx`) are
under-specified. This file enumerates each ambiguity that must be resolved
— or deliberately deferred — before folding the design in as a Phase 2+
addendum.

Each entry includes:

1. What's unclear
2. Why it matters
3. Context the user needs (technical terms explained inline)
4. NL-deferral viability — can it stay prose-only for now?
5. Recommended default if skipping

Ordered by **blocking severity**: items at the top must be resolved (or
explicitly deferred with a placeholder) before the addendum can be
coherent. Items at the bottom can ride along as open questions without
blocking integration.

Where an item says "uncertain" or "not stated," that means I could not
find a commitment in the source files and am flagging it rather than
asserting an answer.

---

## A. Source-of-truth and document layout

### A1. Where does the schema-driven addendum live?  [BLOCKING]

**What's unclear.** Three candidate homes for the new design once it's
folded in:

- Append a "Phase 2 addendum" section to `CONTEXT.md`.
- Update `synthetic-mind-spec.docx` (the canonical spec) and let
  `CONTEXT.md` reference it.
- Create a new top-level doc (e.g., `SCHEMAS.md` or
  `schema-inference-spec.md`) that `CONTEXT.md` links to.

`design/README.md` step 4 says "the artifacts here get distilled into
additions to `CONTEXT.md` and the spec doc" — implying both, but not
saying which is primary.

**Why it matters.** Whichever doc is the source of truth is the one that
gets updated when decisions change. Splitting the design across two docs
without a clear primary creates drift. The `.docx` is also harder to diff
in version control than markdown.

**Context the user needs.** None technical — this is a documentation-
hygiene question. Worth noting that `CONTEXT.md` is described as "a
companion to the spec doc" containing decisions "not captured in the spec
itself" — so today the spec doc and `CONTEXT.md` already have an
ambiguous boundary.

**NL-deferral viability.** No. This is a doc-organization decision, not
a system-design one — it must be made before any text gets written.

**Recommended default.** Treat `CONTEXT.md` as the working source of
truth going forward. Add a "Phase 2 — Schema-driven inference" section
with the new region table, blackboard extensions, and audit-stream
description. Defer updating the `.docx` until the addendum has stabilized
(or retire the `.docx` entirely in favor of markdown).

---

### A2. Phase numbering for the addendum  [BLOCKING]

**What's unclear.** `CONTEXT.md` lists Phase 1 (linear pipeline, four
regions, implemented) and references "Phase 2," "Phase 3," "Phase 4"
without enumerating their contents. Open questions cite "Phase 2"
(Conscience calibration, Broca interrupt semantics) and "Phase 4"
(inter-unit orchestration). The interview's pause point says "fold design
into CONTEXT.md and spec doc as Phase 2+ addendum" but doesn't pick a
number.

The schema design is large enough to span several phases by itself
(recognizer training, slot-filler training, audit infrastructure,
canonicalization tooling). It is not obvious whether it is:

- A single Phase 2 (all schema work).
- Distributed across Phase 2 (recognition), Phase 3 (slot-filling), Phase 4 (full audit).
- A parallel track running alongside existing phase numbering.

**Why it matters.** Phase numbering drives sequencing, dependencies, and
"can we build X without Y" decisions. It also affects the Helm chart
schema (which regions need flags now vs. later) and what the existing
Phase 2 work (Amygdala, Wernicke, Basal Ganglia, Conscience activation)
becomes when overlaid with schema work.

**Context the user needs.** Existing `CONTEXT.md` says "remaining regions
(Amygdala, Wernicke, Basal Ganglia, Conscience) are deferred to Phase 2."
Concept 8 maps schema functions onto **Hippocampus** (recognizer),
**Prefrontal** (selector), and **Wernicke** (slot-filler). So Phase 2 as
currently scoped already overlaps the schema work — Wernicke is both
"activate the existing-spec region" and "implement slot-filler." That
double-meaning has to be resolved.

**NL-deferral viability.** Partial. The user can leave the exact phase
boundaries fuzzy in prose ("schema work begins in Phase 2 and continues
through subsequent phases"), but at minimum needs to commit to whether
the schema track is interleaved with or separate from the existing phase
plan.

**Recommended default.** Treat schema-driven inference as a **Phase 2+
program** (not a single phase). Within it:

- Phase 2a — recognizer + selector + audit-event-emitter scaffolding
  (uses Hippocampus + Prefrontal as their existing regions plus
  schema-aware extensions).
- Phase 2b — slot-filler probe (this is where Wernicke gets implemented
  in the spec sense, by being the slot-filler).
- Phase 3+ — canonicalization tooling, notation versioning,
  multi-domain handling.

This lets the existing Phase 2 work absorb the schema work rather than
race against it.

---

## B. Region architecture

### B1. New region(s) vs. extending existing ones  [BLOCKING]

**What's unclear.** Concept 8 maps the three schema functions onto
existing regions (Hippocampus, Prefrontal, Wernicke). But this is
**provisional** — the interview says "**Provisional Ponder mapping:**
Hippocampus = retrieval; Prefrontal = selection + planning under chosen
lens; Wernicke = slot-filler probe." It is not committed.

Three viable architectures:

- **(a) Extend existing regions.** Hippocampus gains schema-recognition;
  Prefrontal gains schema-aware planning; Wernicke is implemented *as*
  the slot-filler. No new regions.
- **(b) Add new schema-specific regions** alongside existing ones (e.g.,
  a "schema cortex" or "associative cortex" region that handles
  recognition + selection, separate from Hippocampus's text retrieval).
- **(c) Hybrid:** schema-recognition inside Hippocampus (it already does
  vector retrieval, so structural matching is an extension), but
  selection and slot-filling become new dedicated regions.

The interview's "Open architectural questions" in Concept 8 includes
"Specify the schema-awareness contract for Prefrontal" — implying (a),
but never explicitly choosing.

**Why it matters.** This is the single biggest decision driving the
addendum's shape. (a) is cheaper but couples concerns; (b) is cleaner
architecturally but inflates region count; (c) splits the cost. It also
affects the Helm chart, blackboard schema, and which prompts need
revision.

There is also a tension with **Concept 7's recognition mechanism**:
"recognition is graph-structural, not embedding-similarity." Hippocampus
today does **vector** retrieval against text in Qdrant. Graph-pattern
matching is a different computation — possibly different infrastructure
(a graph store or in-memory graph index, not Qdrant). If recognition is
genuinely graph-structural, putting it in Hippocampus may be a poor fit.

**Context the user needs.**

- *Embedding similarity* = compare two pieces of text by the cosine
  distance of their vector representations. Fast, fuzzy, ML-friendly.
  This is what Qdrant does today.
- *Graph-pattern matching / graph homomorphism* = check whether a
  candidate graph contains a subgraph matching a specified shape. Exact
  or near-exact, more interpretable, but a different data structure and
  index than embeddings.

The user is not a data scientist but the choice between these is
architecturally consequential — it determines what infrastructure
("Qdrant + sentence-transformers" vs. "a graph store or in-memory graph
matcher") the recognizer needs.

**NL-deferral viability.** Partial. The user can write the addendum in
prose committing to "schema functions are realized via existing regions
extended with schema-aware contracts" without naming exactly which
region does what — but the implementation will force the question. For
the doc, prose suffices; for the Helm chart and blackboard, it does not.

**Recommended default.** Go with **(a) — extend existing regions** for
the doc-level addendum, with a flagged caveat that "the recognizer's
internal mechanism (embedding vs. graph-structural) is an open
implementation question." This lets the addendum be written without a
new region taxonomy. If graph-matching turns out to be load-bearing,
introduce a new region in Phase 3.

---

### B2. Naming convention for new components  [SOFT-BLOCKING]

**What's unclear.** Existing region names are neuroanatomical (Thalamus,
Amygdala, Hippocampus, Prefrontal, Wernicke, Broca, Basal Ganglia,
Conscience). If new components are added (e.g., a domain identifier, a
schema canonicalizer, a notation versioner, an audit event emitter), it
is not clear whether they:

- Get neuroanatomical names (forced metaphor — "Angular Gyrus" for
  schema recognizer? "Insula" for domain identifier?).
- Get functional names (`schema_recognizer`, `domain_id`,
  `audit_emitter`).
- Mix (regions stay neuroanatomical; non-region infrastructure stays
  functional).

`CONTEXT.md` does say "the biological framing is the hook, but the
architecture is not constrained to it. Non-biological region types are
expected in later phases." This permits non-biological naming but
doesn't pick a convention.

**Why it matters.** Consistent naming is a quality-of-life property of
the codebase and the spec. It affects file paths, Helm chart values
keys, blackboard field names, and how easy it is to read the addendum.

**Context the user needs.** None technical. This is taste + ergonomics.

**NL-deferral viability.** Yes. Pick a rule of thumb in the addendum
prose; refine when concrete components get implemented.

**Recommended default.** **Mixed convention, with a stated rule:**
neuroanatomical names for **regions** (units that read/write the
blackboard and emit chunks); functional names for **infrastructure**
(audit emitter, canonicalizer, domain identifier — these are pipes, not
brain parts). When a non-biological region is genuinely needed, accept a
functional name (`schema_cortex` or similar) rather than forcing a
neuroanatomical analogy.

---

### B3. Conscience as "degenerate" instance — what does that mean for the spec?  [BLOCKING]

**What's unclear.** Concept 5 says: "**Conscience** is a degenerate case
of this pipeline: categorization is trivial (the input is 'the current
draft response'), retrieval is trivial (rules of engagement + operator
context, supplied directly), evaluation is the load-bearing step."

Three possible interpretations for the spec:

- **(i) Reframe Conscience.** The spec retroactively describes Conscience
  as an instance of the (categorize → retrieve → evaluate) pipeline,
  using the new vocabulary. The region's behavior doesn't change but its
  description does.
- **(ii) Replace Conscience.** Conscience is removed from the region
  list and the categorize/retrieve/evaluate pipeline takes its place,
  with Conscience-equivalent rules supplied as one input.
- **(iii) Subsume Conscience.** Conscience stays as a region but its
  internals are restructured to match the three-stage pipeline.

Concept 6 (closed-world strict evaluation) further complicates this — it
says the evaluator "brings no own domain knowledge." That's a strong
constraint that may or may not match the existing Conscience design,
which (per `CONTEXT.md`'s Phase 2 open questions) needs threshold
calibration.

**Why it matters.** Conscience is in the spec's region list and Helm
chart values. Whatever interpretation wins changes the chart, the
blackboard schema, and the Phase 2 plan. Also, Concept 11 explicitly
proposes putting **schema-application validity evaluation** inside
Conscience ("Conscience region is a natural place to evaluate
schema-application validity") — making Conscience double as
schema-quality-evaluator alongside its existing tone/violation-checking
role.

**Context the user needs.** "Degenerate case" in math/CS means *a
special case where some parameters collapse to trivial values* — not
"defective." So Concept 5 is saying Conscience is the same pipeline
shape but with two stages reduced to identity functions.

**NL-deferral viability.** Partial. The addendum can describe the
relationship in prose (e.g., "Conscience is one realization of the
categorize/retrieve/evaluate pipeline; future regulatory-validation
regions are fuller realizations") without restructuring Conscience's
implementation. But the choice between (i), (ii), and (iii) directly
affects whether Conscience's existing spec needs editing.

**Recommended default.** **(i) — reframe, don't replace.** Keep
Conscience as a region in the spec. Add a paragraph: "Conscience is the
trivial-categorization/trivial-retrieval instance of the
categorize-retrieve-evaluate pattern (Concept 5). Its evaluation step is
load-bearing; its categorization and retrieval are inputs supplied by
upstream context." This preserves backward compatibility while
acknowledging the structural unification. Defer the schema-validity-
evaluator role of Conscience to Phase 3.

---

## C. Blackboard schema

### C1. New blackboard fields  [BLOCKING]

**What's unclear.** `CONTEXT.md`'s "Region interface contracts" table
lists today's blackboard fields: `raw_input`, `input_type`,
`retrieved_memories`, `task_plan`, `operator_context`,
`rules_of_engagement`, `urgency_score`, `response_draft`,
`goal_achieved`. The schema design adds:

- **From the data-shape sketches** (`interview.md` end): `trace_id`,
  `domain`, `notation_version`, `candidates` (list of `SchemaMatch`),
  `match_score`, `match_evidence`.
- **Implied by Concept 8:** active-schema(s), slot-question list,
  candidate inferences, parent-event-id chain.
- **Implied by Concept 11:** schema-application history per turn,
  per-inference provenance metadata.

What is unclear: which of these become **first-class blackboard fields**
(every region reads them via the `BlackboardState` TypedDict) vs. which
are **stream-only** (audit events that flow through Redis Streams but
aren't on the blackboard) vs. which are **per-region internal state** (in
Qdrant, in a side store, never on the blackboard).

**Why it matters.** The blackboard is a TypedDict in Python today; every
field added is a contract change touching every region. Bloat hurts
clarity and forces every region to know about fields it doesn't use.
Stream-only is cheaper but harder to query at decision points. Side
stores break the "single source of truth per turn" property.

**Context the user needs.**

- The blackboard is the per-turn state object — small, in-memory,
  TypedDict-validated.
- Redis Streams are the asynchronous message bus — append-only event
  logs, queried separately.
- Qdrant is the long-lived vector store.

A field "lives on the blackboard" only if regions need to read it
synchronously while processing a turn.

**NL-deferral viability.** Partial. The addendum can list the new fields
in a "blackboard extensions" subsection without committing to which are
TypedDict vs. stream vs. side-store, but at integration time the
decisions must be made.

**Recommended default.**

- **Blackboard (TypedDict):** `domain`, `trace_id`, `active_schemas`
  (the schemas currently driving reasoning for this turn). These are
  read by multiple regions.
- **Stream-only (audit stream):** `AuditEvent` records — schema
  recognition events, slot-fills, lens applications. Not needed for
  next-step decisions; needed for retrospective audit.
- **Side store (Qdrant or new store):** schema catalog itself, schema
  application history across turns, candidate inference history.

Document the tri-modal split as a guideline in the addendum.

---

### C2. Backward compatibility with Phase 1 BlackboardState  [SOFT-BLOCKING]

**What's unclear.** `CONTEXT.md` Step 4 says blackboard fields and
region contracts are implemented. Adding fields means changing the
TypedDict. It is not stated whether:

- New fields are optional (default-`None`) so Phase 1 regions keep working
  unmodified.
- Phase 1 regions get touched to populate / pass-through new fields.
- A blackboard schema version field gets introduced.

**Why it matters.** Determines whether the addendum is purely additive
(no Phase 1 code changes) or invasive (Phase 1 regions need updates).
The user has stated POC plan is local orchestration with generalist LLMs;
backward compat is more about doc/spec coherence than runtime breakage at
this stage.

**Context the user needs.** None technical.

**NL-deferral viability.** Yes. Default to "additive only, all new fields
optional with sensible defaults" in the addendum prose; tighten if a Phase
1 region genuinely needs to start emitting one of the new fields.

**Recommended default.** Additive-only. New fields default to `None` /
empty. Phase 1 code is not required to change.

---

## D. Audit event stream

### D1. Same Redis Stream as Broca, or a separate one?  [SOFT-BLOCKING]

**What's unclear.** `CONTEXT.md` says Redis Streams are used as the
"message bus (labeled chunk delivery to Broca)." The interview commits
to "auditable events are emitted as structured records to a stream"
and notes that this "integrates cleanly with existing Ponder Redis
Streams message bus — adding an audit stream is incremental." But
"adding an audit stream" could mean:

- A new stream key (e.g., `audit:turn:<trace_id>`) parallel to Broca's
  chunk stream.
- New event types on the existing Broca stream.
- A separate stream key per region or per event type.

**Why it matters.** Affects retention policy, Broca's consumer logic,
and how downstream tooling reads the audit log. Mixing audit and chunk
events on the same stream means Broca needs to filter; separating
streams means audit consumers don't compete with Broca for stream
position.

**Context the user needs.** Redis Streams are append-only logs keyed by
a stream name. Each entry has an ID and field/value pairs. Multiple
streams in the same Redis instance is normal and cheap.

**NL-deferral viability.** Yes. The addendum can say "audit events flow
on a dedicated audit stream" in prose and pick the exact key naming
later.

**Recommended default.** **Separate stream(s).** Use `audit:<trace_id>`
or `audit:global` — distinct from the Broca chunk stream. Keeps
consumers independent. One audit stream globally is fine for the POC;
shard later if needed.

---

### D2. Audit-event schema versioning  [DEFERRABLE]

**What's unclear.** `AuditEvent` (interview's data-shape sketch)
includes `notation_version` — which versions the *schema notation*. It
does not version the *audit event format itself*. Does the audit event
schema get its own version field?

**Why it matters.** Long-term tooling will care; short-term it doesn't
move the needle.

**Context the user needs.** Two related but distinct version concerns:
the format of the audit record (is `payload` a dict or a string this
month?) and the format of what's inside the payload (the schema notation).
They can drift independently.

**NL-deferral viability.** Yes.

**Recommended default.** Add an `audit_event_schema_version` field;
default it to `1`. Don't actually version anything until you migrate.

---

### D3. Trace retention policy  [DEFERRABLE]

**What's unclear.** Concept 11's "Tradeoffs to be aware of" lists
"Trace storage cost — every turn produces metadata; need a retention
policy" as an open issue. No retention policy is specified.

**Why it matters.** Eventually drives storage costs. Not load-bearing
for POC.

**NL-deferral viability.** Yes.

**Recommended default.** "Retain all audit events for the local POC. In
cluster, expire after 7 days via Redis Stream MAXLEN. Revisit when
volume becomes a concern." One sentence in the addendum.

---

## E. Domain identification

### E1. Where does `domain` come from?  [SOFT-BLOCKING]

**What's unclear.** Concept 10 says "Domain identification is now a
system requirement." The interview's "Open architectural threads"
resolves: "schema components do not infer domain — they receive it as
input. ... For Phase 1/2 prototype, default to fixed-value-in-Helm-
values; defer the classifier mechanism."

Open: where in the architecture is `domain` populated on the blackboard?

- **(a) Helm `values.yaml` config** — set per-deployment, never changes
  per turn. Each deployed Ponder instance is single-domain.
- **(b) A Thalamus extension** — Thalamus today emits `input_type`;
  could also emit `domain` as part of classification. Per-turn dynamic.
- **(c) A new dedicated region** (`domain_classifier` or similar).
  Per-turn, separable.
- **(d) Operator-set field on the blackboard** — explicit per-session,
  like `operator_context`.

The interview's "default to fixed-value-in-Helm-values" points to (a)
for the POC. But it's not crisp about whether that maps to "loaded from
ConfigMap into `BlackboardState.domain`" or "configured per region and
never on the blackboard at all."

**Why it matters.** Determines (a) what the addendum says about the
`domain` field, (b) whether `domain` belongs on the blackboard or only
in deployment config, and (c) whether the addendum should describe a
domain-classifier region for later phases.

**Context the user needs.** "Domain" here is the controlled-vocabulary
domain (engineering specs, regulatory, customer-support, etc.) — not
domain in the DDD sense or a network domain.

**NL-deferral viability.** Yes — for Phase 2 POC. The addendum can say
"Phase 2 POC: `domain` is a deployment-time fixed value provided via
Helm values; loaded into the blackboard at session start. A future phase
may add a domain classifier."

**Recommended default.** Hybrid of (a) and (d): Helm-supplied default,
overridable by an explicit operator-set blackboard field. Add `domain`
to `BlackboardState` as `Optional[str]`, populated from
`config.domain` (env var / ConfigMap) at session start, with operator
override permitted. Defer (b) and (c) to a later phase.

---

### E2. Multi-domain situations  [DEFERRABLE]

**What's unclear.** Concept 10: "Handle multi-domain situations (which
canonicals apply when domains overlap?)". Not addressed.

**Why it matters.** In production this matters; for POC with a single
fixed domain it doesn't.

**NL-deferral viability.** Yes.

**Recommended default.** "Multi-domain handling deferred to Phase 3+."
One sentence in the addendum.

---

## F. Helm chart and deployment

### F1. `values.yaml` extensions  [SOFT-BLOCKING]

**What's unclear.** `CONTEXT.md` says "Region config: all 8 regions,
enabled flags." So the chart already has flags for the spec's full
region set. What's unclear is whether the addendum needs to add:

- New region-type values (if new regions are added per B1 / B2).
- Schema-specific values blocks (`schemaRecognizer.indexBackend`,
  `audit.streamKey`, `domain.default`, `notation.version`).
- A `domains:` section with per-domain canonicals/thresholds.

**Why it matters.** The addendum should specify the Helm surface so
operators understand how to deploy schema-aware Ponder. Otherwise the
addendum is incomplete from an ops perspective.

**Context the user needs.** Helm `values.yaml` is the configuration
input to the chart — anything user-tunable goes there.

**NL-deferral viability.** Partial. Sketch the new top-level keys in
prose; concrete defaults can come at implementation time.

**Recommended default.** Add a small new section to `values.yaml`:

```
schema:
  domain: "general"           # default domain
  notationVersion: "1"
  recognizer:
    backend: "embedding"      # placeholder; "graph" later
  audit:
    enabled: true
    streamKey: "audit:global"
    retention: "7d"
```

Document this block in the addendum.

---

### F2. Chart compatibility — does Phase 1 still install?  [SOFT-BLOCKING]

**What's unclear.** If the addendum adds required values, existing Phase
1 deployments break unless defaults are sensible. Not stated whether
schema features default-on or default-off.

**Why it matters.** Backward compatibility for the existing chart.

**Context the user needs.** Helm's behavior: missing values fall back to
chart defaults. So as long as defaults are sensible, no installation
breaks.

**NL-deferral viability.** Yes.

**Recommended default.** All schema features default to **disabled** at
the chart level (`schema.enabled: false`). When enabled, recognizer
defaults to no-op (returns empty candidate list). This makes the
addendum purely additive for ops.

---

## G. Naming, vocabulary, and contracts

### G1. What's the canonical name for the schema-driven inference subsystem?  [DEFERRABLE]

**What's unclear.** The design files use "schema-driven inference,"
"candidate inference," "slot completion," "schematic reasoning." None is
designated as the name to use in the spec.

**Why it matters.** Pick one for the addendum so cross-references are
unambiguous.

**NL-deferral viability.** Yes.

**Recommended default.** "Schema-driven inference" as the subsystem name
(matches Concept 8's section title and is the user's intuition's most
direct expression). "Candidate inference" reserved for Gentner-style
slot-fill outputs.

---

### G2. SchemaMatch / RecognitionResult / SelectionPolicy — promoted to the spec?  [SOFT-BLOCKING]

**What's unclear.** The interview's "Crystallized data shapes (sketches)"
defines `RecognitionResult`, `SchemaMatch`, `SelectionPolicy`,
`AuditEvent`. The README's flow says these would land in
`design/data-structures.md`. But it's unclear whether the **canonical
spec** (CONTEXT.md or the docx) names these types or just gestures at
them.

**Why it matters.** Same blackboard-vs-stream-vs-side-store question
applies: do these types live in `BlackboardState`, in stream payloads,
or somewhere else? The spec should commit.

**NL-deferral viability.** Partial. Names can be referenced in prose;
concrete TypedDicts come with implementation.

**Recommended default.** The addendum names the types and links them to
their purpose (`RecognitionResult` is the recognizer's output;
`AuditEvent` is the audit-stream record format). Defer formal
TypedDict definitions to `design/data-structures.md` (per the README's
plan) and reference that file from the addendum.

---

### G3. Multi-schema arbitration — top-N + selection policy  [SOFT-BLOCKING]

**What's unclear.** The interview commits: "recognizer outputs ranked
candidates ... Two defaults to ship: deterministic (top-1) and
stochastic (softmax-weighted sampling over top-N)." Open: whether
selection policy is **per-deployment** (Helm-configured), **per-turn**
(operator-set on blackboard), or **per-domain** (looked up from a domain
config).

**Why it matters.** Dictates where `SelectionPolicy` lives — Helm
values vs. blackboard vs. domain config.

**NL-deferral viability.** Yes.

**Recommended default.** Helm-configured default selection policy
(`schema.selection.mode`, `schema.selection.topN`,
`schema.selection.temperature`), with operator-set blackboard override.

---

## H. Cross-cutting

### H1. What's a "schema" in storage terms?  [SOFT-BLOCKING]

**What's unclear.** Schemas have a notation form (Concept 7's
`{entities, relationships, cardinality, variants, domain,
notation_version}`). But where do learned/known schemas live?

- A new Qdrant collection?
- A separate graph store (e.g., something Neo4j-shaped)?
- A flat-file catalog in the chart / image?
- A new region's internal state?

The interview says the catalog is "learned / on demand. Not a fixed
catalog." That implies dynamic storage, but doesn't pick the backing
store.

**Why it matters.** Affects infrastructure (a graph DB is a real
deployment dependency), Qdrant scaling, and recognizer architecture (B1).

**Context the user needs.** "On demand" here means schemas can be
synthesized at inference time, not just retrieved from a fixed library.
That implies write capability on whatever store holds them.

**NL-deferral viability.** Yes for the addendum prose; no for
implementation.

**Recommended default.** For the POC: schemas live as JSON blobs in
Qdrant payloads, indexed by their entity/relationship strings via the
existing embedding model. This keeps the infrastructure footprint at
"one Qdrant" with no new dependencies. If graph-pattern matching becomes
necessary (B1), introduce a graph store at that point. Document this
choice as POC-stage and explicitly tentative.

---

### H2. Is Phase 1's existing implementation invalidated by anything?  [BLOCKING-ish]

**What's unclear.** The user wants this folded in as an *addendum*, but
the design implies several things the current Phase 1 doesn't have:

- Hippocampus does text retrieval today, not schema retrieval. Does
  Hippocampus need restructuring to also do schema recognition?
- Prefrontal generates plans from `(input_type, retrieved_memories,
  ...)`. The schema design wants Prefrontal to operate "under a chosen
  lens" (Concept 8 open question 2). Does this mean the existing
  Prefrontal prompt and contract change?
- Wernicke is currently absent from Phase 1. The schema design assigns
  it the slot-filler role. So when Wernicke gets implemented, it
  arrives schema-shaped, not as a separate "deep parse" region first.

**Why it matters.** Determines whether the addendum can be added with no
edits to Phase 1 code, or whether there's an upgrade path required.

**Context the user needs.** Per A2's recommendation, treat schema work
as Phase 2+ — meaning Phase 1's implementation doesn't change. New
behavior comes online when Phase 2 regions activate.

**NL-deferral viability.** Yes — by stating in the addendum that
"Phase 1 region implementations do not need to change for the schema
addendum. Schema-aware extensions to Hippocampus, Prefrontal, and
Wernicke are introduced in Phase 2."

**Recommended default.** Pure-additive Phase 2+; Phase 1 untouched. The
schema-aware versions of Hippocampus and Prefrontal are described in
the addendum as **Phase 2 contracts that supersede the Phase 1
contracts** when Phase 2 launches — not retroactive edits.

---

### H3. POC vs. trained-model commitment  [DEFERRABLE]

**What's unclear.** The user has stated POC plan is "local orchestration
with generalist LLMs simulating specialized components, before any
training." Concept 9 (Schematic narrative paired training) describes a
training methodology that is not POC-applicable.

So: in the addendum, do we describe the trained-component end state, the
generalist-LLM POC realization, or both with a clear distinction?

**Why it matters.** Avoids confusion about what's prompt-engineering vs.
what's a training program.

**Context the user needs.** None technical.

**NL-deferral viability.** Yes.

**Recommended default.** Describe the trained end state as the
architectural target. Add a "POC realization" callout for each region:
"In Phase 2 POC, this is a generalist LLM with prompt template
`<region>_v1.txt`; training and distillation are deferred to Phase N."

---

### H4. `match_evidence` semantics  [DEFERRABLE]

**What's unclear.** `SchemaMatch` includes `match_evidence: [...]` (a
list of unspecified items). Concept 7 hints at graph-structural
recognition; if so, `match_evidence` would be subgraph-mapping
witnesses. If embedding-similarity, evidence would be top-K nearest
docs. Different recognizer backends produce different evidence shapes.

**Why it matters.** For audit purposes, downstream consumers need to
understand evidence. But evidence shape is recognizer-implementation
specific.

**NL-deferral viability.** Yes.

**Recommended default.** `match_evidence` is `Any` for now, opaque to
the spec. Define structure when recognizer backend is committed.

---

### H5. Notation versioning operations  [DEFERRABLE]

**What's unclear.** Concept 10 says "Migrations between versions must
exist, or vocabulary evolution silently invalidates training data." No
migration mechanism is specified.

**Why it matters.** Long-term cleanliness; not blocking for POC with
notation_version=1 and no migrations yet.

**NL-deferral viability.** Yes.

**Recommended default.** "Notation versioning is `notation_version: 1`
for the POC; migration tooling is deferred to Phase 3+." One sentence
in the addendum.

---

## Summary checklist

Most blocking → least blocking. A user filling these in (or marking
them deferred) gives a complete addendum integration plan.

- [ ] **A1** — Pick source-of-truth doc (recommend: `CONTEXT.md`).
- [ ] **A2** — Phase numbering for schema work (recommend: Phase 2a/2b/3+ program).
- [ ] **B1** — New regions vs. extending existing (recommend: extend existing, flag recognizer-backend question).
- [ ] **B3** — Conscience reframing (recommend: reframe in prose, don't restructure).
- [ ] **C1** — New blackboard fields, tri-modal split (recommend: `domain`/`trace_id`/`active_schemas` on blackboard; events on stream; catalog/history side-store).
- [ ] **H2** — Phase 1 backward compatibility (recommend: pure-additive, no Phase 1 edits).
- [ ] **B2** — Naming convention for new components (recommend: neuroanatomical for regions, functional for infra).
- [ ] **C2** — Blackboard backward-compat policy (recommend: additive-only, optional fields).
- [ ] **D1** — Audit stream layout (recommend: separate stream, `audit:global` for POC).
- [ ] **E1** — Where `domain` originates (recommend: Helm default + operator override on blackboard).
- [ ] **F1** — Helm `values.yaml` extensions (recommend: new `schema:` block).
- [ ] **F2** — Chart backward compat (recommend: `schema.enabled: false` by default).
- [ ] **G2** — Promote `RecognitionResult`/`SchemaMatch`/`AuditEvent` types (recommend: name in addendum, define in `design/data-structures.md`).
- [ ] **G3** — Selection policy location (recommend: Helm + blackboard override).
- [ ] **H1** — Schema storage backing (recommend: Qdrant payloads for POC, flagged tentative).
- [ ] **D2** — Audit-event schema versioning (defer; default `1`).
- [ ] **D3** — Trace retention (defer; 7d MAXLEN).
- [ ] **E2** — Multi-domain handling (defer to Phase 3+).
- [ ] **G1** — Subsystem name (recommend: "schema-driven inference").
- [ ] **H3** — POC vs. trained framing (recommend: describe end state, callout POC realization).
- [ ] **H4** — `match_evidence` shape (defer; `Any` for now).
- [ ] **H5** — Notation migration tooling (defer).

---

## Things I am explicitly *not* asserting

- I have not read `synthetic-mind-spec.docx` (the user instructed not to).
  The spec doc may already commit to some of the above; if so, that takes
  precedence over my "not stated" flags. The user should sanity-check
  each "uncertain" call against the docx.
- I have not inspected `src/ponder/` source — only the textual contracts
  in `CONTEXT.md`. There may be implementation details that change which
  defaults are realistic.
- The "recommended defaults" are starting points for user review, not
  resolutions. They are calibrated to "ship the addendum without
  blocking on hard decisions" rather than to pick architecturally
  optimal answers.
