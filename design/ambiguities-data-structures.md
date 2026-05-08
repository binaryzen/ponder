# Ambiguities — Data Structure Specifications

Surfaced before formalizing `design/data-structures.md`. The interview converged
on rough sketches (`RecognitionResult`, `SchemaMatch`, `SelectionPolicy`,
`AuditEvent`) and a crystallized schema-notation form. This document lists the
under-specified decisions that block turning those sketches into a usable
artifact.

## How to use this document

- Items are ordered by **blocking severity** — the earliest items must be
  resolved before later ones can be answered cleanly.
- Each item lists what's unclear, why it matters, the background you'd need to
  decide, whether the decision can be deferred behind a natural-language (NL)
  free-form field for the POC, and a recommended default if you want to skip
  the decision.
- For the POC posture (local generalist LLMs simulating specialized
  components), prefer NL deferral wherever the answer doesn't change the
  *interfaces between components*. Interface-shape decisions can't be
  deferred — they shape every other artifact.
- "Tighten later" is a real strategy here: you can ship a `notes: str` field
  now and migrate it to a structured field once usage exposes the right shape.
  Notation versioning (item 8) is what makes that migration safe.

---

## 1. Schema entity representation — typed? IDs? attributes?

- **What's unclear.** The crystallized notation has `entities: [...]` with the
  Q9.1 default of "open NL, mirroring relationships." It does not say whether
  an entity is just a label string (`"teacher"`), a record with attributes
  (`{label, type, attributes}`), or a referenceable node with an ID
  (`{id: "e1", label: "teacher"}`).
- **Why it matters.** Relationships have to point *at* entities. If entities
  are bare strings, two entities with the same label collapse, and you can't
  represent a schema with two distinct teachers. If entities are IDs,
  relationships become `(src_id, predicate, dst_id)` triples and the notation
  becomes a real graph. Cardinality (item 3) and slot-fill output (item 11)
  both depend on this. Choosing late forces a rewrite of every example pair.
- **Context you'd need.** In knowledge-representation tooling, three common
  shapes:
  1. *Bag of strings* — easiest, ambiguous when labels repeat.
  2. *Typed nodes* — `{id, label, type}`, where `type` is something like
     `Person | Organization | Process`. Adds an entity-type vocabulary you'd
     have to design (parallel problem to relationship vocabulary).
  3. *Attributed nodes* — nodes carry arbitrary key/value attributes
     (`{id, label, role: "instructor", domain_tags: [...]}`). Most flexible,
     hardest to canonicalize.
  An "entity" in a schema like "teacher teaching students" is a *role*, not a
  concrete individual — closer to a frame element (FrameNet) or a typed slot.
  This is different from a knowledge-graph node, which is usually a concrete
  individual.
- **NL-deferral viability.** Partial. You can defer attributes to a
  `notes: str` field, but the choice between bag-of-strings and IDs is
  structural and changes the type of `relationships`. You must commit to that
  shape now.
- **Recommended default.** Typed nodes with IDs:
  `{id: str, label: str, role_notes: str | null}`. ID enables repeats and
  self-references; `label` is the canonicalized predicate-style noun;
  `role_notes` is the NL-deferral escape hatch for everything you don't yet
  know how to formalize. No separate entity-type enum yet.

---

## 2. Relationship structure — triples or property edges?

- **What's unclear.** `relationships: [...]` is "open NL with domain
  canonicalization" but the shape of an individual relationship is not given.
  Is each entry `(subject, predicate, object)`, or
  `{src, dst, predicate, attributes}`, or something richer (n-ary, hyperedges,
  reified)?
- **Why it matters.** Recognition is supposed to be graph-structural (the
  user's "one of its inputs is affected by an output" example is a path
  pattern). The matcher's complexity is set by the edge shape: triples
  support standard graph-pattern matching; property edges add per-edge
  metadata at the cost of a more complex matcher; hyperedges (one edge
  touching three or more entities — e.g., "A mediates between B and C")
  require a different algorithm entirely. The training-pair format (Concept 9)
  also depends on this — the notation that pairs with each narrative has to
  be writable by hand.
- **Context you'd need.** Brief vocabulary:
  - *Triple* — `(subject, predicate, object)`. RDF's choice. Simplest, most
    tooling. Anything richer is encoded by reification (creating a node that
    *represents* an edge, then attaching attributes to it).
  - *Property edge* — `{src, dst, predicate, attributes: {...}}`. Common in
    property graphs (Neo4j, TinkerPop). Lets you put "polarity: positive" or
    "strength: weak" directly on the edge.
  - *Hyperedge* — one edge connecting more than two entities. Useful for
    n-ary relations like "A teaches B about C." Most graph-matching tools
    don't support these natively.
  Causal-loop diagrams (a precedent the user's archetypes literature draws
  from) need polarity per edge, which favors property edges.
- **NL-deferral viability.** Partial — same as item 1. The wrapper shape must
  be committed; per-edge attributes (polarity, strength, temporal markers) can
  start as a single `notes: str` field on each edge.
- **Recommended default.** Property edges:
  `{src: entity_id, dst: entity_id, predicate: str, notes: str | null}`. No
  reification, no hyperedges. If you discover you need n-ary relations,
  introduce an intermediate "process" entity and connect everything to it
  (the standard Sowa-style workaround).

---

## 3. Cardinality encoding

- **What's unclear.** Q9.3 default is "standard ER (1:1, 1:N, M:N)" but it's
  not clear *where* the cardinality lives. Is it a property of the edge
  (the natural ER reading), a separate parallel list keyed to relationships,
  or attached to entities?
- **Why it matters.** It's mostly a representation choice, not a semantic one,
  but downstream tooling (validation, graph matching, narrative generation)
  needs to look it up consistently. Also: standard ER cardinality is
  *between two entity sets*. If you have an n-ary relation, ER cardinality
  doesn't directly apply — you get cardinalities per role.
- **Context you'd need.** ER cardinality vocabulary: 1:1, 1:N (one teacher
  has many students), M:N (students take many courses; courses have many
  students). Often written as "min..max" pairs per side (e.g., `0..1` vs
  `1..*`) when you also need to distinguish optional from required. The
  three-symbol notation (1:1, 1:N, M:N) hides the optional/required
  distinction.
- **NL-deferral viability.** Yes. For the POC, cardinality can be a free-form
  string per edge or omitted entirely. Validation that uses cardinality is
  not on the Phase 2 critical path.
- **Recommended default.** Attach to the edge as
  `cardinality: "1:1" | "1:N" | "M:N" | null`. Drop the parallel list. Skip
  optional/required for now. Promote to min/max pairs if a use case emerges.

---

## 4. Variant labels — free strings, enum, or extensible?

- **What's unclear.** `variants: [...]` are "named expected behaviors" with
  semantic content carried by the training narratives. Are these arbitrary
  strings ("collapses", "finds equilibrium")? An enum the system knows about?
  A per-domain controlled vocabulary (parallel to canonicalized predicates)?
- **Why it matters.** Variants are the *operational payoff* of recognizing a
  schema — once recognized, the variants list "immediately surfaces what to
  expect." If they're free strings, downstream regions (Prefrontal planning,
  Conscience evaluation) can't match on them programmatically; they have to
  re-interpret each variant via LLM call. If they're a controlled set, you
  can wire them to behavior anticipation traces (Concept 11, requirement 3)
  cheaply.
- **Context you'd need.** Two relevant patterns:
  - *Open enum* — a known set with an "other" escape valve. Stripe's API
    does this.
  - *Tag set with canonicalization* — same shape as the predicate
    canonicalization story (Concept 10). Uses the same machinery.
  Variants are tightly coupled to schemas — "overload / collapse / find
  equilibrium" only makes sense for feedback systems. They're probably
  per-schema, not global.
- **NL-deferral viability.** Yes. Free strings now, canonicalize later, with
  the same hybrid mechanism Concept 10 already commits to for predicates.
- **Recommended default.** Free strings per schema, with the implicit promise
  that domain canonicalization will be applied to variants the same way it's
  applied to predicates. Variants don't need their own vocabulary system
  yet.

---

## 5. Schema-to-schema relationships — composition, inheritance, references?

- **What's unclear.** Nothing in the interview or concepts addresses whether
  a schema can refer to another schema, contain another schema as a subgraph,
  or inherit/specialize from another. The "consultant onboarding client"
  multi-schema example (teacher/student + merchant/service +
  healer/patient) talks about *applying multiple schemas to a situation*, not
  about schemas relating to each other.
- **Why it matters.** Three different shapes have very different
  consequences:
  - *Flat catalog of independent schemas* — simplest, but every common
    sub-pattern (e.g., "two-party communication channel") gets re-described
    in every schema that contains it.
  - *Composable schemas* — a schema can reference another by ID. Enables
    library-style reuse. Now the recognizer has to decide whether to match
    the parent or expand into children.
  - *Inheritance* — "negotiation" specializes "two-party interaction." The
    system archetypes literature has a flat list, no inheritance, which
    suggests this isn't critical for the POC seed catalog.
  Multi-schema parallelism (resolved as "ranked candidates, top-N") is a
  *different* question — it's about applying multiple unrelated schemas to
  one situation. Composition is about whether schemas form a graph among
  themselves.
- **Context you'd need.** Object-oriented inheritance and class composition
  are direct analogues. In KR, OWL has `subClassOf` and `equivalentClass`;
  most production knowledge graphs use a flat type system because hierarchy
  surface area outgrows the modeling benefit. Frame semantics has frame-to-
  frame relations (`Inheritance`, `Subframe`, `Uses`) but they're hand-built
  and rarely automated.
- **NL-deferral viability.** Yes, fully. For the POC, treat the catalog as
  flat. Don't add a `references: [schema_id]` field until a use case forces
  it. Document this as a deliberate Phase-2 deferral.
- **Recommended default.** Flat catalog. No schema-to-schema fields. Add a
  `related_schemas_notes: str | null` if you want a place to capture
  intuitions about composition without committing to a structure.

---

## 6. Recognition input format — raw text, structured, or both?

- **What's unclear.** `RecognitionResult` has no input shape; the recognizer's
  function signature is implied as "situation → ranked candidate schemas."
  But the Ponder spec separates `raw_input` from upstream-region distillates
  (`input_type`, `retrieved_memories`, etc.), and Concept 8 maps the
  recognizer to Hippocampus. Does the recognizer take raw user input,
  blackboard state, both, or some pre-processed structured representation?
- **Why it matters.** Sets the recognizer's contract with the rest of the
  pipeline and determines what the (narrative, notation) training pairs
  should *look like on the input side*. If the recognizer takes raw text, the
  narrative *is* the input format. If it takes structured situation
  descriptions, you need a separate "situation parser" upstream and the
  narratives need to be paired with their structured forms.
- **Context you'd need.** AMR parsing (the closest mature precedent in
  Concept 9) works on raw sentences; the structured form is the output. So
  text-in, graph-out is the default ML-precedent shape. But Ponder's
  pipeline already structures input via Thalamus / Wernicke before reaching
  reasoning components, which suggests the recognizer might receive
  partially-parsed structure.
- **NL-deferral viability.** Partial. The contract shape (one input field
  vs. multiple) must be committed; the *content* of those fields can be NL
  for the POC.
- **Recommended default.** Two-field input:
  `{situation_text: str, blackboard_excerpt: dict | null}`. `situation_text`
  carries either raw input or a Wernicke-distilled summary depending on
  pipeline stage; `blackboard_excerpt` is for downstream stages that have
  more context. Both get included in (narrative, notation) training pairs as
  the input side.

---

## 7. Match evidence format

- **What's unclear.** `SchemaMatch.match_evidence: [...]` has no element
  shape. Evidence for what kind of match — graph homomorphism path? Spans
  of the input that activated which entity in the schema? Embedding-distance
  scores? A free-form NL justification?
- **Why it matters.** Evidence is the *audit substrate* (Concept 11) for
  recognition. If it's NL, audit visualization is human-readable but not
  programmatically inspectable. If it's structural (e.g., "input span X
  matched schema entity E1"), the trace is machine-checkable but you have to
  define the structural alignment format. The user committed to graph-
  structural recognition (Q9 reflection), which biases this toward a
  structural-alignment representation.
- **Context you'd need.** Vocabulary:
  - *Graph homomorphism* — a structure-preserving map from one graph
    (schema) to another (situation graph). Evidence = the map itself.
    Cleanest, requires both sides to *be* graphs.
  - *Span alignment* — "this phrase in input → this entity in schema."
    Common in semantic parsing. Doesn't require situation to be pre-graphed.
  - *Free-form rationale* — "Looks like a feedback loop because A's output
    causes B which feeds back to A." LLM-natural, audit-weak.
- **NL-deferral viability.** Yes for the POC, but with risk: if you ship NL
  evidence and later need structural evidence, every recorded `AuditEvent`
  with old evidence becomes un-replayable. Version this carefully (item 8).
- **Recommended default.** Hybrid:
  `[{kind: "alignment" | "rationale", entity_id: str | null, span: str | null, note: str}]`.
  Allows mixing structural alignments and NL rationales in one list. POC
  starts with `kind: "rationale"` entries only; structural alignments get
  added once the recognizer is more than an LLM prompt.

---

## 8. Notation versioning scheme — semver, monotonic, schema migration?

- **What's unclear.** `notation_version: str` appears on schemas and
  `AuditEvent` but no scheme is specified. Concept 10 says "migrations
  between versions must exist," which implies the format will change in
  breaking ways and you need tooling. Nothing says how versions number,
  whether minor/major distinction matters, or what triggers a version bump.
- **Why it matters.** Notation versioning is *the* mechanism that makes
  NL-deferral safe. If you ship rough fields now and tighten them later, the
  version bump is what lets you migrate old training pairs and old audit
  events. Without a scheme, the only safe choice is to throw away historical
  data on every change. Also: AuditEvent records `notation_version`, so
  every consumer of audit events needs to know how to interpret old
  versions.
- **Context you'd need.** Three common patterns:
  - *Semver* (`1.2.3`) — major/minor/patch. Major = breaking. Conventional
    but heavy.
  - *Monotonic integer* (`v1`, `v2`) — simple, every change is potentially
    breaking, force migration on every bump.
  - *Date-based* (`2026-05-06`) — favored when versions are append-only
    additions (e.g., new variant names) rather than refactors.
  Pair the scheme with a `notation/migrations/<from>-<to>.py` directory or
  equivalent. Without migration code, the version field is decorative.
- **NL-deferral viability.** No. This is what *enables* deferral elsewhere;
  it can't itself be deferred.
- **Recommended default.** Monotonic integer (`"v1"`, `"v2"`). Bump on any
  change to the schema-notation shape (entities/relationships/variants
  fields, evidence shape). Migrations are best-effort scripts kept under
  `design/notation/migrations/`. Don't try to version the *predicate
  vocabulary* with this — that's a separate per-domain concern (item 13).

---

## 9. Trace ID semantics — UUID? scope? lifetime?

- **What's unclear.** `RecognitionResult.trace_id: str` and
  `AuditEvent.trace_id: str` link events, but not specified: format (UUID v4,
  ULID, hash, monotonic counter), scope (per turn, per request, per session,
  per inference call), or lifetime/retention.
- **Why it matters.** Trace IDs are how you reconstruct provenance chains
  (Concept 11, requirement 4). If they're per-turn, you can audit one user
  exchange but can't follow a fact across multiple turns. If they're per-
  session, you can. If a single turn produces many `AuditEvent`s with the
  *same* trace_id, you need `parent_event_id` (already sketched) to recover
  ordering. The format also matters: UUIDs are random-collision-safe but not
  sortable; ULIDs are sortable; hashes give content-addressable
  deduplication.
- **Context you'd need.** Three loose patterns:
  - *Per-turn UUID* — one trace per user turn. Multiple events share it,
    distinguished by `event_id`. Most common in tracing systems.
  - *Per-call UUID* — one trace per inference call. Finer-grained.
  - *Hierarchical* — `session_id / turn_id / event_id`. OpenTelemetry's
    span model.
  Ponder's existing Redis Streams bus is the natural sink; whatever ID
  format you pick has to be a Redis-Stream-friendly string.
- **NL-deferral viability.** No on shape; yes on semantics. The format must
  be committed; what the ID *means* (per-turn vs. per-call) can be left
  loose by carrying both `turn_id` and `event_id` and letting downstream
  decide.
- **Recommended default.** UUID v4 strings. One `trace_id` per user turn.
  `parent_event_id` chains events within a turn. Add a `turn_id` field
  alongside `trace_id` if you ever want to span turns; for now they're the
  same value.

---

## 10. Event-type enum — what are the actual values?

- **What's unclear.** `AuditEvent.event_type: enum` has no enumerated values.
  Concept 11 lists four operational requirements (schema-application trace,
  inference tagging, behavior anticipation trace, provenance unrolling) but
  doesn't map them to specific event types.
- **Why it matters.** The event-type enum is the *vocabulary* of the audit
  stream. Consumers (visualization, replay, Conscience-style validation)
  filter on it. Adding a type later is fine; renaming or splitting one
  retroactively is painful (you need a migration, see item 8). The set
  needs to cover the four Concept 11 requirements without being so fine-
  grained that every consumer has to understand 40 event types.
- **Context you'd need.** Audit-event design wisdom: prefer few coarse types
  with rich payloads over many fine types with thin payloads. Each event
  type implies a payload schema; payload schemas are themselves versioned
  (item 8 again).
- **NL-deferral viability.** Partial. You can defer the *payload shape* per
  event type, but the type names themselves should be committed early so
  that streams produced now are still readable later.
- **Recommended default.** Six values to start, each tied to a Concept 11
  requirement or pipeline boundary:
  - `recognition.candidates_emitted` — recognizer ran, ranked schemas
    available.
  - `selection.schema_chosen` — selector picked schema(s) under a policy.
  - `slotfill.slot_proposed` — a candidate inference was generated.
  - `slotfill.slot_committed` — a candidate inference was accepted into
    blackboard state.
  - `behavior.anticipated` — a variant was flagged as expected.
  - `behavior.observed` — a flagged variant was confirmed (or denied) by
    later evidence.
  Reserve `domain.changed` and `notation.migrated` for later. Keep payloads
  as `dict` for the POC; tighten per-type once usage stabilizes.

---

## 11. Slot-fill output structure

- **What's unclear.** Concept 8 says the slot-filler "generates slot-
  questions and propose answers" and that proposed answers are "candidate
  inferences." Concept 11 says each candidate inference must carry
  "originating schema, slot it filled, evidence used, confidence." But the
  data structure for the slot-fill *output* isn't sketched — only the audit
  metadata is.
- **Why it matters.** The slot-filler is the architecturally hardest piece
  (Concept 8) and its output structure is the contract that downstream
  regions (Prefrontal planning, Broca expression) consume. It also feeds
  the `slotfill.slot_proposed` audit event (item 10), so its shape and the
  audit payload shape are coupled.
- **Context you'd need.** Slot-filling vocabulary from frame semantics: a
  *frame* has *frame elements* (slots); slot-filling assigns values to those
  elements based on text. Each fill has provenance (which span supports it,
  what other slots constrain it). Modern LLM-based slot-fillers usually
  output JSON like
  `{slot: <name>, value: <NL>, supporting_evidence: <span>, confidence: <0..1>}`.
  Confidence values from generalist LLMs are unreliable in absolute terms but
  useful for ranking.
- **NL-deferral viability.** Yes, mostly. The wrapper shape must be
  committed; values can be NL strings.
- **Recommended default.**
  ```
  SlotFill {
    schema_id: str,
    schema_version: str,
    slot_name: str,            # name of an entity or edge in the schema
    proposed_value: str,        # NL for now
    evidence: [...],            # same shape as match_evidence (item 7)
    confidence: float | null,   # 0..1 if available, null if not estimable
    trace_id: str,
    parent_event_id: str | null
  }
  ```
  `slot_name` is the bridge: it has to refer unambiguously to a thing in the
  schema. This is why item 1 (entity IDs) matters — `slot_name` should be an
  entity_id or an edge identifier, not a free string.

---

## 12. Selection policy parameters

- **What's unclear.** `SelectionPolicy` has `mode`, `top_n`, and
  `temperature: float | null`. The interview commits to two defaults
  ("deterministic top-1" and "stochastic softmax-weighted over top-N") but
  doesn't fix the parameter contract. What does `temperature` do when
  `mode == "deterministic"`? What's the default `top_n`? Is the policy a
  constant, configurable per request, or a region-level setting?
- **Why it matters.** This is the seam where multi-schema arbitration policy
  is configured (Concept 8 open question 1). Getting it wrong forces every
  policy experiment to reshape the data structure. Also: `temperature` only
  makes sense in stochastic mode; allowing it as a top-level field
  encourages ill-defined combinations.
- **Context you'd need.** Brief vocabulary:
  - *Softmax temperature* — when sampling from scored candidates with
    probabilities `softmax(scores / temperature)`, low temperature (e.g.,
    0.1) sharpens toward the top score (near-deterministic), high
    temperature (e.g., 2.0) flattens toward uniform random. `0` is
    undefined / argmax; `null` means "not applicable."
  - *Bandit policy* — the user mentioned this as the abstraction. It's a
    family of strategies (epsilon-greedy, Thompson sampling, UCB) for
    choosing actions under uncertainty. Generalizes deterministic +
    stochastic.
  Configuration scope is independent: per-region (one policy for the whole
  recognizer), per-request (operator-supplied), or per-schema (some schemas
  are riskier and need tighter selection).
- **NL-deferral viability.** No on shape; the field set must be committed.
  Yes on the bandit-extension story — additional modes can be added later.
- **Recommended default.**
  ```
  SelectionPolicy {
    mode: "deterministic" | "stochastic",
    top_n: int,                 # default 3
    temperature: float | null,  # required if stochastic, must be null otherwise
    seed: int | null            # for reproducibility in stochastic mode
  }
  ```
  Region-level configuration via Helm values; per-request override allowed
  via blackboard. Reject combinations where `mode == "deterministic"` and
  `temperature != null` at the boundary.

---

## 13. Domain field — string, enum, or structured?

- **What's unclear.** `domain: str` appears on `RecognitionResult` and
  `AuditEvent` and on the schema itself. The interview committed that
  domain is "received from authoritative source" — but is that source
  emitting a free-form name (`"engineering-spec"`), a registered ID
  (`"dom_engineering_v3"`), or a structured value
  (`{name, version, parent_domain}`)? Concept 10 also makes domain the key
  for predicate canonicalization, so domain identity has real weight.
- **Why it matters.** Domain is what selects the canonical-predicate set,
  the seed schema catalog, and the variant vocabulary. If domain values
  drift (`"engineering"` vs `"engineering-spec"` vs `"eng"`), you silently
  fragment your training data. Multi-domain situations (Concept 10's open
  question) get worse if domain is just a string.
- **Context you'd need.** Domain in this system is functioning like a
  *namespace*. Namespaces in production systems usually become hierarchical
  (`org.team.project`) and need their own resolution rules. For the POC
  with fixed-value-in-Helm-values configuration, a flat string is fine; for
  multi-domain it's not.
- **NL-deferral viability.** Yes. Flat string for the POC, with a documented
  promise to formalize.
- **Recommended default.** `domain: str`, with values drawn from a small
  hand-maintained list in `design/domains.md` (or similar). No version
  embedded in the string; if a domain's predicate set evolves, that's
  notation versioning's job (item 8). Multi-domain handling deferred until
  a real two-domain example arises.

---

## 14. RecognitionResult ranking semantics

- **What's unclear.** `candidates: [SchemaMatch]` is "ranked, top-N" but
  the ranking signal isn't specified. `SchemaMatch.match_score: float` —
  what's its range, calibration, comparability across schemas? Are scores
  comparable across recognizer runs?
- **Why it matters.** The selection policy (item 12) consumes scores
  directly. Stochastic mode with softmax assumes scores are comparable in
  magnitude. If scores are unnormalized log-likelihoods from one LLM call,
  softmax-over-top-N is fine. If they're heuristic scores mixing graph
  matches and LLM judgments, softmax may be meaningless. Cross-run
  comparability matters for any meta-analysis ("did this schema's match
  score trend up after we added new training data?").
- **Context you'd need.** Score-calibration vocabulary:
  - *Probability* (0..1, sums to 1 across alternatives) — most useful, hardest
    to obtain honestly.
  - *Logit / log-odds* — unbounded, ordinal-meaningful, can be softmaxed.
  - *Heuristic score* — opaque, only ordinal-meaningful within one run.
  Generalist-LLM-simulated recognizers (the POC plan) usually produce
  heuristic scores. Treating them as probabilities is a known foot-gun.
- **NL-deferral viability.** Partial. Field shape must be committed; the
  *interpretation* can be loose if you document it.
- **Recommended default.** `match_score: float` documented as "ordinal
  within one RecognitionResult, not comparable across results, not a
  probability." Add `score_kind: "heuristic" | "logit" | "probability"`
  later if the POC produces multiple score types.

---

## 15. AuditEvent payload shape per event type

- **What's unclear.** `payload: {...}` is fully unspecified. Each event
  type (item 10) implies a different payload, and consumers need to know
  what to expect.
- **Why it matters.** This is the largest surface area where NL-deferral
  is tempting but risky. A `payload: dict` consumed by a
  `slotfill.slot_proposed` event needs at minimum the
  `SlotFill` record (item 11); a `behavior.observed` event needs the
  variant name and the evidence. Without a shape, every consumer
  re-implements payload parsing.
- **Context you'd need.** OpenTelemetry, CloudEvents, and Sentry all
  solve this with a `data` field whose shape depends on `type`. Schema
  registry pattern: payload schema is keyed by `(event_type, version)`.
- **NL-deferral viability.** Yes, with caveat. Ship `payload: dict` for
  the POC, but write down (in `design/data-structures.md`, when you
  formalize) the *minimum keys* expected per event type. Consumers can
  treat extra keys as opaque.
- **Recommended default.** `payload: dict`, with documented minimum keys
  per event type, mirroring the data structures elsewhere in this list
  (e.g., `slotfill.slot_proposed.payload` minimally contains a `SlotFill`
  record). Tighten to typed payloads in v2.

---

## Items deliberately not raised

- *Schema persistence and storage backend* — out of scope for data-structure
  specs; that's an infra decision (Qdrant vs. Postgres vs. files) tracked
  separately.
- *Streaming vs. batch emission of AuditEvents* — already committed
  ("structured event emitter, async abstraction") and the data structure
  doesn't change either way.
- *Inter-region wire format vs. on-disk training-pair format* — these can
  diverge if needed; the schema *value* is the same, only its container
  differs.
