# Ponder — v1 Data Structures

The first concrete data-structure artifact for the schema-driven inference
subsystem. v1 is **plumbing-grade**: enough to ship the local POC, intentionally
loose where the cost of tightening later is low.

This document is normative for the POC. When practice reveals gaps, tighten
in subsequent versions; bump `notation_version` when the change is breaking.

---

## Conventions

### Entity IDs

UUID v4. Examples: `550e8400-e29b-41d4-a716-446655440000`.

**Three reference forms** depending on context:

| Form | Use when | Example |
|---|---|---|
| Bare UUID | Within a single domain context (most internal references) | `550e8400-e29b-41d4-a716-446655440000` |
| Domain-qualified | Crossing domain contexts; multi-domain payloads; audit trails | `regulatory:550e8400-e29b-41d4-a716-446655440000` |
| Versioned schema reference | Referring to a schema at a specific notation version | `regulatory:550e8400-e29b-41d4-a716-446655440000@7` |

The format is URN-like (colon-separated namespace), not strict RFC 8141 URN.
Strictness can be tightened later if needed.

**Rule of thumb:** if the consumer of an ID has the domain context already,
emit the bare UUID. If the consumer might not, emit the domain-qualified form.
Audit events always emit the qualified form, because the audit consumer is
context-agnostic by design.

### Notation versioning

Monotonic integer. Each `Schema` carries a `notation_version` field. v1 is
defined by this document.

- Bumping the integer means: the notation has changed in a way that requires
  migration of any persisted (narrative, notation) pairs or cached schemas.
- No semver split (no major/minor/patch). One number, monotonic.
- Migrations are linear: a v6→v8 jump goes through v7.

When a breaking change is needed:

1. Increment the version number.
2. Document the change in `design/notation-versions.md` (TBD; create when first
   bump occurs).
3. Provide a migration function: `(old_schema, old_version) → new_schema`.

### Timestamps

ISO 8601 in UTC. Example: `2026-05-06T18:42:09.123Z`. Required precision:
millisecond.

### Free-form fields

Several fields are deliberately typed as `dict` or `str` rather than fixed
schemas. This is intentional — the POC needs the flexibility, and the cost
of tightening later is low because notation versioning gives us a clean
migration path.

---

## Schema

The compact form crystallized from Concept 7.

```python
Schema {
  id                  UUID v4
  notation_version    int                    # monotonic; this doc defines v1
  domain              str                    # "regulatory", "social-systems", ...
  name                str                    # human-readable label
  entities            [Entity]
  relationships       [Relationship]
  variants            [Variant]              # named expected behaviors
  description         str                    # NL prose for narrative-pairing training
  metadata            dict                   # free-form: tags, sources, author, etc.
}

Entity {
  id        UUID v4                          # local to this schema
  role      str                              # NL role label, e.g., "teacher", "supply"
  notes     str                              # NL elaboration; defer typing
}

Relationship {
  id            UUID v4
  from_entity   UUID v4                      # references Entity.id within this schema
  to_entity     UUID v4
  predicate     str                          # NL predicate, e.g., "transmits to"
  cardinality   str                          # "1:1" | "1:N" | "M:N" | "1:0..1" | etc.
  notes         str                          # NL elaboration
}

Variant {
  id      UUID v4
  label   str                                # NL label, e.g., "runaway feedback", "equilibrium"
  notes   str                                # NL elaboration of expected behavior
}
```

**Notes on v1 looseness:**

- `predicate` and `role` are free-form NL strings. Canonicalization (Concept 10)
  is deferred — for the POC, allow synonym sprawl and observe what canonicalizes
  itself in practice.
- `cardinality` is a string rather than an enum. Standard ER values are the
  expected vocabulary, but the field will accept anything until a closed enum
  is justified.
- No first-class `dynamics` or `emergence` operators. Variants are NL labels
  per Q9.4/Q9.5 simplification.
- Schema-to-schema relationships (composition, inheritance, references between
  schemas) are deferred. v1 schemas are independent.

---

## Recognition output

```python
RecognitionResult {
  trace_id      UUID v4                      # propagates through downstream events
  domain        str                          # received from authoritative source
  candidates    [SchemaMatch]                # ranked, top-N
  emitted_at    ISO 8601
}

SchemaMatch {
  schema_id        str                       # domain-qualified + versioned form
  match_score      float                     # in [0, 1]; calibration not assumed
  match_evidence   dict                      # free-form for v1; see notes
}
```

**Notes on `match_score`:**

- Treat as a **rank**, not a probability. v1 does not assume the score is
  calibrated. Selection policies should use it for ordering, not as a
  posterior probability.
- If a recognizer happens to emit calibrated probabilities later, that's
  additive — no v1 consumer will rely on calibration.

**Notes on `match_evidence`:**

- v1: free-form dict. Recommended keys when known: `matched_entities`,
  `matched_relationships`, `prompted_recognizer_rationale` (when the
  recognizer is an LLM).
- This is the field most likely to gain structure as the POC reveals what
  audit consumers actually need.

---

## Selection

```python
SelectionPolicy {
  mode          enum { "deterministic", "stochastic" }
  top_n         int                          # how many candidates to consider
  temperature   float | null                 # required iff mode=="stochastic"; usually [0.1, 2.0]
}

SelectionResult {
  trace_id        UUID v4                    # same trace_id as the recognition
  parent_event_id UUID v4                    # the recognition event's id
  selected        [SchemaMatch]              # ≥1 in stochastic-blend mode; usually 1
  policy          SelectionPolicy
  emitted_at      ISO 8601
}
```

**Notes:**

- Default policy: `{ mode: "deterministic", top_n: 1, temperature: null }`.
  Reproducible, simplest possible.
- `selected` is a list, not a single match, to permit future blending modes.
  v1 typically emits a list of length 1.
- `temperature` is a softmax-style temperature for stochastic sampling over
  the top-N. Higher temperature → more uniform sampling; lower → closer to
  argmax. Brief gloss because the user noted they're not a data scientist:
  it is a single scalar that controls how much randomness vs. determinism
  the sampler uses.

---

## Audit event

```python
AuditEvent {
  trace_id           UUID v4                 # one trace_id per turn; propagated through all events
  parent_event_id    UUID v4 | null          # chains events into provenance trees
  event_id           UUID v4                 # this event's id
  emitted_at         ISO 8601
  event_type         enum                    # see below
  region             str                     # ponder region name: thalamus, hippocampus, ...
  domain             str                     # bare or domain-qualified
  notation_version   int                     # version active at emission
  payload            dict                    # event-type-specific
}
```

**event_type enum (v1):**

| Value | Emitted when | Typical payload |
|---|---|---|
| `recognition` | A recognizer emits its `RecognitionResult` | the `RecognitionResult` |
| `selection` | A selector applies its policy | the `SelectionResult` |
| `slot_fill` | A slot-filler proposes a candidate inference | `{ schema_id, slot_id, proposed_value, evidence }` |
| `behavior_anticipation` | A variant from a selected schema is flagged as expected | `{ schema_id, variant_id, rationale }` |
| `verdict` | A closed-world strict evaluator emits a finding | `{ rules_applied, entity, verdict, citations }` |
| `pipeline` | A boundary event — turn start/end, region entry/exit, errors | `{ boundary, context }` |

**Why these six:**

The four operational requirements from Concept 11 map to the first four:

1. Schema application trace → `recognition`, `selection`
2. Inference tagging → `slot_fill`
3. Behavior anticipation → `behavior_anticipation`
4. Provenance unrolling → all events with `parent_event_id`

`verdict` is added for the rule-evaluation pipeline (Concept 5/6).
`pipeline` is added for boundary events that don't fit the cognitive types
but are necessary for trace reconstruction.

**Payload looseness:** `payload` is `dict`. v1 does not lock in payload shapes
per event_type. Practice will reveal what shapes are needed; tighten in v2.

---

## Domain identification

For the POC, domain is a **fixed value** supplied by deployment configuration
(Helm `values.yaml`). A single Ponder unit operates within one domain.

The data structures already accept `domain` as a field — when a domain
classifier component is later introduced (Phase 3+), it will populate that
field per turn. No structural change is needed.

---

## What's deliberately not specified in v1

These are explicit deferrals, not omissions:

- **Schema composition/inheritance/references.** v1 schemas are independent.
- **Predicate canonicalization.** Allowed to sprawl in NL until we see real
  patterns.
- **Cardinality enum.** Free-form string until closed enum is justified.
- **`payload` shape per event_type.** Free-form dict until practice shapes it.
- **`match_evidence` shape.** Free-form dict until audit consumers reveal needs.
- **Notation migration tooling.** Will be specified at the first version bump.
- **Schema storage backend.** Out of scope for the data structures themselves —
  this is a deployment concern (Concept 10 / spec integration thread).

---

## Versioning of this document

This is `notation_version: 1`. All schemas authored under this document carry
`notation_version: 1`. When a breaking change is needed, a new
`design/data-structures.md` revision will be authored with `notation_version: 2`,
and a migration `(v1_schema) → (v2_schema)` will be defined.
